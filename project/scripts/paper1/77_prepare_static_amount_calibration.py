#!/usr/bin/env python3
"""Prepare a finite, sampled QA/Summary amount-calibration execution package.

No generation or paid scoring. Exact Generator inputs are materialized now;
official scorer templates are bound now and prediction text is filled later.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import canonical_json, iter_jsonl, read_json, sha256_file, sha256_text, stable_hex, write_json, write_jsonl
from metacom_pm.paper1.amount_calibration import sample_static_targets
from metacom_pm.paper1.api_budget import CumulativePaper1ApiBudgetLedger
from metacom_pm.paper1.candidates import compile_multi_view_candidate_bundle
from metacom_pm.paper1.contracts import Head
from metacom_pm.paper1.data.memory_source import enumerate_targets, load_sanitized_runtime_users
from metacom_pm.paper1.evaluation.static_official_templates import extract_templates, render_templates
from metacom_pm.paper1.execution.packing import RankedCandidate, pack_ranked_prefix
from metacom_pm.paper1.execution.rq2_prompts import build_static_rq2_request
from metacom_pm.paper1.llama_tokenizer import build_llama_token_counter
from metacom_pm.paper1.multi_view_memory import load_accepted_multi_view_units

MODEL_DIR = Path('/opt/tokkio-data0/tokkio_models/huggingface/hub/models--NousResearch--Meta-Llama-3.1-8B-Instruct/snapshots/d10aef7999a2b5ba950ab3974312feeedbfe0b77')
PROTOCOL = 'paper1-static-amount-calibration-preparation-20260917-v1'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=PROJECT / 'outputs/paper1_calibration/static_sample_20260917_v1')
    args = parser.parse_args()
    source = PROJECT / 'data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json'
    unit_path = PROJECT / 'data/paper1_public_memory/es_memeval_public_multi_view_session_results_v1.jsonl'
    rank_path = PROJECT / 'data/paper1_public_memory/es_memeval_public_active_multi_view_bge_top8_v1.jsonl'
    fold_path = PROJECT / 'data/paper1_public_memory/es_memeval_public_outer_fold_assignments_k5_seed0_v1.jsonl'
    raw_path = PROJECT / 'data/external/evo_emo.json'
    official_paths = {'qa': PROJECT / 'outputs/vendor_es_memeval/src/lib/qa/qa_experiment.py',
                      'summary': PROJECT / 'outputs/vendor_es_memeval/src/lib/sum/sum_experiment.py'}
    frame = list(iter_jsonl(fold_path))
    selected = sample_static_targets(frame, seed=0)
    assert len(selected) == 148 and Counter(r['task_type'] for r in selected) == {'qa': 85, 'summary': 63}
    args.out.mkdir(parents=True, exist_ok=True)
    # Persist sample identities before binding evaluator-only references.
    write_jsonl(args.out / 'selected_targets.jsonl', selected)
    users = load_sanitized_runtime_users(source)
    targets = {t.target_id: t for t in enumerate_targets(users)}
    units = load_accepted_multi_view_units(unit_path, users=users)
    by_owner = defaultdict(list)
    for unit in units:
        by_owner[unit.owner_id].append(unit)
    counter = build_llama_token_counter(MODEL_DIR / 'tokenizer.json')
    representative = {t.owner_id: t for t in targets.values()}
    bundles = {u.owner_id: compile_multi_view_candidate_bundle(tuple(by_owner[u.owner_id]), u,
               representative[u.owner_id], token_counter=counter) for u in users}
    candidate_map = {(owner, head.value, c.candidate_id): c for owner, bundle in bundles.items()
                     for head, candidates in bundle.items() for c in candidates}
    rankings = {(r['target_id'], r['head']): r for r in iter_jsonl(rank_path)}
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR), local_files_only=True)
    generator_config = {
        'model': 'meta/llama-3.1-8b-instruct', 'revision': MODEL_DIR.name,
        'dtype': 'bfloat16', 'backend': 'Transformers SDPA', 'concurrency': 1,
        'temperature': 0, 'do_sample': False, 'normal_stop': 'EOS/EOT',
        'task_output_token_cap': None, 'native_context_tokens': 131072,
        'technical_timeout_seconds': 300, 'exact_cycle_guard': {'block_tokens': 32, 'repeats': 4},
        'incomplete_is_not_semantic_uncertain': True, 'seed': 0,
        'tokenizer_json_sha256': sha256_file(MODEL_DIR / 'tokenizer.json'),
        'tokenizer_config_sha256': sha256_file(MODEL_DIR / 'tokenizer_config.json'),
        'chat_template_sha256': sha256_text(tokenizer.chat_template)}
    config_hash = sha256_text(canonical_json(generator_config))
    requests, design = [], []
    ordered = sorted(selected, key=lambda r: stable_hex(PROTOCOL, 'schedule', 0, r['target_id']))
    for block, row in enumerate(ordered):
        target = targets[row['target_id']]
        conditions = [(None, 0)] + [(h, k) for h in (Head.MP, Head.ME, Head.MS) for k in (1, 2, 3, 4)]
        conditions.sort(key=lambda hk: stable_hex(PROTOCOL, 'within', target.target_id, str(hk)))
        for index, (head, k) in enumerate(conditions):
            resources, ids, hashes, resource_tokens = (), [], [], 0
            if head is not None:
                ranking = rankings[(target.target_id, head.value)]
                ranked = []
                for item in ranking['ranked_candidates']:
                    c = candidate_map[(target.owner_id, head.value, item['candidate_id'])]
                    assert c.lineage.content_sha256 == item['candidate_content_sha256']
                    ranked.append(RankedCandidate(candidate=c, similarity=item['bge_cosine_similarity']))
                packed = pack_ranked_prefix(head=head, ranked=ranked, k=k, target_owner_id=target.owner_id, token_counter=counter)
                assert packed.realized_k == k
                resources = (packed.envelope,)
                ids = [r.candidate.candidate_id for r in ranked[:k]]
                hashes = [r.candidate.lineage.content_sha256 for r in ranked[:k]]
                resource_tokens = packed.rendered_resource_tokens
            old = build_static_rq2_request(task_type=target.task_type, question=target.visible_query_text or '', resources=resources)
            messages = [m.model_dump(mode='json') for m in old.messages]
            token_ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True)
            assert len(token_ids) < generator_config['native_context_tokens']
            request_hash = sha256_text(canonical_json({'generator_config_sha256': config_hash, 'messages': messages}))
            request_id = 'amount_gen_' + stable_hex(PROTOCOL, target.target_id, head.value if head else 'shared_OFF', k, request_hash, n=24)
            record = {'request_id': request_id, 'request_sha256': request_hash, 'generator_config_sha256': config_hash,
                      'target_id': target.target_id, 'task': target.task_type.value,
                      'owner_id': row['owner_id'], 'outer_fold': row['outer_fold'], 'group_component_id': row['group_component_id'],
                      'analysis_weight': row['analysis_weight'], 'inclusion_probability': row['inclusion_probability'],
                      'head': head.value if head else None, 'k': k, 'messages': messages,
                      'input_tokens': len(token_ids), 'rendered_resource_tokens': resource_tokens,
                      'candidate_ids': ids, 'candidate_content_sha256': hashes,
                      'microblock_index': block, 'within_microblock_index': index}
            requests.append(record)
            for analytical_head in ([head.value] if head else ['MP', 'ME', 'MS']):
                design.append({key: record[key] for key in ['request_id','target_id','task','owner_id','outer_fold','group_component_id','analysis_weight','k','input_tokens']} | {'head': analytical_head})
    assert len(requests) == 1924 and len(design) == 2220
    write_jsonl(args.out / 'generator_requests.jsonl', requests)
    write_jsonl(args.out / 'analytical_design.jsonl', design)
    write_json(args.out / 'generator_config.json', generator_config)
    refs = {}
    for u in read_json(raw_path):
        owner = str(u['id'])
        for group in u['questions']:
            for item in group['questions']:
                refs[f"{owner}::{group['id']}::{item['idx']}"] = str(item['answer'])
        for item in u['summaries']:
            refs[f"{owner}::summary::{item['idx']}"] = str(item['answer'])
    evaluator_inputs = [{'target_id': r['target_id'], 'task': r['task_type'],
                         'question': targets[r['target_id']].visible_query_text, 'gold': refs[r['target_id']]} for r in selected]
    write_jsonl(args.out / 'evaluator_inputs.jsonl', evaluator_inputs)
    templates = {task: extract_templates(path, task=task) for task, path in official_paths.items()}
    write_json(args.out / 'official_scorer_templates.json', templates)
    scorer_config = {'model': 'gpt-4o-2024-11-20', 'official_alias': 'gpt-4o', 'temperature': 'OMITTED_AS_UPSTREAM',
                     'max_completion_tokens': 'OMITTED_AS_UPSTREAM', 'provider_max_output_tokens': 16384,
                     'context_tokens': 128000, 'automatic_SDK_retries': 0, 'project_retry_max': 1,
                     'parser': {'qa': 'upstream first regex [0-2]', 'summary': 'upstream json_repair + integer count formulas'},
                     'source_sha256': {k: sha256_file(p) for k, p in official_paths.items()},
                     'new_paid_execution_authorized': False}
    write_json(args.out / 'scorer_config.json', scorer_config)
    ref_map = {r['target_id']: r for r in evaluator_inputs}
    import tiktoken
    enc = tiktoken.encoding_for_model(scorer_config['model'])
    fixed_input = Counter()
    scorer_slots = []
    for r in requests:
        ref = ref_map[r['target_id']]
        messages = render_templates(templates[r['task']], question=ref['question'], gold=ref['gold'], prediction='')
        # Deliberately conservative chat-framing allowance; generated answer still unknown.
        base = 32 + sum(32 + len(enc.encode(m['content'])) for m in messages)
        fixed_input[r['task']] += base
        scorer_slots.append({'request_id': r['request_id'], 'target_id': r['target_id'], 'task': r['task'],
                             'known_input_token_estimate_excluding_prediction': base,
                             'prediction_source': 'natural-end Generator response; no truncated substitute',
                             'payload_status': 'AWAITING_GENERATED_PREDICTION'})
    write_jsonl(args.out / 'scorer_slots.jsonl', scorer_slots)
    counts = Counter(r['task'] for r in requests)
    scenarios = []
    for name, answer_tokens, qa_out, summary_out in [('short',256,8,512),('central',512,8,1024),('long',1024,16,2048)]:
        inputs = sum(fixed_input.values()) + len(requests)*answer_tokens
        outputs = counts['qa']*qa_out + counts['summary']*summary_out
        scenarios.append({'scenario': name, 'assumed_mean_answer_tokens_in_scorer_encoding': answer_tokens,
                          'assumed_QA_judge_output_tokens': qa_out,'assumed_Summary_judge_output_tokens': summary_out,
                          'first_attempt_estimate_usd': round((inputs*2.5 + outputs*10)/1e6,6),
                          'assumptions_not_token_caps': True})
    ledger = CumulativePaper1ApiBudgetLedger(PROJECT / 'outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl')
    lengths = [r['input_tokens'] for r in requests]
    report = {'protocol': PROTOCOL, 'status': 'PREPARED_NO_GENERATION_NO_PAID_CALLS',
              'sample_targets': len(selected), 'targets_by_task': dict(Counter(r['task_type'] for r in selected)),
              'owners': len({r['owner_id'] for r in selected}), 'outer_folds': sorted({r['outer_fold'] for r in selected}),
              'sampling': 'one component then one target per task/owner/fold, fixed seed 0, inverse inclusion weights',
              'generator_calls': len(requests), 'nominal_official_scorer_calls': len(scorer_slots),
              'scorer_calls_by_task': dict(counts), 'analytical_rows_OFF_reused_across_heads': len(design),
              'generator_input_tokens_min_median_max': [min(lengths),statistics.median(lengths),max(lengths)],
              'max_exact_resource_tokens_by_head': {h:max(r['rendered_resource_tokens'] for r in requests if r['head']==h) for h in ['MP','ME','MS']},
              'per_heldout_fold_training_side_sample': {str(f):dict(Counter(r['task_type'] for r in selected if r['outer_fold']!=f)) for f in range(5)},
              'cost_scenarios': scenarios, 'proposed_stage_hard_cap_including_retries_usd':15,
              'stage_cap_is_not_guaranteed_full_batch_cost': True,
              'budget_execution': 'Sequential worst-case reservation for each actual request and full provider output allowance; stop before next reservation exceeds stage/cumulative cap. Never shorten an answer to fit cost.',
              'current_accounted_Paper1_API_usd': str(ledger.accounted_cost_usd), 'current_remaining_Paper1_API_usd': str(ledger.remaining_usd),
              'price_snapshot': {'date':'2026-09-17','source':'https://developers.openai.com/api/docs/pricing','standard_input_per_million':2.5,'standard_output_per_million':10,'cached_discount_assumed':False},
              'price_estimates_depend_on_unobserved_output_lengths':True, 'calibration_outcomes':0,'formal_outcomes':0,'PM_training_runs':0,
              'not_in_this_static_batch':['RS multi-round calibration','DG live-seeker calibration','formal effect labels','PM training'],
              'sources':{str(p.relative_to(PROJECT)):sha256_file(p) for p in [source,unit_path,rank_path,fold_path,raw_path,*official_paths.values()]},
              'package_artifacts':{p.name:sha256_file(p) for p in args.out.glob('*') if p.is_file() and p.name!='preparation_summary.json'},
              'selection': 'Fold-external one-SE on official task primary; weighted owner-cluster bootstrap, cheapest input tokens then k. Complete paired grids only; missingness disclosed; guards reviewed before freeze.'}
    write_json(args.out / 'preparation_summary.json',report)
    write_json(PROJECT / 'docs/reviews/20260917/static_amount_calibration_preparation.json',report)
    print(json.dumps({k:report[k] for k in ['sample_targets','generator_calls','generator_input_tokens_min_median_max','cost_scenarios','current_remaining_Paper1_API_usd']},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
