#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from metacom_pm.need_aware.data.contracts import load_runtime
from metacom_pm.need_aware.data.personamem import write_json,write_jsonl
from metacom_pm.need_aware.evaluation.score import load_eval,score_predictions

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ['runtime','evaluation','predictions','output']:p.add_argument('--'+name,required=True)
    p.add_argument('--kind',choices=['plumbing','model'],required=True);a=p.parse_args()
    tasks=load_runtime(a.runtime);ev=load_eval(a.evaluation)
    predictions=[json.loads(s) for s in Path(a.predictions).read_text().splitlines() if s.strip()]
    records,summary=score_predictions(tasks,ev,predictions,a.kind)
    write_jsonl(Path(a.output)/'scored.jsonl',records);write_json(Path(a.output)/'summary.json',summary)
    print(json.dumps({k:v for k,v in summary.items() if k!='by_category'},indent=2))
