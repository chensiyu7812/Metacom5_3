"""CPU admission binding for the already frozen 22 temporal payloads."""
import argparse,copy,json,shutil
from pathlib import Path
from metacom_pm.rl1v3.io import file_sha256,object_sha256,write_json_once
from metacom_pm.rl1v3.journal.temporal_run import check,RUN_PROTOCOL,JOB_KIND,jl


def prepare(candidate,template,repo,out):
    candidate,template,repo,out=map(lambda p:Path(p).resolve(),(candidate,template,repo,out))
    if out.exists():raise FileExistsError('new immutable package required')
    freeze=json.loads((candidate/'PAYLOAD_FREEZE.json').read_text())
    for name,h in freeze['output_files_sha256'].items():assert file_sha256(candidate/name)==h
    for name,h in freeze['source_files_sha256'].items():assert file_sha256(name)==h
    base=json.loads(template.read_text());out.mkdir(parents=True)
    executor=out/'executor';shutil.copytree(base['executor_root'],executor)
    name='project/src/metacom_pm/rl1v3/journal/temporal_run.py';shutil.copy2(repo/name,executor/name)
    hashes={n:file_sha256(executor/n) for n in base['executor_files_sha256']}
    assert hashes==base['executor_files_sha256'];hashes[name]=file_sha256(executor/name)
    all_rows=jl(candidate/'REQUESTS_LOGICAL.private.jsonl');tasks=list(dict.fromkeys(r['task_id'] for r in all_rows));reports=[]
    assert len(all_rows)==24 and len(tasks)==8
    for i in (1,2):
        original=candidate/f'batch-{i:02d}';target=out/f'batch-{i:02d}';target.mkdir()
        for source,name in [('REQUESTS.private.jsonl','REQUESTS.private.jsonl'),('LOGICAL.private.jsonl','LOGICAL_REQUESTS.private.jsonl')]:
            shutil.copy2(original/source,target/name)
        rows=jl(target/'REQUESTS.private.jsonl');logical=jl(target/'LOGICAL_REQUESTS.private.jsonl')
        feasibility=json.loads((original/'PROPOSAL.json').read_text())
        plan={k:copy.deepcopy(base[k]) for k in ('baseline_path','baseline_sha256','checkpoint_path','python','model_path',
            'stop_rules','global_seconds','load_seconds','request_seconds','automatic_retry','max_model_loads','warmup_calls','paid_api_allowed')}
        plan.update(protocol=RUN_PROTOCOL,job_kind=JOB_KIND,authorized=False,remaining_batches_authorized=False,batch_number=i,
            task_ids=tasks[4*(i-1):4*i],logical_requests=12,max_calls=len(rows),ordered_request_ids=[r['request_id'] for r in rows],
            requests_path=str(target/'REQUESTS.private.jsonl'),requests_sha256=file_sha256(target/'REQUESTS.private.jsonl'),
            logical_requests_path=str(target/'LOGICAL_REQUESTS.private.jsonl'),frozen_requests_path=str(candidate/'REQUESTS_LOGICAL.private.jsonl'),
            candidate_freeze_path=str(candidate/'PAYLOAD_FREEZE.json'),candidate_freeze_sha256=file_sha256(candidate/'PAYLOAD_FREEZE.json'),
            delivery_path=str(candidate/'DELIVERY.private.jsonl'),renderer_id=rows[0]['renderer_id'],
            executor_root=str(executor),executor_files_sha256=hashes,selection='all eight original explicit-date tasks in original order; four complete three-arm tasks per batch')
        sources=[target/'REQUESTS.private.jsonl',target/'LOGICAL_REQUESTS.private.jsonl',candidate/'REQUESTS_LOGICAL.private.jsonl',
            candidate/'PAYLOAD_FREEZE.json',candidate/'DELIVERY.private.jsonl',candidate/'SELECTION_FROZEN.json',
            candidate/'EVALUATION_RULES.json',original/'PROPOSAL.json',Path(base['baseline_path']),Path(base['checkpoint_path']),template]
        plan['files_sha256']={str(p):file_sha256(p) for p in sources}
        write_json_once(target/'PLAN.json',plan);verified,checked,_=check(target/'PLAN.json')
        report=dict(label='T'+str(i),plan_object_sha256=object_sha256(verified),plan_file_sha256=file_sha256(target/'PLAN.json'),
            requests_sha256=plan['requests_sha256'],physical_calls=len(checked),logical_arms=len(logical),exact_reuses=len(logical)-len(checked),
            max_model_loads=1,warmup=0,retries=0,global_seconds=1200,load_seconds=600,request_seconds=300,
            conservative_scenario_seconds=feasibility['conservative_scenario_seconds'],input_tokens=sum(len(r['model_input']['input_ids']) for r in rows),
            authorized=False,model_calls=0,device_access=False,status='CPU_ADMISSION_PASSED')
        write_json_once(target/'CPU_CHECK.json',report);reports.append(report)
    counts=[dict(task_id=r['task_id'],arm=r['arm'],returned_sessions=len(r['source_sessions']),reading_tokens=r['reading_tokens'],
        input_tokens=r['input_tokens'],future_sources=r['future_sources'],filtering_policy=r['selection']) for r in jl(candidate/'DELIVERY.private.jsonl')]
    public=dict(protocol=RUN_PROTOCOL,plans=reports,physical_calls=22,logical_arms=24,tasks=8,loads=2,
        total_hard_seconds=2400,authorized=False,all_original_date_tasks_retained=True,payloads_changed=False,
        original_end_history_identity_unchanged=True,returned_session_counts=counts,
        interpretation='Legacy selection then filtering has no refill; legal-pool lexical and hybrid also differ in returned count and token supply. Do not attribute all differences to semantic retrieval.',
        candidate_freeze_sha256=file_sha256(candidate/'PAYLOAD_FREEZE.json'))
    write_json_once(out/'REQUEST_PUBLIC.json',public)
    return public


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('candidate','template','repo','out'):p.add_argument('--'+name,required=True)
    result=prepare(**vars(p.parse_args()));print(json.dumps({k:v for k,v in result.items() if k!='returned_session_counts'},indent=2))
