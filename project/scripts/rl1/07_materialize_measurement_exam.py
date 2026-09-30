#!/usr/bin/env python3
"""Bind real replies, inspectable single edits, mild style controls and blind jobs.

Controls are coordinator-authored development diagnostics, not independent human
gold. Missing usable factual assertions are not replaced with invented baselines.
"""
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.evidence import evidence_turns
from metacom_pm.rl1.judge import RUBRIC_ID
from metacom_pm.rl1.schema import digest

OUT = PROJECT / 'outputs/pm_rl1/measurement_pilot_20260928_v1'
# One factual proposition per reply; full text and exact before/after retained.
# Target-claim support is checked against source below, not against model scores.
EDITS = {
 1: ("you're relieved about not having to move", "you're disappointed about not having to move", 'C:T014', "relieved I don't have to move overseas", 'current stated emotion reversed'),
 2: ('feel uncertain about how your supervisor will respond', 'feel certain about how your supervisor will respond', 'C:T015', "I'm not sure how they’ll react", 'explicit uncertainty reversed'),
 4: ('when it feels like it ended on a bad note', 'when you said it ended amicably', 'C:T007', 'We had simple disagreement and both of us were keep fighting', 'conflict misrepresented as an amicable ending'),
 5: ('share those kinds of feelings and concerns with your siblings', 'share those kinds of feelings and concerns with your parents', 'C:T000', 'I talked to my siblings today', 'recipient of the disclosed feelings changed'),
 6: ("you're making a conscious effort to shift your focus now", "you've already reconciled with your father in person", 'C:T009', 'It makes me sad we never got to try', 'working through regrets replaced by a reconciliation they never achieved'),
 9: ("you've already seen the benefits in other areas of your life", "you've never seen any benefits in other areas of your life", 'C:T016', 'My sessions have been helping a lot with stress and career stuff', 'reported therapy benefit negated'),
 10: ('when leaving behind familiar places and people', 'after spending your entire life in Sydney', 'C:T007', 'my recent move to Sydney', 'recent relocation replaced with a lifelong residence'),
 11: ('aligned with your values', 'in conflict with your values', 'C:T007', 'aligns with my values', 'explicit values alignment reversed'),
 12: ("you're almost an adult", "you're already 25 years old", 'C:T013', 'I am 17', 'age changed from seventeen to twenty-five'),
}
EXPAND = {"It's":"It is", "it's":"it is", "That's":"That is", "that's":"that is",
    "you're":"you are", "You've":"You have", "you've":"you have", "I'm":"I am",
    "What's":"What is", "what's":"what is", "don't":"do not", "That's":"That is",
    "they're":"they are", "that's":"that is", "It's":"It is"}


def freeze(path, value):
    text = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text() != text:
        raise RuntimeError('frozen file differs: ' + str(path))
    path.write_text(text)


def style(text):
    # Expansions selected only where these contractions mean is/are/have.
    # No novel advice, emotion, fact, certainty, question or speech act is added.
    expanded = re.sub(r"\b(?:" + '|'.join(re.escape(x) for x in EXPAND) + r")\b", lambda m: EXPAND[m.group()], text)
    return re.sub(r'(?<=[.!?]) +', '\n\n', expanded)


def main():
    ptr = json.loads((OUT/'generation_pointer.json').read_text()); run = Path(ptr['run_dir'])
    assert sha256_file(run/'summary.json') == ptr['summary_sha256']
    rows = json.loads((run/'summary.json').read_text())['rows']
    roster = json.loads((OUT/'input_freeze.json').read_text())['rows']
    evidence = {r['prefix_identity']:r['evidence'] for r in json.loads((OUT/'legal_evidence_private.json').read_text())}
    items, controls, missing, jobs, pairs, key = [], [], [], [], [], []
    conditions = ['OFF', 'ON', 'damage', 'style']
    for r in roster:
        i, pid = r['pilot_index'], r['prefix_identity']; e = evidence[pid]
        replies = {}
        for arm in ('OFF','ON'):
            row = next(x for x in rows if x['pilot_index']==i and x['arm']==arm)
            raw = json.loads((run/(row['request_id']+'.response.json')).read_text())
            assert raw['finish_reason']=='natural_stop'
            replies[arm] = raw['text']
            key.append(dict(pilot_index=i, condition=arm, generation_request_id=row['request_id'],
                prefix_identity=pid, response_identity=digest(raw['text']), source_sha256=sha256_file(run/(row['request_id']+'.response.json'))))
        base = replies['OFF']
        if i in EDITS:
            before, after, sid, quote, purpose = EDITS[i]
            assert base.count(before)==1 and quote in evidence_turns(e)[sid]['text']
            changed=base.replace(before,after,1)
            replies['damage']=changed
            controls.append(dict(pilot_index=i, condition='damage', base_condition='OFF',
                before=before, after=after, original_range=[base.index(before),base.index(before)+len(before)],
                source_id=sid, source_quote=quote, purpose=purpose,
                expected_target_relation='contradicted_current_seeker_statement',
                expected_q=None, expected_m=None,
                qualification='coding-assistant-authored targeted fact edit; independent semantic review pending',
                entire_original_is_gold=False))
        else:
            missing.append(dict(pilot_index=i, condition='damage', reason='No suitably specific literal personal-fact assertion selected from the natural OFF; do not manufacture a supposedly clean baseline.'))
        replies['style']=style(base)
        assert replies['style']!=base
        controls.append(dict(pilot_index=i, condition='style', base_condition='OFF',
            transformation='expand unambiguous contractions and add sentence paragraph breaks',
            original_words=len(base.split()), modified_words=len(replies['style'].split()),
            qualification='mild wording/format check only; does not test large verbosity or new-content bias',
            semantic_check='identical propositions, questions, suggestions and uncertainty; only recorded expansions and whitespace'))
        for c in conditions:
            if c not in replies: continue
            item_id=digest(['rl1-pilot-item-v1',pid,c])
            items.append(dict(item_id=item_id,pilot_index=i,condition=c,split='train',prefix_identity=pid,
                evidence=e,reply=replies[c],reply_identity=digest(replies[c])))
            seed=20260928+int(digest(['rl1-pilot-seed-v1',pid])[:8],16)%1000000
            for repeat in [0,1] if conditions[r['repeat_condition_index']]==c else [0]:
                jobs.append(dict(job_id=digest([item_id,repeat]), item_id=item_id,pilot_index=i,
                    condition=c,split='train',evidence=e,reply=replies[c],repeat=repeat,
                    seed=seed+repeat*1000001,draw_id=digest(['rl1-measurement-draw-v1',pid,repeat])))
        repeat_condition=conditions[r['repeat_condition_index']]
        if repeat_condition not in replies:
            missing.append(dict(pilot_index=i,condition='repeat',missing_selected_condition=repeat_condition,reason='Preselected condition unavailable; no outcome-based replacement.'))
        ca,cb=('OFF','ON') if r['independent_pair_type']=='OFF_ON' else ('OFF','damage') if r['independent_pair_type']=='original_damage' else ('OFF','style')
        if cb not in replies:
            missing.append(dict(pilot_index=i,condition='independent_review',reason='Preselected diagnostic pair unavailable; no replacement.'))
        else:
            order=sorted([ca,cb],key=lambda c:digest(['rl1-independent-order-v1',pid,c]))
            pairid=digest(['rl1-independent-pair-v1',pid])[:20]
            pairs.append(dict(item_id=pairid,evidence=e,replies={label:replies[c] for label,c in zip(['A','B'],order)},
                review=dict(q_A=None,m_A=None,q_B=None,m_B=None,pairwise=None,evidence=[],uncertainty=None,reviewer_identity=None)))
            key.append(dict(independent_item=pairid,pilot_index=i,prefix_identity=pid,
                label_to_condition=dict(zip(['A','B'],order)),planned_pair_type=r['independent_pair_type']))
    # Hash order prevents consecutive condition/repeat runs; no score-dependent order.
    jobs.sort(key=lambda j:digest(['rl1-measurement-job-order-v1',j['job_id']]))
    pairs.sort(key=lambda p:digest(['rl1-independent-display-order-v1',p['item_id']]))
    freeze(OUT/'coordinator_only/controls_and_missing.json',dict(controls=controls,missing=missing))
    freeze(OUT/'coordinator_only/answer_key.json',key)
    freeze(OUT/'exam_private.json',dict(status='FROZEN_DEVELOPMENT_MEASUREMENT_EXAM',rubric_identity=RUBRIC_ID,
        generation_summary_sha256=ptr['summary_sha256'],script_sha256=sha256_file(Path(__file__)),
        planned_items=48,actual_items=len(items),planned_repeats=12,actual_repeats=len(jobs)-len(items),
        items=items,jobs=jobs,limitations=['assistant-constructed controls, no independent gold yet',
            'damage targets current facts; historical-only facts and retrieval/compilation attribution need separate review',
            'style is mild wording/format change; not a comprehensive verbosity test',
            'scores remain measurement candidates, never automatic training rewards']))
    freeze(OUT/'independent_review_UNSCORED.json',dict(status='PENDING_INDEPENDENT_REVIEW',
        original_language='English; no unvalidated translation changes the evidence',
        blinded=True,planned_pairs=12,available_pairs=len(pairs),missing_pairs=12-len(pairs),items=pairs))
    print(json.dumps(dict(natural_replies=24,damage_controls=len(EDITS),style_controls=12,
        single_reply_items=len(items),actual_judge_jobs=len(jobs),independent_pairs=len(pairs),missing=missing),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
