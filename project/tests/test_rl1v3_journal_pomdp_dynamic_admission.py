"""Fail-closed approval, immutable attempts and actual prepared input admission."""
import copy
import json
import os
from pathlib import Path

import pytest
from metacom_pm.rl1v3.journal import pomdp_dynamic_run as R
from metacom_pm.rl1v3.journal.pomdp_latency import MonotonicClock
from metacom_pm.rl1v3.io import file_sha256, object_sha256


def test_false_or_old_approval_cannot_transfer():
    with pytest.raises(ValueError, match='new explicit'):
        R.admit({}, {'authorized': False})
    with pytest.raises(ValueError, match='old approval'):
        R.admit({}, {'authorized': True, 'protocol': 'SMV30', 'job_kind': 'SMV'})


def test_approval_requires_exact_budget_and_actual_decision_bytes(tmp_path):
    catalog = tmp_path / 'catalog.json'; catalog.write_text('{}')
    decision = tmp_path / 'TEST_ONLY.txt'; decision.write_text('unit fixture, not a researcher authorization')
    plan = {'catalog_path': str(catalog)}
    auth = dict(authorized=True, protocol=R.PROTOCOL, job_kind=R.JOB_KIND,
        plan_sha256=object_sha256(plan), catalog_file_sha256=file_sha256(catalog),
        max_calls=22, max_model_loads=1, global_seconds=1200, warmup_calls=0, retry_calls=0,
        gpu_uuid=R.L.GPU, researcher='UNIT_TEST_ONLY', decision_evidence=str(decision),
        decision_evidence_sha256=file_sha256(decision))
    assert R.admit(plan, auth) == auth  # Pure validation; no run/claim/model.
    for key, value in [('max_calls', 23), ('max_model_loads', True), ('retry_calls', 1),
                       ('decision_evidence_sha256', '0' * 64), ('catalog_file_sha256', '0' * 64)]:
        changed = dict(auth, **{key: value})
        with pytest.raises(ValueError): R.admit(plan, changed)


def test_same_source_pair_cannot_be_retried_with_new_approval_or_executor(tmp_path):
    plan = {'task_ids': ['a', 'b'], 'baseline_sha256': 'fixed', 'executor': 'v1'}
    R.claim_scope(plan, {'unit_test_only': True}, tmp_path)
    with pytest.raises(FileExistsError, match='no retry'):
        R.claim_scope(dict(plan, executor='v2'), {'different': 'unit fixture'}, tmp_path)
    assert len(list(tmp_path.glob('*.json'))) == 1


def test_partial_attempt_claim_is_not_silently_ignored(tmp_path):
    (tmp_path / 'partial.json').write_text('{')
    with pytest.raises(ValueError):
        R.claim_scope({'task_ids': ['a', 'b'], 'baseline_sha256': 'fixed'}, {}, tmp_path)


def test_monotonic_durable_journal_binds_clock_and_original_payload(tmp_path):
    ticks = iter([100, 200, 300])
    clock = MonotonicClock(now=lambda: next(ticks), boot_id='fixture-boot')
    journal = R.MonotonicJournal(tmp_path / 'journal', clock)
    journal.add('START', payload={'a': 1})
    journal.add('END', output={'original': 'retained'})
    first, second = [json.loads(p.read_text()) for p in sorted(journal.path.glob('*.json'))]
    assert second['previous_event_sha256'] == file_sha256(journal.path / '000-START.json')
    assert second['stamp']['monotonic_ns'] > first['stamp']['monotonic_ns']
    assert second['output'] == {'original': 'retained'}
    with pytest.raises(ValueError, match='backwards'):
        journal.add('BAD', stamp=dict(clock='CLOCK_MONOTONIC', boot_id='fixture-boot', monotonic_ns=99))
    with pytest.raises(ValueError, match='clock identity'):
        journal.add('BAD', stamp=dict(clock='CLOCK_MONOTONIC', boot_id='other', monotonic_ns=400))


@pytest.fixture
def packages():
    raw = os.environ.get('POMDP_DYNAMIC_PACKAGES_PRIVATE')
    if not raw:
        pytest.skip('requires private prepared dynamic packages; no model access')
    return Path(raw)


def test_all_four_actual_packages_have_same_scope_and_complete_goals(packages):
    scopes = set(); task_ids = []
    for n in range(1, 5):
        plan, tasks, _ = R.check(packages / f'batch-{n:02d}/PLAN.json')
        scopes.add(plan['scope_sha256']);task_ids.extend(t['task_id'] for t in tasks)
        assert len(R.terminal_slots(plan['task_ids'])) == 12
        assert plan['max_calls'] == sum(plan['role_call_caps'].values()) == 22
    assert len(scopes) == 1 and len(set(task_ids)) == 8


@pytest.mark.parametrize('field,value', [
    ('max_calls', 23), ('warmup_calls', 1), ('automatic_retry', True),
    ('global_seconds', 1201), ('cache_policy', 'offline_reuse'), ('policy_elapsed_time_input', True)])
def test_frozen_package_rejects_budget_cache_and_policy_expansion(packages, tmp_path, field, value):
    original = R.read(packages / 'batch-01/PLAN.json')
    changed = copy.deepcopy(original);changed[field] = value
    path = tmp_path / 'changed.json';path.write_text(json.dumps(changed))
    with pytest.raises(ValueError): R.check(path)


def test_unapproved_real_plan_cannot_reach_device_or_model(packages, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError('device/model reached without approval')
    monkeypatch.setattr(R.L, 'device_guard', forbidden)
    monkeypatch.setattr(R.L, 'storage_guard', forbidden)
    with pytest.raises(ValueError, match='new explicit'):
        R.run(packages / 'batch-01/PLAN.json', packages / 'batch-01/APPROVAL_TEMPLATE.json', tmp_path / 'never_created')
    assert not (tmp_path / 'never_created').exists()
