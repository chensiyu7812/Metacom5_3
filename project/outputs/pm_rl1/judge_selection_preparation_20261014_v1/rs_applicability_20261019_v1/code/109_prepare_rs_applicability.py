#!/usr/bin/env python3
"""Prepare one RS-only prompt intervention from the already exposed 24 rows.

CPU/tokenizer only. No full-pool enumeration, model load or account access.
"""
import argparse
import importlib.metadata
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.representation import RESOURCE_GUIDANCE_V2
from metacom_pm.rl1.representation_direct import DirectReplyRenderer
from metacom_pm.rl1.rs_applicability import (RSApplicabilityRenderer, adapt_messages,
    paired_request, INSTRUCTION, VERSION)
from metacom_pm.rl1.rs_development import read, save_once, validate_package
from metacom_pm.rl1.bound_generation import validate_and_project

BASE = PROJECT / 'outputs/pm_rl1/judge_selection_preparation_20261014_v1'
SOURCE = BASE / 'acceptability_resource_review_20261019_v1'
OUT = BASE / 'rs_applicability_20261019_v1'
P2 = PROJECT / 'outputs/pm_rl1/completion_20260930_v2/P2'
CONTEXTS = {'context_01': 111, 'context_02': 102, 'context_03': 104, 'context_04': 109}
PLANS = [[0, 0, 0, 0], [1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1], [1, 1, 1, 1]]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=OUT)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    from transformers import AutoTokenizer
    freeze = read(P2 / 'executor_freeze.json')
    runtime = freeze['primary_runtime']
    packages = {p: importlib.metadata.version(p) for p in runtime['packages']}
    if packages != runtime['packages'] or importlib.metadata.version('peft') != runtime['adapter']['peft_version']:
        raise RuntimeError('reuse the existing frozen environment plus its existing SFT vendor')
    tokenizer = AutoTokenizer.from_pretrained(runtime['model_dir'], local_files_only=True)
    if digest(tokenizer.chat_template) != runtime['chat_template_sha256']:
        raise RuntimeError('chat template changed')
    count = lambda text: len(tokenizer.encode(text, add_special_tokens=False))
    chat = lambda messages: len(tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True))
    renderer_freeze_path = P2.parent / 'P1/renderer_freeze.json'
    kwargs = dict(count_text=count, count_chat=chat,
        tokenizer_identity=read(renderer_freeze_path)['tokenizer_identity'],
        context_limit=runtime['policy']['context_limit'])
    baseline = DirectReplyRenderer(**kwargs)
    changed = RSApplicabilityRenderer(**kwargs)
    if baseline.identity != freeze['renderer_identity']:
        raise RuntimeError('baseline renderer identity drift')
    source_paths = [P2 / 'executor_freeze.json', renderer_freeze_path,
        SOURCE / 'materials/selected_existing_records.json', SOURCE / 'provenance/ACCESS_SCOPE_NOTE.json',
        PROJECT / 'docs/pm_rl1_completion_20260930_v2/execution_contract.json',
        Path(__file__), PROJECT / 'scripts/rl1/92_run_p2_common_pool.py',
        BASE / 'resume_engineering.py', BASE / 'selection.py']
    source_paths += [PROJECT / ('src/metacom_pm/rl1/' + n + '.py') for n in
        ('rs_applicability', 'rs_development', 'representation_direct', 'representation',
         'render', 'generation', 'bound_generation', 'cache')]
    source_paths += [Path(runtime['model_dir']) / n for n in
        ('config.json', 'tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json')]
    records = read(SOURCE / 'materials/selected_existing_records.json')
    expected = {(c, tuple(p)) for c in CONTEXTS for p in PLANS}
    if len(records) != 24 or {(r['context_id'], tuple(r['counts'])) for r in records} != expected:
        raise RuntimeError('selected previously exposed 24-row scope changed')
    by_key = {(r['context_id'], tuple(r['counts'])): r for r in records}
    affected, controls, jobs = [], [], []
    draw = VERSION + ':fresh-paired-greedy-seed0'
    for context, index in CONTEXTS.items():
        for plan in PLANS:
            row = by_key[context, tuple(plan)]
            if row['prefix_index'] != index or row['split'] != 'dev':
                raise RuntimeError('content whitelist mismatch')
            reqpath, rawpath = Path(row['request_path']), Path(row['raw_path'])
            if sha256_file(reqpath) != row['request_file_sha256'] or sha256_file(rawpath) != row['raw_file_sha256']:
                raise RuntimeError('original request/output changed')
            source_paths.extend([reqpath, rawpath])
            old = read(reqpath)
            validate_and_project(old, runtime['identity'])
            if old['renderer_identity'] != baseline.identity or old['provenance']['canonical_counts'] != plan:
                raise RuntimeError('old renderer/plan mismatch')
            if chat(old['messages']) != row['input_tokens']:
                raise RuntimeError('original complete tokenization changed')
            new = adapt_messages(old['messages'], plan)
            if not plan[0]:
                if new != old['messages']:
                    raise RuntimeError('unaffected control input changed')
                controls.append(dict(row_id=row['row_id'], old_request_id=old['request_id'],
                    messages_identity=digest(new), no_new_generation=True,
                    meaning='input equivalence only; old output is not a fresh intervention result'))
                continue
            old_block = old['messages'][0]['content'].split('\n\n' + RESOURCE_GUIDANCE_V2, 1)[1]
            resource_tokens = count('\n\n' + INSTRUCTION + RESOURCE_GUIDANCE_V2 + old_block)
            if resource_tokens > 2048 or chat(new) >= runtime['policy']['context_limit']:
                raise RuntimeError('complete source no longer fits; no truncation permitted')
            pair_number = len(affected)
            order = ('baseline', 'rs_applicability') if pair_number % 2 == 0 else ('rs_applicability', 'baseline')
            affected.append(dict(row_id=row['row_id'], context_id=context, counts=plan,
                old_request_id=old['request_id'], old_slot_id=row['slot_id'], order=list(order),
                old_resource_tokens=row['resource_tokens'], new_resource_tokens=resource_tokens,
                historical_generation_seconds=row['generation_seconds'],
                historical_output_tokens=row['output_tokens'],
                historical_peak_allocated_bytes=row['peak_allocated_bytes']))
            for arm in order:
                renderer_id = baseline.identity if arm == 'baseline' else changed.identity
                req = paired_request(old, arm=arm, renderer_identity=renderer_id, draw_identity=draw)
                validate_and_project(req, runtime['identity'])
                n = chat(req['messages'])
                jobs.append(dict(slot_id=row['row_id'] + '__' + arm,
                    row_id=row['row_id'], context_id=context, arm=arm,
                    old_request_id=old['request_id'], old_slot_id=row['slot_id'],
                    input_tokens=n, native_output_remainder=runtime['policy']['context_limit']-n,
                    resource_tokens=row['resource_tokens'] if arm == 'baseline' else resource_tokens,
                    request=req))
    assert len(affected) == 8 and len(controls) == 16 and len(jobs) == 16
    save_once(out / 'jobs_private.json', jobs)
    save_once(out / 'pairs.json', affected)
    save_once(out / 'unchanged_controls.json', controls)
    save_once(out / 'tokenization_receipt.json', dict(packages=packages,
        prompt_tokens=sum(j['input_tokens'] for j in jobs),
        min_native_output_remainder=min(j['native_output_remainder'] for j in jobs),
        max_resource_tokens=max(j['resource_tokens'] for j in jobs),
        truncation=False, full_input_preserved=True, tokenizer_local_only=True,
        model_loaded=False, GPU_used=False))
    protocol = dict(version='pm-rl1-rs-paired-development-v1',
        status='PREPARED_NOT_EXECUTION_AUTHORIZED', stage='rs_applicability_20261019_v1',
        intervention_version=VERSION, instruction=INSTRUCTION,
        max_generation_attempts=16, new_judge_requests=0, api_cost_usd=0,
        existing_judge_attempts=144, judge_capacity=289,
        original_STOPs_preserved=True, old_D_stage_boundary=143,
        runtime=runtime, renderer_baseline=baseline.identity, renderer_intervention=changed.identity,
        paired_draw_identity=draw, jobs_identity=digest(jobs),
        execution_dir=str(OUT / 'execution'),
        gpu_uuid='GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4',
        gpu_guard_path=str(BASE / 'resume_engineering.py'),
        guard='free>=45000MiB, utilization=0, NVIDIA process visibility, no other visible process; at most one 300s wait',
        technical_failure_policy='stop whole diagnostic on first incomplete/failed generation; no retry',
        semantic_policy='record complete raw outputs for one offline review; no automatic scoring or candidate qualification',
        environment=dict(python='/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python',
            vendor='/opt/tokkio-data0/tokkio_envs/pmrl1_sft_vendor_20260929'),
        files={n:sha256_file(out/n) for n in ('jobs_private.json', 'pairs.json',
            'unchanged_controls.json', 'tokenization_receipt.json')},
        source_files={str(p):sha256_file(p) for p in sorted(set(source_paths))},
        eligible_for_reward=False, independent_validation=False,
        claim_boundary='four exposed contexts, two source owners; eight resource conditions, not eight independent cases')
    save_once(out / 'protocol.json', protocol)
    save_once(out / 'launch_request.json', dict(protocol_identity=digest(protocol),
        status='PENDING_RESEARCHER_APPROVAL', max_generation_attempts=16,
        max_new_judge_requests=0, max_api_cost_usd=0, gpu_uuid=protocol['gpu_uuid'],
        user_instruction=None))
    validate_package(out)
    print(json.dumps(dict(prepared_pairs=8, prepared_requests=16,
        unchanged_controls=16, protocol_identity=digest(protocol), model_calls=0)))


if __name__ == '__main__':
    main()
