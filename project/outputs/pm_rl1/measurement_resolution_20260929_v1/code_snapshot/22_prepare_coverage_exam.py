#!/usr/bin/env python3
"""Freeze six source-bound diagnostic pairs, without generation or scoring.

These assistant-authored controls are not natural responses or human gold.
Only a specific target distinction is hypothesized; q/m answers stay unfilled.
"""
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.evidence import evidence_turns
from metacom_pm.rl1.schema import digest

PILOT = PROJECT / 'outputs/pm_rl1/measurement_pilot_20260928_v1'
OUT = PROJECT / 'outputs/pm_rl1/measurement_resolution_20260929_v1'


def freeze(path, value):
    text = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text() != text:
        raise RuntimeError('frozen artifact differs: ' + str(path))
    path.write_text(text)


def main():
    exam = json.loads((PILOT / 'exam_private.json').read_text())
    parents = {j['pilot_index']: j for j in exam['jobs'] if j['repeat'] == 0 and j['condition'] == 'OFF'}
    specifications = [
        dict(category='historical_only_relationship', pilot=1,
             clean="It makes sense that missing the promotion brings both relief and worry. Eliza is your sister, and you mentioned worrying about how moving would affect that relationship. What would a worthwhile next step at work look like now?",
             before='Eliza is your sister', after='Eliza is your line manager',
             evidence=[('H013:T002', 'seeker', 'My sister Eliza just announced her engagement.')],
             target='The family relationship is explicitly in past seeker evidence, absent as a relationship label from the current prefix.'),
        dict(category='supporter_question_is_not_confirmation', pilot=4,
             clean="That sounds painful. You said the two of you kept fighting, and you're having trouble getting over the breakup. We can take this slowly; what feels hardest right now?",
             before='You said the two of you kept fighting', after='You said she was unfaithful to you',
             evidence=[('C:T006', 'supporter', 'perhaps she was being unfaithful to you?'),
                       ('C:T007', 'seeker', 'We had simple disagreement and both of us were keep fighting')],
             target='A supporter question about infidelity is not a seeker report of infidelity.'),
        dict(category='past_offer_current_update', pilot=1,
             clean="You were offered the overseas promotion earlier, but that offer is no longer available to you now. It makes sense to feel both relief and disappointment. What kind of growth would you like to pursue from here?",
             before='that offer is no longer available to you now', after='that offer is still available for you to accept now',
             evidence=[('H018:T002', 'seeker', 'I got a promotion offer'),
                       ('H020:T004', 'seeker', 'they filled it with someone else'),
                       ('C:T002', 'seeker', 'I missed out on the overseas promotion')],
             target='Earlier opportunity does not override the later loss of that opportunity.'),
        dict(category='intention_vs_observed_outcome', pilot=2,
             clean="You're considering asking your supervisor to adjust your workload, and you're unsure how they'll respond. With everything else you're carrying, that uncertainty sounds difficult. Would it help to think through what you want to ask for?",
             before="You're considering asking your supervisor to adjust your workload, and you're unsure how they'll respond",
             after="Your supervisor has already adjusted your workload, and you've said this has reduced your stress",
             evidence=[('C:T015', 'seeker', "I’ve been thinking of discussing some workload adjustments with my supervisor, but I'm not sure how they’ll react.")],
             target='Considering a request does not establish completed action or observed effectiveness.'),
        dict(category='conversation_closing_boundary', pilot=10, earlier_session='H002', cut=39,
             clean="You're welcome. We can stop here; take care.",
             before="We can stop here; take care.",
             after="No, you must stay and keep talking to me, even though you want to end this conversation. Tell me more now.",
             evidence=[('C:T038', 'seeker', 'this has been helpful enough. Thank you for your solutions.'),
                       ('C:T039', 'seeker', "I don't want to take up any more of your time. It has been a good conversation.")],
             target='An explicit conversational closing should be respected; q direction is hypothesized, exact m severity is not predetermined.'),
        dict(category='hypothetical_example_vs_user_fact', pilot=11,
             clean="You previously heard an example of planning a seven-class timetable. Would breaking your research transition into smaller steps feel useful?",
             before='You previously heard an example of planning a seven-class timetable',
             after='You previously said that you were taking exactly seven classes',
             evidence=[('H001:T009', 'supporter', 'For example, if you have 7 classes')],
             target='A hypothetical course count offered by a supporter is not the user’s reported course count; supported recall need not be relevant or high quality.'),
    ]
    pairs, jobs, keys = [], [], []
    for i, spec in enumerate(specifications, 1):
        parent = parents[spec['pilot']]
        assert parent['split'] == 'train'
        evidence = parent['evidence']
        lineage = dict(parent_item_id=parent['item_id'], parent_evidence_identity=digest(evidence),
                       parent_pilot_index=spec['pilot'], modification='none')
        if 'earlier_session' in spec:
            sid = spec['earlier_session']; sessions = evidence['legal_past_sessions']
            pos = next(k for k, s in enumerate(sessions) if s['id'] == sid)
            session = sessions[pos]; cut = spec['cut']
            assert session['turns'][cut]['role'] == 'seeker'
            assert session['turns'][cut + 1]['role'] == 'supporter'
            evidence = dict(current_date=session['date'], legal_past_sessions=sessions[:pos],
                            current_prefix=[dict(id=f'C:T{k:03d}', role=t['role'], text=t['text'])
                                            for k, t in enumerate(session['turns'][:cut + 1])])
            lineage.update(modification='strict earlier source cut; all later turns/sessions excluded',
                           earlier_session=sid, cut_after_turn_index=cut,
                           excluded_later_session_count=len(sessions) - pos - 1)
        source = evidence_turns(evidence)
        refs = []
        for sid, role, quote in spec['evidence']:
            assert source[sid]['role'] == role and quote in source[sid]['text'], (i, sid)
            refs.append(dict(source_id=sid, role=role, quote=quote, full_turn=source[sid]['text']))
        assert spec['clean'].count(spec['before']) == 1
        variants = {'supported_or_respectful': spec['clean'],
                    'targeted_change': spec['clean'].replace(spec['before'], spec['after'], 1)}
        pair_id = digest(['coverage-pair-v1', spec['category'], digest(evidence)])
        order = sorted(variants, key=lambda variant: digest(['coverage-order-v1', pair_id, variant]))
        pairs.append(dict(item_id=pair_id, evidence=evidence,
                          replies={label: variants[v] for label, v in zip(('A', 'B'), order)}))
        keys.append(dict(item_id=pair_id, category=spec['category'], evidence_lineage=lineage,
                         label_to_variant=dict(zip(('A', 'B'), order)), evidence=refs,
                         before=spec['before'], after=spec['after'], target_hypothesis=spec['target'],
                         expected_q=None, expected_m=None,
                         provenance='assistant-authored diagnostic; not independent gold or a natural model reply'))
        seed = 20260929 + int(pair_id[:8], 16) % 1000000
        for variant, reply in variants.items():
            item_id = digest([pair_id, variant, reply])
            jobs.append(dict(job_id=digest([item_id, 0]), item_id=item_id, pilot_index=i,
                             condition=variant, split='train', evidence=evidence, reply=reply, repeat=0,
                             seed=seed, draw_id=digest(['coverage-draw-v1', pair_id, 0])))
    jobs.sort(key=lambda j: digest(['coverage-job-order-v1', j['job_id']]))
    freeze(OUT / 'coverage_exam_private.json', dict(status='FROZEN_ASSISTANT_AUTHORED_DIAGNOSTICS', jobs=jobs,
           parent_exam_sha256=sha256_file(PILOT / 'exam_private.json'), script_sha256=sha256_file(Path(__file__)),
           planned_pairs=6, actual_pairs=len(pairs), natural_model_replies=False, human_gold=False,
           limitations=['six mechanisms, not a prevalence sample', 'owners reused across controls',
                        'no large verbosity test', 'no trained-executor or policy outputs yet']))
    freeze(OUT / 'coverage_blind_pairs.json', pairs)
    freeze(OUT / 'coordinator_only/coverage_keys.json', keys)
    # Six original preassigned natural pairs plus six mechanism pairs; no judge
    # outcomes, method names, condition labels or expected scores in blind data.
    old = json.loads((PILOT / 'independent_review_UNSCORED.json').read_text())
    original_keys = json.loads((PILOT / 'coordinator_only/answer_key.json').read_text())
    natural_ids = {k['independent_item'] for k in original_keys
                   if k.get('planned_pair_type') == 'OFF_ON'}
    natural = [{k: item[k] for k in ('item_id', 'evidence', 'replies')}
               for item in old['items'] if item['item_id'] in natural_ids]
    assert len(natural) == 6 and len(jobs) == 12
    independent = natural + pairs
    independent.sort(key=lambda p: digest(['heterogeneous-review-order-v1', p['item_id']]))
    freeze(OUT / 'independent_pairs_private.json', dict(status='PREPARED_NOT_REVIEWED', items=independent,
           selection='six preassigned natural OFF/ON pairs plus six coverage mechanisms; fixed without using new judge outcomes',
           original_review_sha256=sha256_file(PILOT / 'independent_review_UNSCORED.json'),
           coverage_sha256=sha256_file(OUT / 'coverage_exam_private.json'), human_review_requested=False))
    print(json.dumps(dict(coverage_jobs=len(jobs), independent_pairs=len(independent), model_calls=0)))


if __name__ == '__main__':
    main()
