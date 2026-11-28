#!/usr/bin/env python3
"""Strict modified-MCQ evaluation, with real vs plumbing provenance preserved."""
import argparse,json
from pathlib import Path
from metacom_pm.need_aware.data.contracts import load_runtime
from metacom_pm.need_aware.data.response_data import jsonl
from metacom_pm.need_aware.data.personamem import write_json,write_jsonl,sha_file
from metacom_pm.need_aware.evaluation.contracts import EvalTask
from metacom_pm.need_aware.evaluation.wp4_mcq import score,summarize,paired,POLICY

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ('runtime','evaluation','requests','predictions','model','arm','out'):p.add_argument('--'+n,required=True)
    p.add_argument('--compare-scored');p.add_argument('--kind',choices=['model','plumbing'],default='model')
    a=p.parse_args();out=Path(a.out)
    if out.exists():raise FileExistsError('immutable evaluation destination')
    ts=load_runtime(a.runtime);ev={r['task_id']:EvalTask(**r) for r in jsonl(a.evaluation)}
    rs=score(ts,ev,jsonl(a.requests),jsonl(a.predictions),model=a.model,arm=a.arm,kind=a.kind)
    report=dict(policy=POLICY,result_kind=a.kind,model_capability_result=a.kind=='model',summary=summarize(rs),
        inputs={n:sha_file(getattr(a,n)) for n in ('runtime','evaluation','requests','predictions')})
    categories=sorted({(k,v) for r in rs for k,v in r['category'].items()})
    report['categories']={f'{k}:{v}':summarize([r for r in rs if r['category'].get(k)==v]) for k,v in categories}
    if a.compare_scored:
        other=jsonl(a.compare_scored)
        if {r['result_kind'] for r in other}!={a.kind}:raise ValueError('mixed provenance')
        report['paired']=paired(other,rs)
    write_jsonl(out/'scored.private.jsonl',rs);write_json(out/'SUMMARY.json',report)
    print(json.dumps(report['summary']))
