"""Recompute public physical-call measurements from the five authorized closeout journals."""
import argparse,json
from pathlib import Path
from collections import Counter
from metacom_pm.rl1v3.io import object_sha256,file_sha256,write_json_once

SCOPES=(
    ('M2','M2_run1','memory_packages/final-v2/representation-batch-2/PLAN.json',18,
     'c435369a25f668f459b37f461187fa8689aa61ad0935fb908b034195d39ca37f'),
    ('U1','U1_run1','memory_packages/final-v2/mpme6/PLAN.json',6,
     '0317dd13d7ed7b08d5302b7c4a7b52293f6ec60e1cdcd0ddcc6a59776a3f6b9b'),
    ('R2','R2_run1','rs_complex/package-v2/batch-02/PLAN.json',18,
     'c3f71c59595164c1f4d063d261f5b11cec58f132de553a96b03d553a3435c532'),
    ('R3','R3_run1','rs_complex/package-v2/batch-03/PLAN.json',17,
     'a5fbb93eb41d9aebfaa43449f37a0569ec0c1f518b2d94ea2a7b56bf8f63685a'),
    ('R4','R4_run1','rs_complex/package-v2/batch-04/PLAN.json',17,
     '9437bbc23a0652d6689fe001ffadf72017d9dfd55318e4b3af28912a0cf39af9'))


def validate_finish(payload, value):
    tokens=value['token_ids'];eos=payload['decode']['eos_token_id']
    eos=[eos] if isinstance(eos,int) else eos
    if value['finish_reason']=='eos':
        assert tokens and tokens[-1] in eos and not any(t in eos for t in tokens[:-1])
    elif value['finish_reason']=='length':
        assert len(tokens)==payload['decode']['max_new_tokens'] and not any(t in eos for t in tokens)
    else:
        raise AssertionError('unrecognized completion state')


def collect(root,packages):
    root,packages=Path(root),Path(packages);rows=[];hashes={}
    for name,directory,relative,count,expected in SCOPES:
        plan_path=packages/relative;plan=json.loads(plan_path.read_text());assert object_sha256(plan)==expected
        requests=[json.loads(s) for s in Path(plan['requests_path']).read_text().splitlines()]
        assert file_sha256(plan['requests_path'])==plan['requests_sha256']
        auth=json.loads((root/(name+'_AUTHORIZED.json')).read_text())
        assert auth['authorized'] and auth['plan_sha256']==expected and auth['max_calls']==count and auth['max_model_loads']==1
        assert file_sha256(auth['decision_evidence'])==auth['decision_evidence_sha256']
        job=root/directory/('job-'+object_sha256(auth));events=[];previous=None
        for seq,p in enumerate(sorted(job.glob('[0-9]*.json'))):
            e=json.loads(p.read_text());assert e['seq']==seq and e['previous_event_sha256']==previous
            previous=file_sha256(p);events.append(e)
        summary=json.loads((job/'SUMMARY.json').read_text())
        assert summary['plan_sha256']==expected and summary['last_journal_sha256']==previous
        assert summary['status']=='FINISHED' and summary['physical_calls']==summary['validated_calls']==count
        assert summary['wall_seconds']<=plan['global_seconds']==1200
        assert not summary['unattempted_or_failed_pending']
        assert summary['pending']==summary['truncated_pending']
        assert events[0]['event']=='RUN_START' and events[0]['approval']==auth
        assert sum(e['event']=='LOAD_START' for e in events)==sum(e['event']=='LOAD_OK' for e in events)==1
        starts=[e for e in events if e['event']=='REQUEST_START'];returned=[e for e in events if e['event']=='REQUEST_RETURNED']
        assert [e['request_id'] for e in starts]==plan['ordered_request_ids']==[r['request_id'] for r in requests]
        assert [e['request_id'] for e in returned]==plan['ordered_request_ids']
        assert len(set(plan['ordered_request_ids']))==count
        measurements=[]
        for request,start,event in zip(requests,starts,returned):
            payload=request['model_input'];value=event['output'];tokens=value['token_ids']
            assert object_sha256(payload)==request['payload_sha256']==start['payload_sha256']
            assert value['input_tokens']==len(payload['input_ids'])
            validate_finish(payload,value)
            measurements.append(dict(request_id=request['request_id'],arm=request.get('arm'),
                task_id=request.get('task_id'),input_tokens=value['input_tokens'],output_tokens=len(tokens),
                generation_seconds=value['seconds'],finish_reason=value['finish_reason'],payload_sha256=request['payload_sha256']))
        truncated=[m['request_id'] for m in measurements if m['finish_reason']=='length']
        assert truncated==summary['truncated_pending'] and len(truncated)==summary['length_count']
        load=next(e['measurement']['seconds'] for e in events if e['event']=='LOAD_OK')
        rows.append(dict(scope=name,plan_object_sha256=expected,requests_sha256=plan['requests_sha256'],physical_calls=count,
            logical_arms=18 if name.startswith('R') else count,
            exact_payload_reuses=(18-count) if name.startswith('R') else 0,
            loads=1,warmup=0,inference_retries=0,input_tokens=sum(r['input_tokens'] for r in measurements),
            output_tokens=sum(r['output_tokens'] for r in measurements),generation_seconds=sum(r['generation_seconds'] for r in measurements),
            load_seconds=load,total_job_seconds=summary['wall_seconds'],finish_counts=dict(Counter(r['finish_reason'] for r in measurements)),
            truncated_pending=truncated,per_physical_call=measurements,qualified_reward=None))
        hashes[str(plan_path)]=file_sha256(plan_path);hashes[str(job/'SUMMARY.json')]=file_sha256(job/'SUMMARY.json')
    return dict(protocol='pmrl1-j-closeout76-physical-measurement-v1',jobs=rows,
        physical_calls=sum(r['physical_calls'] for r in rows),logical_arms=sum(r['logical_arms'] for r in rows),
        model_loads=5,warmup=0,inference_retries=0,prelaunch_wrapper_failures=0,
        prelaunch_failure_changed_frozen_executor=False,prelaunch_failure_changed_requests=False,
        total_input_tokens=sum(r['input_tokens'] for r in rows),total_output_tokens=sum(r['output_tokens'] for r in rows),
        total_generation_seconds=sum(r['generation_seconds'] for r in rows),
        total_load_seconds=sum(r['load_seconds'] for r in rows),sum_job_seconds=sum(r['total_job_seconds'] for r in rows),
        total_truncated_pending=sum(len(r['truncated_pending']) for r in rows),
        limits='five separately guarded 1200-second jobs; summed time is not client end-to-end latency',hashes=hashes)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('root','packages','out'):p.add_argument('--'+name,required=True)
    a=p.parse_args();report=collect(a.root,a.packages);write_json_once(Path(a.out),report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('jobs','hashes')},indent=2))
