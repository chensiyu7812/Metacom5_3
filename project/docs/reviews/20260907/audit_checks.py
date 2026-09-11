"""Read-only research audit. No LLM calls, response quality judgement, or ratings ingestion.

Run with PYTHONNOUSERSITE=1 and the existing paper1-py311 Python environment.
Outputs aggregate metadata only; original study files are never modified.
"""
from pathlib import Path
from collections import Counter, defaultdict
from decimal import Decimal
import hashlib
import json
import sys

ROOT = Path('/opt/tokkio-data0/tokkio_projects/Metacom5_3')
P = ROOT / 'project'
A = P / 'data/paper1_authority'
OUT = Path(__file__).parent
sys.path.insert(0, str(P / 'src'))

def read(p): return json.loads(Path(p).read_text())
def rows(p): return [json.loads(s) for s in Path(p).read_text().splitlines() if s]
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def text_sha(s): return hashlib.sha256(s.encode()).hexdigest()
def canonical(o): return json.dumps(o, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

evidence = {'audit_date': '2026-09-07', 'scope': 'current public-only Paper-1, metadata and implementation checks'}
checks = {}
def check(name, condition): checks[name] = bool(condition)

base_path = A / 'paper1_pairwise_teacher_base_pair_preflight_20260904_v1.jsonl'
pres_path = A / 'paper1_pairwise_teacher_presentation_plan_20260904_v1.jsonl'
key_path = A / 'paper1_pairwise_teacher_blind_key_20260904_v1.jsonl'
gen_path = A / 'paper1_pairwise_teacher_local_generation_result_20260904_v1.json'
binding_path = A / 'paper1_pairwise_teacher_generator_request_binding_20260904_v1.json'
sheet_manifest_path = A / 'paper1_pairwise_teacher_human_sheet_manifest_20260904_v1.json'
base, presentations, keys = rows(base_path), rows(pres_path), rows(key_path)
gen, binding, sheets_manifest = read(gen_path), read(binding_path), read(sheet_manifest_path)
base_by_id = {x['base_pair_id']: x for x in base}
key_by_id = {x['presentation_id']: x for x in keys}
pair_map = {x['base_pair_id']: x for x in gen['base_pair_response_map']}
check('80_unique_base_pairs', len(base) == len(base_by_id) == len(pair_map) == 80)
check('96_unique_presentations', len(presentations) == len({x['presentation_id'] for x in presentations}) == len(key_by_id) == 96)
check('16_reverse_presentations', sum(x['reverse_duplicate'] for x in presentations) == 16)
hash_sources = {'base_pairs': base_path, 'presentations': pres_path, 'blind_key': key_path,
                'instrument': A / 'paper1_pairwise_teacher_human_instrument_20260904_v1.json', 'local_generation_result': gen_path}
for name, p in hash_sources.items(): check('sheet_source_hash_' + name, sha(p) == sheets_manifest['source_sha256'][name])
check('generation_binding_hash', sha(binding_path) == gen['request_binding_sha256'])
private_path = P / binding['private_request_manifest']['path']
check('private_request_file_hash', sha(private_path) == binding['private_request_manifest']['sha256'] == gen['private_request_manifest_sha256'])
requests = rows(private_path)
request_by_id = {r['request_id']: r for r in requests}
tracked_requests = {r['request_id']: r for r in binding['request_identities']}
cache = {r['request_id']: read(P / gen['private_success_cache']['path'] / (r['request_id'] + '.json')) for r in requests}
check('142_unique_requests_and_caches', len(requests) == len(request_by_id) == len(cache) == len(tracked_requests) == 142)
check('all_request_and_cache_hashes', all(text_sha(canonical(r['request'])) == r['request_sha256'] == cache[r['request_id']]['request_sha256'] == tracked_requests[r['request_id']]['request_sha256'] for r in requests))
check('all_response_text_hashes', all(text_sha(c['accepted_text']) == c['accepted_response_sha256'] and text_sha(c['raw_text']) == c['raw_response_sha256'] for c in cache.values()))
check('all_nonempty_accepted_responses', all(c['accepted_text'].strip() for c in cache.values()))
check('pair_map_response_hashes', all(pair[arm]['response_sha256'] == cache[pair[arm]['request_id']]['accepted_response_sha256'] for pair in pair_map.values() for arm in ('ON', 'OFF')))
check('focal_pair_identity', all(all(request_by_id[pair[arm]['request_id']]['target_id'] == base_by_id[bid]['target_id'] and request_by_id[pair[arm]['request_id']]['task'] == base_by_id[bid]['task'] and request_by_id[pair[arm]['request_id']]['arm'] == arm for arm in ('ON', 'OFF')) for bid, pair in pair_map.items()))
decode_keys = ('temperature', 'max_output_tokens', 'model', 'model_revision', 'chat_template_sha256', 'model_artifact_identity_sha256')
check('matched_pair_decoding', all(all(request_by_id[pair['ON']['request_id']]['request'][k] == request_by_id[pair['OFF']['request_id']]['request'][k] for k in decode_keys) for pair in pair_map.values()))
sheet_items = {}
for rater, meta in sheets_manifest['sheets'].items():
    sheet = read(P / meta['path'])
    check(rater + '_original_sheet_hash', sha(P / meta['path']) == meta['sha256'])
    items = {x['presentation_id']: x for x in sheet['items']}
    sheet_items[rater] = items
    check(rater + '_complete_blank_ids', len(items) == 96 and set(items) == set(key_by_id) and all(x['verdict'] is None and x['rationale'] is None for x in items.values()))
    check(rater + '_responses_match_blind_key', all(x['response_' + side] == cache[pair_map[key_by_id[pid]['base_pair_id']][key_by_id[pid][side + '_arm']]['request_id']]['accepted_text'] for pid, x in items.items() for side in ('A', 'B')))
    check(rater + '_no_direct_unblinding_fields', all(set(x) == {'item_number','presentation_id','task','task_input','reference_material','response_A','response_B','verdict','rationale'} for x in items.values()))
check('same_AB_content_both_raters', all({k:v for k,v in sheet_items['RATER_A'][pid].items() if k != 'item_number'} == {k:v for k,v in sheet_items['RATER_B'][pid].items() if k != 'item_number'} for pid in key_by_id))
check('different_rater_orders', list(sheet_items['RATER_A']) != list(sheet_items['RATER_B']))
for p in presentations:
    if not p['reverse_duplicate']: continue
    other = next(q for q in presentations if q['base_pair_id'] == p['base_pair_id'] and not q['reverse_duplicate'])
    x, y = sheet_items['RATER_A'][p['presentation_id']], sheet_items['RATER_A'][other['presentation_id']]
    check('reverse_swap_' + p['presentation_id'], x['response_A'] == y['response_B'] and x['response_B'] == y['response_A'] and x['task_input'] == y['task_input'] and x['reference_material'] == y['reference_material'])
finish = Counter(f"{x['task']}:{x['arm']}:{x['finish_reason']}" for x in cache.values())
check('finish_counts_match_result', dict(finish) == gen['execution']['finish_reason_counts'])
usage = {k: sum(x['usage'][k] for x in cache.values()) for k in ('prompt_tokens','completion_tokens','total_tokens')}
check('usage_matches_result', usage == gen['usage'])
evidence['teacher_reference'] = {
    'base_by_task': dict(Counter(x['task'] for x in base)),
    'presentations_by_task': dict(Counter(x['task'] for x in presentations)),
    'base_by_head': dict(Counter(x['head'] for x in base)),
    'independent_target_counts_by_task': {t: len({x['target_id'] for x in base if x['task']==t}) for t in ('ESC','QA','Summary','DG')},
    'finish_reason_counts': dict(sorted(finish.items())), 'usage': usage,
    'length_finished_total': sum(x['finish_reason'] == 'length' for x in cache.values()),
    'pair_count_with_any_length_finish': sum(any(cache[p[arm]['request_id']]['finish_reason']=='length' for arm in ('ON','OFF')) for p in pair_map.values()),
    'output_caps_by_task': {t: sorted({x['request']['max_output_tokens'] for x in requests if x['task']==t}) for t in ('ESC','QA','Summary','DG')},
    'observed_original_sheet_ratings': 0,
    'same_response_hash_base_pairs': sum(p['ON']['response_sha256']==p['OFF']['response_sha256'] for p in pair_map.values()),
}

ledger = rows(P / 'outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl')
terminal = {r['reservation_id']:r for r in ledger}
opening = Decimal(ledger[0]['opening_cost_usd'])
stage_totals = defaultdict(Decimal)
for r in terminal.values(): stage_totals[r['stage']] += Decimal(r['actual_cost_usd'] if r['event']=='SETTLED' else r['maximum_cost_usd'])
accounted = opening + sum(stage_totals.values())
settled = [r for r in terminal.values() if r['event']=='SETTLED']
unknown = [r for r in settled if r.get('outcome') != 'SUCCEEDED']
evidence['budget'] = {'event_rows':len(ledger), 'reservations':len(terminal), 'unsettled_reservations':sum(r['event']!='SETTLED' for r in terminal.values()),
    'opening_cost_usd':str(opening), 'accounted_cost_usd':str(accounted), 'remaining_usd':str(Decimal('50')-accounted),
    'stage_totals_usd':{k:str(v) for k,v in stage_totals.items()},
    'settlement_outcomes':dict(Counter(r.get('outcome') for r in settled)),
    'non_success_settlement_accounting':dict(Counter(r.get('accounting') for r in unknown)),
    'non_success_settlement_cost_usd':str(sum((Decimal(r['actual_cost_usd']) for r in unknown), Decimal('0'))),
    'gemini_events':sum('gemini' in str(r.get('model','')).lower() for r in ledger)}
check('budget_accounted_total_matches_claim', accounted == Decimal('1.44178151'))
dg = read(A / 'paper1_pairwise_teacher_dg_first_turn_result_20260904_v1.json')
dg_rows=dg['execution']['responses']
dg_cost=sum((Decimal(x['usage']['prompt_tokens'])*Decimal('2.5')+Decimal(x['usage']['completion_tokens'])*Decimal('10'))/Decimal('1000000') for x in dg_rows)
check('DG_seeker_cost_recomputed', dg_cost==Decimal('0.1013300'))
check('DG_seeker_count',len(dg_rows)==8)

raw_path=P / 'data/external/evo_emo.json'
check('public_ESMemEval_sha256', sha(raw_path)=='f30698e87fddaeff51270a666c654da604f487a3456ec60d2b6ae08a6fecd420')
check('public_ESConv_sha256', sha(P/'data/external/ESConv.json')=='aa0556c5b330562ba009c1cd5137486bfa2a7255f33225a6524cd58f7efdd9af')
raw=read(raw_path)
evidence['public_data_counts']={'owners':len(raw),'sessions':sum(len(u['dialog_history']) for u in raw),'QA':sum(len(g['questions']) for u in raw for g in u['questions']), 'Summary':sum(len(u['summaries']) for u in raw),'DG':sum(len(u['subsequent_topics']) for u in raw)}
sessions=rows(P/'data/paper1_public_memory/es_memeval_public_multi_view_session_results_v1.jsonl')
units=[unit for s in sessions for unit in s['accepted_units']]
evidence['compiler']={'sessions':len(sessions),'owners':len({s['owner_id'] for s in sessions}),'accepted_units':len(units),'compiler_versions':dict(Counter(s['compiler_version'] for s in sessions)),
    'schema_rejection_records':sum(len(s['schema_rejections']) for s in sessions),'semantic_rejection_records':sum(len(s['rejected_decisions']) for s in sessions)}
from metacom_pm.paper1.data.memory_source import load_sanitized_runtime_users, enumerate_targets
from metacom_pm.paper1.multi_view_memory import load_accepted_multi_view_units
users=load_sanitized_runtime_users(P/'data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json')
validated=load_accepted_multi_view_units(P/'data/paper1_public_memory/es_memeval_public_multi_view_session_results_v1.jsonl', users=users)
check('all_2236_units_load_with_source_validation', len(validated)==2236)
targets=enumerate_targets(users)
evidence['target_cutoffs']={'target_count':len(targets), 'unique_cutoffs_per_owner':{u.owner_id:sorted({t.cutoff_rank for t in targets if t.owner_id==u.owner_id}) for u in users}}
fold_path=P/'data/paper1_public_memory/es_memeval_public_outer_fold_assignments_k5_seed0_v1.jsonl'
folds=rows(fold_path)
by_component=defaultdict(set)
for f in folds: by_component[f['group_component_id']].add(f['outer_fold'])
check('no_exact_component_crosses_outer_folds', all(len(v)==1 for v in by_component.values()))
check('1586_unique_fold_targets',len(folds)==len({r['target_id'] for r in folds})==1586)
memory_teacher_targets={r['target_id'] for r in base if r['task']!='ESC'}
touched=[f for f in folds if f['target_id'] in memory_teacher_targets]
touched_components={f['group_component_id'] for f in touched}
expanded=[f for f in folds if f['group_component_id'] in touched_components]
evidence['teacher_fold_overlap']={'teacher_unique_memory_targets':len(memory_teacher_targets),'targets_in_frozen_outer_fold_manifest':len(touched),
    'direct_touched_target_counts_by_fold':dict(Counter(r['outer_fold'] for r in touched)),
    'touched_exact_components':len(touched_components),'targets_in_touched_components':len(expanded),
    'expanded_target_counts_by_task':dict(Counter(r['task_type'] for r in expanded))}

rs_catalog=rows(P/'data/paper1_public_rs/esconv_rs_exact_canonical_treatments_v1.jsonl')
rs_by_id={r['treatment_id']:r for r in rs_catalog}
rs_top8=rows(P/'data/paper1_public_rs/esconv_rs_canonical_bge_top8_v1.jsonl')
check('RS_all_exact_treatment_content_hashes', all(text_sha(r['rendered_card_text'])==r['rendered_card_text_sha256'] for r in rs_catalog))
check('RS_11883_states_all_eight_distinct', len(rs_top8)==len({r['state_id'] for r in rs_top8})==11883 and all(len(r['ranked_treatments'])==len({t['treatment_id'] for t in r['ranked_treatments']})==8 for r in rs_top8))
check('RS_95064_retrievals_exclude_current_dialogue_union', all(r['source_dialogue_id'] not in rs_by_id[t['treatment_id']]['source_dialogue_ids'] for r in rs_top8 for t in r['ranked_treatments']))
check('RS_stored_top8_order', all(r['ranked_treatments']==sorted(r['ranked_treatments'],key=lambda t:(-t['cosine_similarity'],t['treatment_id'])) for r in rs_top8))
evidence['RS']={'canonical_treatments':len(rs_catalog),'decision_states':len(rs_top8),'retrieval_assignments_checked':sum(len(r['ranked_treatments']) for r in rs_top8),'state_source_splits':dict(Counter(r['source_split'] for r in rs_top8))}

# This is an arithmetic counterexample, not a study outcome or a synthetic
# longitudinal input. It shows that summing marginal p95s is no upper bound.
tails=[[60000 if h*4 <= i < (h+1)*4 else 0 for i in range(100)] for h in range(3)]
def p95(xs): return sorted(xs)[94]
evidence['latency_p95_counterexample']={'description':'three disjoint 4% tail events; constant base 5000 ms',
    'marginal_p95_ms':[p95(x) for x in tails],
    'base_plus_sum_p95_ms':5000+sum(p95(x) for x in tails),
    'actual_bundle_p95_ms':p95([5000+sum(t[i] for t in tails) for i in range(100)]),
    'is_empirical_project_outcome':False}

from metacom_pm.paper1.evaluation.effect_coding import SummaryEffectSurface, code_summary_effect
from metacom_pm.paper1.contracts import PairedOutcome
def summary(n,llm):return SummaryEffectSurface(rouge_1=0,rouge_2=0,rouge_l=0,reference_events=2,generated_events=2,recalled_events=n,llm_score=llm)
reproductions=[]
for name,on,off in [('event_tie_llm_direction',summary(1,3),summary(1,2)),('event_direction_llm_opposite',summary(2,2),summary(1,3))]:
    result=code_summary_effect(on,off,pairwise_verdict=PairedOutcome.EQUIVALENT)
    reproductions.append({'case':name,'pairwise_verdict':'equivalent','actual_outcome':result.outcome.value,'reason':result.reason_code,'contract_common_equivalence_expectation':'equivalent'})
evidence['summary_equivalence_contract_reproductions']=reproductions
from metacom_pm.paper1.evaluation.pairwise_teacher import parse_pairwise_teacher_response
duplicate_keys='{"verdict":"A_better","verdict":"B_better","rationale":"conflicting keys"}'
try: evidence['duplicate_JSON_key_parser']={'input_verdict_keys':['A_better','B_better'],'accepted_verdict':parse_pairwise_teacher_response(duplicate_keys).verdict}
except Exception as ex:evidence['duplicate_JSON_key_parser']={'rejected':type(ex).__name__}

evidence['checks']=checks
evidence['check_summary']={'passed':sum(checks.values()),'failed':[k for k,v in checks.items() if not v]}
(OUT/'evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in evidence.items() if k not in ('checks','target_cutoffs')},ensure_ascii=False,indent=2))
