#!/usr/bin/env python3
"""Record a complete, source-only AI development audit of the frozen 101 rows.

Citation sufficiency is separate from truth, durability and current relevance.
No generator outcomes or test answers enter these decisions.
"""
from collections import Counter
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest

PREV=PROJECT/'outputs/pm_rl1/executor_pilot_20260929_v1'
OUT=PROJECT/'outputs/pm_rl1/source_repair_20260929_v2'
SOURCE=PROJECT/'data/paper1_public_memory/es_memeval_public_multi_view_session_results_v1.jsonl'

# S: the cited new text reaffirms the full slot claim; P: only a component or
# context is supported; U: unrelated/absent; C: positive claim conflicts with
# the cited change. P/U do NOT say the old fact never existed.
DECISIONS=[
('U','HR uncertainty does not restate a six-month sleep duration.'),
('U','HR uncertainty does not restate a bedtime thinking preference.'),
('U','HR uncertainty does not establish living/working nearby or daily contact.'),
('U','Feeling betrayed does not establish proximity or daily contact.'),
('P','Therapy is praised, but attendance/personal-growth content is inherited rather than fully newly attested.'),
('P','Creative outlet is praised; painting antecedent needs additional current-session evidence.'),
('P','Ups and downs are mentioned, but mutual need for space/support is not reaffirmed.'),
('S','User explicitly again reports depression; this is self-report, not a clinical diagnosis or proof of durability.'),
('P','Argument with Bob does not by itself newly establish marital status.'),
('S','Returning to therapy and some benefit are explicitly stated.'),
('P','Jerry leaving after an argument does not establish being an ADULT son.'),
('S','Morning walks to clear the mind explicitly reaffirm the coping activity.'),
('P','George hospitalization does not reaffirm youngest-son role.'),
('S','Fear of being seen as incapable explicitly reaffirms the communication concern.'),
('P','Affection for deceased Max supports attachment but species/dog interest needs context.'),
('P','David moving in does not alone establish boyfriend role.'),
('P','Adopting Buddy is related but does not identify dog species or durable interest by itself.'),
('P','David providing support does not by itself reaffirm romantic role.'),
('P','David providing support does not by itself reaffirm romantic role.'),
('P','Living away for college does not establish graduate thesis program.'),
('P','A difficult class and grades do not establish graduate thesis program.'),
('P','Thesis presentation is confirmed; graduate level is not in the cited turn.'),
('P','Thesis draft is confirmed; graduate level is not in the cited turn.'),
('P','Thesis work is confirmed; graduate level is not in the cited turn.'),
('P','Progress/feedback has an unresolved antecedent; graduate level is not attested.'),
('P','Plans with Matthew do not by themselves identify a dating relationship.'),
('P','Thesis/advisor are explicit; graduate level remains inherited.'),
('P','Past thesis presentation does not prove current program or graduate level.'),
('P','Feeling off after memorial supports grief, not a durable health constraint or the full prolonged-sadness formulation.'),
('U','Seeing relatives after years does not establish residence in another state.'),
('U','Memorial attendance says nothing about living alone.'),
('U','Staying connected with family says nothing about living alone.'),
('U','Staying connected with family says nothing about their state of residence.'),
('P','A performance review establishes employment context, not project/team duties.'),
('S','Repeated supervisor criticism and never-enough effort support the stated strained work relationship.'),
('P','Tests and professors establish study context, not engineering field.'),
('P','Academic distress is explicit, but loneliness and durable-health status are not fully reaffirmed.'),
('P','Study/testing is explicit, but six classes are not.'),
('U','Rough time with friends does not establish six classes.'),
('U','Rough time with friends does not establish engineering studies.'),
('U','Rough time with friends does not reaffirm religious involvement.'),
('P','Friendship difficulty does not establish the full academic-stress/sadness/loneliness profile.'),
('U','Greeting does not reaffirm daily sleeping difficulty.'),
('P','Career/marrying-rich comparisons do not newly attest academic-success pressure.'),
('P','An ex is mentioned, but the name Nate requires additional source context.'),
('P','General overwhelm does not specifically establish academic stress or durability.'),
('P','Midterm failure does not establish multiple classes with group projects.'),
('U','Falling out with a classmate and an ex does not reaffirm friends supporting relationship matters.'),
('P','Midterm/classmate references do not establish group-project course load.'),
('P','Sharing writing struggles is helpful; writing itself as emotional outlet is not fully reaffirmed.'),
('U','Overwhelm after conflicts does not reaffirm a direct-communication preference.'),
('U','Overwhelm after conflicts does not reaffirm family academic expectations.'),
('P','Overwhelm is not the same as persistent overthinking and academic self-doubt.'),
('P','They listen/support is positive but the friendship antecedent needs current-session context.'),
('S','Being overwhelmed with midterm/classmate pressures supports self-reported academic stress, not durable-health ontology.'),
('P','An ex is mentioned, but Nate is not named in the selected evidence.'),
('U','Joining a writing workshop does not reaffirm multiple group-project courses.'),
('P','Daunting writing and failed-midterm thoughts support part of self-doubt, not the complete durable profile.'),
('S','Writing as an escape explicitly reaffirms emotional-outlet use.'),
('P','They remind me is supportive but needs friendship antecedent.'),
('S','Joining a writing workshop and benefit are explicit; does not certify continued enrollment indefinitely.'),
('P','Supportive online community does not establish a stable role with a trusted individual.'),
('P','University workload is explicit but group-project requirements are not.'),
('P','Requesting a conversation does not establish stable trusted-person/nonjudgmental relationship.'),
('S','Stress and difficulty focusing on studies explicitly support academic stress; durability remains unproven.'),
('P','Peer-comparison self-doubt supports part of the claim, not a clinical label or full persistent trigger formulation.'),
('P','Attending university in a past narrative does not alone certify current enrollment.'),
('P','Lack of university support is compatible with student status but current enrollment needs full context.'),
('S','Switching major clearly reaffirms university-study context.'),
('C','Physics no longer fitting is evidence of changed interest; cannot use an enduring-interest slot as current preference.'),
('U','A breakup statement does not reaffirm college enrollment.'),
('S','Explicit switch to psychology reaffirms the current major/interest.'),
('S','Explicit major switch reaffirms university-study context.'),
('P','Relationship with Sally is explicit; rekindling chronology is inherited, not re-established here.'),
('P','Major switch is mentioned without naming psychology.'),
('S','Now at university directly reaffirms current education level.'),
('U','Greeting does not reaffirm former physics interest.'),
('U','Greeting does not reaffirm a long-term friendship with Henry.'),
('P','A university club is related context but not direct confirmation of enrollment.'),
('U','Greeting does not reaffirm psychology major.'),
('P','She is supportive needs entity/relationship context and does not re-establish rekindling.'),
('P','New major is mentioned but not psychology specifically.'),
('P','Sally and emotional distance support relationship context; the full rekindled role is inherited.'),
('P','Better communication supports relationship continuity; romantic/rekindled interpretation requires source context.'),
('P','Academic improvement and a major change do not explicitly reaffirm psychology.'),
('P','Past-year major change does not itself re-establish current enrollment.'),
('U','Past-year major/family/friends context does not reaffirm health impairment.'),
('U','Professor outreach and academic stress do not reaffirm health-related impairment.'),
('P','Best friend moving is not enough to identify Henry as that person.'),
('P','Sally and distance are mentioned; full rekindled relationship claim is not newly evidenced.'),
('P','Studies and club do not themselves establish college level.'),
('P','Studies and club do not establish psychology major.'),
('U','Friends criticizing club involvement does not reaffirm psychology major.'),
('P','She is stable and has episodes requires entity and asthma antecedents; not a complete new diagnosis confirmation.'),
('P','Previous child health issues do not reaffirm asthma or its current status.'),
('C','How things ended with Lisa conflicts with presenting the earlier close friendship as current.'),
('U','Logically did what I could does not reaffirm a marriage timeline preference.'),
('P','Financial issues and Lisa fallout do not establish loans reducing venture savings or health-constraint status.'),
('U','Letting go does not establish an ongoing romantic relationship; a year ago also has an old temporal anchor.'),
('U','Lisa/money fallout is not evidence of a best friend affair; separate relationships are being conflated.'),
('P','Current self-described alcoholism supports alcohol concern, but workplace drinking/absences were in an earlier explicitly portrayed scenario, not reaffirmed here.'),
]

def main():
    census=json.loads((PREV/'source_census_private.json').read_text())
    if sha256_file(SOURCE)!=census['source_sha256']:raise ValueError('source changed')
    units={u['memory_id']:u for line in SOURCE.read_text().splitlines() for u in json.loads(line)['accepted_units']}
    assert len(DECISIONS)==len(census['reassertion_rows'])==101
    names={'S':'citation_sufficient','P':'citation_partial','U':'citation_unrelated','C':'citation_conflicts_with_current_slot'}
    rows=[]
    for i,(r,(label,note)) in enumerate(zip(census['reassertion_rows'],DECISIONS),1):
        prior,new=units[r['prior_id']],units[r['new_id']]
        assert prior['normalized_value']==new['normalized_value']
        rows.append(dict(index=i,owner=new['owner_id'],slot=new['profile_slot_key'],source_rank=new['source_session_rank'],
            prior_unit_id=prior['memory_id'],unit_id=new['memory_id'],prior_unit_identity=digest(prior),unit_identity=digest(new),
            normalized_value=new['normalized_value'],prior_date=prior['timestamp'],new_date=new['timestamp'],
            prior_spans=prior['supporting_spans'],new_spans=new['supporting_spans'],
            citation_status=names[label],rationale=note,
            source_disposition='retain_reassertion_subject_to_per_prefix_ontology_and_time_review' if label=='S' else 'suppress_unsupported_new_version_without_automatic_fallback',
            truth_of_earlier_fact='not decided by new-citation sufficiency alone',
            reviewer='Codex coordinator AI-assisted source-only review',independent_human_gold=False))
    result=dict(protocol='pm-rl1-profile-reassertion-source-audit-v2',source_sha256=sha256_file(SOURCE),
        census_sha256=sha256_file(PREV/'source_census_private.json'),script_sha256=sha256_file(Path(__file__)),
        scope='All 101 exact-value reassertions in prior pilot legal train/dev past; not all 1008 units or the full corpus.',
        counting='unit-level new-citation support, not population factual-error rate or generator quality',
        counts=dict(Counter(r['citation_status'] for r in rows)),rows=rows)
    with (OUT/'profile_reassertion_reviews.json').open('x') as f:f.write(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result['counts']))

if __name__=='__main__':main()
