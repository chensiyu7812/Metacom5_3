"""Freeze one GE2 comparison into four independently approved jobs on CPU."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import shlex
import shutil

from ..io import file_sha256, object_sha256, write_json_once
from . import ge2_run as R
from .ge2_controller import protocol_contract
from .ge2_memory import environment_contract
from .ge2_runtime import terminal_slots
from .pomdp_latency import latency_contract


def prepare(*, repo, original_plan, bundle, selection, retrieval_freeze, out, evaluation_contract=None):
    repo, original_plan, bundle, selection, retrieval_freeze, out = map(
        lambda x: Path(x).resolve(), (repo, original_plan, bundle, selection, retrieval_freeze, out))
    if out.exists():
        raise FileExistsError(out)
    old = R.read(original_plan)
    tasks = R.rows(bundle/'TASKS.runtime.jsonl')
    direct = R.rows(bundle/'DIRECT_SOURCE_RECIPE_PRIVATE.jsonl')
    if len(tasks) != 8 or len(direct) != 5:
        raise ValueError('frozen eight-task/five-diagnostic scope required')
    out.mkdir(parents=True)
    executor = out/'executor'
    shutil.copytree(old['executor_root'], executor, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    # New identity copies the original composite dependency, plus the current
    # additive journal implementation. No original executor or worktree is edited.
    for p in (repo/'project/src/metacom_pm/rl1v3/journal').glob('*.py'):
        shutil.copy2(p, executor/'project/src/metacom_pm/rl1v3/journal'/p.name)
    for name in ('journal_ge2_run.py', 'journal_prepare_ge2.py', 'journal_check_ge2_runtime.py', 'journal_check_ge2_controller.py'):
        target = executor/'project/scripts/rl1v3'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo/'project/scripts/rl1v3'/name, target)
    vendor_rel = Path(old['vendor_path']).relative_to(Path(old['executor_root']))
    vendor = executor/vendor_rel
    # Already copied by copytree: the native grammar binary remains byte-identical.
    vendor_hashes = {str(p.relative_to(vendor)): file_sha256(p) for p in vendor.rglob('*') if p.is_file() and p.suffix != '.pyc'}
    executor_hashes = {str(p.relative_to(executor)): file_sha256(p) for p in (executor/'project').rglob('*')
                       if p.is_file() and p.suffix != '.pyc'}
    control_path, env_path, latency_path = out/'CONTROLLER_CONTRACT.json', out/'ENVIRONMENT_CONTRACT.json', out/'LATENCY_CONTRACT.json'
    write_json_once(control_path, protocol_contract())
    write_json_once(env_path, environment_contract())
    write_json_once(latency_path, latency_contract())
    source = R.read(bundle/'SOURCE_CONFIG_PRIVATE.json')
    source['asset_manifest_path'] = R.read(old['source_config_path'])['asset_manifest_path']
    source_path = out/'SOURCE_CONFIG_PRIVATE.json'
    write_json_once(source_path, source)
    common = dict(task_manifest_path=str(bundle/'TASKS.runtime.jsonl'),
        envelopes_path=str(bundle/'TASK_ENVELOPES.private.jsonl'),
        review_path=str(bundle/'EVALSPEC.private.jsonl'),
        direct_recipes_path=str(bundle/'DIRECT_SOURCE_RECIPE_PRIVATE.jsonl'),
        source_config_path=str(source_path), selection_path=str(selection),
        baseline_path=old['baseline_path'], checkpoint_path=old['checkpoint_path'],
        controller_contract_path=str(control_path), environment_contract_path=str(env_path), latency_contract_path=str(latency_path))
    files = {p: file_sha256(p) for p in common.values()}
    for p in (*source['source_inputs_sha256'], source['asset_manifest_path'], original_plan, retrieval_freeze,
              bundle/'MANIFEST_PRIVATE.json', bundle/'LEGAL_POOLS_PRIVATE.jsonl'):
        files[str(p)] = file_sha256(p)
    if evaluation_contract:
        files[str(Path(evaluation_contract).resolve())] = file_sha256(evaluation_contract)
    scope = dict(protocol=R.PROTOCOL, base_commit=R.BASE_COMMIT,
        tasks=[(t['task_id'], object_sha256(t)) for t in tasks], direct_task_ids=[d['task_id'] for d in direct],
        source_config_sha256=object_sha256(source), retrieval=R.CONFIG,
        selection_file_sha256=file_sha256(selection), evaluation_file_sha256=file_sha256(common['review_path']),
        controller_contract_sha256=object_sha256(protocol_contract()), environment_contract_sha256=object_sha256(environment_contract()),
        max_calls=85, terminal_slots=37, model_loads_max=4, total_hard_seconds=4800,
        no_training=True, formal_reward=None, runtime_observation_never_contains_eval=True)
    write_json_once(out/'COMPARISON_SCOPE_PRIVATE.json', scope)
    files[str(out/'COMPARISON_SCOPE_PRIVATE.json')] = file_sha256(out/'COMPARISON_SCOPE_PRIVATE.json')
    baseline = R.read(old['baseline_path'])
    catalog_path = out/'CATALOG.json'
    batches = []
    for n in range(1, 5):
        chosen = tasks[2*(n-1):2*n]
        ids = [t['task_id'] for t in chosen]
        slots = terminal_slots(chosen, [d['task_id'] for d in direct])
        caps = dict(terminal=len(slots), oneshot=2, agent=10)
        batch = out/('batch-%02d'%n)
        batch.mkdir()
        requests = dict(protocol=R.PROTOCOL, task_ids=ids, terminal_slots=slots, role_call_caps=caps,
            max_calls=sum(caps.values()), scope_sha256=object_sha256(scope),
            controller_contract_sha256=object_sha256(protocol_contract()),
            future_payload_binding='exact actual observation, validated source receipt and native payload at each call', authorized=False)
        request_path = batch/'REQUEST_SCOPE_PRIVATE.json'
        write_json_once(request_path, requests)
        plan = dict(common, protocol=R.PROTOCOL, job_kind=R.JOB_KIND, base_commit=R.BASE_COMMIT,
            authorized=False, automatic_followup=False, batch_number=n,
            task_ids=ids, task_sha256={t['task_id']: object_sha256(t) for t in chosen},
            scope_sha256=object_sha256(scope), arms=list(R.ARMS), diagnostic_arm=R.DIRECT,
            terminal_slots=slots, role_call_caps=caps, max_calls=sum(caps.values()),
            max_model_loads=1, warmup_calls=0, retry_calls=0, global_seconds=1200, load_seconds=600, request_seconds=300,
            cache_policy='disabled', formal_reward=None, retrieval_config=R.CONFIG,
            gpu_uuid=R.L.GPU, python=old['python'], model_path=old['model_path'],
            baseline_sha256=object_sha256(baseline), renderer_id=old['renderer_id'],
            controller_contract_sha256=object_sha256(protocol_contract()),
            requests_path=str(request_path), requests_sha256=file_sha256(request_path), catalog_path=str(catalog_path),
            executor_root=str(executor), executor_files_sha256=executor_hashes,
            executor_inventory_sha256=object_sha256(executor_hashes), vendor_path=str(vendor),
            vendor_files_sha256=vendor_hashes, constraint_runtime_files_sha256=old['constraint_runtime_files_sha256'],
            files_sha256=dict(files, **{str(request_path): file_sha256(request_path)}),
            stop_rules=dict(controller_protocol_or_length='end that acquisition path; one already-budgeted terminal fallback; preserve degradation',
                terminal_length='retain technical incomplete endpoint; next independent slot may proceed without retry',
                capacity_or_time_reserve='forced STOP with current validated evidence, distinct from model STOP',
                worker_transport_model_device_integrity='stop whole own job, no fallback to another device or backend',
                job_deadline='hard stop all own computation, preserve incomplete and unexecuted separately'),
            timing_notes=['No terminal cache; physical latency for every endpoint.',
                'Fixed order and zero warmup; cold first inference marked, not a causal timing estimate.',
                'Direct recipe loading/selection is diagnostic; not deployed retrieval performance.',
                'Local internal first nonempty text is not client first text or Tokkio useful speech.'])
        path = batch/'PLAN.json'
        write_json_once(path, plan)
        batches.append(dict(label='GE2-'+str(n), batch=n, plan_path=str(path),
            plan_object_sha256=object_sha256(plan), plan_file_sha256=file_sha256(path),
            request_scope_file_sha256=file_sha256(request_path), max_calls=plan['max_calls'],
            terminal_slots=len(slots), max_model_loads=1, hard_seconds=1200, authorized=False))
    catalog = dict(protocol=R.PROTOCOL, base_commit=R.BASE_COMMIT, authorized=False,
        task_ids=[t['task_id'] for t in tasks], scope_sha256=object_sha256(scope),
        max_calls=85, terminal_slots=37, model_loads_max=4, total_hard_seconds=4800,
        batches=batches, executor_inventory_sha256=object_sha256(executor_hashes),
        controller_contract_sha256=object_sha256(protocol_contract()),
        new_actual_model_calls=0, automatic_followup=False, formal_reward=None)
    if sum(b['max_calls'] for b in batches) != 85:
        raise ValueError('GE2 total scope mismatch')
    write_json_once(catalog_path, catalog)
    for b in batches:
        plan, _, _ = R.check(b['plan_path'])
        batch = Path(b['plan_path']).parent
        write_json_once(batch/'APPROVAL_TEMPLATE.json', dict(protocol=R.PROTOCOL, job_kind=R.JOB_KIND,
            authorized=False, plan_sha256=object_sha256(plan), catalog_file_sha256=file_sha256(catalog_path),
            max_calls=plan['max_calls'], max_model_loads=1, global_seconds=1200, warmup_calls=0, retry_calls=0,
            gpu_uuid=R.L.GPU, researcher='', decision_evidence='', decision_evidence_sha256=''))
        script = ['#!/usr/bin/env bash', 'set -euo pipefail',
            'approval_file="${1:?Pass new explicit researcher approval JSON}"',
            'job_output="${2:?Pass a fresh data-volume output directory}"',
            'test ! -e "$job_output"', 'mkdir -p "$job_output/runtime-cache"',
            'export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1',
            'export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 TOKENIZERS_PARALLELISM=false',
            'export PYTHONPATH='+shlex.quote(str(executor/'project/src')+':'+str(vendor))]
        for key in ('TMPDIR', 'TMP', 'TEMP', 'HF_HOME', 'HF_HUB_CACHE', 'TRANSFORMERS_CACHE', 'XDG_CACHE_HOME',
                    'TORCH_HOME', 'TORCHINDUCTOR_CACHE_DIR', 'TRITON_CACHE_DIR', 'CUDA_CACHE_PATH', 'PYTHONPYCACHEPREFIX'):
            script.append('export '+key+'="$job_output/runtime-cache"')
        script.append('exec '+shlex.quote(old['python'])+' '+shlex.quote(str(executor/'project/scripts/rl1v3/journal_ge2_run.py'))+
            ' run --plan '+shlex.quote(b['plan_path'])+' --approval "$approval_file" --run-root "$job_output"')
        (batch/'RUN_AFTER_NEW_APPROVAL.sh').write_text('\n'.join(script)+'\n')
    return dict(catalog, catalog_file_sha256=file_sha256(catalog_path))
