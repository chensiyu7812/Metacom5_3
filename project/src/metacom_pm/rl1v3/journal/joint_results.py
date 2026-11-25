"""Read-only collection and evidence validation for authorized J06 actual replies."""
import json
from pathlib import Path
from ..io import file_sha256,object_sha256,write_json_once,write_jsonl_once
from ..generator import limited_run as L
from .joint_run import check

PROTOCOL='pmrl1-j-joint-actual-response-v1'

def jl(p):return [json.loads(x) for x in Path(p).read_text().splitlines()]

def collect(plan_path,job,out):
    plan,physical,_=check(plan_path);job,out=Path(job),Path(out);out.mkdir(parents=True,exist_ok=False)
    logical=jl(plan['logical_requests_path']);evals={r['task_id']:r for r in jl(plan['review_path'])}
    events=[];previous=None
    for seq,path in enumerate(sorted(job.glob('[0-9]*.json'))):
        event=json.loads(path.read_text())
        if event['seq']!=seq or event['previous_event_sha256']!=previous:raise ValueError('journal hash/order mismatch')
        previous=file_sha256(path);events.append(event)
    summary=json.loads((job/'SUMMARY.json').read_text())
    if summary['last_journal_sha256']!=previous or summary['plan_sha256']!=object_sha256(plan):raise ValueError('job summary identity')
    if events[0]['event']!='RUN_START' or events[0]['plan_sha256']!=object_sha256(plan):raise ValueError('job start identity')
    starts=[e for e in events if e['event']=='REQUEST_START'];by_id={r['request_id']:r for r in physical}
    if [r['request_id'] for r in starts]!=plan['ordered_request_ids'][:len(starts)]:raise ValueError('duplicate/reordered/unrequested execution')
    returned={};validated={}
    for e in events:
        if e['event']=='REQUEST_START' and e['payload_sha256']!=by_id[e['request_id']]['payload_sha256']:raise ValueError('start payload mismatch')
        if e['event']=='REQUEST_RETURNED':
            if e['request_id'] in returned:raise ValueError('duplicate physical return')
            returned[e['request_id']]=e['output']
        if e['event']=='REQUEST_VALIDATED':
            if e['request_id'] in validated:raise ValueError('duplicate validation')
            validated[e['request_id']]=e['finish_reason']
    if not set(returned)<={e['request_id'] for e in starts}:raise ValueError('unstarted output')
    for rid,output in returned.items():
        if rid in validated and L.validate_result(by_id[rid],output)!=validated[rid]:raise ValueError('output token/stop mismatch')
    rows=[]
    for request in logical:
        rid=request['request_id'];output=returned.get(rid);finish=validated.get(rid)
        status='pending' if output is None else 'technical_incomplete' if finish!='eos' else 'ready_for_development_review'
        binding=dict(protocol=PROTOCOL,task_id=request['task_id'],logical_id=request['logical_id'],arm=request['arm'],
            request_id=rid,payload_sha256=request['payload_sha256'],query_sha256=request['task_query_sha256'],
            renderer_id=request['renderer_id'],source_port_binding_sha256=request['source_port_binding_sha256'],
            evalspec_sha256=object_sha256(evals[request['task_id']]),baseline_sha256=request['baseline_sha256'])
        rows.append(dict(**binding,endpoint_id='joint-endpoint:'+object_sha256(binding),status=status,
            output=output,output_sha256=object_sha256(output) if output is not None else None,
            technical_status=finish or 'missing_or_unvalidated',formal_reward=None,
            plan_sha256=object_sha256(plan),job_summary_sha256=file_sha256(job/'SUMMARY.json')))
    write_jsonl_once(out/'ACTUAL_RESPONSES_PRIVATE.jsonl',rows)
    report=dict(protocol=PROTOCOL,batch_number=plan['batch_number'],plan_sha256=object_sha256(plan),
        physical_starts=len(starts),physical_returns=len(returned),logical_rows=len(rows),
        eos=sum(r['technical_status']=='eos' for r in rows),formal_rewards=0,
        actual_input_tokens=sum(r['input_tokens'] for r in returned.values()),
        actual_output_tokens=sum(len(r['token_ids']) for r in returned.values()),
        generation_seconds=sum(r['seconds'] for r in returned.values()),job_wall_seconds=summary['wall_seconds'],
        original_worker_outputs_preserved=True,logical_reuse_not_rebilled=True,
        responses_sha256=file_sha256(out/'ACTUAL_RESPONSES_PRIVATE.jsonl'),collector_sha256=file_sha256(__file__))
    write_json_once(out/'COLLECTION_PUBLIC.json',report);return report


def validate_support_review(review,response,evalspec):
    for key in ('logical_id','task_id','arm','request_id','output_sha256','evalspec_sha256'):
        if review.get(key)!=response.get(key):raise ValueError('review response identity: '+key)
    if object_sha256(evalspec)!=response['evalspec_sha256']:raise ValueError('frozen evaluation identity')
    if review.get('formal_reward') is not None or review.get('reference_independence')!='assistant_development_not_independent_human':
        raise ValueError('unqualified review cannot create formal reward')
    text=response['output']['text'] if response['output'] else ''
    for field in ('requirements','prohibitions'):
        expected={r['id'] for r in evalspec[field]}
        if set(review[field])!=expected:raise ValueError('criterion coverage mismatch')
        for finding in review[field].values():
            if finding['verdict'] not in ('pass','fail','uncertain'):raise ValueError('invalid development verdict')
            if any(not q or q not in text for q in finding['output_quotes']):raise ValueError('output evidence not exact')
            if finding.get('reviewed_span')!=[0,len(text)]:raise ValueError('whole response inspection required')
            if not finding.get('reason'):raise ValueError('explicit source/goal reasoning required')
    if response['technical_status']!='eos' and review.get('support_interval') is not None:
        raise ValueError('technical incomplete cannot be a quality zero')
    return True
