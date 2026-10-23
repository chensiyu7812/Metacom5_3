"""Failure/restart/dependency tests; no network, real score or account access."""
from concurrent.futures import ThreadPoolExecutor
import json
import pytest

from metacom_pm.rl1.recovery_schedule import RecoverySchedule, Slot


def reserve(claim):
    return dict(attempt_id=claim['attempt_id'], reservation_identity='MOCK:' + claim['attempt_id'])


def finish(s, c, outcome='valid', **kw):
    args = dict(outcome=outcome, input_identity=c['input_identity'], config_identity=c['config_identity'],
                settlement_identity='MOCK:settled', result_identity='MOCK:' + outcome)
    args.update(kw)
    s.settle(c['attempt_id'], **args)


def schedule(tmp_path, slots=None, **kw):
    return RecoverySchedule(tmp_path/'queue.sqlite', slots or [Slot('a', 'input-a', 'config-a')],
                            protocol_identity='MOCK:protocol', max_attempts=50, **kw)


def test_settled_failure_allows_independent_slot_then_same_input_recovery(tmp_path):
    s = schedule(tmp_path, [Slot('a', 'x', 'c'), Slot('audit-a', 'audit-x', 'c', dependencies=('a',)),
                            Slot('b', 'y', 'c')])
    a = s.claim_next(reserve); finish(s, a, 'format_failure')
    b = s.claim_next(reserve)
    assert b['slot_id'] == 'b'
    assert s.report()['states']['audit-a'] == 'DEPENDENCY_PENDING'
    finish(s, b)
    retry = s.claim_next(reserve)
    assert retry['slot_id'] == 'a' and retry['ordinal'] == 1
    assert retry['input_identity'] == a['input_identity'] and retry['attempt_id'] != a['attempt_id']
    finish(s, retry)
    audit = s.claim_next(reserve); assert audit['slot_id'] == 'audit-a'; finish(s, audit)
    report = s.report()
    assert report['first_attempts'] == 3 and report['first_technical_valid'] == 2
    assert s.claim_next(reserve) is None
    with pytest.raises(ValueError, match='immutable'):
        finish(s, a)


def test_restart_never_reclaims_unknown_delivery(tmp_path):
    s = schedule(tmp_path); c = s.claim_next(reserve)
    reopened = schedule(tmp_path)
    assert reopened.claim_next(reserve) is None
    assert reopened.report()['global_stop'] == 'OUTSTANDING_DELIVERY_OR_SETTLEMENT'
    finish(reopened, c)
    assert reopened.report()['states']['a'] == 'VALID'


@pytest.mark.parametrize('role,recoveries', [('development', 2), ('qualification', 1), ('repeat', 0)])
def test_specific_retry_limits_and_repeat_draw_identity(tmp_path, role, recoveries):
    s = schedule(tmp_path, [Slot('a', 'x', 'c', role)])
    attempts = []
    for i in range(recoveries + 1):
        c = s.claim_next(reserve); assert c is not None; attempts.append(c)
        # Alternate failure class so retry ceiling is not hidden by circuit.
        finish(s, c, 'format_failure' if i % 2 == 0 else 'schema_failure')
    assert s.claim_next(reserve) is None
    assert s.report()['recovery_attempts'] == recoveries
    assert attempts[0]['independent_draw_identity'] == ('a' if role == 'repeat' else None)


def test_semantic_unknown_not_retried_but_counts_as_delivered(tmp_path):
    s = schedule(tmp_path); c = s.claim_next(reserve); finish(s, c, 'semantic_unknown')
    assert s.claim_next(reserve) is None
    assert s.report()['first_technical_valid_rate'] == 1
    assert s.report()['states']['a'] == 'UNRESOLVED'
    assert not s.report()['qualification_granted']


@pytest.mark.parametrize('kw', [dict(settled=False, settlement_identity=None),
    dict(input_identity='wrong'), dict(config_identity='wrong'), dict(outcome='global_risk')])
def test_global_risks_block_independent_configs(tmp_path, kw):
    s = schedule(tmp_path, [Slot('a', 'x', 'c'), Slot('b', 'y', 'other')])
    c = s.claim_next(reserve); finish(s, c, **kw)
    assert s.report()['global_stop'] == 'GLOBAL_RECONCILIATION_REQUIRED'
    assert s.claim_next(reserve) is None


def test_circuit_three_same_failures_blocks_only_affected_config(tmp_path):
    s = schedule(tmp_path, [Slot(str(i), str(i), 'bad' if i < 4 else 'good') for i in range(5)])
    for _ in range(3):
        finish(s, s.claim_next(reserve), 'format_failure')
    c = s.claim_next(reserve)
    assert c['slot_id'] == '4'
    assert s.report()['states']['3'] == 'CONFIG_STOPPED'
    finish(s, c)
    assert s.claim_next(reserve) is None


def test_shared_recovery_cap_and_first_valid_wins(tmp_path):
    s = schedule(tmp_path, [Slot('a', 'x', 'c'), Slot('b', 'y', 'c')], recovery_cap=1)
    finish(s, s.claim_next(reserve), 'format_failure')
    finish(s, s.claim_next(reserve), 'schema_failure')
    finish(s, s.claim_next(reserve))
    assert s.report()['states'] == {'a': 'VALID', 'b': 'RECOVERY_EXHAUSTED'}
    assert s.claim_next(reserve) is None


def test_budget_rejection_and_two_workers_do_not_duplicate_claim(tmp_path):
    s = schedule(tmp_path)
    def reject(_):
        raise RuntimeError('MOCK budget unavailable')
    with pytest.raises(RuntimeError):
        s.claim_next(reject)
    assert s.report()['attempts'] == 0
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: s.claim_next(reserve), range(2)))
    assert sum(c is not None for c in claims) == 1


def test_protocol_mutation_rejected_and_settlement_idempotent(tmp_path):
    s = schedule(tmp_path); c = s.claim_next(reserve); finish(s, c); finish(s, c)
    assert s.report()['attempts'] == 1
    with pytest.raises(ValueError, match='change'):
        schedule(tmp_path, recovery_cap=3)


def test_bad_dependency_and_unbound_reservation_rejected(tmp_path):
    with pytest.raises(ValueError):
        schedule(tmp_path, [Slot('a', 'x', 'c', dependencies=('future',))])
    s = schedule(tmp_path)
    with pytest.raises(ValueError, match='reservation'):
        s.claim_next(lambda c: dict(attempt_id='wrong', reservation_identity='MOCK'))
    assert s.report()['attempts'] == 0


def test_persisted_input_drift_cannot_dispatch_and_capacity_reports(tmp_path):
    s = schedule(tmp_path); c = s.claim_next(reserve); finish(s, c)
    with s.transaction() as db:
        changed = dict(c, input_identity='wrong')
        db.execute('UPDATE attempts SET claim=? WHERE id=?', (json.dumps(changed), c['attempt_id']))
    with pytest.raises(ValueError, match='drift'):
        s.claim_next(reserve)
    limited = RecoverySchedule(tmp_path/'limited.sqlite', [Slot('x', 'x', 'c'), Slot('y', 'y', 'c')],
        protocol_identity='MOCK:limited', max_attempts=1)
    finish(limited, limited.claim_next(reserve))
    assert limited.claim_next(reserve) is None
    assert limited.report()['attempt_capacity_exhausted']
