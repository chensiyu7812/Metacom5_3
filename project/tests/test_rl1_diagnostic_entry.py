"""Offline contract/adapter checks: no data, key, GPU, HTTP or real updates."""
from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace
import importlib.util
import json

import pytest

from test_rl1_diagnostic_scope import fixture, reviewed
from metacom_pm.rl1.diagnostic_scope import feedback_disposition, require_approval
from metacom_pm.rl1.calibration_workflow import stamp
from metacom_pm.rl1.diagnostic_analysis import summarize_results
from metacom_pm.rl1.natural_batch import FeedbackQueue


def entry():
    path = Path(__file__).parents[1] / 'scripts/rl1/112_run_four_head_diagnostic.py'
    spec = importlib.util.spec_from_file_location('prepared_diagnostic_entry_test', path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_pending_approval_precedes_all_live_dependencies(monkeypatch):
    m = entry()
    _, p, a, _, _ = fixture()
    def forbidden(*args, **kwargs):
        raise AssertionError('live dependency must not be touched')
    monkeypatch.setattr(m, 'LocalProviders', forbidden)
    monkeypatch.setattr(m, 'PaidProvider', forbidden)
    with pytest.raises(ValueError, match='approval required'):
        m.advance(p, dict(a, status='PENDING'))


def test_credential_outbound_and_money_scope_cannot_be_omitted():
    _, p, a, _, _ = fixture()
    p.pop('identity')
    p = stamp(dict(p, approval_scope=dict(credential_process_read_authorized=True,
        outbound_scope=['exactly bound legal reply and sources'])))
    a['protocol_identity'] = p['identity']
    with pytest.raises(ValueError, match='approval missing'):
        require_approval(p, a)
    a.update(p['approval_scope'])
    require_approval(p, a)
    a['limits'] = dict(a['limits'], cumulative=306)
    with pytest.raises(ValueError):
        require_approval(p, a)


def test_ambiguity_is_not_blanket_permission():
    r = dict(measurement_status='measured_candidate', q=3, m=.25)
    rv = reviewed(r, True)
    rv['ambiguities'][0]['type'] = 'known_person_attribution_error'
    with pytest.raises(ValueError, match='approved category'):
        feedback_disposition(r, rv)
    rv = reviewed(r, True)
    rv['confirmed_errors'] = [dict(claim='speaker misattribution', source_ids=['C:T000'],
        original_criterion='role contract', reason='source proves different speaker',
        target='measurement_decision', decision_error_type='wrong_subject_or_time')]
    assert feedback_disposition(r, rv) == 'stop_before_update'
    with pytest.raises(ValueError, match='unknown mechanical'):
        feedback_disposition(dict(measurement_status='made_up', q=None, m=None), None)


def test_paid_guard_allows_own_settlement_but_no_foreign_writer(tmp_path, monkeypatch):
    m = entry()
    monkeypatch.setattr(m, 'check', lambda:None)
    p = m.PaidProvider.__new__(m.PaidProvider)
    p.visible_paid_writers = lambda:[]
    p.protocol = {'version':'bound-diagnostic'}
    p.original = b''
    p.ledger = tmp_path / 'mock_ledger.jsonl'
    reserved = dict(event='RESERVED', reservation_id='x', stage='bound-diagnostic',
                    binding=dict(study='bound-diagnostic'))
    settled = dict(event='SETTLED', reservation_id='x')  # Old settlement has no stage field.
    p.ledger.write_text('\n'.join(map(json.dumps, [reserved, settled]))+'\n')
    p.guard()
    with p.ledger.open('a') as f:
        f.write(json.dumps(dict(event='RESERVED', reservation_id='other', stage='foreign'))+'\n')
    with pytest.raises(ValueError, match='foreign paid writer'):
        p.guard()


def test_report_preserves_missing_denominators_and_unique_OFF():
    p = dict(trajectory_manifest={
        'a':dict(split='train', condition='sampled_policy', prefix_identity='same'),
        'b':dict(split='train', condition='sampled_policy', prefix_identity='same')})
    r = dict(measurement_status='semantic_uncertainty', q=None, m=None)
    f = dict(record=r, review=None, disposition='pending_stop_stage')
    result = summarize_results(p, {}, [f, f])
    assert result['unique_feedback_records'] == 1
    assert result['feedback_categories']['model_unknown'] == 1
    assert result['planned_training_trajectories'] == 2
    assert result['started_trajectories'] == 0
    assert result['human_comparable_pairs'] is None
    assert all(x['measured_return'] is None for x in result['trajectories'])


def test_corrupted_queue_payload_never_dispatches(tmp_path):
    from rl1_batch_fixtures import episodes
    e = episodes(n=1)[0]
    e.acquire(lambda o:0)
    q = FeedbackQueue(tmp_path / 'queue.sqlite')
    assert q.generate(e.env.generation_request()) is None
    with q.transaction() as db:
        db.execute("UPDATE feedback SET payload='{}'")
    with pytest.raises(ValueError, match='identity changed'):
        q.claim_next()
    assert q.counts()[0]['state'] == 'WAITING'


def test_old_stop_not_rewritten(tmp_path):
    from metacom_pm.rl1.diagnostic_session import save_once
    p = tmp_path / 'STOP.json'
    save_once(p, {'reason':'original'})
    before = p.read_bytes()
    with pytest.raises(ValueError, match='immutable'):
        save_once(p, {'reason':'new'})
    assert p.read_bytes() == before


def test_sensitivity_is_separate_from_training_grades():
    from metacom_pm.rl1.diagnostic_analysis import decision_sensitivity
    s = decision_sensitivity(4, 0, 4, 0, .05)
    assert s['original_direction'] == 'negative'
    assert any(x['direction'] == 'positive' for x in s['cases'])
    assert s['used_for_training'] is False
    assert s['grade_plausibility_validated'] is False


@pytest.mark.parametrize('wrong_identity', [False, True])
def test_private_process_boundary_roundtrip_without_provider(tmp_path, monkeypatch, wrong_identity):
    import sys
    m = entry()
    worker = tmp_path / 'synthetic_ipc_worker.py'
    worker.write_text('''import json,sys,os
assert os.environ['CUDA_VISIBLE_DEVICES']==''
fd=int(sys.argv[sys.argv.index('--parent-lock-fd')+1])
os.fstat(fd)
print(json.dumps({'state':'ready'}),flush=True)
for line in sys.stdin:
 job=json.loads(line)['job']
 key='wrong' if WRONG else job['id']
 print(json.dumps({'queue_id':key,'record':{'mock_only':True}}),flush=True)
'''.replace('WRONG', repr(wrong_identity)))
    monkeypatch.setattr(m, '__file__', str(worker))
    protocol = {'config':{'timeout_seconds':1}, 'judge_python':sys.executable}
    with (tmp_path / 'mock.lock').open('a') as lock:
        p = m.PaidProcess(protocol, tmp_path / 'unused_mock_approval.json', lock.fileno())
        try:
            if wrong_identity:
                with pytest.raises(ValueError, match='identity mismatch'):
                    p({'id':'synthetic-job'})
            else:
                assert p({'id':'synthetic-job'}) == {'mock_only':True}
        finally:
            p.close()
        assert p.child.poll() == 0
