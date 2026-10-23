#!/usr/bin/env python3
"""Offline, source-bound census. NO model calls, gold export to runtime or split edits.

Test QA/Summary answers/evidence are removed immediately after JSON decoding.
Lexical features are review candidates, never semantic labels or reward scores.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import csv
from hashlib import sha256
import json
from pathlib import Path
import re
import statistics
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
OUT = PROJECT / 'outputs/pm_rl1/dataset_diagnostics_20260930_v1'
EXTERNAL = Path('/opt/tokkio-data0/tokkio_external/ESC-Eval/data')
PATHS = {
    'esconv': PROJECT / 'data/external/ESConv.json',
    'evo': PROJECT / 'data/external/evo_emo.json',
    'runtime': PROJECT / 'data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json',
    'esconv_split': PROJECT / 'data/strategy/esconv_split_manifest_v1_5.jsonl',
    'rs': PROJECT / 'data/paper1_public_rs/esconv_rs_exact_canonical_treatments_v1.jsonl',
    'units': PROJECT / 'data/paper1_public_memory/es_memeval_public_multi_view_session_results_v1.jsonl',
    'overlay': PROJECT / 'outputs/pm_rl1/source_repair_20260929_v2/source_overlay_private.json',
    'specs': PROJECT / 'outputs/pm_rl1/executor_coverage_20260929_v1/episode_specs_private.json',
    'sft': PROJECT / 'outputs/pm_rl1/executor_training_20260930_v1/accepted_dataset_private.json',
    'freeze': PROJECT / 'outputs/pm_rl1/source_and_capacity_20260928_v1/dataset_freeze.json',
    'esc_en': EXTERNAL / 'card_high_en.json', 'esc_zh': EXTERNAL / 'card_high_zh.json',
    'esc_overlap': PROJECT / 'data/paper1_authority/esc_eval_english331_source_overlap_v1.jsonl',
}
SELF = re.compile(r"\b(?:my (?:mother|mom|father|dad|wife|husband|son|daughter|boyfriend|girlfriend|sister|brother|family|job|boss)|when i (?:was|lost|went)|i (?:went through|have been through|had a similar|lost my|experienced this))\b", re.I)
DEICTIC = re.compile(r'\b(?:remember|last time|you (?:said|mentioned|suggested)|before|again|still|anymore|no longer|used to|since then)\b', re.I)
GREETING = re.compile(r"^(?:hi|hello|hey)(?:[.! ,]|$)", re.I)
THANKS = re.compile(r'\b(?:thank you|thanks|appreciate|goodbye|bye)\b', re.I)

def read(path):
    return json.loads(path.read_text())

def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

def normalized(s):
    return ' '.join(s.lower().split())

def unknown_answer(s):
    return normalized(str(s)).strip(' .!?') in ('unknown', 'not known', 'not mentioned', 'unanswerable')

def words(s):
    return re.findall(r"\b[\w']+\b", s)

def quantiles(values):
    a = sorted(values)
    if not a:
        return dict(n=0, min=None, median=None, p90=None, max=None)
    return dict(n=len(a), min=a[0], median=statistics.median(a),
                p90=a[max(0, (9 * len(a) + 9) // 10 - 1)], max=a[-1])

def owner_splits(owners):
    ordered = sorted(owners, key=lambda s: sha256(('pmseq-v2-owner|' + s).encode()).hexdigest())
    assert len(set(ordered)) == 18
    return {o: 'train' if i < 12 else 'dev' if i < 15 else 'test' for i, o in enumerate(ordered)}

def project_gold(raw, splits):
    """Keep only counts/capabilities for test; never export its gold or question text."""
    projected = []
    for owner in raw:
        if splits[owner['id']] != 'test':
            projected.append(owner)
            continue
        projected.append({'id': owner['id'], 'questions': [
            {'id': group['id'], 'questions': [
                {'idx': q.get('idx'), 'capability': q['capability']} for q in group['questions']]}
            for group in owner['questions']],
            'summaries': [{'idx': q.get('idx'), 'capability': q.get('capability')} for q in owner['summaries']],
            'subsequent_topics': [{'idx': q.get('idx')} for q in owner['subsequent_topics']]})
    return projected

def resolve_reference(ref, sessions, events):
    """Owner-local lookup only. Never rescue broken IDs using another owner."""
    if ref in events:
        return {'kind': 'private_event', 'session': events[ref].get('conv_id')}
    if ref in sessions:
        return {'kind': 'visible_session', 'session': ref}
    if ':' in ref:
        sid, idx = ref.rsplit(':', 1)
        if sid in sessions and idx.isdigit():
            found = [t for t in sessions[sid]['turns'] if t['idx'] == int(idx)]
            if len(found) == 1:
                return {'kind': 'visible_turn', 'session': sid, 'role': found[0]['role'], 'text': found[0]['content']}
    return {'kind': 'unresolved', 'session': None}

def write_json(out, name, obj):
    (out / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')

def write_csv(out, name, rows):
    if not rows:
        return
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with (out / name).open('w') as f:
        w = csv.DictWriter(f, fieldnames=keys); w.writeheader()
        for row in rows:
            w.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k, v in row.items()})

def main(out):
    out.mkdir(parents=True, exist_ok=True)
    if (out / 'closeout.json').exists():
        raise RuntimeError('Use a new --out directory; preserve completed analysis.')
    manifest = {k: {'path': str(p), 'sha256': sha256(p.read_bytes()).hexdigest(), 'bytes': p.stat().st_size} for k, p in PATHS.items()}
    write_json(out, 'input_manifest.json', manifest)
    runtime = read(PATHS['runtime'])['users']
    splits = owner_splits([u['owner_id'] for u in runtime])
    users = {u['owner_id']: u for u in runtime}
    raw = project_gold(read(PATHS['evo']), splits)
    esconv = read(PATHS['esconv']); split_rows = lines(PATHS['esconv_split'])
    es_splits = {r['index']: r for r in split_rows}
    stats = {'scope': 'Complete structural census; train/dev-only gold analysis; lexical flags are not error labels.', 'owner_splits': splits}

    # ESConv source features, plus exact long-turn provenance (not semantic matching).
    es_rows, es_turn_index, strategy_counts = [], defaultdict(set), Counter()
    es_transcripts = defaultdict(list)
    for i, conv in enumerate(esconv):
        support = [t for t in conv['dialog'] if t['speaker'] == 'supporter']
        strategies = Counter(t.get('annotation', {}).get('strategy', 'missing') for t in support)
        strategy_counts.update(strategies)
        sid = f'esconv_{i:04d}'
        es_transcripts[tuple((t['speaker'], normalized(t['content'])) for t in conv['dialog'])].append(sid)
        for t in conv['dialog']:
            if len(words(t['content'])) >= 8:
                es_turn_index[(t['speaker'], normalized(t['content']))].add(sid)
        es_rows.append(dict(dialogue_id=sid, split=es_splits[i]['split'], excluded_for_evoemo_overlap=es_splits[i]['excluded_for_evoemo_overlap'],
            emotion=conv['emotion_type'], problem=conv['problem_type'], experience_type=conv.get('experience_type'),
            turns=len(conv['dialog']), supporter_turns=len(support), self_disclosure_turns=strategies['Self-disclosure'] + strategies['Self Disclosure'],
            self_life_lexical_turns=sum(bool(SELF.search(t['content'])) for t in support),
            words=sum(len(words(t['content'])) for t in conv['dialog'])))
    write_csv(out, 'esconv_dialogue_features.csv', es_rows)
    stats['esconv'] = dict(dialogues=len(esconv), turns=sum(r['turns'] for r in es_rows), supporter_turns=sum(r['supporter_turns'] for r in es_rows),
        strategy_counts=dict(strategy_counts), split_counts=dict(Counter(r['split'] for r in es_rows)),
        self_disclosure_dialogues=sum(r['self_disclosure_turns'] > 0 for r in es_rows),
        self_life_lexical_dialogues=sum(r['self_life_lexical_turns'] > 0 for r in es_rows),
        emotion_counts=dict(Counter(r['emotion'] for r in es_rows)), problem_counts=dict(Counter(r['problem'] for r in es_rows)),
        words=quantiles(r['words'] for r in es_rows))

    # Runtime history, without evaluator annotations, across all owners.
    session_rows, transcripts, ids, role_flags = [], defaultdict(list), defaultdict(list), []
    owner_rows = []
    for owner, u in users.items():
        for s in u['sessions']:
            support = [t for t in s['turns'] if t['role'] == 'supporter']
            key = tuple((t['role'], normalized(t['content'])) for t in s['turns'])
            long_matches = Counter(source for t in s['turns'] for source in es_turn_index.get((t['role'], normalized(t['content'])), ()))
            source, matches = long_matches.most_common(1)[0] if long_matches else (None, 0)
            r = dict(owner=owner, split=splits[owner], session_id=s['session_id'], rank=s['chronological_rank'], timestamp=s['timestamp'],
                origin_by_id='esconv_seed' if s['session_id'].startswith('esc') else 'expanded_session',
                turns=len(s['turns']), words=sum(len(words(t['content'])) for t in s['turns']), supporter_turns=len(support),
                self_life_lexical_turns=sum(bool(SELF.search(t['content'])) for t in support), exact_esconv_transcripts=es_transcripts.get(key, []),
                best_exact_long_turn_source=source, matching_long_turns=matches,
                duplicate_turn_indices=len(s['turns']) - len({t['idx'] for t in s['turns']}),
                adjacent_same_role=sum(a['role'] == b['role'] for a, b in zip(s['turns'], s['turns'][1:])))
            session_rows.append(r); ids[s['session_id']].append((owner, splits[owner])); transcripts[key].append((owner, splits[owner], s['session_id']))
            if splits[owner] != 'test':
                role_flags.extend(dict(owner=owner, split=splits[owner], session=s['session_id'], turn=t['idx'], text=t['content']) for t in support if SELF.search(t['content']))
        ss = [r for r in session_rows if r['owner'] == owner]
        owner_rows.append(dict(owner=owner, split=splits[owner], sessions=len(ss), turns=sum(r['turns'] for r in ss),
            words=sum(r['words'] for r in ss), first_date=min(r['timestamp'] for r in ss), last_date=max(r['timestamp'] for r in ss),
            seed_sessions=sum(r['origin_by_id'] == 'esconv_seed' for r in ss)))
    write_csv(out, 'history_session_features.csv', session_rows); write_csv(out, 'owner_features.csv', owner_rows)
    write_json(out, 'supporter_role_review_candidates_private.json', role_flags)
    cross = lambda groups: [v for v in groups.values() if len({x[1] for x in v}) > 1]
    stats['history'] = dict(owners=len(users), sessions=len(session_rows), turns=sum(r['turns'] for r in session_rows),
        origin_counts=dict(Counter(r['origin_by_id'] for r in session_rows)), session_words=quantiles(r['words'] for r in session_rows),
        owner_words=quantiles(r['words'] for r in owner_rows),
        self_life_lexical_sessions=sum(r['self_life_lexical_turns'] > 0 for r in session_rows),
        self_life_lexical_turns=sum(r['self_life_lexical_turns'] for r in session_rows),
        exact_esconv_transcript_sessions=sum(bool(r['exact_esconv_transcripts']) for r in session_rows),
        cross_split_exact_transcript_groups=cross(transcripts), cross_split_shared_session_ids=cross(ids),
        duplicate_turn_index_sessions=sum(r['duplicate_turn_indices'] > 0 for r in session_rows),
        adjacent_same_role_sessions=sum(r['adjacent_same_role'] > 0 for r in session_rows))

    # Gold-dependent analyses are train/dev only; official QA scope = all history.
    qa_rows, summary_rows, examples, task_counts = [], [], [], Counter()
    test_caps = Counter()
    for u in raw:
        owner=u['id']; split=splits[owner]
        sessions={s['session_id']: s for s in users[owner]['sessions']}
        for group in u['questions']:
            for q in group['questions']:
                task_counts[(split, 'qa')] += 1
                if split == 'test':
                    test_caps[q['capability']] += 1
                    continue
                events={e['id']: e for e in u['event_experience']}
                refs=q.get('evidence', []); resolved=[resolve_reference(ref, sessions, events) for ref in refs]
                kinds=Counter(x['kind'] for x in resolved); visible=[x for x in resolved if x['kind'].startswith('visible')]
                ans=normalized(str(q['answer'])); unknown=unknown_answer(q['answer'])
                # Exact text overlap is a triage feature, not an entailment test.
                answer_hits=[f"{s['session_id']}:{t['idx']}" for s in sessions.values() for t in s['turns']
                    if not unknown and len(ans) >= 3 and ans in normalized(t['content'])]
                seeker_hits=[f"{s['session_id']}:{t['idx']}" for s in sessions.values() for t in s['turns']
                    if t['role']=='seeker' and not unknown and len(ans)>=3 and ans in normalized(t['content'])]
                row=dict(owner=owner, split=split, group=group['id'], idx=q['idx'], capability=q['capability'],
                    question_words=len(words(q['question'])), answer_words=len(words(str(q['answer']))), unknown_answer=unknown,
                    evidence_count=len(refs), unique_evidence=len(set(refs)), duplicate_evidence=len(refs)-len(set(refs)),
                    private_event_refs=kinds['private_event'], visible_turn_refs=kinds['visible_turn'], visible_session_refs=kinds['visible_session'],
                    unresolved_refs=kinds['unresolved'], only_private_event_refs=bool(refs) and kinds['private_event']==len(refs),
                    visible_evidence_sessions=len({x['session'] for x in visible}),
                    group_missing_from_owner=group['id']!='timeline' and group['id'] not in sessions,
                    literal_answer_hits=len(answer_hits), literal_seeker_answer_hits=len(seeker_hits))
                qa_rows.append(row)
                examples.append(dict(**row, question=q['question'], answer=q['answer'], evidence=refs,
                    reference_resolution=resolved, literal_answer_locations=answer_hits, literal_seeker_locations=seeker_hits))
        for q in u['summaries']:
            task_counts[(split,'summary')] += 1
            if split == 'test': continue
            refs=q.get('evidence', []); resolved=[resolve_reference(ref, sessions, {}) for ref in refs]
            summary_rows.append(dict(owner=owner, split=split, idx=q['idx'], capability=q['capability'],
                answer_words=len(words(str(q['answer']))), evidence_count=len(refs), unique_evidence=len(set(refs)),
                unresolved_refs=sum(x['kind']=='unresolved' for x in resolved),
                visible_sessions=len({x['session'] for x in resolved if x['kind'].startswith('visible')})))
        task_counts[(split,'dg')] += len(u['subsequent_topics'])
    write_csv(out, 'qa_train_dev_features.csv', qa_rows); write_csv(out, 'summary_train_dev_features.csv', summary_rows)
    write_json(out, 'qa_train_dev_review_private.json', examples)
    stats['tasks'] = {s: {t: task_counts[s,t] for t in ('qa','summary','dg')} for s in ('train','dev','test')}
    stats['qa_train_dev'] = dict(rows=len(qa_rows), capabilities=dict(Counter(r['capability'] for r in qa_rows)),
        unknown_answers=sum(r['unknown_answer'] for r in qa_rows), answer_words=quantiles(r['answer_words'] for r in qa_rows),
        no_evidence=sum(r['evidence_count']==0 for r in qa_rows), duplicate_evidence_rows=sum(r['duplicate_evidence']>0 for r in qa_rows),
        private_event_any=sum(r['private_event_refs']>0 for r in qa_rows), only_private_event=sum(r['only_private_event_refs'] for r in qa_rows),
        visible_evidence_any=sum(r['visible_turn_refs']+r['visible_session_refs']>0 for r in qa_rows),
        unresolved_rows=sum(r['unresolved_refs']>0 for r in qa_rows), unresolved_refs=sum(r['unresolved_refs'] for r in qa_rows),
        group_missing_rows=sum(r['group_missing_from_owner'] for r in qa_rows),
        literal_answer_any=sum(r['literal_answer_hits']>0 for r in qa_rows), literal_answer_seeker=sum(r['literal_seeker_answer_hits']>0 for r in qa_rows),
        only_private_but_literal_seeker=sum(r['only_private_event_refs'] and r['literal_seeker_answer_hits']>0 for r in qa_rows),
        multiple_visible_sessions=sum(r['visible_evidence_sessions']>1 for r in qa_rows))
    stats['qa_test_structure_only'] = dict(rows=sum(test_caps.values()), capabilities=dict(test_caps), gold_semantics_not_analyzed=True)
    stats['summary_train_dev'] = dict(rows=len(summary_rows), answer_words=quantiles(r['answer_words'] for r in summary_rows),
        visible_sessions=quantiles(r['visible_sessions'] for r in summary_rows), unresolved_rows=sum(r['unresolved_refs']>0 for r in summary_rows))

    # Extracted MP/ME lineage: byte-correct quotation != semantic entailment.
    unit_rows=[]; repeats=[]; prior={}; overlay=read(PATHS['overlay'])
    reviewed={r['unit_id']: r for r in overlay['unit_reviews']}
    for sr in lines(PATHS['units']):
        owner=sr['owner_id']; sessions={s['session_id']:s for s in users[owner]['sessions']}
        for unit in sr['accepted_units']:
            head='MP' if 'profile_slot_key' in unit else 'ME'
            spans=unit.get('supporting_spans', []); missing=0; mismatched=0; roles=Counter()
            for span in spans:
                resolved=resolve_reference(span['turn_id'],sessions,{})
                if resolved['kind']!='visible_turn': missing+=1; continue
                roles[resolved['role']]+=1
                if resolved['text'][span['start_char']:span['end_char']]!=span['exact_text']: mismatched+=1
            key=(owner,unit.get('profile_slot_key')); previous=prior.get(key) if head=='MP' else None
            repeat=bool(previous and previous['normalized_value']==unit['normalized_value'])
            r=dict(owner=owner,split=splits[owner],unit_id=unit['memory_id'],head=head,source_session=unit['source_session_id'],
                source_rank=unit['source_session_rank'],source_time=unit['timestamp'],
                type=unit.get('profile_field_type',unit.get('event_experience_type')), slot=unit.get('profile_slot_key'),
                temporal_status=unit.get('temporal_status'), span_count=len(spans), missing_turn_refs=missing, bad_span_slices=mismatched,
                seeker_spans=roles['seeker'],supporter_spans=roles['supporter'],repeat_prior_same_slot_value=repeat,
                reviewed=unit['memory_id'] in reviewed, review_status=reviewed.get(unit['memory_id'],{}).get('citation_status'),
                source_disposition=reviewed.get(unit['memory_id'],{}).get('source_disposition'))
            unit_rows.append(r)
            if repeat and splits[owner]!='test':
                repeats.append(dict(**r,content=unit['rendered_candidate_content'],prior_unit_id=previous['memory_id'],
                    prior_time=previous['timestamp'],spans=spans))
            if head=='MP': prior[key]=unit
    write_csv(out,'memory_unit_features.csv',unit_rows); write_json(out,'profile_repeat_review_private.json',repeats)
    stats['memory'] = dict(units=len(unit_rows),head_counts=dict(Counter(r['head'] for r in unit_rows)),
        types=dict(Counter(r['type'] for r in unit_rows)),temporal_status=dict(Counter(r['temporal_status'] for r in unit_rows if r['head']=='ME')),
        missing_turn_refs=sum(r['missing_turn_refs'] for r in unit_rows),bad_span_slices=sum(r['bad_span_slices'] for r in unit_rows),
        only_supporter_units=sum(r['supporter_spans']>0 and r['seeker_spans']==0 for r in unit_rows),
        repeat_same_slot_value=sum(r['repeat_prior_same_slot_value'] for r in unit_rows),
        reviewed_repeat_units=sum(r['repeat_prior_same_slot_value'] and r['reviewed'] for r in unit_rows),
        overlay_reviewed=len(reviewed),overlay_status=dict(Counter(r['citation_status'] for r in reviewed.values())),
        temporal_blocks=len(overlay['temporal_blocks']),session_blocks=len(overlay['session_blocks']))

    # Current frozen inventories, current prefixes and weak-SFT coverage.
    specs=read(PATHS['specs']); rs=lines(PATHS['rs']); rs_rows=[]; prefix_rows=[]
    for r in rs:
        txt=r['rendered_card_text']; match=re.search(r'Strategy family \[([^]]+)\]',txt)
        rs_rows.append(dict(treatment_id=r['treatment_id'],family=match[1] if match else 'unknown',
            source_dialogues=r['source_dialogue_ids'],words=len(words(txt)),self_disclosure='Self Disclosure' in txt or 'Self-disclosure' in txt))
    seed_matches=set(sid for r in session_rows for sid in r['exact_esconv_transcripts'])
    retrieved_rs_sources=set()
    for i,spec in enumerate(specs):
        p=spec['prefix']; turn=p['turns'][-1]['content']; n=len(words(turn))
        prior_support=[t['content'] for t in p['turns'][:-1] if t['role']=='supporter']
        rr=dict(index=i,owner=p['owner_id'],split=p['split'],session_id=p['session_id'],cutoff_rank=p['cutoff_rank'],
            prefix_turns=len(p['turns']),last_turn_words=n,short_greeting_candidate=n<=12 and bool(GREETING.search(turn)),
            thanks_marker=bool(THANKS.search(turn)),history_or_update_marker=bool(DEICTIC.search(turn)),
            prior_supporter_self_life_flag=any(SELF.search(s) for s in prior_support),
            rs_self_disclosure_in_top4=any('Self Disclosure' in r['content'] or 'Self-disclosure' in r['content'] for r in spec['inventory'][0]))
        for h,items in zip(('RS','MP','MS','ME'),spec['inventory']):
            rr[h+'_inventory']=len(items)
            if h=='RS': retrieved_rs_sources.update(s for r in items for s in r['source_ids'])
        prefix_rows.append(rr)
    write_csv(out,'rs_treatment_features.csv',rs_rows); write_csv(out,'prefix_features.csv',prefix_rows)
    stats['rs'] = dict(treatments=len(rs),families=dict(Counter(r['family'] for r in rs_rows)),
        self_disclosure_treatments=sum(r['self_disclosure'] for r in rs_rows),
        top4_prefixes_with_self_disclosure=sum(r['rs_self_disclosure_in_top4'] for r in prefix_rows),
        retrieved_source_overlap_with_exact_seed_matches=sorted(retrieved_rs_sources & seed_matches))
    stats['prefixes'] = dict(rows=len(prefix_rows),splits=dict(Counter(r['split'] for r in prefix_rows)),
        short_greeting_candidates=sum(r['short_greeting_candidate'] for r in prefix_rows),
        thanks_marker=sum(r['thanks_marker'] for r in prefix_rows),history_or_update_marker=sum(r['history_or_update_marker'] for r in prefix_rows),
        prior_supporter_self_life_candidates=sum(r['prior_supporter_self_life_flag'] for r in prefix_rows),
        last_turn_words=quantiles(r['last_turn_words'] for r in prefix_rows),
        deficient_inventory={h:sum(r[h+'_inventory']<4 for r in prefix_rows) for h in ('RS','MP','MS','ME')})
    sft=read(PATHS['sft'])['rows']; sft_rows=[]
    for r in sft:
        support=[m['content'] for m in r['messages'] if m['role']=='assistant']
        sft_rows.append(dict(request_id=r['request_id'],owner=r['owner'],split=r['split'],prefix_identity=r['prefix_identity'],
            counts=r['counts'],count_total=sum(r['counts']),same_head_repeat=max(r['counts'])>1,
            response_words=len(words(r['response'])),response_self_life_flag=bool(SELF.search(r['response'])),
            prefix_self_life_flag=any(SELF.search(t) for t in support),
            supplied_self_disclosure_rs=any(('Self Disclosure' in m['content'] or 'Self-disclosure' in m['content']) for m in r['messages'] if m['role']=='system')))
    write_csv(out,'sft_features.csv',sft_rows)
    stats['sft'] = {split:dict(rows=len(ss),owners=len({r['owner'] for r in ss}),prefixes=len({r['prefix_identity'] for r in ss}),
        resource_counts=dict(Counter(r['count_total'] for r in ss)),same_head_repeat_rows=sum(r['same_head_repeat'] for r in ss),
        response_words=quantiles(r['response_words'] for r in ss),response_self_life_candidates=sum(r['response_self_life_flag'] for r in ss),
        prefix_self_life_candidates=sum(r['prefix_self_life_flag'] for r in ss),rs_self_disclosure_rows=sum(r['supplied_self_disclosure_rs'] for r in ss))
        for split in ('train','dev') for ss in [[r for r in sft_rows if r['split']==split]]}

    # ESC role cards: evaluation-only. No role scenario content exported as training input.
    stats['esc_eval']={}
    for lang in ('en','zh'):
        cards=read(PATHS['esc_'+lang]); keys=[(r['language'],r['source'],str(r['id'])) for r in cards]
        stats['esc_eval'][lang]=dict(cards=len(cards),sources=dict(Counter(r['source'] for r in cards)),
            topic_labels=dict(Counter(r.get('res') for r in cards)),duplicate_keys=len(keys)-len(set(keys)),
            empty_base=sum(not r.get('base','').strip() for r in cards),base_words=quantiles(len(words(r.get('base',''))) for r in cards),
            active_primary_language=lang=='en')
    stats['esc_eval']['frozen_slices']=dict(Counter(r['analysis_slice'] for r in lines(PATHS['esc_overlap'])))
    write_json(out,'census.json',stats)
    print(json.dumps(stats,ensure_ascii=False,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--out',type=Path,default=OUT)
    main(parser.parse_args().out)
