"""Independent CPU admission and guarded supervisor for the bounded dynamic 88.

No device, model or network access in check/admit. An immutable plan is not
authorization. No old SMV, SC36 or remaining-220 approval transfers here.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
from pathlib import Path
import signal
import sys

from ..generator import limited_run as L
from ..generator.g0e import DECODE, SYSTEM
from ..io import file_sha256, object_sha256
from .pomdp_controller_protocol import protocol_contract, controller_decode
from .pomdp_latency import MonotonicClock, latency_contract, duration_ns

PROTOCOL = 'pmrl1-j-dynamic88-run-v1'
JOB_KIND = 'JOURNAL_POMDP_DYNAMIC88'
BASE_COMMIT = 'f2d59f1c42de672c0785e034dbbd76e424f5529e'
ORIGINAL_PROPOSAL_SHA = '13dcf42a8d9ff2e8b6724b0d3142acac9d289a025138dfc3a8a5f6d03046c0fb'
ORIGINAL_BUNDLE_SHA = '418e2865e98c41630ddbd70770cbcd3785dbfabcaf95cbe6b490bfb5a6179386'
ORIGINAL_KNOWN_SHA = '1dcc19fbee72e3158f2fec8d4917ef41832d9b9c462817069d5727f0bcf07b62'
ORIGINAL_SELECTION_SHA = '3bf423595b592eed31b3b5b835983522fcfd6841ccd8cb92c998fddb5638a56f'
ORIGINAL_TASKS_SHA = '14bf4753ca76f26c4a11e5c94c26381f0d686a9ddd539cf63640e0854c7fb8a1'
ORIGINAL_EVAL_SHA = '58c90e1230b674ff41e640dd68cda281e520829b305b15a4d2340b20377638b2'
ARMS = ('STOP', 'FixedTop4Macro', 'LLMOneShot', 'LLMToolAgent', 'SequentialRule', 'SequentialNoText')
ROLE_CAPS = {'terminal': 12, 'oneshot': 2, 'agent': 8}
REQUIRED_MODULES = tuple('project/src/metacom_pm/rl1v3/journal/' + name + '.py' for name in (
    'pomdp_dynamic_run', 'pomdp_dynamic_runtime', 'pomdp_dynamic_worker',
    'pomdp_controller_protocol', 'pomdp_latency', 'pomdp_memory',
    'pomdp_memory_prepare', 'pomdp_memory_proposal', 'temporal_retrieval',
    'selective_memory_validation_sources', 'joint_task_port', 'renderer')) + (
    'project/src/metacom_pm/rl1v3/generator/limited_run.py',
    'project/src/metacom_pm/rl1v3/generator/limited_worker_guard.py',
    'project/src/metacom_pm/rl1v3/generator/runprep_checkpoint.py',
    'project/scripts/rl1v3/journal_pomdp_dynamic_run.py')


def read(path):
    return json.loads(Path(path).read_text())


def rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def terminal_slots(task_ids):
    return [dict(task_id=t, method=m,
                 slot_id='pd88:' + object_sha256([PROTOCOL, t, m, 'terminal']))
            for t in task_ids for m in ARMS]


def comparison_scope(task_ids, control, timing):
    return dict(protocol=PROTOCOL, original_proposal_file_sha256=ORIGINAL_PROPOSAL_SHA,
        original_source_bundle_file_sha256=ORIGINAL_BUNDLE_SHA,
        original_selection_file_sha256=ORIGINAL_SELECTION_SHA,
        task_ids=task_ids, arms=list(ARMS), calls_max=88,
        jobs=4, calls_max_per_job=22, role_caps_per_job=ROLE_CAPS,
        model_loads_max=4, seconds_max_per_job=1200, seconds_max_total=4800,
        warmup=0, retries=0, automatic_followup=False,
        controller_contract_sha256=object_sha256(control),
        latency_contract_sha256=object_sha256(timing),
        cache_policy='disabled_for_latency_measurement',
        future_elapsed_time_state_in_policy=False, no_training=True, authorized=False)


def check_catalog(plan):
    catalog = read(plan['catalog_path'])
    L.require(catalog['protocol'] == PROTOCOL and catalog['authorized'] is False, 'catalog identity')
    L.require(catalog['max_calls'] == 88 and catalog['model_loads_max'] == 4
              and catalog['total_hard_seconds'] == 4800, 'whole comparison cap')
    batches = catalog['batches']
    L.require(len(batches) == 4 and [b['batch'] for b in batches] == [1, 2, 3, 4], 'four fixed source pairs')
    all_tasks = read(plan['original_proposal_path'])['task_ids']
    for b in batches:
        p = read(b['plan_path'])
        L.require(object_sha256(p) == b['plan_object_sha256']
                  and file_sha256(b['plan_path']) == b['plan_file_sha256'], 'catalog/plan binding')
        L.require(p['max_calls'] == 22 and p['batch_number'] == b['batch'], 'catalog budget')
        L.require(p['task_ids'] == all_tasks[2 * (b['batch'] - 1):2 * b['batch']]
                  and p['scope_sha256'] == plan['scope_sha256'], 'catalog source-pair scope')
    own = batches[plan['batch_number'] - 1]
    L.require(own['plan_object_sha256'] == object_sha256(plan), 'plan outside catalog')
    return catalog


def check(path):
    """Read-only CPU check: fixed task scope, dynamic program and byte identities."""
    plan = read(path)
    L.require((plan['protocol'], plan['job_kind']) == (PROTOCOL, JOB_KIND), 'independent dynamic identity')
    L.require(plan['authorized'] is False and plan['automatic_followup'] is False, 'immutable unapproved plan')
    L.require(plan['base_commit'] == BASE_COMMIT, 'fixed research starting point')
    L.require(type(plan['max_calls']) is int and plan['max_calls'] == 22
              and plan['role_call_caps'] == ROLE_CAPS, '22-call and role bounds')
    L.require(all(type(plan[k]) is int for k in ('max_model_loads', 'warmup_calls',
              'global_seconds', 'load_seconds', 'request_seconds', 'batch_number')), 'integer budget fields')
    L.require(plan['max_model_loads'] == 1 and plan['warmup_calls'] == 0
              and plan['automatic_retry'] is False, 'one load; no warmup/retry')
    L.require((plan['global_seconds'], plan['load_seconds'], plan['request_seconds']) == (1200, 600, 300), 'hard limits')
    L.require(plan['cache_policy'] == 'disabled_for_latency_measurement', 'no offline reuse as online latency')
    L.require(plan['python'] == '/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python', 'frozen Python')
    L.require(plan['model_path'] == '/opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3', 'frozen model')
    L.require(plan['gpu_uuid'] == L.GPU and plan['arms'] == list(ARMS), 'device or arms changed')
    L.require(plan['policy_elapsed_time_input'] is False and plan['formal_reward'] is None, 'measurement is not a new policy/reward')
    required_inputs = {
        plan[k] for k in ('original_proposal_path', 'bundle_manifest_path', 'selection_path',
                         'task_manifest_path', 'envelopes_path', 'review_path', 'known_requests_path',
                         'original_controller_path', 'cpu_pools_path', 'baseline_path', 'checkpoint_path',
                         'source_config_path', 'controller_contract_path', 'latency_contract_path',
                         'requests_path', 'initial_controllers_path', 'comparison_scope_path')}
    L.require(required_inputs <= set(plan['files_sha256']), 'unbound run input')
    for name, sha in plan['files_sha256'].items():
        L.require(file_sha256(name) == sha, 'bound input changed: ' + name)
    for key, sha in (('original_proposal_path', ORIGINAL_PROPOSAL_SHA),
                     ('bundle_manifest_path', ORIGINAL_BUNDLE_SHA), ('selection_path', ORIGINAL_SELECTION_SHA),
                     ('known_requests_path', ORIGINAL_KNOWN_SHA), ('task_manifest_path', ORIGINAL_TASKS_SHA),
                     ('review_path', ORIGINAL_EVAL_SHA)):
        L.require(file_sha256(plan[key]) == sha, 'old research scope changed: ' + key)
    original = read(plan['original_proposal_path'])
    L.require(original['tasks'] == 8 and original['physical_call_upper_bound_before_exact_cache'] == 88, 'original eight-task scope')
    L.require(plan['batch_number'] in (1, 2, 3, 4), 'batch range')
    chosen = original['task_ids'][2 * (plan['batch_number'] - 1):2 * plan['batch_number']]
    L.require(plan['task_ids'] == chosen and len(chosen) == 2, 'fixed full source-pair task order')
    selection = read(plan['selection_path'])
    L.require(selection['selected_task_ids'] == original['task_ids'], 'source-only selection changed')
    tasks = {t['task_id']: t for t in rows(plan['task_manifest_path'])}
    L.require(plan['task_sha256'] == {t: object_sha256(tasks[t]) for t in chosen}, 'worker task allowlist binding')
    envelopes = {t['task_id']: t for t in rows(plan['envelopes_path'])}
    reviews = {t['task_id']: t for t in rows(plan['review_path'])}
    L.require(all(t in tasks and t in envelopes and t in reviews for t in chosen), 'missing task/reference binding')
    for t in chosen:
        L.require(envelopes[t]['visible_task'] == tasks[t]
                  and envelopes[t]['visible_task_sha256'] == object_sha256(tasks[t]), 'visible task changed')
    L.require(len({reviews[t]['case_id'] for t in chosen}) == 1
              and {reviews[t]['goal_kind'] for t in chosen} == {'fact', 'natural_support'}, 'paired goals required')
    contract = read(plan['controller_contract_path'])
    L.require(contract == protocol_contract() and object_sha256(contract) == plan['controller_contract_sha256'], 'controller identity')
    timing = read(plan['latency_contract_path'])
    L.require(timing == latency_contract() and object_sha256(timing) == plan['latency_contract_sha256'], 'latency identity')
    global_scope = read(plan['comparison_scope_path'])
    L.require(global_scope == comparison_scope(original['task_ids'], contract, timing)
              and object_sha256(global_scope) == plan['scope_sha256'], 'global 88-call scope binding')
    baseline = read(plan['baseline_path'])
    L.require(file_sha256(plan['baseline_path']) == '1639a4a6f4c6f94cb256e24017f1a904c478642ea4549d4ca2f9e5c6ad8fa7ae'
              and file_sha256(plan['checkpoint_path']) == '288944b7d3fcb6faf52b2f82ba658e0d4a0fe26e4e3f91676b5e694817e63584', 'original signed G dependency bytes')
    L.require(object_sha256(baseline) == plan['baseline_sha256'], 'baseline identity')
    spec = baseline['spec']
    L.require(spec['decode'] == DECODE and spec['system_prompt'] == SYSTEM, 'terminal G unchanged')
    L.require(spec['model']['revision'] == '707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7'
              and spec['runtime']['gpu_uuid'] == L.GPU and spec['runtime']['backend'] == 'hf', 'model/backend identity')
    scope = read(plan['requests_path'])
    L.require(file_sha256(plan['requests_path']) == plan['requests_sha256'], 'dynamic request scope SHA')
    L.require(scope == dict(protocol=PROTOCOL, task_ids=chosen, terminal_slots=terminal_slots(chosen),
                           role_caps=ROLE_CAPS, max_calls=22,
                           controller_contract_sha256=plan['controller_contract_sha256'],
                           later_inputs='bind exact actual observations, requests and terminal inputs at runtime',
                           cache_policy=plan['cache_policy'], formal_reward=None), 'dynamic scope or implicit calls changed')
    initial = rows(plan['initial_controllers_path'])
    L.require(file_sha256(plan['original_controller_path']) == original['files_sha256']['CONTROLLER_INITIAL_16.private.jsonl'], 'original controller input identity')
    old_initial = [r for r in rows(plan['original_controller_path']) if r['task_id'] in chosen]
    L.require(len(initial) == len(old_initial) == 4, 'two controllers per task')
    for row, old in zip(initial, old_initial):
        L.require(row['task_id'] == old['task_id'] and row['method'] == old['method']
                  and row['messages'] == old['initial_messages'], 'initial controller messages changed')
        L.require(row['messages_sha256'] == object_sha256(row['messages']), 'initial messages SHA')
        L.require(row['decode'] == controller_decode(dict(DECODE), row['method'])
                  and row['controller_contract_sha256'] == plan['controller_contract_sha256'], 'common controller decode')
    known = rows(plan['known_requests_path'])
    L.require(len(known) == 32 and len({(r['task_id'], r['arm']) for r in known}) == 32, 'four deterministic arms per original task')
    for r in known:
        L.require(object_sha256(r['model_input']) == r['payload_sha256']
                  and r['model_input']['decode'] == DECODE, 'known terminal input drift')
    source = read(plan['source_config_path'])
    bundle = read(plan['bundle_manifest_path'])
    for key in ('resources_path', 'metadata_path'):
        L.require(source[key] in bundle['inputs_sha256'] and file_sha256(source[key]) == bundle['inputs_sha256'][source[key]], 'original source cache binding')
        L.require(source[key] in plan['files_sha256'], 'runtime source not frozen')
    L.require(source['asset_manifest_path'] in plan['files_sha256'], 'native tokenizer asset binding')
    source_design_path = next(k for k in bundle['inputs_sha256'] if k.endswith('SOURCE_DESIGN_V2_PRIVATE.json'))
    L.require(file_sha256(source_design_path) == bundle['inputs_sha256'][source_design_path], 'source scope recipe changed')
    design = read(source_design_path)
    L.require(source['allowed_owners'] == design['allowed_owners']
              and source['excluded_owners'] == design['excluded_J06_owners'], 'source family boundary changed')
    root = Path(plan['executor_root']).resolve()
    L.require(set(REQUIRED_MODULES) <= set(plan['executor_files_sha256']), 'unbound executor module')
    for rel, sha in plan['executor_files_sha256'].items():
        p = (root / rel).resolve()
        L.require(p.is_relative_to(root) and file_sha256(p) == sha, 'executor changed: ' + rel)
    L.require(object_sha256(plan['executor_files_sha256']) == plan['executor_inventory_sha256'], 'executor inventory')
    vendor = Path(plan['vendor_path']).resolve()
    L.require(vendor.is_relative_to(root) and 'xgrammar/__init__.py' in plan['vendor_files_sha256'], 'isolated grammar vendor')
    L.require(any(k.endswith('.so') for k in plan['vendor_files_sha256']), 'compiled grammar dependency required')
    for rel, sha in plan['vendor_files_sha256'].items():
        p = (vendor / rel).resolve()
        L.require(p.is_relative_to(vendor) and file_sha256(p) == sha, 'grammar vendor changed')
    for p, sha in plan['constraint_runtime_files_sha256'].items():
        L.require(file_sha256(p) == sha, 'grammar runtime changed')
    check_catalog(plan)
    return plan, [tasks[t] for t in chosen], baseline


def admit(plan, auth):
    L.require(auth.get('authorized') is True, 'new explicit dynamic88 researcher approval required')
    L.require((auth.get('protocol'), auth.get('job_kind')) == (PROTOCOL, JOB_KIND), 'old approval cannot transfer')
    L.require(auth.get('plan_sha256') == object_sha256(plan), 'approval plan identity')
    L.require(auth.get('catalog_file_sha256') == file_sha256(plan['catalog_path']), 'approval full comparison identity')
    for key, value in (('max_calls', 22), ('max_model_loads', 1), ('global_seconds', 1200),
                       ('warmup_calls', 0), ('retry_calls', 0)):
        L.require(type(auth.get(key)) is int and auth[key] == value, 'approval scope: ' + key)
    L.require(auth.get('gpu_uuid') == L.GPU and auth.get('researcher'), 'researcher/device required')
    evidence = Path(auth.get('decision_evidence', '/nonexistent'))
    L.require(evidence.is_file() and file_sha256(evidence) == auth.get('decision_evidence_sha256'), 'actual researcher decision bytes required')
    return auth


def claim_scope(plan, auth, directory=None):
    """Conservative reservation: failure cannot become an automatic second attempt."""
    directory = Path(directory) if directory is not None else L.DATA / 'tokkio_projects/pmrl1-validation/limited-g0e-claims'
    directory.mkdir(parents=True, exist_ok=True)
    identity = dict(job_kind=JOB_KIND, original_proposal_sha256=ORIGINAL_PROPOSAL_SHA,
                    task_ids=plan['task_ids'], baseline_sha256=plan['baseline_sha256'], arms=list(ARMS))
    key = object_sha256(identity)
    for p in directory.glob('*.json'):
        old = read(p)  # Partial/corrupt claims stop admission; never erase them.
        if old.get('dynamic_scope_sha256') == key or old.get('plan_sha256') == object_sha256(plan):
            raise FileExistsError('dynamic source pair already reserved; no retry or implicit resume')
    return L.write_once(directory / ('dynamic88-' + key + '.json'), dict(
        dynamic_scope_sha256=key, plan_sha256=object_sha256(plan),
        approval_sha256=object_sha256(auth), no_retry=True, utc=L.utc()))


class MonotonicJournal:
    def __init__(self, path, clock):
        self.inner = L.Journal(path)
        self.clock = clock
        self.path = self.inner.path
        self.last_ns = None

    @property
    def prev(self):
        return self.inner.prev

    def add(self, event, **fields):
        stamp = fields.pop('stamp', None) or self.clock.stamp()
        L.require(stamp['clock'] == 'CLOCK_MONOTONIC' and stamp['boot_id'] == self.clock.boot_id, 'event clock identity')
        L.require(type(stamp.get('monotonic_ns')) is int and stamp['monotonic_ns'] >= 0
                  and (self.last_ns is None or stamp['monotonic_ns'] >= self.last_ns), 'journal clock moved backwards')
        self.last_ns = stamp['monotonic_ns']
        return self.inner.add(event, stamp=stamp, **fields)


def assert_loaded_executor(plan):
    for name, module in list(sys.modules.items()):
        f = getattr(module, '__file__', None)
        if not name.startswith('metacom_pm.') or not f or not f.endswith('.py'):
            continue
        marker = '/metacom_pm/'
        if marker not in f:
            continue
        rel = 'project/src/metacom_pm/' + f.split(marker, 1)[1]
        L.require(rel in plan['executor_files_sha256']
                  and file_sha256(f) == plan['executor_files_sha256'][rel], 'loaded executor differs: ' + name)


def run(path, approval, run_root):
    plan, tasks, baseline = check(path)
    auth = admit(plan, read(approval))  # Before any device, model, cache or claim access.
    from .pomdp_dynamic_runtime import LiveEpisodeFactory, execute_source_pair
    from .pomdp_dynamic_worker import SubprocessDynamicHF
    from .selective_memory_validation_sources import load_development_cache
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
        deadline_ns = start['monotonic_ns'] + 1200 * 10**9
        journal = MonotonicJournal(root / ('job-' + object_sha256(auth)), clock)
        journal.add('RUN_START', stamp=start, plan_sha256=object_sha256(plan), approval=auth,
                    storage=storage, gpu=device, actual_model_calls=0, cache_policy=plan['cache_policy'])
        backend = None
        result = None
        failure = None
        phase = 'model_byte_verification'
        phase_started = clock.stamp()
        previous_handler = signal.getsignal(signal.SIGALRM)
        def expire(_signum, _frame):
            raise L.AdmissionError('whole-job 1200-second deadline')
        signal.signal(signal.SIGALRM, expire)
        signal.setitimer(signal.ITIMER_REAL, max(0.001, (deadline_ns - clock.now_ns()) / 1e9))
        try:
            journal.add('MODEL_BYTES_VERIFY_START', stamp=phase_started)
            for name, expected in baseline['spec']['model']['files'].items():
                p = Path(plan['model_path']) / name
                L.require(p.stat().st_size == expected['bytes'], 'model size: ' + name)
                h = hashlib.sha256()
                with p.open('rb') as f:
                    for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
                        L.require(clock.now_ns() < deadline_ns, 'model hash/global deadline')
                        h.update(block)
                L.require(h.hexdigest() == expected['sha256'], 'model SHA: ' + name)
            for p, sha in read(plan['checkpoint_path'])['software_files'].items():
                L.require(file_sha256(p) == sha, 'HF software changed')
            journal.add('MODEL_BYTES_VERIFIED')
            source = read(plan['source_config_path'])
            cold = clock.stamp()
            phase, phase_started = 'source_startup', cold
            journal.add('SOURCE_STARTUP_START', stamp=cold, online_request_cost=False)
            registry = load_development_cache(resources_path=source['resources_path'], metadata_path=source['metadata_path'],
                allowed_owners=source['allowed_owners'], excluded_owners=source['excluded_owners'])
            tokenizer = PromptTokenizer(NativeTokenizer(plan['model_path'], source['asset_manifest_path']))
            envelopes = {r['task_id']: r for r in rows(plan['envelopes_path'])}
            factory = LiveEpisodeFactory(registry=registry, tokenizer=tokenizer,
                baseline_sha256=baseline['binding_sha256'], envelopes=envelopes,
                ledger_root=journal.path / 'runtime-ledgers', frozen_pools_path=plan['cpu_pools_path'])
            factory.prepare(tasks)
            journal.add('SOURCE_STARTUP_FINISHED', started=cold,
                        elapsed_ns=clock.now_ns() - cold['monotonic_ns'], online_request_cost=False)
            assert_loaded_executor(plan)
            backend = SubprocessDynamicHF(Path(plan['executor_root']), plan, baseline, journal.path, deadline_ns / 1e9)
            load_start = clock.stamp()
            phase, phase_started = 'model_load', load_start
            journal.add('LOAD_START', stamp=load_start, max_loads=1)
            loaded = backend.load(min(600, (deadline_ns - clock.now_ns()) / 1e9))
            journal.add('LOAD_OK', started=load_start, measurement=loaded)
            phase, phase_started = 'online_comparison', clock.stamp()
            result = execute_source_pair(tasks=tasks, factory=factory, backend=backend,
                emit=journal.add, clock=clock, deadline_ns=deadline_ns,
                guard=lambda: (L.storage_guard(root), L.device_guard(backend.p.pid if backend.p else None)),
                terminal_cache=None)
        except BaseException as exc:
            failure = type(exc).__name__ + ': ' + str(exc)
            failed_at = clock.stamp()
            journal.add('SUPERVISOR_STOP', stamp=failed_at, reason=failure,
                        phase=phase, phase_started=phase_started,
                        partial_phase_ns=duration_ns(phase_started, failed_at),
                        technical_incomplete=True, no_retry=True, formal_reward=None)
        finally:
            # Worker guard additionally owns parent-death/deadline cleanup.
            if backend is not None:
                try:
                    backend.close()
                except BaseException as exc:
                    failure = (failure or '') + '; close: ' + str(exc)
                    journal.add('SUPERVISOR_STOP', reason=failure, no_retry=True)
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)
        end = clock.stamp()
        summary = dict(protocol=PROTOCOL, job_kind=JOB_KIND, plan_sha256=object_sha256(plan),
            started=start, ended=end, wall_ns=duration_ns(start, end),
            supervisor_failure=failure, runtime=result, formal_reward=None,
            status='STOPPED' if failure or result is None or result.get('status') != 'FINISHED' else 'FINISHED',
            backend='hf_dynamic_real', no_retry=True, automatic_followup=False,
            latency_scope='instrumented local text Agent; not Tokkio client or audio E2E',
            technical_incomplete_endpoints=None if result is None else len(result['pending']),
            all_endpoints_technically_complete=False if result is None else not result['pending'],
            last_journal_sha256=journal.prev)
        L.write_once(journal.path / 'SUMMARY.json', summary)
        return summary
