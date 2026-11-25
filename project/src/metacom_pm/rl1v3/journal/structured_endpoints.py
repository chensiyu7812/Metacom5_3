"""Task-qualified endpoint identities, distinct from natural-dialogue C0 terminals.

This module creates pending manifests and evaluates only attested worker returns.
It never constructs a reward-bearing TerminalTable or calls a model.
"""
from collections import Counter
import html
import json
from pathlib import Path
from ..io import file_sha256,object_sha256,write_json_once,write_jsonl_once
from .structured_learning import evaluate
from .structured_run import check

PROTOCOL='pmrl1-j-structured-task-endpoint-v1'


def jl(path):return [json.loads(x) for x in Path(path).read_text().splitlines()]


def bind_endpoint(request,reference,task,port,evaluator_sha):
    if not request['task_id']==reference['task_id']==task['task_id']==port['task_id']:
        raise ValueError('cross-task endpoint binding rejected')
    if object_sha256(request['model_input'])!=request['payload_sha256']:
        raise ValueError('payload identity mismatch')
    binding=dict(protocol=PROTOCOL,task_id=request['task_id'],logical_id=request['logical_id'],arm=request['arm'],
        request_id=request['request_id'],payload_sha256=request['payload_sha256'],
        visible_question_sha256=object_sha256(task['question']),renderer_id=request['renderer_id'],
        baseline_sha256=request['baseline_sha256'],reference_sha256=object_sha256(reference),evaluator_sha256=evaluator_sha,
        legal_source_port_binding_sha256=port['binding_sha256'],source_prefix_id=port['prefix_id'],
        source_prefix_is_model_input=False,reward_qualified=False)
    return dict(binding=binding,endpoint_id='structured-endpoint:'+object_sha256(binding),status='pending',
        task_success=None,reward=None,actual_G_output=None)


def validate_result_binding(endpoint,result):
    binding=endpoint['binding']
    if binding.get('protocol')!=PROTOCOL or result.get('protocol')!=PROTOCOL:
        raise ValueError('natural dialogue terminal or wrong endpoint protocol rejected')
    if result.get('endpoint_id')!=endpoint['endpoint_id'] or result.get('binding')!=binding:
        raise ValueError('task/payload/renderer/evaluation endpoint mismatch')
    if endpoint['endpoint_id']!='structured-endpoint:'+object_sha256(binding):
        raise ValueError('endpoint content identity mismatch')


def prepare_pending(package,out):
    package,out=Path(package),Path(out);out.mkdir(parents=True,exist_ok=False)
    refs={x['task_id']:x for x in jl(package/'REFERENCES.private.jsonl')}
    tasks={x['task_id']:x for x in jl(package/'TASKS.private.jsonl')}
    ports={x['task_id']:x for x in jl(package/'PORT_CHECKS.private.jsonl')}
    rules=json.loads((package/'EVALUATION_RULES.json').read_text())
    from . import structured_learning
    if file_sha256(structured_learning.__file__)!=rules['evaluator_sha256']:
        raise ValueError('frozen evaluation code changed')
    endpoints=[bind_endpoint(r,refs[r['task_id']],tasks[r['task_id']],ports[r['task_id']],rules['evaluator_sha256'])
        for r in jl(package/'REQUESTS_ALL.private.jsonl')]
    assert len(endpoints)==36 and len({x['endpoint_id'] for x in endpoints})==36
    write_jsonl_once(out/'ENDPOINTS_PENDING.private.jsonl',endpoints)
    receipt=dict(protocol=PROTOCOL,logical_endpoints=36,status='pending',actual_G_calls=0,known_task_successes=0,
        qualified_reward_rows=0,action_subset=['BASE','GET_MS'],Memory_RS_joint_complete=False,
        source_port_checks=18,sidecar_tasks_distinct_from_natural_dialogue=True,
        evaluator_sha256=rules['evaluator_sha256'],endpoint_code_sha256=file_sha256(__file__),
        endpoints_sha256=file_sha256(out/'ENDPOINTS_PENDING.private.jsonl'),
        inputs_sha256={str(p):file_sha256(p) for p in [package/'TASKS.private.jsonl',package/'REFERENCES.private.jsonl',
            package/'REQUESTS_ALL.private.jsonl',package/'PORT_CHECKS.private.jsonl',package/'EVALUATION_RULES.json']})
    write_json_once(out/'PENDING_RECEIPT.json',receipt)
    return receipt


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
        actual_output_tokens=sum(v['output_tokens'] for v in returned.values()),
        no_token_rebilling_for_logical_reuse=True,qualified_rewards=0,reference_status='assistant-authored explicit-source development',
        Memory_RS_joint_complete=False,endpoint_code_sha256=file_sha256(__file__),evaluator_sha256=receipt['evaluator_sha256'])
    write_json_once(out/'AGGREGATE_PUBLIC.json',aggregate)
    return aggregate
