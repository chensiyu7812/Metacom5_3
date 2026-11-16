#!/usr/bin/env python3
"""Offline candidate construction. No target examples, model calls, or runtime edits."""
import argparse
import collections
import hashlib
import json
from pathlib import Path

SEED = 'pmrl1-rs-cases-20261115-v1'
VERSION = 'pmrl1-rs-complete-case-candidate-v1'
STRATEGIES = ['Question', 'Restatement or Paraphrasing', 'Reflection of feelings',
              'Self-disclosure', 'Affirmation and Reassurance', 'Providing Suggestions',
              'Information', 'Others']
DEFAULT_ROOT = Path('/home/tokkio/Metacom5_3/project')

def digest(x):
    return hashlib.sha256(json.dumps(x, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()

def read_jsonl(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]

def numbered(turns, start, end):
    return [dict(turn_index=i, **turns[i]) for i in range(start, end)]

def allowed_for_target(card, target_family_ids, lineage_complete):
    """Fail closed for missing lineage; same family includes derivatives/aliases."""
    if not lineage_complete or not target_family_ids:
        return False
    return not set(card['source']['source_family_ids']).intersection(target_family_ids)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--project-root', type=Path, default=DEFAULT_ROOT)
    ap.add_argument('--output-dir', type=Path, default=Path(__file__).resolve().parent)
    args = ap.parse_args()
    root, out = args.project_root, args.output_dir
    source_path = root / 'data/external/ESConv.json'
    split_path = root / 'data/strategy/esconv_split_manifest_v1_5.jsonl'
    identity_path = root / 'data/paper1_public_rs/esconv_strategy_source_identity_dialogue_only_v2.jsonl'
    # The aggregate source file contains all splits. Only manifest train rows are
    # subsequently inspected, selected, rendered, or written.
    raw = json.loads(source_path.read_text())
    manifest = read_jsonl(split_path)
    train = [m for m in manifest if m['split'] == 'train'
             and not m.get('excluded_for_evoemo_overlap', False)]
    identities = {(x['source_dialogue_id'], x['source_turn_index']): x
                  for x in read_jsonl(identity_path) if x['source_split'] == 'train'}
    eligible = collections.defaultdict(list)
    for m in train:
        turns = raw[m['index']]['dialog']
        for start in range(6, len(turns)):
            if turns[start]['speaker'] != 'supporter' or turns[start - 1]['speaker'] != 'seeker':
                continue
            stop = start
            while stop < len(turns) and turns[stop]['speaker'] == 'supporter':
                stop += 1
            next_stop = stop
            while next_stop < len(turns) and turns[next_stop]['speaker'] == 'seeker':
                next_stop += 1
            # Structural eligibility only: enough prior interaction and a fully
            # observed reply block, with further interaction still in the source.
            if stop == next_stop or next_stop == len(turns):
                continue
            label = turns[start].get('annotation', {}).get('strategy')
            if label not in STRATEGIES:
                continue
            key = hashlib.sha256(f'{SEED}|{m["dialogue_id"]}|{start}'.encode()).hexdigest()
            eligible[label].append((key, m, start, stop, next_stop))
    quotas = STRATEGIES + ['Reflection of feelings', 'Providing Suggestions',
                           'Affirmation and Reassurance', 'Restatement or Paraphrasing']
    chosen, used = [], set()
    for label in quotas:
        options = [v for v in sorted(eligible[label], key=lambda v: v[0])
                   if v[1]['dialogue_id'] not in used]
        if not options:
            raise RuntimeError(f'Cannot supply quota for {label}; no fabricated replacements')
        row = options[0]
        chosen.append((label, *row))
        used.add(row[1]['dialogue_id'])
    out.mkdir(parents=True, exist_ok=True)
    (out / 'sources').mkdir(exist_ok=True)
    cards = []
    for n, (label, key, m, start, stop, next_stop) in enumerate(chosen, 1):
        original = raw[m['index']]
        turns = original['dialog']
        normalized = [(t['speaker'], ' '.join(t['content'].lower().split())) for t in turns]
        family = [f'esconv_dialogue:{m["dialogue_id"]}', f'esconv_text_sha256:{digest(normalized)}']
        refs = []
        for i in range(start, stop):
            old = identities.get((m['dialogue_id'], i))
            normalized_response_hash = hashlib.sha256(' '.join(turns[i]['content'].split()).encode()).hexdigest()
            if old:
                assert old['example_response_sha256'] == normalized_response_hash
                assert old['source_strategy_annotation'] == turns[i].get('annotation', {}).get('strategy')
            refs.append({'turn_index': i, 'old_rs_card_id': old['card_id'] if old else None,
                         'identity_status': 'matched' if old else 'not_in_old_identity_map',
                         'old_response_hash_check': 'passed_whitespace_normalized' if old else 'not_available',
                         'old_response_sha256': old.get('example_response_sha256') if old else None})
        feedback = [{'turn_index': i, 'raw_feedback': t['annotation']['feedback'],
                     'location': 'immediate_seeker_block' if stop <= i < next_stop else 'later_in_same_source',
                     'attributable_to_individual_action': False,
                     'exact_rating_scope': 'unknown_from_row_annotation'}
                    for i, t in enumerate(turns) if i >= stop and 'feedback' in t.get('annotation', {})]
        card = {
            'card_id': f'rs_case_candidate_{n:02d}', 'protocol': VERSION,
            'status': 'candidate_not_a_positive_example_or_validated_resource',
            'source': {'dataset': 'ESConv', 'split': 'train', 'dialogue_id': m['dialogue_id'],
                       'source_index': m['index'], 'dialogue_sha256': digest(original),
                       'source_family_ids': family, 'lineage_alias_closure_status': 'base_dialogue_and_exact_text_only; target_derivative_lineage_required',
                       'original_rs_identities': refs,
                       'full_source_file': f'sources/{m["dialogue_id"]}.json',
                       'source_url': 'https://github.com/thu-coai/Emotional-Support-Conversation'},
            'sampling': {'seed': SEED, 'order_key': key, 'stratum_original_first_turn_strategy': label,
                         'selection_uses_feedback': False, 'selection_uses_target': False},
            'source_context_before_action': numbered(turns, 0, start),
            'supporter_action_block': numbered(turns, start, stop),
            'observed_next_seeker_block': numbered(turns, stop, next_stop),
            'feedback_observations': feedback,
            'session_level_observations': {
                'raw_survey_score': original.get('survey_score'),
                'scope': 'whole_source_session; not a causal outcome of the focus action',
                'downstream_real_world_outcome': 'unknown'},
            'method_links': {'original_strategy_tags': list(dict.fromkeys(
                turns[i].get('annotation', {}).get('strategy') for i in range(start, stop))),
                'curated_method_unit_ids': [], 'crosswalk_status': 'not_reviewed'},
            'applicability_review': {'status': 'pending_qualified_review',
                'supported_conditions': 'unknown', 'unsuitable_conditions': 'unknown',
                'why_this_might_help': 'unknown', 'AI_hypotheses': [],
                'expert_approval': False, 'measured_incremental_value_to_G': 'unknown'},
            'review': {'source_alignment': 'passed_automatic_exact_slice_checks',
                'train_only_and_distinct_source': 'passed',
                'semantic_review': 'stored_separately_in_SEMANTIC_REVIEW_ZH.md; not_recomputed_by_builder',
                'professional_review': 'not_done', 'runtime_approved': False},
            'limitations': ['Recorded reaction is observation, not proof of benefit or causation.',
                'Original strategy labels describe annotation, not correctness or expert approval.',
                'Source participants are different people; never convert their facts into current-user memory.',
                'Human supporter personal experience must never become fabricated AI autobiography.',
                'Session ratings and later source observations are not current-target future information.',
                'Current source-family exclusions must be applied before retrieval; unknown lineage fails closed.']}
        # Independent assertions against raw source, rather than snapshots of outputs.
        assert [dict((k,v) for k,v in t.items() if k != 'turn_index')
                for t in card['source_context_before_action']] == turns[:start]
        assert [dict((k,v) for k,v in t.items() if k != 'turn_index')
                for t in card['supporter_action_block']] == turns[start:stop]
        assert [dict((k,v) for k,v in t.items() if k != 'turn_index')
                for t in card['observed_next_seeker_block']] == turns[stop:next_stop]
        assert not allowed_for_target(card, [family[0]], True)
        assert not allowed_for_target(card, [], False)
        assert allowed_for_target(card, ['independent_demo_family'], True)
        (out / 'sources' / f'{m["dialogue_id"]}.json').write_text(
            json.dumps(original, ensure_ascii=False, indent=2) + '\n')
        cards.append(card)
    assert len(cards) == len(used) == 12
    (out / 'case_candidates.jsonl').write_text(''.join(json.dumps(c, ensure_ascii=False) + '\n' for c in cards))
    review = ['# RS 候选完整案例：原文核对视图', '',
        '仅用于离线内容审核。以下不是给当前 target 选出的正例。完整原始会话另存 sources/。',
        '上下文从第 0 turn 完整保留；行动与紧接其后的反应按连续说话者块保留。', '']
    for c in cards:
        review += [f'## {c["card_id"]} | {c["source"]["dialogue_id"]} | {c["sampling"]["stratum_original_first_turn_strategy"]}', '']
        for field, title in [('source_context_before_action', '完整前情'),
                             ('supporter_action_block', '行动块'),
                             ('observed_next_seeker_block', '紧随反应块')]:
            review += [f'### {title}', '']
            for t in c[field]:
                review += [f'[{t["turn_index"]}] {t["speaker"]} {json.dumps(t.get("annotation", {}), ensure_ascii=False)}: {t["content"]}', '']
        review += ['反馈范围：逐条保留原注解，单一行动归因 unknown；全会话评分只在 JSON 的独立字段。', '']
    (out / 'CASE_REVIEW_VIEW_ZH.md').write_text('\n'.join(review))
    checks = {'protocol': VERSION, 'seed': SEED, 'count': len(cards), 'distinct_train_dialogues': len(used),
              'source_path': str(source_path), 'source_file_sha256': hashlib.sha256(source_path.read_bytes()).hexdigest(),
              'split_path': str(split_path), 'split_file_sha256': hashlib.sha256(split_path.read_bytes()).hexdigest(),
              'old_identity_path': str(identity_path), 'old_identity_file_sha256': hashlib.sha256(identity_path.read_bytes()).hexdigest(),
              'checks': {'exact_prefix_action_reaction_slices': 'passed', 'complete_contiguous_blocks': 'passed',
                         'old_rs_response_hash_and_original_strategy': 'passed_whitespace_normalized',
                         'train_only_not_overlap_excluded': 'passed', 'same_family_rejected': 'passed',
                         'unknown_lineage_rejected': 'passed', 'independent_family_accepted': 'passed'},
              'strategy_counts': dict(collections.Counter(c['sampling']['stratum_original_first_turn_strategy'] for c in cards)),
              'runtime_approved_count': 0, 'helpfulness_validated_count': 0,
              'raw_test_or_validation_dialogues_selected_or_rendered': 0,
              'note': 'Single aggregate ESConv file was parsed; field inspection/selection/output restricted to train rows.'}
    (out / 'BUILD_CHECKS.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(checks, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
