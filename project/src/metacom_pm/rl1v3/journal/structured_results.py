"""Versioned actual-output collector: frozen worker token/seconds accounting fix.

The original collector is preserved. Scoring, JSON handling, reference bindings,
and response evidence are unchanged; this adapter corrects only cost field names.
"""
from collections import Counter
import html
import json
from pathlib import Path
from ..io import file_sha256,object_sha256,write_json_once,write_jsonl_once
from .structured_learning import evaluate
from .structured_run import check
from .structured_endpoints import PROTOCOL,validate_result_binding,jl

def collect(plan_path,job,pending,out):
    """Join a bounded job's hash-chained actual outputs; preserve incomplete rows."""
    plan,physical,_=check(plan_path);job,pending,out=map(Path,(job,pending,out));out.mkdir(parents=True,exist_ok=False)
    rows=jl(plan['logical_requests_path']);refs={x['task_id']:x for x in jl(plan['review_path'])}
    endpoint_rows=jl(pending/'ENDPOINTS_PENDING.private.jsonl');endpoints={x['binding']['logical_id']:x for x in endpoint_rows}
    receipt=json.loads((pending/'PENDING_RECEIPT.json').read_text())
    assert file_sha256(pending/'ENDPOINTS_PENDING.private.jsonl')==receipt['endpoints_sha256']
    for name,sha in receipt['inputs_sha256'].items():assert file_sha256(name)==sha
    from . import structured_learning
    assert file_sha256(structured_learning.__file__)==receipt['evaluator_sha256']
    events=[];previous=None
    for seq,path in enumerate(sorted(job.glob('[0-9]*.json'))):
        event=json.loads(path.read_text())
        if event['seq']!=seq or event['previous_event_sha256']!=previous:raise ValueError('journal chain mismatch')
        previous=file_sha256(path);events.append(event)
    summary=json.loads((job/'SUMMARY.json').read_text())
    assert summary['plan_sha256']==object_sha256(plan) and summary['last_journal_sha256']==previous
    assert events[0]['event']=='RUN_START' and events[0]['plan_sha256']==object_sha256(plan)
    starts=[e for e in events if e['event']=='REQUEST_START'];returned={};validated={}
    if [e['request_id'] for e in starts]!=plan['ordered_request_ids'][:len(starts)]:raise ValueError('order or retry')
    for event in events:
        if event['event']=='REQUEST_RETURNED':
            rid=event['request_id']
            if rid in returned:raise ValueError('duplicate return')
            returned[rid]=event['output']
        if event['event']=='REQUEST_VALIDATED':validated[event['request_id']]=event['finish_reason']
    phys={r['request_id']:r for r in physical}
    for e in starts:assert e['payload_sha256']==phys[e['request_id']]['payload_sha256']
    assert set(returned)<=set(e['request_id'] for e in starts)
    results=[]
    for request in rows:
        endpoint=endpoints[request['logical_id']];binding=endpoint['binding'];rid=request['request_id']
        assert binding['payload_sha256']==request['payload_sha256'] and binding['reference_sha256']==object_sha256(refs[request['task_id']])
        output=returned.get(rid);status='pending';score=None
        if output is not None and rid in validated:
            assert output['input_tokens']==len(request['model_input']['input_ids'])
            if validated[rid]=='length':status='technical_incomplete'
            else:
                supplied=html.unescape('\n'.join(m['content'] for m in request['model_input']['messages']))
                score=evaluate(output['text'],refs[request['task_id']],arm=request['arm'],delivered_text=supplied)
                status='development_scored'
        result=dict(protocol=PROTOCOL,endpoint_id=endpoint['endpoint_id'],binding=binding,status=status,
            actual_output_sha256=object_sha256(output) if output is not None else None,score=score,
            plan_sha256=object_sha256(plan),job_summary_sha256=file_sha256(job/'SUMMARY.json'),reward=None)
        validate_result_binding(endpoint,result);results.append(result)
    write_jsonl_once(out/'ACTUAL_ENDPOINTS.private.jsonl',results)
    write_json_once(out/'ACTUAL_OUTPUTS.private.json',returned)
    counts={arm:dict(n=sum(r['binding']['arm']==arm for r in results),
        scored=sum(r['binding']['arm']==arm and r['status']=='development_scored' for r in results),
        task_success=sum(r['binding']['arm']==arm and bool(r['score'] and r['score']['task_success']) for r in results))
        for arm in ('BASE','RAW')}
    aggregate=dict(protocol=PROTOCOL,plan_sha256=object_sha256(plan),physical_calls=len(starts),
        logical_endpoints=len(results),status_counts=dict(Counter(r['status'] for r in results)),arms=counts,
        actual_input_tokens=sum(v['input_tokens'] for v in returned.values()),
        actual_output_tokens=sum(len(v['token_ids']) for v in returned.values()),
        actual_generation_seconds=sum(v['seconds'] for v in returned.values()),
        original_collector_cost_field_fix='output_tokens absent in frozen worker; count exact token_ids; wall uses seconds',
        no_token_rebilling_for_logical_reuse=True,qualified_rewards=0,reference_status='assistant-authored explicit-source development',
        Memory_RS_joint_complete=False,endpoint_code_sha256=file_sha256(__file__),evaluator_sha256=receipt['evaluator_sha256'])
    write_json_once(out/'AGGREGATE_PUBLIC.json',aggregate)
    return aggregate
