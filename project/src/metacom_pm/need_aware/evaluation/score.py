"""Complete-denominator offline evaluation. Missing predictions stay visible."""
from collections import Counter, defaultdict
import json
from .contracts import EvalTask
from .mcq import score_one


def load_eval(path):
    with open(path) as f:
        rows=[EvalTask(**json.loads(line)) for line in f if line.strip()]
    if len({r.task_id for r in rows})!=len(rows):
        raise ValueError('duplicate evaluation task')
    return {r.task_id:r for r in rows}


def score_predictions(tasks, evaluations, predictions, kind):
    if kind not in {'model','plumbing'}:
        raise ValueError('explicit result kind required')
    mapping={}
    ids={t.task_id for t in tasks}
    if set(evaluations)!=ids:
        raise ValueError('evaluation task population mismatch')
    for p in predictions:
        if p['task_id'] not in ids or p['task_id'] in mapping:
            raise ValueError('unknown/duplicate prediction; score one model/arm at a time')
        if p.get('result_kind')!=kind:
            raise ValueError('plumbing/model provenance mismatch')
        if kind=='model' and (not p.get('request_sha256') or not p.get('model_id') or not p.get('run_id')):
            raise ValueError('model prediction lacks run identity')
        mapping[p['task_id']]=p
    records=[]
    for t in tasks:
        p=mapping.get(t.task_id)
        status='missing' if p is None else p.get('status','completed')
        r=score_one(p.get('output','') if p and status=='completed' else '',t,evaluations[t.task_id])
        r.update(status=status,persona_group=t.persona_group,category=evaluations[t.task_id].category,result_kind=kind)
        records.append(r)
    groups=defaultdict(list)
    for r in records:
        for key,value in r['category'].items():groups[f'{key}:{value}'].append(r)
    def counts(rows):
        completed=[r for r in rows if r['status']=='completed']
        return {'planned':len(rows),'completed':len(completed),'correct':sum(r['correct'] for r in completed),
                'invalid':sum(not r['parse_valid'] for r in completed),
                'accuracy_on_completed':sum(r['correct'] for r in completed)/len(completed) if completed else None,
                'status':dict(Counter(r['status'] for r in rows))}
    summary={'result_kind':kind,'model_capability_result':kind=='model',**counts(records),
             'by_category':{k:counts(v) for k,v in sorted(groups.items())}}
    return records,summary
