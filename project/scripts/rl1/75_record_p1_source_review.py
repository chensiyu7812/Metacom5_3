#!/usr/bin/env python3
"""Persist the coordinator's finite source-only review, never human gold.

Train/dev only. Existing 101 decisions and raw sources remain unchanged.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest

OUT = PROJECT/'outputs/pm_rl1/completion_20260930_v2/P1'
MP_DECISIONS = [
('P','Feedback validates feelings; writing itself as a processing method is not fully reaffirmed.'),
('P','A blog is mentioned, but its mental-health topic is not reaffirmed.'),
('P','Jerry returned home; his son/older-child role is not in the cited turn.'),
('P','Lily being away does not reaffirm a current romantic/childhood-best-friend relationship or prove a breakup.'),
('U','University acceptance does not establish age 18.'),
('U','University acceptance does not establish a short attention span.'),
('U','University acceptance does not reaffirm learning difficulties.'),
('U','University acceptance does not establish family reasons for valuing education.'),
('U','University acceptance does not establish father occupation.'),
('U','University acceptance does not establish tutoring-club membership.'),
('U','University acceptance does not establish an art interest.'),
('U','University acceptance does not establish a reading interest.'),
('U','University acceptance does not establish a writing interest.'),
('U','University acceptance does not establish sibling-time preference.'),
('U','University acceptance does not establish a revision-method preference.'),
('P','Video call and missing Lily establish contact, not the full romantic/childhood-friend role.'),
('P','Sally is explicitly a new friend; school affiliation is not in the cited turn.'),
('P','Buddy brings joy; dog species and the full dog-lover claim are not reaffirmed.'),
('P','David provides support; boyfriend status is not directly reaffirmed.'),
('P','Work is mentioned but being on leave is not reaffirmed; work mention alone does not prove return either.'),
('P','David is supportive; the cited turn does not establish boyfriend status.'),
('P','An argument with Lily does not establish sister role or recent reconnection.'),
('P','Buddy is a pet and brings joy; dog species is not in the cited turn.'),
('P','Tension with David does not alone specify boyfriend role.'),
('P','Thesis is mentioned, but graduate level/current program are not fully reaffirmed.'),
('P','Thesis draft/advisor are explicit; graduate level is not.'),
('S','Matthew is named as the person in the strained relationship; no new duration claim is added.'),
('P','Graduate school is explicit; the thesis component is not in this citation.'),
('P','Conversation with Matthew does not alone identify his partner role.'),
('P','A reconnection trip with Matthew is related, but exact partner role needs context.'),
('S','Both thesis and graduate school are explicitly reaffirmed.'),
('P','Breakup last October is explicit, but three-year relationship duration is not reaffirmed.'),
('S','Supervisor undermining efforts and withholding recognition support the strained work relationship.'),
('P','A breakup is recalled, but duration/recency/full current status are not reaffirmed.'),
('P','Friend loss and persisting distress are explicit; the whole academic-stress/sadness/loneliness formulation is not.'),
('U','A generic rough period does not newly establish academic stress, sadness and loneliness.'),
('P','Conflict with Jenny does not by itself identify spouse/committed-partner status.'),
('P','Isolation, advisor pressure and relationship tension support parts of the composite claim; full emotional-exhaustion formulation remains inferred.'),
('P','Family-plan disagreement supports relationship tension, not full marriage/committed-role confirmation.'),
('P','Thesis advisor does not establish engineering field.'),
('P','Thesis advisor does not establish a six-class course load.'),
('P','Mother health relapse adds burden; ongoing caregiving role is not directly stated.'),
('P','Annie is supportive, but sister relationship is not reaffirmed in the citation.'),
('P','Mother illness adds stress; direct ongoing caregiving role is not established.'),
('P','Annie provides support; sister role is not in the cited text.'),
('S','Professor/effort difficulties and distress explicitly support academic-stress self-report, not a clinical diagnosis.'),
('S','Anxiety about studies, failed midterm and slipping grades support academic-stress self-report.'),
('P','Seeking conversation and relief are explicit; stable trusted/nonjudgmental relationship is not fully established.'),
('P','Writing and supportive online community are explicit; the full sharing-experiences formulation is not.'),
('S','School struggle and slipping grades explicitly support academic stress.'),
('P','Workshops and writing prompts are explicit; enrollment specifically to address writer block is not.'),
('P','Self-labelled imposter syndrome and peer comparison are explicit; the full academic-trigger formulation is not.'),
('P','A changed major is mentioned without naming psychology.'),
('P','Emily health is mentioned without asthma diagnosis or child role.'),
('P','Financial problems do not specifically establish inability to afford therapy.'),
('P','Emily health is improving; asthma diagnosis and child role are not reaffirmed.'),
('U','A heavy period does not establish a job layoff.'),
('P','Reconciliation with an unnamed woman is explicit; sister Eliza and wedding context are not reaffirmed.'),
('S','Alcohol concerns and attending AA are directly reported.'),
('P','Bob is a helpful understanding friend; this citation does not explicitly establish AA as their meeting source.'),
('P','Relapse/guilt concerns alcohol, but attendance at AA is not reaffirmed.'),
('P','Hiking is completed; renewed intention to run is a different action and is not reaffirmed.'),
('S','Bob is explicitly a supportive friend from AA.'),
('U','Wanting a fresh place does not establish impatience about healing speed.'),
('P','Fresh-start motive is stated; Sydney destination and uncertainty about relocation effects are not in these citations.'),
('P','Work is mentioned, not gig-employment type.'),
('P','Back pain and anxiety coexist; chronic stress as the cause is not established.'),
('P','Back pain and anxiety coexist; stress causation is not established.'),
('P','An isolating job does not establish gig-employment type.'),
('S','Brother providing financial help directly evidences family contact at this time.'),
('P','Past back pain is recalled, not confirmed current pain caused by chronic stress.'),
('S','Fear of another falling out explicitly supports difficulty reaching out after conflict.'),
]

# summary, stage of the stated action (not all events), observed result, extra
# same-session context turn indices, reason. A proposal is never completion.
ME_DECISIONS = [
('Considered couples therapy; concerned about Jane\'s reaction.', 'intention', None, [16], 'Concern about a future reaction is not an observed therapy result.'),
('Reported that talking about struggles helped.', 'completed', 'Reported feeling more optimistic.', [], 'Self-reported immediate benefit, not lasting improvement.'),
('Planned to catch Mike after lunch the following day.', 'intention', None, [], 'No completed conversation or improved preparedness is attested.'),
('Added suggested snacks and trail mix to an online cart.', 'completed', None, [], 'Cart addition occurred; delivery in one hour is expected, not observed.'),
('Reported sorting out an earlier difficulty with a friend.', 'completed', 'Reported that things were sorted out and was glad to have persisted.', [12], 'Retrospective self-report; no clinical or permanent success claim.'),
('Performed at a poetry slam and received applause.', 'completed', 'Reported increased confidence after applause.', [], 'Confidence is explicit; pride is not added.'),
('Agreed to try the suggested practice.', 'intention', None, [], 'Agreement and optimism are not practice or an observed result.'),
('Wanted to switch to activities other than work.', 'intention', None, [], 'Desire is not implementation.'),
('Reported taking extra classes while parental pressure continued.', 'attempted', 'Reported that pressure continued despite taking extra classes.', [], 'Ongoing attempt; continued pressure is self-report, not proof of ineffectiveness for all goals.'),
('Considered talking to the manager about concerns.', 'intention', None, [], 'Should probably talk soon is prospective.'),
('Requested video links for yoga and meditation.', 'completed', None, [], 'Request occurred; actually practicing the activities is not established.'),
('Considered sharing feelings with spouse over a quiet dinner.', 'intention', None, [], 'A proposed conversation is not a completed one.'),
('Reported trying meditation or walks when possible.', 'attempted', 'Reported that it helped a little.', [], 'Source contains a limited subjective result omitted by the old outcome field.'),
('Reported trying to write in a journal each night.', 'attempted', 'Putting thoughts on paper helped, while anxiety sometimes remained too strong.', [9], 'Preserve both limited benefit and remaining difficulty; journal antecedent added from source.'),
('Reported trying walks for relief.', 'attempted', 'Reported that it had not helped much.', [], 'Source contains limited/non-benefit omitted by old outcome field.'),
('Reported a person\'s cold, asthma and associated labored breathing.', 'not_applicable', None, [], 'Do not assign another person\'s health condition to the seeker or certify a diagnosis.'),
('Talked to family and reported being listened to.', 'completed', 'Reported relief in some ways.', [2], 'Limited subjective support result was omitted in the old field.'),
('Reported a recent drinking slip-up and a difficult reaction from another person.', 'not_applicable', None, [], 'Retain reported event without inferring treatment outcome.'),
('Considered temporarily not speaking to parents as a worst-case possibility.', 'hypothetical', None, [], 'Worst-case speculation is not an action already taken.'),
('Reported overhearing friends criticize club involvement and feeling hurt.', 'not_applicable', None, [], 'Keep reported speech and feeling without adding a personal identity.'),
('Considered allowing feelings rather than always using distraction.', 'intention', None, [], 'Tentative reflection does not establish an implemented change or benefit.'),
('Reported the boss making unwanted advances toward a coworker.', 'not_applicable', None, [], 'The boss/coworker are distinct from the reporting seeker.'),
('Reported that their mother had a health relapse.', 'not_applicable', None, [], 'Do not turn mother health into seeker health.'),
('Reported that friends had distanced themselves and bullied them.', 'not_applicable', None, [], 'Retain seeker account without adding an independently verified interpretation.'),
]


def save(path, obj):
    content = json.dumps(obj, ensure_ascii=False, indent=2)+'\n'
    if path.exists():
        if path.read_text() != content:
            raise RuntimeError('Refusing changed existing artifact: '+str(path))
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def main(out):
    source = PROJECT/'data/paper1_public_memory/es_memeval_public_multi_view_session_results_v1.jsonl'
    raw_path = PROJECT/'data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json'
    units = {u['memory_id']:u for line in source.read_text().splitlines() for u in json.loads(line)['accepted_units']}
    users = {u['owner_id']:u for u in json.loads(raw_path.read_text())['users']}
    queue = json.loads((out/'mp_review_queue_private.json').read_text())
    if sha256_file(out/'mp_review_queue_private.json')!='15ed18bbeb40ffc5fa6cce27d6c8433773a87994c242b2fa6f2cbb5f740c6b1f':
        raise ValueError('MP review queue identity/order changed')
    assert len(queue)==len(MP_DECISIONS)==72
    names={'S':'citation_sufficient','P':'citation_partial','U':'citation_unrelated'}
    rows=[]
    for q,(label,why) in zip(queue,MP_DECISIONS):
        assert q['split'] in ('train','dev') and not q['reviewed']
        u,prior=units[q['unit_id']],units[q['prior_unit_id']]
        assert u['supporting_spans']==q['spans'] and u['normalized_value']==prior['normalized_value']
        rows.append(dict(unit_id=u['memory_id'], unit_identity=digest(u), owner=u['owner_id'],
            slot=u['profile_slot_key'], source_rank=u['source_session_rank'],
            prior_unit_id=prior['memory_id'], prior_unit_identity=digest(prior),
            citation_status=names[label], rationale=why, new_spans=u['supporting_spans'],
            source_disposition='retain_past_report_not_current_truth' if label=='S' else 'suppress_unsupported_new_version_without_automatic_fallback',
            reviewer='Codex coordinator source-only AI review', independent_human_gold=False))
    old=json.loads((PROJECT/'outputs/pm_rl1/source_repair_20260929_v2/source_overlay_private.json').read_text())
    assert old['source_sha256']==sha256_file(source) and old['raw_sha256']==sha256_file(raw_path)
    overlay=dict(old, version='pm-rl1-source-overlay-p1-20261001-v1',
        inherited_overlay_identity=digest(old), unit_reviews=old['unit_reviews']+rows)
    assert len(overlay['unit_reviews'])==len({r['unit_id'] for r in overlay['unit_reviews']})==173
    me_queue=json.loads((out/'me_review_queue_private.json').read_text())
    if sha256_file(out/'me_review_queue_private.json')!='4c84a91383c12f4b019a22adfbf78f9d7ac2834170c9cb4936781f31be142613':
        raise ValueError('ME review queue identity/order changed')
    assert len(me_queue['rows'])==len(ME_DECISIONS)==24
    me=[]
    for q,(summary,stage,outcome,extra,why) in zip(me_queue['rows'],ME_DECISIONS):
        u=q['unit']; assert units[u['memory_id']]==u
        session=next(s for s in users[u['owner_id']]['sessions'] if s['session_id']==u['source_session_id'])
        turns={t['idx']:t for t in session['turns']}
        for span in u['supporting_spans']:
            assert turns[span['turn_index']]['content'][span['start_char']:span['end_char']]==span['exact_text']
        me.append(dict(unit_id=u['memory_id'],unit_identity=digest(u),source_rank=u['source_session_rank'],
            summary=summary,action_stage=stage,observed_outcome=outcome,
            context_evidence=[dict(turn_index=i,role=turns[i]['role'],text=turns[i]['content']) for i in extra],
            rationale=why, reviewer='Codex coordinator source-only AI review',independent_human_gold=False))
    save(out/'source_overlay_private.json',overlay)
    save(out/'source_review_registry.json',dict(version='pm-rl1-p1-source-review-v1',
        source_sha256=sha256_file(source),raw_sha256=sha256_file(raw_path),
        mp_queue_sha256=sha256_file(out/'mp_review_queue_private.json'),
        me_queue_sha256=sha256_file(out/'me_review_queue_private.json'),
        mp=rows,me=me,mp_counts=dict(Counter(r['citation_status'] for r in rows)),
        me_stage_counts=dict(Counter(r['action_stage'] for r in me)),
        raw_sources_modified=False,human_labels=0,api_usd=0,
        limits='Finite development source audit. Unreviewed is not approved; source citation support is not truth/currentness. No test semantic review.'))
    print(json.dumps(dict(mp=len(rows),mp_counts=dict(Counter(r['citation_status'] for r in rows)),me=len(me),total_mp=len(overlay['unit_reviews'])),ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=OUT)
    main(parser.parse_args().out)
