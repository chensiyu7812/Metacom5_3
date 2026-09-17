"""Read-only instrument audit; no verdicts, response ranking, or provider calls."""
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path('/opt/tokkio-data0/tokkio_projects/Metacom5_3')
P = ROOT / 'project'
AUTH = P / 'data/paper1_authority'
OUT = Path(__file__).resolve().parent

def read(path):
    return json.loads(path.read_text())

def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()

def render(sessions):
    return '\n\n'.join('Prior session [' + s['timestamp'] + ']:\n' + '\n'.join(
        t['role'] + ': ' + t['content'] for t in s['dialogue']) for s in sessions)

checks = {}
def check(name, value):
    checks[name] = bool(value)

manifest = read(AUTH / 'paper1_pairwise_teacher_human_sheet_manifest_20260904_v1.json')
instrument = read(AUTH / 'paper1_pairwise_teacher_human_instrument_20260904_v1.json')
base = {r['base_pair_id']: r for r in rows(AUTH / 'paper1_pairwise_teacher_base_pair_preflight_20260904_v1.jsonl')}
blind = {r['presentation_id']: r for r in rows(AUTH / 'paper1_pairwise_teacher_blind_key_20260904_v1.jsonl')}
binding = read(AUTH / 'paper1_pairwise_teacher_generator_request_binding_20260904_v1.json')
generation = read(AUTH / 'paper1_pairwise_teacher_local_generation_result_20260904_v1.json')
pairs = {r['base_pair_id']: r for r in generation['base_pair_response_map']}
requests = rows(P / binding['private_request_manifest']['path'])
cache = {r['request_id']: read(P / generation['private_success_cache']['path'] / (r['request_id'] + '.json')) for r in requests}
by_request = {r['request_id']: r for r in requests}
user = {u['id']: u for u in read(P / 'data/external/evo_emo.json')}
units = {u['memory_id']: u for r in rows(P / 'data/paper1_public_memory/es_memeval_public_multi_view_session_results_v1.jsonl') for u in r['accepted_units']}
sheets = {}
expected_fields = {'item_number', 'presentation_id', 'task', 'task_input', 'reference_material', 'response_A', 'response_B', 'verdict', 'rationale'}
for rater, meta in manifest['sheets'].items():
    path = P / meta['path']
    sheet = read(path)
    sheets[rater] = sheet
    items = sheet['items']
    check(rater + '_frozen_hash', sha(path) == meta['sha256'])
    check(rater + '_96_unique_presentations', len(items) == len({i['presentation_id'] for i in items}) == 96)
    check(rater + '_complete_numbering', [i['item_number'] for i in items] == list(range(1, 97)))
    check(rater + '_instrument_exact', sheet['instrument'] == instrument)
    check(rater + '_only_blinded_item_fields', all(set(i) == expected_fields for i in items))
    check(rater + '_unrated_original', all(i['verdict'] is None and i['rationale'] is None for i in items))
    check(rater + '_nonempty_input_and_responses', all(all(isinstance(i[k], str) and i[k].strip() for k in ['task_input', 'response_A', 'response_B']) for i in items))
    check(rater + '_responses_exact_cache', all(i['response_' + side] == cache[pairs[blind[i['presentation_id']]['base_pair_id']][blind[i['presentation_id']][side + '_arm']]['request_id']]['accepted_text'] for i in items for side in ['A', 'B']))
    check(rater + '_references_exact_preflight', all(i['reference_material'] == base[blind[i['presentation_id']]['base_pair_id']]['reference_material'] for i in items))
    check(rater + '_non_DG_inputs_exact', all(i['task_input'] == base[blind[i['presentation_id']]['base_pair_id']]['task_input'] for i in items if i['task'] != 'DG'))
    check(rater + '_DG_visible_prefix_exact', all(i['task_input'] == '\n'.join(('supporter' if m['role'] == 'assistant' else 'seeker') + ': ' + m['content'] for m in by_request[pairs[blind[i['presentation_id']]['base_pair_id']]['OFF']['request_id']]['request']['messages'] if m['role'] in ['user', 'assistant']) for i in items if i['task'] == 'DG'))

a, b = sheets['RATER_A']['items'], sheets['RATER_B']['items']
clean = lambda i: {k: v for k, v in i.items() if k != 'item_number'}
check('same_items_and_orientation', {i['presentation_id']: clean(i) for i in a} == {i['presentation_id']: clean(i) for i in b})
check('different_rater_order', [i['presentation_id'] for i in a] != [i['presentation_id'] for i in b])
grouped = defaultdict(list)
for i in a:
    grouped[blind[i['presentation_id']]['base_pair_id']].append(i)
check('80_base_16_reversed', len(grouped) == 80 and Counter(map(len, grouped.values())) == {1: 64, 2: 16})
check('reversal_only_swaps_responses', all(x[0]['task_input'] == x[1]['task_input'] and x[0]['reference_material'] == x[1]['reference_material'] and x[0]['response_A'] == x[1]['response_B'] and x[0]['response_B'] == x[1]['response_A'] for x in grouped.values() if len(x) == 2))

coverage = []
full_reference = {}
current_reference = {}
for r in binding['dg_dynamic_retrieval']:
    owner, _, idx = r['target_id'].split('::')
    u = user[owner]
    topic = next(t for t in u['subsequent_topics'] if str(t['idx']) == idx)
    shown = set(topic['related_sessions'])
    source_ids = [c.split('::')[-1] if c.startswith('ms::') else units[c.split('::', 1)[1]]['source_session_id'] for c in r['candidate_ids']]
    coverage.append({'candidate_count': len(source_ids), 'outside_reference_source_count': sum(s not in shown for s in source_ids)})
    sessions = {s['id']: s for s in u['dialog_history']}
    expected = render([sessions[sid] for sid in topic['related_sessions']])
    current_reference[r['target_id']] = expected
    full_reference[r['target_id']] = render(sorted(u['dialog_history'], key=lambda s: (s['timestamp'], s['id'])))
check('all_DG_references_exact_related_sessions_projection', all(r['reference_material'] == current_reference[r['target_id']] for r in base.values() if r['task'] == 'DG'))
qa_gold = {u['id'] + '::' + str(g['id']) + '::' + str(q['idx']): q['answer'] for u in user.values() for g in u['questions'] for q in g['questions']}
summary_gold = {u['id'] + '::summary::' + str(q['idx']): q['answer'] for u in user.values() for q in u['summaries']}
check('QA_gold_matches_raw_source', all(r['reference_material'] == qa_gold[r['target_id']] for r in base.values() if r['task'] == 'QA'))
check('Summary_gold_matches_raw_source', all(r['reference_material'] == summary_gold[r['target_id']] for r in base.values() if r['task'] == 'Summary'))

# Evidence-presence probe only, not a judgement of either response or the pair.
probe_target = 'p13::dg::1'
probe_present = any('Lily' in i['response_A'] or 'Lily' in i['response_B'] for i in a if base[blind[i['presentation_id']]['base_pair_id']]['target_id'] == probe_target)
probe_source = next(s for s in user['p13']['dialog_history'] if s['id'] == 'p13_conv_8')
probe_supported = any(t['role'] == 'seeker' and "I've reconnected with my sister Lily." in t['content'] for t in probe_source['dialogue'])
evidence_gap_confirmed = probe_present and probe_supported and 'Lily' not in current_reference[probe_target]

result = {
    'audit_date': '2026-09-07',
    'scope': 'Blinded instrument integrity and evidence sufficiency; no response verdicts assigned.',
    'counts': {
        'base_by_task': dict(Counter(r['task'] for r in base.values())),
        'presentations_per_rater_by_task': dict(Counter(i['task'] for i in a)),
        'primary_judgements': len(a) + len(b),
        'DG_scenario_count': len(current_reference),
        'all_local_generations': len(cache),
        'length_finish_generations': sum(c['finish_reason'] == 'length' for c in cache.values()),
        'base_pairs_with_any_length_finish': sum(any(cache[p[arm]['request_id']]['finish_reason'] == 'length' for arm in ['ON', 'OFF']) for p in pairs.values()),
        'exact_response_equal_base_pairs': sum(x[0]['response_A'] == x[0]['response_B'] for x in grouped.values()),
    },
    'DG_reference_coverage': {
        'base_pair_bundles': len(coverage),
        'bundles_with_any_source_session_outside_reference': sum(r['outside_reference_source_count'] > 0 for r in coverage),
        'bundles_with_all_source_sessions_outside_reference': sum(r['outside_reference_source_count'] == r['candidate_count'] for r in coverage),
        'observed_response_fact_supported_in_raw_history_but_absent_from_shown_reference': evidence_gap_confirmed,
        'interpretation': 'Source-session absence is a coverage risk, not a count of invalid pairs, erroneous responses, or uncertain human verdicts. The independent presence probe establishes an actual missing-evidence case without rating the pair.',
        'current_unique_scenario_reference_words': sum(len(s.split()) for s in current_reference.values()),
        'proposed_full_history_unique_scenario_reference_words': sum(len(s.split()) for s in full_reference.values()),
        'current_reference_chars_min_max': [min(map(len, current_reference.values())), max(map(len, current_reference.values()))],
        'proposed_full_history_chars_min_max': [min(map(len, full_reference.values())), max(map(len, full_reference.values()))],
        'boundary': 'Current B17 target cutoff is the full historical session count; proposal must still enforce rank < target.cutoff_rank and must exclude hidden new-scenario narrative.',
    },
    'integrity_checks': checks,
    'integrity_checks_passed': sum(checks.values()),
    'integrity_checks_total': len(checks),
    'measurement_readiness': 'Recommend DG reference correction before starting final human rating; active frozen v1 left unchanged.',
    'paid_calls': 0,
    'formal_outcomes': 0,
    'human_or_teacher_verdicts_created': 0,
    'frozen_repo_files_modified': 0,
}
assert all(checks.values()), checks
assert evidence_gap_confirmed
(OUT / 'human_sheet_readiness_evidence.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(result, ensure_ascii=False, indent=2))
