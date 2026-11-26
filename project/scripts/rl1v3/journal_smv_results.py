"""Collect/review the frozen SMV30 outputs without another model call.

Only the pre-generation review-v2 contract determines completion. Semantic
observations are explicit private development records, never a qualified reward.
"""
import argparse
import copy
import json
from collections import Counter
from pathlib import Path
from datetime import datetime
from metacom_pm.rl1v3.io import file_sha256,object_sha256,write_json_once,write_jsonl_once
from metacom_pm.rl1v3.generator import limited_run as L
from metacom_pm.rl1v3.journal.selective_memory_validation_run import check,admit
from metacom_pm.rl1v3.journal.selective_memory_validation_review import validate_review


def jl(path):return [json.loads(x) for x in Path(path).read_text().splitlines()]


def collect(package,run_root,preparation,out):
    package,run_root,preparation,out=map(Path,(package,run_root,preparation,out))
    if out.exists():raise FileExistsError(out)
    rows=[];reports=[];inputs={};all_evals={};all_requests={};all_tasks={}
    for n in (1,2):
        path=package/f'batch-{n:02d}/PLAN.json';plan,requests,baseline=check(path)
        auth_path=run_root/f'SMV{n}_AUTHORIZED.json';auth=json.loads(auth_path.read_text());admit(plan,auth)
        job=run_root/f'SMV{n}_run1'/('job-'+object_sha256(auth))
        summary=json.loads((job/'SUMMARY.json').read_text())
        previous=None;events=[]
        for seq,f in enumerate(sorted(job.glob('[0-9]*.json'))):
            e=json.loads(f.read_text())
            if e['seq']!=seq or e['previous_event_sha256']!=previous:raise ValueError('journal chain')
            if f.name!=f"{seq:03d}-{e['event']}.json":raise ValueError('journal filename')
            previous=file_sha256(f);inputs[str(f)]=previous;events.append(e)
        if summary['last_journal_sha256']!=previous or summary['plan_sha256']!=object_sha256(plan):raise ValueError('summary identity')
        if events[0]['event']!='RUN_START' or events[0]['approval']!=auth:raise ValueError('approval identity')
        if file_sha256(auth['decision_evidence'])!=auth['decision_evidence_sha256']:raise ValueError('researcher evidence identity')
        starts=[e for e in events if e['event']=='REQUEST_START']
        if [e['request_id'] for e in starts]!=plan['ordered_request_ids'][:len(starts)]:raise ValueError('order/retry/unrequested call')
        by_id={r['request_id']:r for r in requests};returns={};validated={}
        loads=[e for e in events if e['event']=='LOAD_START'];loaded=[e for e in events if e['event']=='LOAD_OK']
        if len(loads)>1 or len(loaded)>len(loads):raise ValueError('load count')
        for i,e in enumerate(starts,1):
            if e['physical_ordinal']!=i or e['payload_sha256']!=by_id[e['request_id']]['payload_sha256']:raise ValueError('start payload')
        started={e['request_id']:e for e in starts}
        for e in events:
            rid=e.get('request_id')
            if e['event']=='REQUEST_RETURNED':
                if rid not in started or rid in returns or e['seq']<=started[rid]['seq']:raise ValueError('unstarted/duplicate return')
                returns[rid]=e
            elif e['event']=='REQUEST_VALIDATED':
                if rid not in returns or rid in validated or e['seq']<=returns[rid]['seq']:raise ValueError('unreturned/duplicate validation')
                validated[rid]=e['finish_reason']
        if summary['physical_calls']!=len(starts) or summary['validated_calls']!=len(validated):raise ValueError('count mismatch')
        if summary['status']=='FINISHED' and len(validated)!=len(requests):raise ValueError('incomplete finished set')
        evals={r['task_id']:r for r in jl(plan['review_path'])};all_evals.update(evals);all_requests.update(by_id)
        all_tasks.update({r['task_id']:r for r in jl(plan['task_manifest_path'])})
        for r in requests:
            e=returns.get(r['request_id']);output=e['output'] if e else None;finish=validated.get(r['request_id'])
            if output is not None and finish is not None and L.validate_result(r,output)!=finish:raise ValueError('token/stop identity')
            binding=dict(task_id=r['task_id'],arm=r['arm'],logical_id=r['logical_id'],request_id=r['request_id'],
                payload_sha256=r['payload_sha256'],evalspec_sha256=object_sha256(evals[r['task_id']]),
                source_port_binding_sha256=r['source_port_binding_sha256'],renderer_id=r['renderer_id'])
            rows.append(dict(**binding,endpoint_id='smv-endpoint:'+object_sha256(binding),output=output,
                output_sha256=object_sha256(output) if output else None,technical_status=finish or 'unrun_or_unvalidated',
                channel=evals[r['task_id']]['channel'],source_case_id=evals[r['task_id']]['source_case_id'],
                formal_reward=None,plan_sha256=object_sha256(plan)))
        returned=[e['output'] for e in returns.values()]
        reports.append(dict(batch=n,plan_sha256=object_sha256(plan),job_status=summary['status'],
            physical_starts=len(starts),physical_returns=len(returns),validated=len(validated),
            finish_counts=dict(Counter(validated.values())),model_loads=len(loads),
            input_tokens=sum(o['input_tokens'] for o in returned),output_tokens=sum(len(o['token_ids']) for o in returned),
            generation_seconds=sum(o['seconds'] for o in returned),job_wall_seconds=summary['wall_seconds'],
            worker_load_seconds=loaded[0]['measurement']['seconds'] if loaded else None,
            supervisor_load_seconds=(datetime.fromisoformat(loaded[0]['utc'])-datetime.fromisoformat(loads[0]['utc'])).total_seconds() if loaded else None))
        for f in (path,auth_path,job/'SUMMARY.json',Path(plan['requests_path']),Path(plan['review_path'])):inputs[str(f)]=file_sha256(f)
    templates={r['logical_id']:r for r in jl(preparation/'REVIEW_TEMPLATE_PRIVATE.jsonl')}
    reviews=[];readback=['# SMV30 full actual response readback — PRIVATE','No formal reward; source-authored development observations only.']
    for i,row in enumerate(rows):
        review=copy.deepcopy(templates[row['logical_id']]);review.update(output_sha256=row['output_sha256'],technical_status=row['technical_status'])
        reviews.append(review);ev=all_evals[row['task_id']];r=all_requests[row['request_id']]
        readback += [f"\n## {i//2+1:02d} / {row['arm']} / {ev['channel']} / {ev['source_case_id']}",
            '\nVisible query:\n'+all_tasks[row['task_id']]['query'],
            '\nRequired facts: '+','.join(ev['required_fact_ids']), '\nSupport goal: '+ev['support_goal'],
            '\nProhibitions:\n'+'\n'.join(ev['prohibitions']), '\nSource references:']
        for ref in ev['fact_references']:readback += [ref['atom_id']+' '+ref['semantic_reference']+'\n'+ref['quote']]
        readback += ['\nFull G output:\n'+(row['output']['text'] if row['output'] else '[NOT RETURNED]')]
    out.mkdir(parents=True)
    write_jsonl_once(out/'ACTUAL_RESPONSES_PRIVATE.jsonl',rows)
    write_jsonl_once(out/'REVIEW_UNFILLED_PRIVATE.jsonl',reviews)
    (out/'READBACK_PRIVATE.md').write_text('\n'.join(readback)+'\n')
    report=dict(protocol='pmrl1-j-smv-actual-v1',jobs=reports,rows=len(rows),
        physical_calls=sum(r['physical_starts'] for r in reports),eos=sum(r['technical_status']=='eos' for r in rows),
        input_tokens=sum(r['input_tokens'] for r in reports),output_tokens=sum(r['output_tokens'] for r in reports),
        generation_seconds=sum(r['generation_seconds'] for r in reports),job_wall_seconds=sum(r['job_wall_seconds'] for r in reports),
        worker_load_seconds=sum(r['worker_load_seconds'] or 0 for r in reports),model_loads=sum(r['model_loads'] for r in reports),
        new_sequential_model_calls=0,formal_rewards=0,semantic_review_status='pending',collector_sha256=file_sha256(__file__))
    write_json_once(out/'TECHNICAL_PUBLIC.json',report)
    write_json_once(out/'INPUTS_PRIVATE.json',inputs)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('package','run-root','preparation','out'):p.add_argument('--'+k,required=True)
    print(json.dumps(collect(**{k.replace('-','_'):v for k,v in vars(p.parse_args()).items()}),indent=2))
