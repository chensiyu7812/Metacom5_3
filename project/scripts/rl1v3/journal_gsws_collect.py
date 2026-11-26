#!/usr/bin/env python3
"""Read actual logs, never infer a reply/latency from a finished job label."""
import argparse,json,hashlib
from collections import Counter
from pathlib import Path


def collect(run_root,catalog_path,output):
    root=Path(run_root);out=Path(output);out.mkdir(parents=True,exist_ok=False)
    catalog=json.loads(Path(catalog_path).read_text());jobs=[];endpoints=[];interpretations=[];slots=[]
    plan0=json.loads(Path(catalog['batches'][0]['plan_path']).read_text())
    tasks=[json.loads(s) for s in Path(plan0['task_manifest_path']).read_text().splitlines()]
    aliases={t['task_id']:f'Q{i+1:02}' for i,t in enumerate(tasks)}
    for n,b in enumerate(catalog['batches'],1):
        plan=json.loads(Path(b['plan_path']).read_text());paths=list((root/f'run-{n:02}').glob('job-*/SUMMARY.json'))
        if len(paths)>1:raise ValueError('multiple attempts; must not silently select one')
        if not paths:
            jobs.append(dict(job=b['name'],status='not_started',loads=0,model_calls_started=0,model_calls_returned=0,terminal_outputs=0,interpreter_outputs=0,wall_seconds=None))
            for slot in plan['terminal_slots']:slots.append(dict(task=aliases[slot['task_id']],stage=slot['stage'],arm=slot['arm'],status='not_started',semantic_result=None))
            continue
        summary=json.loads(paths[0].read_text());events=[json.loads(p.read_text()) for p in sorted(paths[0].parent.glob('[0-9]*.json'))]
        starts={e['request']['request_id']:e['request'] for e in events if e['event']=='MODEL_CALL_START'}
        returned=[e for e in events if e['event']=='MODEL_CALL_RETURNED'];actual=[e for e in events if e['event']=='ENDPOINT']
        for e in returned:
            req=starts[e['request_id']];binding=req['binding'];row=dict(task=aliases[binding['task_id']],stage=binding['stage'],arm=binding['arm'],request=req,raw_output=e['output'])
            if req['role']=='terminal':endpoints.append(row)
            else:interpretations.append(row)
        completed={(e['task_id'],e['stage'],e['arm']):e for e in actual}
        for slot in plan['terminal_slots']:
            e=completed.get((slot['task_id'],slot['stage'],slot['arm']))
            slots.append(dict(task=aliases[slot['task_id']],stage=slot['stage'],arm=slot['arm'],
                status=('terminal_eos' if e['terminal_technical_complete'] else 'terminal_length') if e else 'unexecuted_after_job_stop',semantic_result=None))
        load_start=next((e for e in events if e['event']=='LOAD_START'),None);load_end=next((e for e in events if e['event']=='LOAD_OK'),None)
        jobs.append(dict(job=b['name'],status=summary['status'],failure=summary.get('supervisor_failure'),
            loads=int(load_start is not None),model_calls_started=len(starts),model_calls_returned=len(returned),
            terminal_outputs=sum(starts[e['request_id']]['role']=='terminal' for e in returned),
            interpreter_outputs=sum(starts[e['request_id']]['role']!='terminal' for e in returned),
            wall_seconds=summary['wall_ns']/1e9,
            load_parent_seconds=(load_end['stamp']['monotonic_ns']-load_start['stamp']['monotonic_ns'])/1e9 if load_end and load_start else None,
            source_summary_sha256=hashlib.sha256(paths[0].read_bytes()).hexdigest()))
    for name,data in [('TERMINALS_RAW.private.jsonl',endpoints),('INTERPRETERS_RAW.private.jsonl',interpretations),('SLOT_STATUS_PUBLIC.jsonl',slots)]:
        (out/name).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in data))
    report=dict(protocol='gsws-actual-log-collection-v1',jobs=jobs,total_model_calls=sum(j['model_calls_returned'] for j in jobs),
        terminal_outputs=len(endpoints),interpreter_outputs=len(interpretations),slots=48,
        slot_status=dict(Counter(s['status'] for s in slots)),semantic_comparison_available=bool(endpoints),
        formal_reward=None,unexecuted_is_not_semantic_failure=True)
    (out/'ACTUAL_PUBLIC.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('run-root','catalog','output'):p.add_argument('--'+name,required=True)
    a=p.parse_args();collect(a.run_root,a.catalog,a.output)
