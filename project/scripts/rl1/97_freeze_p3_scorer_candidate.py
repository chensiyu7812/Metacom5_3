#!/usr/bin/env python3
"""Freeze the initial P3 candidate and finite jobs; do not open human labels."""
import importlib.metadata
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.judge_completion import VERSION, RUBRIC, RUBRIC_ID, RECHECK_INSTRUCTION
from metacom_pm.rl1.schema import digest

ROOT = PROJECT / 'outputs/pm_rl1/completion_20260930_v2/P3'
OUT = ROOT / 'candidate_v1'
MODEL = Path('/opt/tokkio-data0/tokkio_models/paper1_judges/qwen35_9b')


def read(p):
    return json.loads(p.read_text())


def save(p, obj):
    with p.open('x') as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')


def main():
    if (OUT / 'candidate_freeze.json').exists():
        raise RuntimeError('initial candidate already frozen')
    OUT.mkdir(exist_ok=True)
    packet = ROOT / 'calibration'
    pf = read(packet / 'packet_freeze.json')
    for name, sha in pf['files'].items():
        assert sha256_file(packet / name) == sha, name
    pairs = read(packet / 'pairs_private.json')['pairs']
    pool = read(ROOT / 'common_evidence/evidence_pool_private.json')
    jobs = {}
    refs = []
    for p in pairs:
        for side, reply in enumerate(p['replies']):
            evidence = pool[p['prefix_identity']]
            key = digest([digest(evidence), reply])
            group = p['group']
            job = dict(job_id=key, group=group, prefix_identity=p['prefix_identity'],
                evidence=evidence, reply=reply, seed=int(digest(['p3-primary-seed', digest(evidence)])[:8], 16),
                draw_id='primary', repeat=False, recheck=False)
            if key in jobs:
                assert jobs[key]['group'] == group, 'cross-partition response collision'
            jobs[key] = job
            refs.append(dict(pair_id=p['pair_id'], side=side, job_id=key, kind=p['kind'], group=group))
    # Exactly twelve single-response repeats, selected before scores: both sides
    # of four severe validation controls plus four hash-selected natural replies.
    severe_ids = {r['job_id'] for r in refs if r['group'] == 'validation'
        and next(p for p in pairs if p['pair_id'] == r['pair_id']).get('control_type') in
        ('identity', 'subject', 'currentness', 'intent_to_result')}
    natural_ids = sorted({r['job_id'] for r in refs if r['group'] == 'validation' and r['kind'] == 'natural'},
        key=lambda x: digest(['p3-repeat-natural', x]))[:4]
    repeat_ids = sorted(severe_ids | set(natural_ids))
    assert len(repeat_ids) == 12
    repeats = [dict(jobs[key], job_id=digest(['p3-independent-repeat', key]),
        primary_job_id=key, group='repeat', seed=(jobs[key]['seed'] + 104729) % (2**32),
        draw_id='independent-repeat-1', repeat=True) for key in repeat_ids]
    probe = min((j for j in jobs.values() if j['group'] == 'development'),
                key=lambda j: digest(['p3-recheck-path-probe', j['job_id']]))
    probe = dict(probe, job_id=digest(['p3-recheck-probe', probe['job_id']]),
        primary_job_id=probe['job_id'], group='recheck_probe', recheck=True,
        draw_id='full-source-recheck-1')
    context = read(MODEL / 'config.json')['text_config']['max_position_embeddings']
    protocol = dict(version=VERSION, status='INITIAL_CANDIDATE_NOT_MEASUREMENT_QUALIFICATION',
        packet_identity=pf['packet_identity'], semantic_revisions_after_human_labels=0,
        rubric=RUBRIC, rubric_identity=RUBRIC_ID, recheck_instruction=RECHECK_INSTRUCTION,
        model=str(MODEL), model_files={p.name: sha256_file(p) for p in sorted(MODEL.iterdir())
            if p.is_file() and p.suffix in ('.json', '.safetensors', '.jinja', '.txt')},
        packages={p: importlib.metadata.version(p) for p in ('torch', 'transformers', 'vllm')},
        decode=dict(thinking=True, temperature=1., top_p=.95, top_k=20, min_p=0.,
            presence_penalty=1.5, repetition_penalty=1.),
        runtime=dict(dtype='bfloat16', native_context=context, serving_context=context,
            output_token_cap=None, technical_timeout_seconds=900, repetition_width=32,
            repetition_repeats=4, concurrency=4, gpu_memory_utilization=.88,
            max_num_batched_tokens=4096, enforce_eager=True, enable_prefix_caching=False,
            language_model_only=True, engine_seed=20261001, reasoning_parser='qwen3'),
        technical_set='All distinct primary single replies in the forty active pairs; duplicates reuse the exact first measurement.',
        technical_smoke='First four development jobs by fixed hash. If any has technical/parse failure stop before the remaining jobs; preserve every attempt.',
        recovery='One fixed first-stage technical recovery with identical messages/schema/decode/seed and a distinct attempt ID. Never semantic score selection.',
        semantic_recheck=dict(trigger='semantic_uncertainty only; same complete evidence and rubric',
            max_per_reply=1, max_total=96, first_development_probe=probe['job_id'],
            result_rule='Use the sole recheck if scored; otherwise remain pending. Probe does not replace its primary score.'),
        qualification=read(PROJECT / 'docs/pm_rl1_completion_20260930_v2/execution_contract.json')['measurement'],
        human_protocol='Forty pairs once per independent human; development-only decryption first; at most one semantic revision before final measurement freeze and validation access.',
        validation_scoring='Do not run validation/repeat/reserve before final measurement freeze after development labels.',
        blind_fields='Only same-prefix full evidence, reply and indexed reply units; no method/executor/cost/plan/seed exposed in model messages.',
        reward_qualified=False)
    protocol['identity'] = digest(protocol)
    save(OUT / 'protocol.json', protocol)
    ordered = sorted(jobs.values(), key=lambda j: digest(['p3-job-order', j['job_id']]))
    save(OUT / 'jobs_private.json', ordered + repeats + [probe])
    save(OUT / 'pair_score_map_private.json', refs)
    source_paths = [Path(__file__), PROJECT / 'scripts/rl1/98_run_p3_candidate.py',
        *[PROJECT / f'src/metacom_pm/rl1/{s}.py' for s in ('judge_completion', 'judge_explicit',
            'judge_flat', 'judge_scoped', 'judge_indexed', 'judge', 'evidence', 'schema', 'cache')],
        packet / 'packet_freeze.json', ROOT / 'common_evidence/input_freeze.json']
    save(OUT / 'candidate_freeze.json', dict(protocol_identity=protocol['identity'],
        files={p.name: sha256_file(p) for p in OUT.iterdir() if p.is_file()},
        source_files={str(p.relative_to(PROJECT)): sha256_file(p) for p in source_paths}))
    print(json.dumps(dict(protocol_identity=protocol['identity'], distinct_primary_jobs=len(jobs),
        repeats=len(repeats), recheck_probes=1, max_base_calls_with_reserve=len(jobs)+12,
        development_jobs=sum(j['group']=='development' for j in ordered)), ensure_ascii=False))


if __name__ == '__main__':
    main()
