#!/usr/bin/env python3
import argparse,json
from pathlib import Path
from metacom_pm.need_aware.data.v11 import jsonl
from metacom_pm.need_aware.data.personamem import write_json,write_jsonl
from metacom_pm.need_aware.evaluation.open_reply import score_open_predictions

if __name__=='__main__':
    p=argparse.ArgumentParser(description='Strict open output identity and independent-rating aggregation; no judge API')
    for n in ('targets','requests','predictions','method','model','out'):p.add_argument('--'+n,required=True)
    p.add_argument('--ratings');p.add_argument('--kind',choices=('model','plumbing'),default='model')
    a=p.parse_args();rows,report=score_open_predictions(jsonl(a.targets),jsonl(a.requests),jsonl(a.predictions),
        jsonl(a.ratings) if a.ratings else [],method=a.method,model=a.model,kind=a.kind)
    out=Path(a.out)
    if out.exists():raise FileExistsError('scored output exists')
    write_jsonl(out/'scored.private.jsonl',rows);write_json(out/'RECEIPT.json',report);print(json.dumps(report,indent=2))
