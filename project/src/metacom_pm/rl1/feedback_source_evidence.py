"""Versioned findings.source_evidence interface and STOP-preserving continuation.

The original prototype, parser, dispatcher and six old requests remain frozen.
This adapter changes the literal findings key, exposes the exact schema, and
selects only unstarted slots of the same fixed experiment. No key repair.
"""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json

from . import feedback_prototype as old, feedback_workflow as w
from . import paired_dependencies as d, relation_reference as rr
from .evidence import evidence_turns
from .judge_indexed import response_units

VERSION='pmrl1-feedback-source-evidence-v2-20261022'
INTERFACE='audit-findings-source-evidence-v2-20261022'


def audit_schema(item,p):
    schema=deepcopy(old.audit_schema(item,p))
    finding=schema['properties']['findings']['items']
    finding['properties']['source_evidence']=finding['properties'].pop('evidence')
    finding['required']=['source_evidence' if x=='evidence' else x for x in finding['required']]
    return schema


def audit_payload(item,score,p):
    messages,_=old.audit_payload(item,score,p)
    schema=audit_schema(item,p)
    messages[0]['content']+='\nOUTPUT INTERFACE '+INTERFACE+': Field names are literal. '
    messages[0]['content']+='Use source_evidence inside each findings item; check.claims keeps evidence. '
    messages[0]['content']+='Return one JSON object matching this complete schema exactly:\n'+json.dumps(schema,ensure_ascii=False)
    return messages,schema


def validate_audit(value,item,p):
    from jsonschema import Draft202012Validator
    Draft202012Validator(audit_schema(item,p)).validate(value)
    p.validate_extract(value['check'],item)
    units={u['id']:u['text'] for u in response_units(item['reply'])}
    turns=evidence_turns(item['evidence'])
    for finding in value['findings']:
        if finding['response_quote'] not in units[finding['response_unit_id']]:
            raise ValueError('audit quote not in original reply unit')
        for ev in finding['source_evidence']:
            if ev['quote'] not in turns[ev['source_id']]['text']:
                raise ValueError('audit quote not in original source')
    return deepcopy(value)


def evaluate_audit(raw,item,p):
    try:
        final,finish=p.final_content(raw)
        if finish!='natural_stop':raise ValueError('audit final incomplete')
        _,value,adaptation=p.envelope.unwrap(final)
        validate_audit(value,item,p)
        return dict(technical_valid=True,value=value,outer_adaptation=adaptation,
                    interface_version=INTERFACE,reward_eligible=False,semantic_gold=False)
    except Exception as exc:
        return dict(technical_valid=False,value=None,error_type=type(exc).__name__,
                    error=str(exc),interface_version=INTERFACE,reward_eligible=False)


def inherited(pr,p):
    prior=rr.read(pr['prior_protocol_path']);root=Path(prior['run_dir'])
    starts,results=p.replay(root,prior);d.verify_receipts(p,root,prior,starts,results)
    if set(starts)!=set(pr['inherited_started_ids']) or set(results)!=set(starts):
        raise ValueError('inherited attempts changed or unresolved')
    for path,h in pr['inherited_receipt_hashes'].items():
        if rr.sha(path)!=h:raise ValueError('inherited receipt or STOP changed')
    return starts,results


def dependency(pr,slot,results,started,prior_results):
    all_results=prior_results|results
    if slot['slot_id'] in prior_results:raise ValueError('already started in prior interface')
    if slot['component']!='repair':return w.dependency(pr,slot,results,started)
    full=pr|dict(schedule=pr['full_schedule'])
    j=w.find(full,slot['item_key'],'joint')['slot_id'];a=w.find(full,slot['item_key'],'audit')['slot_id']
    # The old failed audit is not repaired or retried. Its endpoint remains missing.
    if a in pr['inherited_failed_ids']:
        return dict(action='skip',reason='prior_failed_audit_preserved_no_retry',dependencies=[])
    if j not in all_results or a not in all_results:return dict(action='wait',dependencies=[])
    if not all_results[j]['technical_valid'] or not all_results[a]['technical_valid']:
        return dict(action='wait',dependencies=[])
    deps=[sid for sid in (j,a) if sid in results]
    if not w.flagged(all_results[j],all_results[a]):return dict(action='skip',reason='not_flagged',dependencies=deps)
    eligible=[]
    for candidate in pr['full_schedule']:
        if candidate['component']!='joint':continue
        jid=candidate['slot_id'];aid=w.find(full,candidate['item_key'],'audit')['slot_id']
        if jid not in all_results or aid not in all_results:return dict(action='wait',dependencies=deps)
        if aid in pr['inherited_failed_ids']:continue
        if not all_results[jid]['technical_valid'] or not all_results[aid]['technical_valid']:
            return dict(action='wait',dependencies=deps)
        if w.flagged(all_results[jid],all_results[aid]):eligible.append(candidate['item_key'])
    if slot['item_key'] not in eligible[:4]:return dict(action='skip',reason='supplement_cap_four',dependencies=deps)
    return dict(action='dispatch',dependencies=deps)


def payload(pr,slot,item,results,p,prompt):
    if slot['component']=='joint':return w.payload(pr,slot,item,results,p,prompt)
    score=results[w.find(pr,slot['item_key'],'joint')['slot_id']]['evaluation']['value']
    if slot['component']=='audit':return audit_payload(item,score,p)
    audit=results[w.find(pr,slot['item_key'],'audit')['slot_id']]['evaluation']['value']
    validate_audit(audit,item,p)
    if not (score['status']=='uncertain' or audit['check']['status']=='uncertain'
            or any(x['verdict']!='no_issue_identified' for x in audit['findings'])):
        raise ValueError('unflagged extra sampling forbidden')
    messages,schema=p.payload(item,'joint');data=json.loads(messages[1]['content'])
    data.update(preliminary_score=deepcopy(score),machine_audit=deepcopy(audit))
    messages[0]['content']=prompt+old.REPAIR_ADDITION
    messages[1]['content']=json.dumps(data,ensure_ascii=False)
    return messages,schema


def summary(pr,root,p):
    past,old_results=inherited(pr,p);current,results=p.replay(root,pr)
    if set(past)&set(current):raise ValueError('cross-version duplicated attempt')
    proxy=SimpleNamespace(replay=lambda *_:(past|current,old_results|results))
    report=w.summarize(pr|dict(schedule=pr['full_schedule']),root,proxy)
    report.update(new_started=len(current),inherited_started=len(past),interface_version=INTERFACE,
        protocol_family=pr['prior_protocol_identity'],prior_stop_preserved=True,
        continuation_limit=14,old_failure_not_reclassified=True)
    return report


def require_approval(pr,approval):
    w.require_approval(pr,approval)
    if approval.get('source_evidence_interface')!=INTERFACE or approval.get('new_request_limit')!=14:
        raise ValueError('source_evidence continuation not authorized')


def runtime(pr,p,prompt):
    _,old_results=inherited(pr,p)
    def validate(slot,item,messages,schema,results):
        if (messages,schema)!=payload(pr,slot,item,results,p,prompt):raise ValueError('outbound changed')
        data=json.loads(messages[1]['content']);allowed={'legal_evidence','reply','response_units'}
        if slot['component'] in ('audit','repair'):allowed.add('preliminary_score')
        if slot['component']=='repair':allowed.add('machine_audit')
        if set(data)!=allowed or data['legal_evidence']!=item['evidence'] or data['reply']!=item['reply']:
            raise ValueError('complete source or payload allowlist mismatch')
    return dict(approve=require_approval,
        dependency=lambda pr,slot,results,starts:dependency(pr,slot,results,starts,old_results),
        stop=w.stop,summarize=summary,
        payload=lambda slot,item,results:payload(pr,slot,item,results,p,prompt),validate_outbound=validate,
        evaluate=lambda slot,item,raw:evaluate_audit(raw,item,p) if slot['component']=='audit'
                 else p.evaluate(item,'joint',raw,pr['identity'],slot['slot_id']))


def budget_class(p):
    class SameExperimentBudget(p.DiagnosticBudget):
        def stage_total(self,reserved,settled):
            return sum(p.s.nanodollars(settled[k]['actual_cost_usd'] if k in settled else v['maximum_cost_usd'])
                for k,v in reserved.items() if v.get('binding',{}).get('study') in (w.VERSION,self.study))
    return SameExperimentBudget


def historical_guard(pr,base):
    root=Path(pr['run_dir'])
    actual={str(path):rr.sha(path) for name in w.RUN_ROOTS for path in (Path(base)/name).rglob('*.started.json')
            if 'management' not in path.parts and not path.is_relative_to(root)}
    if actual!=pr['historical_started_hashes']:raise ValueError('cross-version historical attempts changed')
    for path,h in pr['old_stop_hashes'].items():
        if rr.sha(path)!=h:raise ValueError('old STOP changed')
    if 66+len(actual)!=291:raise ValueError('actual baseline is not 291')
    return 291
