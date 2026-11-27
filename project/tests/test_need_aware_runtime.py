"""NAA B-line batch runtime regression: identity, dedupe, caps, ledger/resume, admission.

CPU fixtures with the plumbing backend and the real worker guard/transport. These are
plumbing checks, not model results.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from metacom_pm.need_aware.runtime import authorization as AU
from metacom_pm.need_aware.runtime import requests as Q
from metacom_pm.need_aware.runtime import runner
from metacom_pm.need_aware.runtime.backend import NAAHFBackend, PlumbingBackend
from metacom_pm.need_aware.runtime.budget import NAABatchBudget, default_caps
from metacom_pm.need_aware.runtime.ledger import Ledger, LedgerError
from metacom_pm.need_aware.runtime.models import G0E, capacity
from metacom_pm.rl1v3.generator.limited_run import AdmissionError

SRC = Path(__file__).resolve().parents[1] / 'src'
DECODE = G0E.decode(8)


def row(task, arm, msgs, label='G0e', ids=None):
    ids = ids or [2, 10, len(msgs[-1]['content'])]
    sha = Q.physical_identity('g:' + label, msgs, ids, DECODE)
    return dict(logical_id=Q.logical_id(task, arm, label), task_id=task, task_mode='mcq', persona_group='p', arm=arm,
                model_label=label, model_id='m', g_id='g:' + label, decode=DECODE, messages=msgs, input_ids=ids,
                status='ready', request_sha256=sha)


def manifest(rows, models=('G0e',)):
    counts = Q.deduplicate(rows)
    caps = default_caps(counts['physical_unique'], gpu_seconds=3600)
    caps.update(input_cap=12000, backend_cap=16384)
    return dict(protocol=AU.MANIFEST_PROTOCOL, authorized=False, model_order=list(models), caps=caps, counts=counts,
                requests=rows, scope_sha256='s', runtime={})


def approval(m):
    return dict(models=m['model_order'], max_physical_calls=m['caps']['max_physical_calls'],
                max_gpu_seconds=m['caps']['max_gpu_seconds'], _sha256='test')


def fixture_rows():
    rs = [row(f't{i}', arm, [{'role': 'user', 'content': f'q{i}-{arm}'}]) for i in range(3) for arm in 'ABCD']
    dup = row('t3', 'A', [{'role': 'user', 'content': 'q0-A'}])            # exact repeat of t0|A
    ne = dict(logical_id='t3|C|G0e', task_id='t3', arm='C', model_label='G0e', status='not_evaluable',
              reason='direct missing', request_sha256=None)
    return rs + [dup, ne]


def test_request_identity_and_exact_deduplication():
    rows = fixture_rows()
    counts = Q.deduplicate(rows)
    assert counts == dict(physical_unique=12, logical_ready=13, exact_duplicates=1)
    assert rows[12]['duplicate_of'] == 't0|A|G0e' and rows[12]['request_sha256'] == rows[0]['request_sha256']
    assert Q.physical_identity('g', [{'role': 'user', 'content': 'x'}], [1], DECODE) != \
        Q.physical_identity('g', [{'role': 'user', 'content': 'x'}], [1], G0E.decode(9))


def test_native_capacity_check():
    assert capacity([1] * 12000, DECODE)['fits'] and not capacity([1] * 12001, DECODE)['fits']
    assert not capacity([1] * 11000, G0E.decode(6000))['fits']


def test_plumbing_run_resume_retry_reuse_and_complete_denominator(tmp_path):
    rows = fixture_rows()
    m = manifest(rows)
    fail = {rows[5]['request_sha256']}
    lg = Ledger(tmp_path, manifest_sha256=AU.manifest_sha256(m))
    s1 = runner.run(m, approval(m), lg, lambda label, **k: PlumbingBackend({}, fail_on=fail), result_kind='plumbing')
    assert s1['status'] == 'STOPPED' and s1['pending_logical'] == ['t1|B|G0e']
    assert s1['physical_calls'] == 13                                        # 12 unique + 1 retry; no call for duplicate
    events = [e['event'] for e in lg.events]
    assert events.count('REUSE') == 1 and events.count('NOT_EVALUABLE') == 1 and events.count('ATTEMPT_FAILED') == 2
    # Resume in a new process view: chain verified, new segment, caps count prior calls.
    lg2 = Ledger(tmp_path, manifest_sha256=AU.manifest_sha256(m))
    assert lg2.physical_calls() == 13 and lg2.path.name == 'LEDGER.002.jsonl'
    s2 = runner.run(m, approval(m), lg2, lambda label, **k: PlumbingBackend({}), result_kind='plumbing')
    assert s2['status'] == 'STOPPED'                                         # per-request attempt cap (2) reached
    assert lg2.physical_calls() == 13
    new = [e['event'] for e in lg2.events[len(lg.events):]]
    assert 'LOAD_START' not in new and new.count('EXHAUSTED') == 1            # no model load when nothing may run
    assert sum(e['event'] == 'NOT_EVALUABLE' for e in lg2.events) == 1       # settled slots are not re-recorded


def test_resume_finishes_without_repeating_completed_calls(tmp_path):
    rows = fixture_rows()
    m = manifest(rows)
    lg = Ledger(tmp_path, manifest_sha256=AU.manifest_sha256(m))
    calls = []

    class Counting(PlumbingBackend):
        def generate(self, request, seconds):
            calls.append(request['request_sha256'])
            if len(calls) == 4:
                raise KeyboardInterrupt('simulated interrupt')
            return super().generate(request, seconds)
    with pytest.raises(KeyboardInterrupt):
        runner.run(m, approval(m), lg, lambda label, **k: Counting({}), result_kind='plumbing')
    lg2 = Ledger(tmp_path, manifest_sha256=AU.manifest_sha256(m))
    done_before = set(lg2.completed())
    s = runner.run(m, approval(m), lg2, lambda label, **k: Counting({}), result_kind='plumbing')
    assert s['status'] == 'FINISHED' and len(lg2.completed()) == 12
    assert not done_before & set(calls[4:])                                  # completed requests never re-called


def test_budget_rejects_out_of_scope_and_caps(tmp_path):
    rows = fixture_rows()
    m = manifest(rows)
    lg = Ledger(tmp_path, manifest_sha256=AU.manifest_sha256(m))
    b = NAABatchBudget(m, dict(approval(m), max_physical_calls=2), lg)
    with pytest.raises(AdmissionError, match='scope'):
        b.claim('naareq:not-in-manifest', 'G0e')
    with pytest.raises(AdmissionError, match='scope'):
        b.claim(rows[0]['request_sha256'], 'Qwen35')
    with pytest.raises(AdmissionError, match='model not approved'):
        b.claim_load('Qwen35')
    for r in rows[:2]:
        b.claim(r['request_sha256'], 'G0e')
        lg.add('ATTEMPT_START', request_sha256=r['request_sha256'])
    with pytest.raises(AdmissionError, match='physical call cap'):
        b.claim(rows[2]['request_sha256'], 'G0e')


def test_gpu_seconds_not_double_counted_and_per_model_share(tmp_path):
    rows = fixture_rows()
    m = manifest(rows, models=('G0e', 'Qwen35'))
    lg = Ledger(tmp_path, manifest_sha256=AU.manifest_sha256(m))
    b = NAABatchBudget(m, dict(approval(m), max_gpu_seconds=100), lg)
    assert b.per_model_seconds == 50
    lg.add('ATTEMPT_START', request_sha256='x', model_label='G0e', session_id='s1', session_elapsed_s=30.)
    assert b.seconds_left('G0e', 's1', 30.) == 20                          # live session counted once
    lg.add('MODEL_SESSION_END', model_label='G0e', session_id='s1', session_elapsed_s=45.)
    assert b.seconds_left('G0e') == 5 and b.seconds_left('Qwen35') == 50
    with pytest.raises(AdmissionError, match='GPU seconds'):
        b.claim(rows[0]['request_sha256'], 'G0e', session_id='s2', session_elapsed_s=6.)


def test_ledger_tamper_and_torn_tail(tmp_path):
    lg = Ledger(tmp_path, manifest_sha256='m')
    lg.add('A', x=1); lg.add('B', x=2)
    with open(lg.path, 'ab') as f:
        f.write(b'{"torn')
    lg2 = Ledger(tmp_path, manifest_sha256='m')
    assert lg2.torn_tail_seen and len(lg2.events) == 2 and lg2.path.name == 'LEDGER.002.jsonl'
    lg2.add('C')
    raw = lg.path.read_text().replace('"x": 1', '"x": 9')
    lg.path.write_text(raw)
    with pytest.raises(LedgerError):
        Ledger(tmp_path, manifest_sha256='m')
    other = tmp_path / 'other'
    Ledger(other, manifest_sha256='m').add('X')
    with pytest.raises(LedgerError, match='manifest'):
        Ledger(other, manifest_sha256='different')


def test_model_execution_refused_without_researcher_approval(tmp_path):
    m = manifest(fixture_rows())
    with pytest.raises(AdmissionError, match='no approval'):
        AU.refuse_without(None)
    with pytest.raises(AdmissionError, match='no approval'):
        AU.refuse_without(tmp_path / 'missing.json')
    good = dict(protocol=AU.APPROVAL_PROTOCOL, authorized=True, manifest_sha256=AU.manifest_sha256(m),
                max_physical_calls=1, max_gpu_seconds=10, models=['G0e'], researcher='r', decision_evidence='e')
    for change, why in [(dict(protocol='pmrl1-limited-run-1'), 'protocol'), (dict(authorized=False), 'authorization'),
                        (dict(manifest_sha256='x'), 'different manifest'),
                        (dict(max_physical_calls=10 ** 6), 'physical call cap'), (dict(models=['GPT']), 'model labels'),
                        (dict(researcher=''), 'signature')]:
        with pytest.raises(AdmissionError, match=why):
            AU.authorize(m, {**good, **change}, root=tmp_path)
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    with pytest.raises((AdmissionError, subprocess.CalledProcessError)):
        AU.authorize(m, {**good, 'executor_checkout_head': 'deadbeef'}, root=tmp_path)


def test_worker_refuses_standalone_start():
    env = dict(os.environ, PYTHONPATH=str(SRC))
    env.pop('PMRL1_LIMITED_SUPERVISOR_PID', None)
    p = subprocess.run([sys.executable, '-m', 'metacom_pm.need_aware.runtime.hf_worker'], input='', text=True,
                       env=env, capture_output=True)
    assert p.returncode != 0 and 'admitted supervisor' in p.stderr


def test_real_guard_and_transport_fail_closed_on_binding_mismatch(tmp_path):
    """Spawns the real NAA guard + worker; the worker rejects the runtime pin before importing torch."""
    m = dict(scope_sha256='s', caps=dict(input_cap=12000, backend_cap=16384),
             runtime=dict(python_executable=sys.executable, python='0.0.0', packages={},
                          worker_module='metacom_pm.need_aware.runtime.hf_worker'),
             checkpoints={'G0e': dict(header_sha256=[])})
    calls = []
    guard = lambda *a, **k: calls.append(a) or {}
    root = SRC.parents[1]
    b = NAAHFBackend(root, dict(label='G0e', path='/nonexistent'), m, tmp_path / 'w', time.monotonic() + 60,
                     guard_bound_s=60, device_guard=guard)
    with pytest.raises(AdmissionError, match='Python version'):
        b.load(30)
    b.close()
    failure = json.loads(next((tmp_path / 'w').glob('WIRE_FAILURE_*.private.json')).read_text())
    assert failure['operation'] == 'load' and failure['partial_generated_output'] is None
    assert calls                                                             # device guard consulted before/while loading
