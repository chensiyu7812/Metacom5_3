"""GSWS independent CPU admission and one-load guarded supervisor.

No prior authorization transfers. check never touches devices or model weights.
Normal policies cannot access the bound evaluation sidecar or Direct recipe.
"""
from __future__ import annotations

import fcntl
import hashlib
from pathlib import Path
import signal

from ..generator import limited_run as L
from ..generator.g0e import DECODE, SYSTEM
from ..io import file_sha256, object_sha256
from .gsws import contract as protocol_contract, ARMS
from .ge2_memory import environment_contract
from .ge2_retrieval import RetrievalConfig
from .gsws_runtime import slots as terminal_slots
from .pomdp_dynamic_run import read, rows, MonotonicJournal, assert_loaded_executor
from .pomdp_latency import MonotonicClock, latency_contract, duration_ns

PROTOCOL = 'pmrl1-j-gsws-bounded-run-v1'
JOB_KIND = 'JOURNAL_GSWS'
BASE_COMMIT = '73b6c5e09ec842a4bb9c41f9ba23f6d7eb568ffc'
CONFIG = dict(backend='bm25', top_k=4, window_radius=1, bm25_k1=1.2, bm25_b=.75)
REQUIRED_MODULES = tuple('project/src/metacom_pm/rl1v3/journal/' + n + '.py' for n in (
    'gsws', 'gsws_run', 'gsws_runtime', 'gsws_worker', 'ge2_memory', 'ge2_retrieval',
    'ge2_factory', 'ge2_sources', 'renderer', 'runtime_binding', 'memory_port', 'memory',
    'joint_task_port', 'pomdp_dynamic_runtime', 'pomdp_dynamic_run', 'pomdp_latency')) + (
    'project/src/metacom_pm/rl1v3/generator/limited_run.py',
    'project/src/metacom_pm/rl1v3/generator/limited_worker_guard.py',
    'project/scripts/rl1v3/journal_gsws_run.py')


def check(path):
    plan = read(path)
    L.require((plan['protocol'], plan['job_kind'], plan['base_commit']) == (PROTOCOL, JOB_KIND, BASE_COMMIT), 'GSWS identity')
    L.require(plan['authorized'] is False and plan['automatic_followup'] is False, 'plan is not approval')
    L.require(plan['arms'] == list(ARMS) and plan['diagnostic_arm'] is None, 'GSWS comparisons')
    for key, value in dict(max_model_loads=1, warmup_calls=0, retry_calls=0,
                           global_seconds=1200, load_seconds=600, request_seconds=300).items():
        L.require(type(plan[key]) is int and plan[key] == value, 'GSWS budget ' + key)
    L.require(plan['cache_policy'] == 'disabled' and plan['formal_reward'] is None, 'no cache/reward promotion')
    L.require(plan['gpu_uuid'] == L.GPU and plan['python'] == '/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python'
              and plan['model_path'] == '/opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3', 'frozen execution stack')
    L.require(plan['retrieval_config'] == CONFIG, 'one frozen shared retrieval configuration')
    required = {plan[k] for k in ('task_manifest_path', 'envelopes_path', 'review_path',
        'source_config_path', 'selection_path', 'baseline_path', 'checkpoint_path', 'requests_path',
        'controller_contract_path', 'environment_contract_path', 'latency_contract_path')}
    L.require(required <= set(plan['files_sha256']), 'unbound GSWS inputs')
    for p, sha in plan['files_sha256'].items():
        L.require(file_sha256(p) == sha, 'GSWS input changed: ' + p)
    all_tasks = rows(plan['task_manifest_path'])
    L.require(len(all_tasks) == 8 and len({t['task_id'] for t in all_tasks}) == 8, 'eight frozen tasks')
    ids = [t['task_id'] for t in all_tasks]
    L.require(plan['batch_number'] in (1, 2, 3, 4) and type(plan['batch_number']) is int, 'GSWS four jobs')
    n = plan['batch_number']
    tasks = all_tasks[2 * (n - 1):2 * n]
    L.require(plan['task_ids'] == [t['task_id'] for t in tasks]
              and plan['task_sha256'] == {t['task_id']: object_sha256(t) for t in tasks}, 'task allowlist')
    envelopes = {r['task_id']: r for r in rows(plan['envelopes_path'])}
    for t in tasks:
        e = envelopes[t['task_id']]
        L.require(t == e['visible_task'] and object_sha256(t) == e['visible_task_sha256'], 'visible task binding')
    slots = terminal_slots(tasks)
    caps = {'terminal': 12, 'oneshot': 4, 'agent': 4}
    L.require(plan['terminal_slots'] == slots and plan['role_call_caps'] == caps
              and plan['max_calls'] == sum(caps.values()), 'GSWS call/slot caps')
    scope = read(plan['requests_path'])
    L.require(scope == dict(protocol=PROTOCOL, task_ids=plan['task_ids'], terminal_slots=slots,
        role_call_caps=caps, max_calls=sum(caps.values()), scope_sha256=plan['scope_sha256'],
        controller_contract_sha256=plan['controller_contract_sha256'],
        future_payload_binding='exact actual observation, validated source receipt and native payload at each call',
        authorized=False), 'frozen dynamic request scope')
    L.require(file_sha256(plan['requests_path']) == plan['requests_sha256'], 'request scope file SHA')
    L.require(read(plan['controller_contract_path']) == protocol_contract()
              and plan['controller_contract_sha256'] == object_sha256(protocol_contract()), 'GSWS controller identity')
    L.require(read(plan['environment_contract_path']) == environment_contract(), 'GSWS environment identity')
    L.require(read(plan['latency_contract_path']) == latency_contract(), 'unchanged real monotonic timing contract')
    source = read(plan['source_config_path'])
    L.require(set(source['source_inputs_sha256']) <= set(plan['files_sha256']), 'source files outside bound scope')
    baseline = read(plan['baseline_path'])
    L.require(file_sha256(plan['baseline_path']) == '1639a4a6f4c6f94cb256e24017f1a904c478642ea4549d4ca2f9e5c6ad8fa7ae'
              and file_sha256(plan['checkpoint_path']) == '288944b7d3fcb6faf52b2f82ba658e0d4a0fe26e4e3f91676b5e694817e63584', 'signed G dependency unchanged')
    L.require(object_sha256(baseline) == plan['baseline_sha256'], 'baseline SHA')
    spec = baseline['spec']
    L.require(spec['decode'] == DECODE and spec['system_prompt'] == SYSTEM
              and spec['model']['revision'] == '707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7'
              and spec['runtime']['gpu_uuid'] == L.GPU and spec['runtime']['backend'] == 'hf', 'same terminal G/model')
    root = Path(plan['executor_root']).resolve()
    L.require(set(REQUIRED_MODULES) <= set(plan['executor_files_sha256']), 'GSWS executor closure')
    for rel, sha in plan['executor_files_sha256'].items():
        p = (root / rel).resolve()
        L.require(p.is_relative_to(root) and file_sha256(p) == sha, 'GSWS executor changed: ' + rel)
    L.require(object_sha256(plan['executor_files_sha256']) == plan['executor_inventory_sha256'], 'GSWS executor inventory')
    vendor = Path(plan['vendor_path']).resolve()
    L.require(vendor.is_relative_to(root), 'isolated grammar vendor')
    for rel, sha in plan['vendor_files_sha256'].items():
        p = (vendor / rel).resolve()
        L.require(p.is_relative_to(vendor) and file_sha256(p) == sha, 'grammar vendor bytes')
    for p, sha in plan['constraint_runtime_files_sha256'].items():
        L.require(file_sha256(p) == sha, 'constraint runtime bytes')
    catalog = read(plan['catalog_path'])
    L.require(catalog['protocol'] == PROTOCOL and catalog['authorized'] is False and catalog['max_calls'] == 80
              and catalog['terminal_slots'] == 48 and catalog['model_loads_max'] == 4
              and catalog['total_hard_seconds'] == 4800 and catalog['task_ids'] == ids, 'one bounded GSWS comparison')
    L.require(len(catalog['batches']) == 4, 'GSWS job count')
    for i, batch in enumerate(catalog['batches']):
        bp = read(batch['plan_path'])
        L.require(object_sha256(bp) == batch['plan_object_sha256']
                  and file_sha256(batch['plan_path']) == batch['plan_file_sha256']
                  and bp['task_ids'] == ids[2*i:2*i+2]
                  and bp['scope_sha256'] == plan['scope_sha256'], 'GSWS catalog/plan binding')
    L.require(catalog['batches'][n-1]['plan_object_sha256'] == object_sha256(plan), 'own plan outside catalog')
    return plan, tasks, baseline


def admit(plan, auth):
    L.require(auth.get('authorized') is True and (auth.get('protocol'), auth.get('job_kind')) == (PROTOCOL, JOB_KIND),
              'new explicit GSWS researcher authorization required; old budgets never transfer')
    L.require(auth.get('plan_sha256') == object_sha256(plan)
              and auth.get('catalog_file_sha256') == file_sha256(plan['catalog_path']), 'GSWS approval identities')
    for k in ('max_calls', 'max_model_loads', 'global_seconds', 'warmup_calls', 'retry_calls'):
        L.require(type(auth.get(k)) is int and auth[k] == plan[k], 'GSWS approval cap ' + k)
    L.require(auth.get('gpu_uuid') == L.GPU and auth.get('researcher'), 'researcher/device binding')
    evidence = Path(auth.get('decision_evidence', '/nonexistent'))
    L.require(evidence.is_file() and file_sha256(evidence) == auth.get('decision_evidence_sha256'), 'actual approval evidence')
    return auth


def claim_scope(plan, auth, directory=None):
    directory = Path(directory) if directory else L.DATA / 'tokkio_projects/pmrl1-validation/limited-g0e-claims'
    directory.mkdir(parents=True, exist_ok=True)
    key = object_sha256(dict(job_kind=JOB_KIND, scope_sha256=plan['scope_sha256'], task_ids=plan['task_ids']))
    for p in directory.glob('*.json'):
        old = read(p)
        if old.get('gsws_scope_sha256') == key or old.get('plan_sha256') == object_sha256(plan):
            raise FileExistsError('GSWS job reserved; no retry/implicit resume')
    return L.write_once(directory / ('gsws-' + key + '.json'), dict(gsws_scope_sha256=key,
        plan_sha256=object_sha256(plan), approval_sha256=object_sha256(auth), no_retry=True, utc=L.utc()))


def run(path, approval, run_root):
    plan, tasks, baseline = check(path)
    auth = admit(plan, read(approval))  # before GPU, weights, claim or runtime cache
    from .ge2_factory import GE2Factory
    from .gsws_runtime import execute
    from .gsws_worker import SubprocessGSWSHF
    from ..retrieve.native_tokens import NativeTokenizer
    from ..generator.g0e_port import PromptTokenizer
    assert_loaded_executor(plan)
    root = Path(run_root).resolve()
    storage = L.storage_guard(root)
    lock_path = L.DATA / 'tokkio_projects/pmrl1-validation/limited-g0e-exclusive.lock'
    with lock_path.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        device = L.device_guard(initial=True)
        claim_scope(plan, auth)
        clock = MonotonicClock()
        start = clock.stamp()
        deadline = start['monotonic_ns'] + plan['global_seconds'] * 10**9
        journal = MonotonicJournal(root / ('job-' + object_sha256(auth)), clock)
        journal.add('RUN_START', stamp=start, plan_sha256=object_sha256(plan), approval=auth, storage=storage, gpu=device,
                    actual_model_calls=0, cache_policy='disabled')
        backend = result = failure = None
        phase, phase_started = 'model_byte_verification', clock.stamp()
        old_handler = signal.getsignal(signal.SIGALRM)
        def expire(_sig, _frame):
            raise L.AdmissionError('GSWS whole-job deadline')
        signal.signal(signal.SIGALRM, expire)
        signal.setitimer(signal.ITIMER_REAL, max(.001, (deadline-clock.now_ns())/1e9))
        try:
            journal.add('MODEL_BYTES_VERIFY_START', stamp=phase_started)
            for name, expected in baseline['spec']['model']['files'].items():
                p = Path(plan['model_path']) / name
                L.require(p.stat().st_size == expected['bytes'], 'model size ' + name)
                h = hashlib.sha256()
                with p.open('rb') as stream:
                    for block in iter(lambda: stream.read(8*1024*1024), b''):
                        L.require(clock.now_ns() < deadline, 'model hash deadline')
                        h.update(block)
                L.require(h.hexdigest() == expected['sha256'], 'model SHA ' + name)
            for p, sha in read(plan['checkpoint_path'])['software_files'].items():
                L.require(file_sha256(p) == sha, 'HF software identity')
            journal.add('MODEL_BYTES_VERIFIED')
            source = read(plan['source_config_path'])
            phase, phase_started = 'source_startup', clock.stamp()
            journal.add('SOURCE_STARTUP_START', stamp=phase_started, online_request_cost=False)
            tok = PromptTokenizer(NativeTokenizer(plan['model_path'], source['asset_manifest_path']))
            envelopes = {r['task_id']: r for r in rows(plan['envelopes_path'])}
            factory = GE2Factory(source_config=source, envelopes=envelopes, tokenizer=tok,
                baseline=baseline, ledger_root=journal.path/'runtime-ledgers', retrieval_config=RetrievalConfig(**CONFIG))
            factory.prepare(tasks)
            journal.add('SOURCE_STARTUP_FINISHED', elapsed_ns=clock.now_ns()-phase_started['monotonic_ns'], online_request_cost=False)
            assert_loaded_executor(plan)
            backend = SubprocessGSWSHF(Path(plan['executor_root']), plan, baseline, journal.path, deadline/1e9)
            phase, phase_started = 'model_load', clock.stamp()
            journal.add('LOAD_START', stamp=phase_started, max_loads=1)
            loaded = backend.load(min(600, (deadline-clock.now_ns())/1e9))
            journal.add('LOAD_OK', started=phase_started, measurement=loaded)
            phase, phase_started = 'online_comparison', clock.stamp()
            result = execute(tasks=tasks, factory=factory, backend=backend, slots=plan['terminal_slots'],
                emit=journal.add, clock=clock, deadline_ns=deadline,
                guard=lambda: (L.storage_guard(root), L.device_guard(backend.p.pid if backend.p else None)))
        except BaseException as exc:
            failure = type(exc).__name__ + ': ' + str(exc)
            now = clock.stamp()
            journal.add('SUPERVISOR_STOP', stamp=now, reason=failure, phase=phase,
                        partial_phase_ns=duration_ns(phase_started, now), retry_calls=0, formal_reward=None)
        finally:
            if backend is not None:
                try:
                    backend.close()
                except BaseException as exc:
                    failure = (failure or '') + '; close: ' + str(exc)
                    journal.add('SUPERVISOR_STOP', reason=failure)
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_handler)
        end = clock.stamp()
        summary = dict(protocol=PROTOCOL, job_kind=JOB_KIND, plan_sha256=object_sha256(plan),
            started=start, ended=end, wall_ns=duration_ns(start, end), runtime=result,
            status='FINISHED' if failure is None and result and result['status']=='FINISHED' else 'STOPPED',
            supervisor_failure=failure, retry_calls=0, automatic_followup=False, formal_reward=None,
            last_journal_sha256=journal.prev, latency_scope='local Agent; not client text or Tokkio audio')
        L.write_once(journal.path/'SUMMARY.json', summary)
        return summary
