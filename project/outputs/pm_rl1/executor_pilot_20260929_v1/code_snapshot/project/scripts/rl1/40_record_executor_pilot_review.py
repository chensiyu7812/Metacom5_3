#!/usr/bin/env python3
"""Record the coordinator's explicit read-through decisions, not a model grader.

The decision table below was written after inspecting all 108 original replies,
all visible inputs and the cited source excerpts. No score threshold is used.
"""
from collections import Counter
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.executor_pilot import admitted_rows
OUT=PROJECT/'outputs/pm_rl1/executor_pilot_20260929_v1'

# Within each prefix: OFF17, OFF29, R17, R29, L17, L29.
# A=accept, R=reject, U=uncertain. These are AI-assisted weak judgments.
DECISIONS={
1:[('A','Reflects the current academic improvement and overload; backpack is a metaphor, not a personal event.'),
   ('A','Study changes, goals and breakup are explicitly in C:T003–009; offers venting without new facts.'),
   ('A','Earlier family/friend issues are supported by H021:T003/T015; question does not assume they remain the main issue.'),
   ('A','Asks about coping without inventing a historical success.'),
   ('R','Changes friends upset about the club into someone FROM the club; H024:T003/T013/T015 do not support that entity relation.'),
   ('A','No forced club detail or invented history; offers breakup/venting discussion. Unprompted Chinese word is a style weakness, not a factual failure.')],
2:[('A','Responds to request for company; calming invitation is generic, not a factual diagnosis.'),
   ('R','Introduces crisis/harm framing and a lengthy disclaimer without a risk cue in the current request; unsuitable weak target for this turn.'),
   ('A','Open invitation fits request to talk; no hidden history.'),('A','Open invitation and need for connection fit current request.'),
   ('A','Ignores old friends/family consultations appropriately.'),('A','Tentative overwhelm and open invitation; no imported personal facts.')],
3:[('A','Supports the explicit plan for lighter exploration and asks about manageable confidence building.'),
   ('A','Browsing listings is a proposed option, not an assertion of completed action.'),
   ('A','Supportive coworker and improved collaboration are current C:T014–016; not evidence of additional memory uptake.'),
   ('A','Resume reflection is offered tentatively and remains compatible with light exploration.'),
   ('A','Coworker support is current evidence; ignores the unsupported interview-anxiety strategy.'),
   ('A','Encouragement grounded in current setbacks; resilience language is reassurance, not a claim of future guaranteed success.')],
4:[('A','Offers listening and choice; no invented cause for rough week. Longer wording is not automatically better.'),
   ('A','Open listening/distraction choice; no added personal history.'),('A','Feeling inquiry matches vague request to talk.'),
   ('A','Feeling inquiry without diagnosing a cause.'),
   ('A','Anxiety techniques are offered as an optional alternative, not asserted as a current condition; mild topic-steering limitation.'),
   ('A','Optional techniques are consistent with the visible preference but not evidence of present anxiety or historical outcome.')],
5:[('A','Metaphor and question about Jerry acknowledging issues do not assert that he has done so; binary framing is a quality limitation.'),
   ('A','Question about prior arguments preserves the current fact that Jerry has returned.'),
   ('R','You have taken the step of having him come back attributes agency not established in C:T002–006 or the profile.'),
   ('A','Explores triggers without asserting the cause or an already successful repair.'),
   ('R','Both ready to try again is not established by a brief text or return; intention/outcome overreach.'),
   ('A','Past text and longing are supported by H016:T017; asks current interpretation without saying Jerry is still away.')],
6:[('A','Reflects expressed fascination/apprehension and asks about reactions; no invented interaction outcome.'),
   ('A','Brain/heart language is a metaphor; asks rather than asserts projection. Leading alternatives are a style limitation.'),
   ('A','Responds to current infidelity-linked pain; no new journal/therapy claims.'),('A','Asks about interaction without asserting the user distanced or engaged.'),
   ('A','Tentative protective reaction question; ignores the unverified current-friend slot.'),
   ('R','Given how close you are with your long-time friend refreshes a stale profile. The source H010:T015 describes how things ended with Lisa; H005–H012 record loss, not a currently close available confidant.')],
7:[('A','Respects explicit therapy plan; tentative possible benefit, no assertion that closure already happened.'),
   ('A','Keeps contact with Alex optional and on user terms.'),('A','Therapy for stress/career is current C:T016; no incremental historical claim.'),
   ('A','Uncertainty about breakup is already in current prefix; respects therapy-first choice.'),
   ('A','Does not force retrieved direct-contact suggestion; asks about chosen therapist discussion.'),
   ('A','Optional preparation for therapy respects the boundary; a question about difficulty does not assert such difficulty exists.')],
8:[('A','Recognizes relocation/pay constraints. Luck-versus-resources framing is limiting, but is a question about experience, not an asserted personal failure.'),
   ('R','Break the cycle of waiting presumes passivity despite C:T011 explicitly reporting ongoing search.'),
   ('R','Converts previously considered recruiter/job-counselor advice into reaching out having made a difference. esc682 reports relief at suggestions, not completed outreach.'),
   ('A','Offers possible local career support without asserting prior use or success.'),
   ('R','Forces the quick-trust profile into a work/relocation question and adds usually working through things on your own, which is not established.'),
   ('A','Asks about available support without asserting a friend/mentor exists.')],
9:[('A','Current name and rough day are visible; open listening choice.'),('A','Current rough day; user controls topic.'),
   ('A','Permission/open invitation fits request.'),('A','Brief open invitation is sufficient; length is not a quality requirement.'),
   ('A','Does not surface unrelated alcohol history.'),('A','Does not import unrelated alcohol-help event.')],
10:[('A','Appropriate greeting; no hidden profile.'),('A','Greeting with open invitation.'),('A','Greeting with open invitation.'),
    ('A','Greeting with open invitation.'),('A','Does not impose religious framing.'),('A','Does not impose religious framing.')],
11:[('A','Survival-mode wording is explicitly speculative/metaphorical, not a diagnosis; asks about current support. Psychological explanation is a quality caveat.'),
    ('R','States a specific brain/emotion cause for time-management difficulty as fact rather than tentative reflection.'),
    ('A','Offers space or later discussion without forcing immediate parental contact.'),
    ('R','Asks whether tension affects studying after C:T008 already says the argument is distracting; weak attentiveness target.'),
    ('A','Small break is suggested, not claimed to have occurred or worked.'),
    ('A','Past lack of support and anxiety are explicit H001:T020; asks whether current tension adds to that feeling without conflating friends and parents.')],
12:[('A','Welcomes talking; no panic diagnosis.'),('A','Welcomes talking without invented current facts.'),
    ('A','Open inquiry fits the stated request.'),('A','Open inquiry fits the stated request.'),
    ('A','Ignores stale panic-attack detail.'),('A','Does not assume a current panic attack.')],
13:[('U','No invented personal story, but avoids the user question asking how the assistant handled the previously claimed experience; adequacy is uncertain.'),
    ('A','Explicitly corrects assistant personal-experience premise; offers optional suggestions and preserves user autonomy. Long wording is a limitation.'),
    ('R','Imports this trip and ongoing month-long discussion into current friend-choice conflict; H002:T004/T010 are an earlier June episode, current date July 1.'),
    ('U','Past trip discussions exist but present-perfect this trip blends earlier episode with current mother/friends issue; cannot certify temporal/task fit.'),
    ('A','Addresses mother rather than following the unsuitable friends strategy; no new self-disclosure.'),
    ('A','Keeps focus on mother and autonomy, not an invented assistant experience.')],
14:[('A','Acknowledges closure; effort/resilience refers to current thesis/group difficulties without claiming completion.'),
    ('A','Supportive closure; no invented scholarship success.'),('A','Respects thanks and closure without importing extra history.'),
    ('R','You have a strong support system around you is not established by the visible current prefix or the supplied thesis event.'),
    ('A','Does not invent personal scholarship experience; closing choice remains optional.'),
    ('A','Reassurance, not a report of a guaranteed future result; no invented personal experience.')],
15:[('A','Asks about sharing new posts/art; knowing friend found the blog does not establish deliberate sharing of new work. Some repetition risk.'),
    ('A','Therapist, supportive college friend, art and blog are all current evidence.'),
    ('A','Focuses on current creative priorities; does not conflate colleague and college friend.'),
    ('A','Sharing question has some redundancy given blog discovery, but no assertion or relationship conflation.'),
    ('A','Respects creative priorities rather than generic busyness.'),('A','Asks about processing feelings without adding commitments.')],
16:[('U','Hand-holding, feeding and listening examples are attached to you are providing; unclear whether illustrative advice or asserted actual care, so not admitted.'),
    ('A','Small-task option is clearly a suggestion, not a claim of past action.'),
    ('A','General reassurance about presence/care is not treated as a measured claim about mother\'s reaction; specific work/care context is current.'),
    ('A','Current C:T005/T007 supports work/care and talking with family; no novel historical uptake claimed.'),
    ('U','Sleep problem exists in older H001, but MP attaches it to H003 greeting and reply says recently. Recency/current persistence not established.'),
    ('A','Uses only current caregiving/work facts and ignores questionable sleep refresh.')],
17:[('A','User explicitly requests advice; optional record/support suggestions are not completed-action claims. Verbosity and overidentification are limitations.'),
    ('A','Advice matches explicit request; documentation is conditional. Do not equate the user\'s report with independently proven workplace facts.'),
    ('A','Asks about support and next steps without importing sleep history.'),
    ('A','Frames perceived injustice and asks about existing support; no invented outreach.'),
    ('R','Imports sleep difficulties and late nights into a favoritism question using an ungrounded refreshed MP; current sleep pattern is not established.'),
    ('R','Trouble sleeping lately relies on the same false source refresh; changes topic to evenings without current support.')],
18:[('R','Says rather than fearing another setback despite C:T008 explicitly expressing fear of worse leadership.'),
    ('A','Question about HR/colleagues is not an assertion of prior outreach.'),
    ('A','Months of harassment is explicit in selected past session H005:T006; keeps it historical and asks about replacement.'),
    ('A','Harassment grounding is in visible MS; does not claim a new harmful boss has arrived.'),
    ('A','Asks about hiring signals without importing unrelated friend-support profile.'),
    ('A','Possibility of improvement is conditional; colleague feelings are asked, not assumed.')],
}

def main():
    contract=json.loads((OUT/'condition_contract_private.json').read_text())
    author=Path(json.loads((OUT/'author_pointer.json').read_text())['run_dir'])
    jobs=json.loads((author/'jobs.json').read_text());conditions={(c['index'],c['condition']):c for c in contract['conditions']}
    evidence=json.loads((OUT/'legal_evidence_private.json').read_text())
    requests={};raws={};reviews=[]
    historical={(1,'R',17),(5,'L',29),(11,'L',29),(18,'R',17),(18,'R',29)}
    for j in jobs:
        key=j['request_id'];req=json.loads((author/(key+'.request.json')).read_text());raw=json.loads((author/(key+'.raw.json')).read_text())
        position={'OFF':0,'R':2,'L':4}[j['condition']]+int(j['seed']==29)
        decision,note=DECISIONS[j['index']][position];status={'A':'accept','R':'reject','U':'uncertain'}[decision]
        assert raw['finish_reason']=='natural_stop'
        c=conditions[j['index'],j['condition']]
        reviews.append(dict(request_identity=key,raw_identity=digest(raw),messages_identity=digest(req['messages']),
            index=j['index'],condition=j['condition'],seed=j['seed'],split=j['split'],status=status,rationale=note,
            evidence_identity=evidence[j['index']-1]['evidence_identity'],visible_source_ids=c['source_ids'],
            review_scope='Full visible input and answer; source excerpts and relevant temporal contradictions inspected. Not an exhaustive claim that every private historical turn was read.',
            checks=dict(technical_completion=True,exact_input=True,semantic_source_time_task_admission=(status=='accept')),
            unresolved_claims=[note] if status=='uncertain' else [],
            historical_uptake=(j['index'],j['condition'],j['seed']) in historical))
        requests[key]=req;raws[key]=raw
    doc=dict(reviewer=contract['admission']['reviewer'],independent_human_truth=False,
        contract_sha256=sha256_file(OUT/'condition_contract_private.json'),author_runtime_sha256=sha256_file(author/'runtime.json'),
        decision_table_sha256=sha256_file(Path(__file__)),old_q_m_used=False,repairs=0,rows=reviews)
    with (OUT/'admission_reviews_private.json').open('x') as f:f.write(json.dumps(doc,ensure_ascii=False,indent=2)+'\n')
    accepted=[r for r in reviews if r['status']=='accept']
    counts=Counter(r['status'] for r in reviews)
    coverage=Counter((r['index'],r['condition']) for r in accepted)
    missing=[dict(index=i,condition=c) for i,c in conditions if not coverage[i,c]]
    try:
        admitted_rows(contract,jobs,requests,raws,{r['request_identity']:r for r in reviews})
        gate=dict(passed=True,error=None)
    except ValueError as exc:gate=dict(passed=False,error=str(exc))
    summary=dict(status='ADMISSION_GATE_PASSED' if gate['passed'] else 'ADMISSION_GATE_FAILED_NO_TRAINING',
        counts=dict(counts),by_split={s:dict(Counter(r['status'] for r in reviews if r['split']==s)) for s in ('train','dev')},
        by_condition={c:dict(Counter(r['status'] for r in reviews if r['condition']==c)) for c in ('OFF','R','L')},
        coverage=[dict(index=i,condition=c,accepted=coverage[i,c]) for i,c in conditions],
        missing_prefix_conditions=missing,historical_uptake_train_prefixes=sorted({r['index'] for r in accepted if r['split']=='train' and r['historical_uptake']}),
        gate=gate,training_updates=0,adapter_created=False,repairs=0,paid_api_usd=0,
        supervision_exported=False,decision='Do not relax the pre-generation coverage gate after seeing outcomes; preserve all decisions and investigate provenance.')
    with (OUT/'admission_summary.json').open('x') as f:f.write(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='coverage'},ensure_ascii=False))

if __name__=='__main__':main()
