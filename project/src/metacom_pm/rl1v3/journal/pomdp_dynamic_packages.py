"""Freeze four source-paired dynamic jobs on CPU; never grant or exercise approval."""
from __future__ import annotations

import json
from pathlib import Path
import shlex
import shutil

from ..io import file_sha256, object_sha256, write_json_once, write_jsonl_once
from . import pomdp_dynamic_run as R
from .pomdp_controller_protocol import protocol_contract, controller_decode
from .pomdp_latency import latency_contract
from ..generator.g0e import DECODE


def prepare(*, repo, prior, bundle, cpu, original_plan, constrained_plan, asset_manifest, out):
    repo, prior, bundle, cpu, original_plan, constrained_plan, asset_manifest, out = map(
        lambda p: Path(p).resolve(), (repo, prior, bundle, cpu, original_plan, constrained_plan, asset_manifest, out))
    if out.exists():
        raise FileExistsError(out)
    original = R.read(original_plan)
    old_constraint = R.read(constrained_plan)
    old_proposal_path = prior / 'PROPOSAL_PRIVATE.json'
    if file_sha256(old_proposal_path) != R.ORIGINAL_PROPOSAL_SHA:
        raise ValueError('wrong original bounded proposal')
    old_proposal = R.read(old_proposal_path)
    source_manifest = R.read(bundle / 'MANIFEST.json')
    design_path = Path(next(p for p in source_manifest['inputs_sha256'] if p.endswith('SOURCE_DESIGN_V2_PRIVATE.json')))
    design = R.read(design_path)
    resources = Path(next(p for p in source_manifest['inputs_sha256'] if p.endswith('resources_private.jsonl')))
    metadata = Path(next(p for p in source_manifest['inputs_sha256'] if p.endswith('/registry/registry.json')))
    tasks = {r['task_id']: r for r in R.rows(bundle / 'TASKS.runtime.jsonl')}
    out.mkdir(parents=True)
    executor = out / 'executor'
    shutil.copytree(original['executor_root'], executor, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    # Existing generator/guard stack retained; current journal modules are
    # explicitly frozen in this new snapshot, never copied over old evidence.
    for src in (repo / 'project/src/metacom_pm/rl1v3/journal').glob('*.py'):
        target = executor / 'project/src/metacom_pm/rl1v3/journal' / src.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
    for name in ('journal_pomdp_dynamic_run.py', 'journal_prepare_pomdp_dynamic.py'):
        target = executor / 'project/scripts/rl1v3' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(repo / 'project/scripts/rl1v3' / name, target)
    vendor = executor / 'vendor_dynamic_controller'
    shutil.copytree(old_constraint['vendor_path'], vendor, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    vendor_hashes = {str(p.relative_to(vendor)): file_sha256(p) for p in vendor.rglob('*') if p.is_file()}
    executor_hashes = {str(p.relative_to(executor)): file_sha256(p)
        for p in (executor / 'project').rglob('*') if p.is_file() and p.suffix != '.pyc'}
    control_path, timing_path = out / 'CONTROLLER_CONTRACT.json', out / 'LATENCY_CONTRACT.json'
    control, timing = protocol_contract(), latency_contract()
    write_json_once(control_path, control)
    write_json_once(timing_path, timing)
    source = dict(resources_path=str(resources), metadata_path=str(metadata),
        asset_manifest_path=str(asset_manifest), allowed_owners=design['allowed_owners'],
        excluded_owners=design['excluded_J06_owners'])
    source_path = out / 'SOURCE_CONFIG_PRIVATE.json'
    write_json_once(source_path, source)
    scope = R.comparison_scope(old_proposal['task_ids'], control, timing)
    scope_path = out / 'COMPARISON_SCOPE_PRIVATE.json'
    write_json_once(scope_path, scope)
    original_controls = R.rows(prior / 'CONTROLLER_INITIAL_16.private.jsonl')
    known = R.rows(prior / 'DETERMINISTIC_32_REQUESTS.private.jsonl')
    common = dict(original_proposal_path=str(old_proposal_path),
        bundle_manifest_path=str(bundle / 'MANIFEST.json'), selection_path=str(bundle / 'FUTURE_G_SELECTION_PRIVATE.json'),
        task_manifest_path=str(bundle / 'TASKS.runtime.jsonl'), envelopes_path=str(bundle / 'TASK_ENVELOPES.private.jsonl'),
        review_path=str(bundle / 'EVALSPEC.private.jsonl'),
        known_requests_path=str(prior / 'DETERMINISTIC_32_REQUESTS.private.jsonl'),
        original_controller_path=str(prior / 'CONTROLLER_INITIAL_16.private.jsonl'),
        cpu_pools_path=str(cpu / 'LEGAL_POOLS.private.jsonl'),
        baseline_path=original['baseline_path'], checkpoint_path=original['checkpoint_path'],
        source_config_path=str(source_path), controller_contract_path=str(control_path),
        latency_contract_path=str(timing_path), comparison_scope_path=str(scope_path))
    files = {p: file_sha256(p) for p in common.values()}
    for p in (resources, metadata, asset_manifest, design_path, original_plan, constrained_plan,
              cpu / 'POLICY_AND_RUNTIME_FREEZE.json', cpu / 'CPU_SUMMARY_PUBLIC.json'):
        files[str(p)] = file_sha256(p)
    baseline = R.read(original['baseline_path'])
    catalog_path = out / 'CATALOG.json'
    batches = []
    for n in range(1, 5):
        batch = out / f'batch-{n:02d}'
        batch.mkdir()
        chosen = old_proposal['task_ids'][2 * (n - 1):2 * n]
        request_scope = dict(protocol=R.PROTOCOL, task_ids=chosen, terminal_slots=R.terminal_slots(chosen),
            role_caps=R.ROLE_CAPS, max_calls=22, controller_contract_sha256=object_sha256(control),
            later_inputs='bind exact actual observations, requests and terminal inputs at runtime',
            cache_policy='disabled_for_latency_measurement', formal_reward=None)
        request_path = batch / 'REQUEST_SCOPE_PRIVATE.json'
        write_json_once(request_path, request_scope)
        initial = [dict(task_id=r['task_id'], method=r['method'], messages=r['initial_messages'],
            messages_sha256=object_sha256(r['initial_messages']),
            decode=controller_decode(dict(DECODE), r['method']), controller_contract_sha256=object_sha256(control),
            model_called=False, authorized=False)
            for r in original_controls if r['task_id'] in chosen]
        initial_path = batch / 'INITIAL_CONTROLLERS_PRIVATE.jsonl'
        write_jsonl_once(initial_path, initial)
        plan = dict(common, protocol=R.PROTOCOL, job_kind=R.JOB_KIND, base_commit=R.BASE_COMMIT,
            authorized=False, automatic_followup=False, batch_number=n,
            task_ids=chosen, task_sha256={t: object_sha256(tasks[t]) for t in chosen},
            scope_sha256=object_sha256(scope), arms=list(R.ARMS), max_calls=22,
            role_call_caps=R.ROLE_CAPS, max_model_loads=1, warmup_calls=0, automatic_retry=False,
            global_seconds=1200, load_seconds=600, request_seconds=300,
            cache_policy='disabled_for_latency_measurement', policy_elapsed_time_input=False,
            formal_reward=None, gpu_uuid=R.L.GPU, python=original['python'], model_path=original['model_path'],
            baseline_sha256=object_sha256(baseline), renderer_id=original['renderer_id'],
            controller_contract_sha256=object_sha256(control), latency_contract_sha256=object_sha256(timing),
            requests_path=str(request_path), requests_sha256=file_sha256(request_path),
            initial_controllers_path=str(initial_path), catalog_path=str(catalog_path),
            executor_root=str(executor), executor_files_sha256=executor_hashes,
            executor_inventory_sha256=object_sha256(executor_hashes),
            vendor_path=str(vendor), vendor_files_sha256=vendor_hashes,
            constraint_runtime_files_sha256=old_constraint['constraint_runtime_files_sha256'],
            files_sha256=dict(files, **{str(request_path): file_sha256(request_path), str(initial_path): file_sha256(initial_path)}),
            stop_rules=dict(controller_protocol_or_length='stop whole job, no retry',
                            terminal_length='retain technical incomplete; stop on third per job',
                            token_budget='stop that acquisition path; final G may answer with observed evidence',
                            unavailable_precommitted_hit='stop that acquisition path',
                            device_or_integrity='stop own job; do not interfere with other projects',
                            total_deadline='stop all own computation at hard deadline; preserve incomplete evidence'),
            timing_notes=['All tasks and arms run in predeclared order; zero warmup, cold first-inference flagged.',
                          'No cache reuse even when exact terminal inputs repeat; each observed latency is actual.',
                          'Worker-side first nonempty decoded text is not client-delivered or semantically qualified.',
                          'Model load and source startup are separate from resident online Agent intervals.'])
        path = batch / 'PLAN.json'
        write_json_once(path, plan)
        batches.append(dict(batch=n, label='DR'+str(n), plan_path=str(path),
            plan_object_sha256=object_sha256(plan), plan_file_sha256=file_sha256(path),
            request_scope_file_sha256=file_sha256(request_path), initial_controllers_file_sha256=file_sha256(initial_path),
            max_calls=22, model_loads_max=1, hard_seconds=1200, terminal_slots=12,
            deterministic_payloads=sum(r['task_id'] in chosen for r in known), authorized=False))
    catalog = dict(protocol=R.PROTOCOL, base_commit=R.BASE_COMMIT, authorized=False,
        scope_sha256=object_sha256(scope), tasks=8, source_pairs=4, terminal_logical_slots=48,
        max_calls=88, model_loads_max=4, total_hard_seconds=4800,
        controller_contract_sha256=object_sha256(control), latency_contract_sha256=object_sha256(timing),
        executor_inventory_sha256=object_sha256(executor_hashes), batches=batches,
        cache_policy='disabled_for_latency_measurement', new_model_calls=0,
        automatic_followup=False, formal_reward=None)
    write_json_once(catalog_path, catalog)
    for b in batches:
        path = Path(b['plan_path'])
        plan, _, _ = R.check(path)
        write_json_once(path.parent / 'APPROVAL_TEMPLATE.json', dict(protocol=R.PROTOCOL, job_kind=R.JOB_KIND,
            authorized=False, plan_sha256=object_sha256(plan), catalog_file_sha256=file_sha256(catalog_path),
            max_calls=22, max_model_loads=1, global_seconds=1200, warmup_calls=0, retry_calls=0,
            gpu_uuid=R.L.GPU, researcher='', decision_evidence='', decision_evidence_sha256=''))
        script = ['#!/usr/bin/env bash', 'set -euo pipefail',
                  'approval_file="${1:?Pass the new researcher-authorized JSON file}"',
                  'job_output="${2:?Pass a fresh data-volume output root}"',
                  'test ! -e "$job_output"', 'mkdir -p "$job_output/runtime-cache"',
                  "export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1",
                  'export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 TOKENIZERS_PARALLELISM=false',
                  'export PYTHONPATH=' + shlex.quote(str(executor / 'project/src') + ':' + str(vendor))]
        for name in ('TMPDIR','TMP','TEMP','HF_HOME','HF_HUB_CACHE','TRANSFORMERS_CACHE','XDG_CACHE_HOME',
                     'TORCH_HOME','TORCHINDUCTOR_CACHE_DIR','TRITON_CACHE_DIR','CUDA_CACHE_PATH','PYTHONPYCACHEPREFIX'):
            script.append('export ' + name + '="$job_output/runtime-cache"')
        script.append('exec ' + shlex.quote(original['python']) + ' ' +
            shlex.quote(str(executor / 'project/scripts/rl1v3/journal_pomdp_dynamic_run.py')) +
            ' run --plan ' + shlex.quote(str(path)) + ' --approval "$approval_file" --run-root "$job_output"')
        (path.parent / 'RUN_AFTER_NEW_APPROVAL.sh').write_text('\n'.join(script) + '\n')
    return dict(catalog, catalog_file_sha256=file_sha256(catalog_path))
