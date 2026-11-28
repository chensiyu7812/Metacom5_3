#!/usr/bin/env python3
"""Score one frozen WP3 cell; predictions include all planned logical slots."""
import argparse,json
from pathlib import Path
from metacom_pm.need_aware.data.contracts import load_runtime
from metacom_pm.need_aware.data.v11 import jsonl
from metacom_pm.need_aware.data.personamem import write_json,write_jsonl,sha_file
from metacom_pm.need_aware.evaluation.contracts import EvalTask
from metacom_pm.need_aware.evaluation.wp3 import score_requests
from metacom_pm.need_aware.evaluation.wp2 import counts

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('runtime','evaluation','requests','predictions','model','arm','out'):p.add_argument('--'+n,required=True)
    p.add_argument('--task-ids',help='Frozen JSON list; e.g. the preselected Gemma subset')
    p.add_argument('--kind',choices=('model','plumbing'),default='model')
    a=p.parse_args();tasks=load_runtime(a.runtime);ev={r['task_id']:EvalTask(**r) for r in jsonl(a.evaluation)}
    if a.task_ids:
        ids=set(json.loads(Path(a.task_ids).read_text()));tasks=[t for t in tasks if t.task_id in ids];ev={t:ev[t] for t in ids}
        if {t.task_id for t in tasks}!=ids:raise ValueError('unknown selected tasks')
    rows=score_requests(tasks,ev,jsonl(a.requests),jsonl(a.predictions),model=a.model,arm=a.arm,kind=a.kind)
    out=Path(a.out)
    if out.exists():raise FileExistsError('sealed scoring output exists')
    write_jsonl(out/'scored.private.jsonl',rows)
    report=dict(result_kind=a.kind,model_capability_result=a.kind=='model',summary=counts(rows),
                inputs={n:sha_file(Path(getattr(a,n))) for n in ('runtime','evaluation','requests','predictions')})
    write_json(out/'RECEIPT.json',report);print(json.dumps(report,indent=2))
