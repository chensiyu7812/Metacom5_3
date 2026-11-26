#!/usr/bin/env python3
"""CPU adapter on the 16 real GSWS observations, no learned-state claim."""
import argparse,importlib.util,json,sys,time
from pathlib import Path


def run(events,skill_file,output):
    name='metacom_pm.rl1v3.journal.event_understanding'
    spec=importlib.util.spec_from_file_location(name,skill_file);module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module;spec.loader.exec_module(module)
    out=Path(output);out.mkdir(parents=True,exist_ok=False);seen=set();rows=[]
    for line in Path(events).open():
        r=json.loads(line)
        if r.get('kind')!='SEMANTIC_STATE':continue
        key=(r['task_id'],r['stage'])
        if key in seen:continue
        seen.add(key);obs=r['observation'];before=time.monotonic_ns()
        result=module.invoke_from_gsws(obs)
        assert all(e['text']==next(x['text'] for x in obs['evidence'] if x['evidence_id']==e['evidence_id']) for e in result['result']['evidence'])
        rows.append(dict(task_id=r['task_id'],stage=r['stage'],receipt=result,total_ns=time.monotonic_ns()-before))
    assert len(rows)==16
    (out/'TOOL_RESULTS.private.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
    report=dict(protocol='gsws-event-tool-cpu-connection-v1',observations=16,
        delivered_evidence_units=sum(len(r['receipt']['result']['evidence']) for r in rows),
        source_bound_cue_spans=sum(len(r['receipt']['result']['surface_cues']) for r in rows),
        total_ns=sum(r['total_ns'] for r in rows),semantic_qualification=False,model_calls=0,
        original_gpu_experiment_modified=False,adaptive_decision_tested=False,
        states=[dict(index=i+1,stage=r['stage'],units=len(r['receipt']['result']['evidence']),
                     cue_spans=len(r['receipt']['result']['surface_cues']),elapsed_ns=r['total_ns']) for i,r in enumerate(rows)])
    (out/'CONNECTION_PUBLIC.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ('events','skill-file','output'):p.add_argument('--'+n,required=True)
    a=p.parse_args();run(a.events,a.skill_file,a.output)
