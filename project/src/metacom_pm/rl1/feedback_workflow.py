"""Thin joint→audit→bounded-resolution adapter for the paired dispatch engine."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
import json

from .schema import digest
from . import feedback_prototype as f
from . import relation_reference as rr
from . import task_reference as tr

VERSION='pmrl1-feedback-validation-v1-20261022'
RUN_ROOTS=tr.RUN_ROOTS+('feedback_validation_runs',)
POLICY=dict(semantic_error='record_continue',reviewer_dispute='record_continue',
    model_unknown='missing_continue_and_audit',technical_failure='stop_stage',
    identity_or_source_failure='stop_stage',usage_unknown='retain_full_liability_stop',
    budget_insufficient='stop_before_dispatch',supplemental_max=4,per_endpoint_max=1,
    retries=0,training_updates=0,old_stops_released=False)


def schedule(fixed,items):
    rows=[]
    for s in fixed:
        key=s['material_id'];item=items[key]
        rows.append(dict(s,item_key=key,reply_identity=digest(item['reply']),evidence_identity=digest(item['evidence'])))
    for s in [x for x in rows if x['component']=='joint']:
        logical=dict(study=f.VERSION,material_id=s['material_id'],component='repair',repetition=1)
        rows.append(dict(position=len(rows)+1,slot_id=digest(logical),**logical,item_key=s['item_key'],
            reply_identity=s['reply_identity'],evidence_identity=s['evidence_identity'],dependency='same endpoint joint and audit'))
    if len(rows)!=24 or len({s['slot_id'] for s in rows})!=24:raise ValueError('fixed eight-endpoint design changed')
    return rows


def find(pr,key,component):
    return next(s for s in pr['schedule'] if s['item_key']==key and s['component']==component)


def flagged(joint,audit):
    return (joint['evaluation']['model_unknown'] or audit['evaluation']['value']['check']['status']=='uncertain'
            or any(finding['verdict']!='no_issue_identified' for finding in audit['evaluation']['value']['findings']))


def dependency(pr,slot,results,started):
    key,component=slot['item_key'],slot['component']
    if component=='joint':return dict(action='dispatch',dependencies=[])
    j=find(pr,key,'joint')['slot_id'];deps=[j]
    if j not in results or not results[j]['technical_valid']:return dict(action='wait',dependencies=deps)
    if component=='audit':return dict(action='dispatch',dependencies=deps)
    a=find(pr,key,'audit')['slot_id'];deps.append(a)
    if a not in results or not results[a]['technical_valid']:return dict(action='wait',dependencies=deps)
    if not flagged(results[j],results[a]):return dict(action='skip',reason='not_flagged',dependencies=deps)
    # Determine membership from ALL fixed first-stage results, never selected scores.
    ordered=[]
    for s in pr['schedule']:
        if s['component']!='joint':continue
        jid=s['slot_id'];aid=find(pr,s['item_key'],'audit')['slot_id']
        if jid not in results or aid not in results:return dict(action='wait',dependencies=deps)
        if flagged(results[jid],results[aid]):ordered.append(s['item_key'])
    if key not in ordered[:4]:return dict(action='skip',reason='supplement_cap_four',dependencies=deps)
    return dict(action='dispatch',dependencies=deps)


def stop(pr,started,results):
    for s in pr['schedule']:
        sid=s['slot_id']
        if sid not in started:continue
        if sid not in results:return 'started request unresolved; no retry'
        r=results[sid]
        if r.get('hard_stop'):return r['hard_stop']
        if not r['technical_valid']:return 'technical or usage failure; no retry'
    return None


def payload(pr,slot,item,results,p,prompt):
    key,component=slot['item_key'],slot['component']
    if component=='joint':
        messages,schema=p.payload(item,'joint');messages[0]['content']=prompt
        return messages,schema
    score=results[find(pr,key,'joint')['slot_id']]['evaluation']['value']
    if component=='audit':return f.audit_payload(item,score,p)
    audit=results[find(pr,key,'audit')['slot_id']]['evaluation']['value']
    return f.repair_payload(item,score,audit,prompt,p)


def require_approval(pr,approval):
    if approval.get('status')!='APPROVED' or approval.get('protocol_identity')!=pr['identity']:
        raise ValueError('new fixed execution scope is not approved')
    if any(approval.get(k)!=v for k,v in pr['approval_required'].items()):
        raise ValueError('calling/data/credential/budget/human policy scope mismatch')
    record=approval.get('researcher_authorization_record')
    if not record or rr.sha(record)!=approval.get('researcher_record_sha256'):
        raise ValueError('actual researcher authorization record required')
    amendment=rr.read(pr['activation_file'])
    if (amendment.get('applied') is not True or amendment.get('protocol_identity')!=pr['identity']
            or amendment.get('approval_identity')!=digest(approval)
            or amendment.get('capacity')!=369 or amendment.get('trial_usd')!='3.65'):
        raise ValueError('approved scoped capacity/financial amendment not active')


def historical_guard(pr,base):
    root=Path(pr['run_dir'])
    actual={str(p):rr.sha(p) for name in RUN_ROOTS for p in (Path(base)/name).rglob('*.started.json')
            if 'management' not in p.parts and not p.is_relative_to(root)}
    if actual!=pr['historical_started_hashes']:raise ValueError('historical/cross-version attempt set changed')
    for path,h in pr['old_stop_hashes'].items():
        if rr.sha(path)!=h:raise ValueError('historical STOP changed')
    if 66+len(actual)!=285:raise ValueError('baseline no longer 285')
    return 285


def summarize(pr,root,p):
    root=Path(root);started,results=p.replay(root,pr);slots=[];endpoints=[]
    st=rr.read(root/'STOP.json') if (root/'STOP.json').exists() else None
    for s in pr['schedule']:
        sid=s['slot_id'];r=results.get(sid)
        skip=rr.read(root/(sid+'.skip.json')) if (root/(sid+'.skip.json')).exists() else None
        status=('failed' if r and not r['technical_valid'] else 'completed' if r
                else 'started_unresolved' if sid in started else 'skipped' if skip else 'not_dispatched')
        slots.append(dict(**s,status=status,result=r,skip=skip,not_dispatched_reason=st['reason'] if st and status=='not_dispatched' else None))
    for s in pr['schedule']:
        if s['component']!='joint':continue
        key=s['item_key'];j=results.get(s['slot_id']);a=results.get(find(pr,key,'audit')['slot_id']);r=results.get(find(pr,key,'repair')['slot_id'])
        state='missing';candidate=None
        if j and a and j['technical_valid'] and a['technical_valid']:
            if flagged(j,a):
                state='unresolved_no_supplement' if not r else 'supplement_failed' if not r['technical_valid'] else (
                    'model_unknown_after_supplement' if r['evaluation']['model_unknown'] else 'supplement_proposal_needs_local_review')
                candidate=r['evaluation'] if r and r['technical_valid'] and not r['evaluation']['model_unknown'] else None
            else:state='unflagged_numeric_candidate';candidate=j['evaluation']
        endpoints.append(dict(material_id=key,state=state,
            initial={k:j['evaluation'].get(k) for k in ('q','m','U','model_unknown')} if j else None,
            supplemental={k:r['evaluation'].get(k) for k in ('q','m','U','model_unknown')} if r else None,
            proposed_U=candidate.get('U') if candidate else None,
            final_usable_U=None,local_review='not_performed',automatic_accuracy_unknown=True,reward_eligible=False))
    validcost=sum((Decimal(r['financial']['accounted_upper_usd'] or '0') for r in results.values()),Decimal(0))
    liability=sum((Decimal(r['financial']['unsettled_reservation_usd']) for r in results.values()),Decimal(0))+Decimal('.786432')*len(set(started)-set(results))
    def tokens(row,name):
        value=(row.get('usage') or {}).get(name)
        return value if type(value) is int and value>=0 else 0
    paired=[];bykey={e['material_id']:e for e in endpoints}
    for context in pr.get('contexts',[]):
        cid=context['context_id'];off=bykey[cid+'_OFF'];on=bykey[cid+'_ON']
        cost=context['resource_tokens']/40960
        def net(a,b):return b-a-cost if a is not None and b is not None else None
        initial=net((off['initial'] or {}).get('U'),(on['initial'] or {}).get('U'))
        proposal=net(off['proposed_U'],on['proposed_U'])
        oslot=find(pr,cid+'_OFF','joint');nslot=find(pr,cid+'_ON','joint')
        identical=all(oslot[k]==nslot[k] for k in ('reply_identity','evidence_identity'))
        paired.append(dict(context_id=cid,head=context['head'],resource_tokens=context['resource_tokens'],cost=cost,
            identical_full_input=identical,score_difference_is_not_content_improvement=identical,
            initial_net=initial,diagnostic_proposal_net=proposal,
            numerical_change=proposal-initial if proposal is not None and initial is not None else None,
            final_usable_net=None,source_review_required=True,initial_output_shared_with_workflow=True,
            improvement_or_correct_direction_established=False))
    return dict(protocol_identity=pr['identity'],status='STOP' if st else 'CLOSED' if (root/'CLOSED.json').exists() else 'PENDING',
        slots=slots,endpoints=endpoints,paired=paired,started=len(started),cumulative=285+len(started),
        fixed_planned=16,conditional_slots=8,maximum_attempts=20,
        skipped=sum(x['status']=='skipped' for x in slots),not_dispatched=sum(x['status']=='not_dispatched' for x in slots),
        technical_failed=sum(x['status']=='failed' for x in slots),
        model_unknown=sum(bool(r['evaluation'].get('model_unknown')) for r in results.values() if r['component']!='audit'),
        audit_relation_uncertain=sum(r['evaluation']['value']['check']['status']=='uncertain' for r in results.values() if r['component']=='audit' and r['technical_valid']),
        accounted_usd=str(validcost),attempt_liability_usd=str(liability),
        authoritative_liability_source='shared ledger also includes any reserve-before-start orphan',
        known_prompt_tokens=sum(tokens(r,'prompt_tokens') for r in results.values()),
        known_output_tokens_including_thinking=sum(tokens(r,'completion_tokens') for r in results.values()),
        usage_incomplete_attempts=sum(not r['financial']['settlement_confirmed'] for r in results.values()),
        elapsed_seconds=sum(r['elapsed_seconds'] for r in results.values()),stop=st,
        natural_updates=0,human_reviews=0,reward_eligible=False)


def runtime(pr,p,prompt):
    def validate_outbound(slot,item,messages,schema,results):
        if (messages,schema)!=payload(pr,slot,item,results,p,prompt):raise ValueError('outbound input differs from fixed dependency')
        allowed={'legal_evidence','reply','response_units'}
        if slot['component'] in ('audit','repair'):allowed.add('preliminary_score')
        if slot['component']=='repair':allowed.add('machine_audit')
        data=json.loads(messages[1]['content'])
        if set(data)!=allowed or data['legal_evidence']!=item['evidence'] or data['reply']!=item['reply']:
            raise ValueError('complete original source or outward-field allowlist mismatch')
    def evaluate(slot,item,raw):
        if slot['component']=='audit':return f.evaluate_audit(raw,item,p)
        return p.evaluate(item,'joint',raw,pr['identity'],slot['slot_id'])
    return dict(approve=require_approval,dependency=dependency,stop=stop,summarize=summarize,
        payload=lambda slot,item,results:payload(pr,slot,item,results,p,prompt),
        validate_outbound=validate_outbound,evaluate=evaluate)
