"""Read-only task-fit analysis of existing PM-RL1 structural exports.

Run from any directory inside the repository. No gold, G/J or GPU.
Train/dev episode text is read only for prefix-identity hashing, never exported.
Prints JSON; saving the result is left to the caller.
"""
from pathlib import Path
from collections import Counter
from itertools import product
import ast
import csv
import hashlib
import json
import statistics


def analyze(repo):
    folder = repo / 'project/outputs/pm_rl1/dataset_diagnostics_20260930_v1'
    sources = []

    def read(name, csv_file=False):
        path = folder / name
        data = path.read_bytes()
        sources.append({'path': str(path.relative_to(repo)),
                        'sha256': hashlib.sha256(data).hexdigest()})
        return list(csv.DictReader(data.decode().splitlines())) if csv_file else json.loads(data)

    prefixes = read('prefix_features.csv', True)
    capacity = read('capacity_prefix_features.csv', True)
    plans = read('reachable_plan_features.csv', True)
    memory = read('memory_unit_features.csv', True)
    sft = read('sft_features.csv', True)
    census = read('census.json')
    specs_path = repo / 'project/outputs/pm_rl1/executor_coverage_20260929_v1/episode_specs_private.json'
    specs_bytes = specs_path.read_bytes()
    specs = json.loads(specs_bytes)
    assert {s['prefix']['split'] for s in specs} == {'train', 'dev'}
    assert len(specs) == len(prefixes)
    sources.append({'path': str(specs_path.relative_to(repo)),
                    'sha256': hashlib.sha256(specs_bytes).hexdigest()})
    train_prefix_ids = {hashlib.sha256(json.dumps(s['prefix'], ensure_ascii=False,
        sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        for s in specs if s['prefix']['split']=='train'}
    train_sft_ids = {r['prefix_identity'] for r in sft if r['split']=='train'}
    assert train_sft_ids <= train_prefix_ids
    source_overlap = {}
    for name, left, right in [('MP_MS',1,2), ('MP_ME',1,3), ('MS_ME',2,3)]:
        eligible = same_first = any_shared = 0
        for s in specs:
            a,b = s['inventory'][left][:4],s['inventory'][right][:4]
            if not a or not b:
                continue
            eligible += 1
            same_first += a[0]['source_rank'] == b[0]['source_rank']
            any_shared += bool({r['source_rank'] for r in a} & {r['source_rank'] for r in b})
        source_overlap[name] = {'prefixes_with_both_heads': eligible,
                               'first_items_share_source_session': same_first,
                               'top4_inventories_share_any_source_session': any_shared}
    heads = ('RS', 'MP', 'MS', 'ME')
    universe = [p for p in product(range(5), repeat=4) if sum(p) <= 4]
    assert len(universe) == 70
    assert len(prefixes) == len({p['index'] for p in prefixes}) == 114
    assert {p['split'] for p in prefixes} == {'train', 'dev'}
    assert {p['index'] for p in prefixes} == {p['index'] for p in capacity}
    assert len(plans) == len({(r['index'], r['counts']) for r in plans}) == 7240
    prefix_by_id = {r['index']: r for r in prefixes}
    for r in plans:
        p = prefix_by_id[r['index']]
        vector = ast.literal_eval(r['counts'])
        assert r['split'] == p['split'] and vector in universe
        assert all(vector[i] <= int(p[h + '_inventory']) for i,h in enumerate(heads))
        assert 0 <= int(r['resource_tokens']) <= 2048
    for r in capacity:
        assert int(r['reachable']) == sum(p['index'] == r['index'] for p in plans)

    contract_path = repo / 'project/docs/pm_rl1_completion_20260930_v2/execution_contract.json'
    contract = json.loads(contract_path.read_text())
    sources.append({'path': str(contract_path.relative_to(repo)),
                    'sha256': hashlib.sha256(contract_path.read_bytes()).hexdigest()})
    fixed = {tuple(v) for v in contract['shared_pool']['fixed_plans']}
    split_results = {}
    for split in ('train', 'dev'):
        px = [p for p in prefixes if p['split'] == split]
        cp = [p for p in capacity if p['split'] == split]
        pp = [p for p in plans if p['split'] == split]
        inventory_allowed = 0
        inventory_four = 0
        for p in px:
            allowed = [v for v in universe if all(v[i] <= int(p[h+'_inventory']) for i,h in enumerate(heads))]
            inventory_allowed += len(allowed)
            inventory_four += sum(sum(v) == 4 for v in allowed)
        four = [p for p in pp if int(p['total']) == 4]
        split_results[split] = {
            'prefixes': len(px), 'owners': len({p['owner'] for p in px}),
            'current_sessions': len({(p['owner'],p['session_id']) for p in px}),
            'per_owner_prefixes': dict(sorted(Counter(p['owner'] for p in px).items())),
            'theoretical_plans': len(px)*70,
            'inventory_allowed_plans': inventory_allowed,
            'reachable_plans': len(pp),
            'additional_feasibility_exclusions': inventory_allowed-len(pp),
            'exclusion_fraction_of_inventory_allowed': (inventory_allowed-len(pp))/inventory_allowed,
            'reachable_four_get_plans': len(four),
            'inventory_allowed_four_get_plans': inventory_four,
            'four_distinct_heads_reachable_prefixes': sum(ast.literal_eval(p['counts']) == (1,1,1,1) for p in pp),
            'median_four_get_resource_tokens': statistics.median(int(p['resource_tokens']) for p in four),
            'median_current_prefix_chat_tokens': statistics.median(int(p['prefix_chat_tokens']) for p in cp),
            'fixed_15_menu_reachable_slots': sum(ast.literal_eval(p['counts']) in fixed for p in pp),
            'fixed_15_menu_planned_slots': len(px)*15,
            'lexical_flags_not_need_labels': {k: sum(p[k]=='True' for p in px) for k in (
                'short_greeting_candidate','thanks_marker','history_or_update_marker','rs_self_disclosure_in_top4')}
        }
    single_cost = {}
    for i,h in enumerate(heads):
        vec = tuple(int(i==j) for j in range(4))
        costs = [int(p['resource_tokens']) for p in plans if ast.literal_eval(p['counts']) == vec]
        single_cost[h] = {'reachable_prefixes': len(costs), 'min_tokens': min(costs),
                          'median_tokens': statistics.median(costs), 'max_tokens': max(costs),
                          'median_reward_cost': statistics.median(costs)*.05/2048}
    train_sft = [p for p in sft if p['split']=='train']
    repeat_mp = [r for r in memory if r['head']=='MP' and r['split'] in ('train','dev')
                 and r['repeat_prior_same_slot_value']=='True']
    total_inventory = sum(v['inventory_allowed_plans'] for v in split_results.values())
    exclusions = total_inventory-len(plans)
    result = {
        'status': 'STRUCTURAL_TASK_FIT_AUDIT_NOT_RESOURCE_EFFECT_OR_REWARD_VALIDATION',
        'population': 'Existing 2026-09-30 old-renderer train/dev structural exports; no test semantic analysis',
        'by_split': split_results,
        'totals': {'prefixes': len(prefixes), 'inventory_allowed_plans': total_inventory,
                   'reachable_plans': len(plans), 'additional_feasibility_exclusions': exclusions,
                   'exclusion_fraction_of_inventory_allowed': exclusions/total_inventory,
                   'four_distinct_heads_reachable_prefixes': sum(v['four_distinct_heads_reachable_prefixes'] for v in split_results.values())},
        'single_resource_total_block_cost': single_cost,
        'cross_head_source_overlap_not_semantic_redundancy': source_overlap,
        'training_coverage': {'sft_rows': len(train_sft),
            'independent_prefixes': len({p['prefix_identity'] for p in train_sft}),
            'count_distribution': dict(sorted(Counter(p['count_total'] for p in train_sft).items())),
            'same_head_repeat_rows': sum(p['same_head_repeat']=='True' for p in train_sft),
            'train_prefix_hash_join': {'source_prefixes':len(train_prefix_ids),
                'sft_prefixes':len(train_sft_ids), 'matched':len(train_sft_ids & train_prefix_ids)},
            'reachable_plans_dose_3_or_4_fraction': sum(int(p['total'])>=3 for p in plans)/len(plans),
            'sft_to_RL_prefix_fraction': len({p['prefix_identity'] for p in train_sft})/96},
        'train_dev_MP_repeated_updates': {'total': len(repeat_mp),
            'reviewed': sum(p['reviewed']=='True' for p in repeat_mp),
            'unreviewed': sum(p['reviewed']!='True' for p in repeat_mp)},
        'reward_geometry': {'q_values':[0,1,2,3,4], 'm_values':[0,.25,1],
            'utility_min_nonzero_step': .25, 'resource_cost_max': .05,
            'smallest_utility_step_over_max_cost': 5,
            'off_subtraction': 'constant for all plans of a fixed prefix/executor; does not change their ranking or create quality labels',
            'step_costs': 'telescope to final resource cost at gamma=1; individual GETs do not measure marginal support benefit'},
        'public_source_scope': {'history_owners': census['history']['owners'],
            'history_sessions': census['history']['sessions'],
            'memory_units': census['memory']['units'], 'memory_heads': census['memory']['head_counts'],
            'official_QA_train_dev_rows': census['qa_train_dev']['rows'],
            'official_QA_no_evidence': census['qa_train_dev']['no_evidence'],
            'official_QA_only_private_event': census['qa_train_dev']['only_private_event'],
            'official_QA_multiple_visible_sessions': census['qa_train_dev']['multiple_visible_sessions']},
        'unknowns': ['Incremental information relative to current prefix',
            'Cross-head semantic redundancy and complementarity',
            'Fixed-executor response gain from each plan',
            'Between-prefix variation in useful plans',
            'Value of acquired text for later action choice',
            'Natural-pair human-calibrated evaluator resolution'],
        'caveats': ['Additional feasibility exclusions combine actual renderer budget/context/path rules; not attributed to token budget alone.',
            'Resource costs include shared wrapper; not intrinsic per-item or marginal costs.',
            'Lexical flags are candidate strata, never relevance/error/reward labels.',
            'Old renderer statistics must be recomputed after representation changes.',
            'Counts are not effect estimates, independent people or proof of an RL advantage.'],
        'sources': sources
    }
    assert result['training_coverage']['independent_prefixes']==19
    assert result['train_dev_MP_repeated_updates']=={'total':173,'reviewed':101,'unreviewed':72}
    return result


def locate_repo():
    for candidate in [Path.cwd(), *Path.cwd().parents]:
        if (candidate/'project/outputs/pm_rl1/dataset_diagnostics_20260930_v1').is_dir():
            return candidate
    raise FileNotFoundError('Run inside the research repository with local diagnostic exports.')


if __name__ == '__main__':
    print(json.dumps(analyze(locate_repo()), ensure_ascii=False, indent=2))
