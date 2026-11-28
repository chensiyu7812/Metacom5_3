"""Open-reply evaluator: mechanical format/action is NOT semantic quality.

Independent blinded ratings are required for task success and naturalness.
No API judge, keyword proxy, missing rating or synthetic output becomes a score.
"""
from collections import Counter,defaultdict
import json
from .wp2 import require,wilson
from .aggregate import paired_cluster
from .wp2 import unique,STATUSES,FAILURES
from ..data.contracts import digest
from ..data.training_v11 import runtime_projection

RUBRIC='naa-open-rubric-v1'
DIMENSIONS=('task_complete','appropriate_use','misuse','unnecessary_clarification','over_refusal','natural_quality')


def parse_reply(text):
    try:r=json.loads(text)
    except (ValueError,TypeError):return None
    if not isinstance(r,dict) or set(r)!={'action','response'}:return None
    if r['action'] not in ('USE','IGNORE','CLARIFY') or not isinstance(r['response'],str) or not r['response'].strip():return None
    return r


def action_score(row,output):
    r=parse_reply(output)
    return dict(variant_id=row['variant_id'],group_id=row['group_id'],source_family=row['source_family'],
                parse_valid=r is not None,action_correct=r is not None and r['action'] in row['acceptable_actions'],
                semantic_success=None,natural_quality=None,
                limitation='Action-format check only; not answer quality or model capability without actual sealed predictions.')


def adjudicate_two(ratings):
    require(len(ratings)==2 and len({r['rater_id'] for r in ratings})==2,'two independent rater identities required')
    require(all(r.get('rubric')==RUBRIC for r in ratings),'rubric mismatch')
    for r in ratings:
        for d in DIMENSIONS:
            require(r.get(d) is None or type(r[d]) is int and r[d] in (range(1,6) if d=='natural_quality' else (0,1)), 'invalid rating')
    agreed={d:ratings[0][d] if ratings[0][d]==ratings[1][d] else None for d in DIMENSIONS}
    # Disagreement stays unknown, never picked to favor a method.
    agreed['semantic_success']=(int(agreed['task_complete']==1 and agreed['appropriate_use']==1 and
                                   agreed['misuse']==0 and agreed['over_refusal']==0)
                                if all(agreed[d] is not None for d in ('task_complete','appropriate_use','misuse','over_refusal')) else None)
    agreed['disagreements']=[d for d in DIMENSIONS if ratings[0][d]!=ratings[1][d]]
    return agreed


def group_success(rows):
    groups=defaultdict(list)
    for r in rows:groups[r['group_id']].append(r)
    result=[]
    for gid,rs in sorted(groups.items()):
        require(len({r['variant_id'] for r in rs})==len(rs),'duplicate variant')
        known=all(r.get('semantic_success') is not None for r in rs)
        kinds={r.get('result_kind') for r in rs}
        require(len(kinds)==1 and kinds<={'model','plumbing'},'explicit prediction provenance required')
        result.append(dict(task_id=gid,persona_group=rs[0]['source_family'],
            result_kind=next(iter(kinds)),status='completed' if known else 'missing',correct=all(r['semantic_success']==1 for r in rs) if known else None))
    return result


def paired_open(left,right,*,seed=20261128,replicates=10000):
    require({r['variant_id'] for r in left}=={r['variant_id'] for r in right},'same open tasks required')
    a,b=group_success(left),group_success(right)
    return paired_cluster(a,b,seed=seed,replicates=replicates)


def score_open_predictions(targets,requests,predictions,ratings,*,method,model,kind='model'):
    require(method in ('U0','U1','U2','U3') and kind in ('model','plumbing'),'unknown open method/provenance')
    ts=unique(targets,'variant_id');qs=unique(requests,'task_id');ps=unique(predictions,'task_id')
    require(set(ts)==set(qs)==set(ps),'every frozen open slot must be exported')
    rmap=defaultdict(list)
    for r in ratings:
        require(r['variant_id'] in ts,'rating for unknown task')
        rmap[r['variant_id']].append(r)
    out=[];runs=set()
    for tid,t in ts.items():
        q,p=qs[tid],ps[tid];lid=f'{tid}|{method}|{model}'
        require(q['logical_id']==p['logical_id']==lid and p['result_kind']==kind,'open prediction identity')
        require(q['runtime_sha256']==digest(runtime_projection(t)),'runtime/evidence changed')
        require(q['model_id']==p['model_id'] and q['request_sha256']==p['request_sha256'],'open model/request hash mismatch')
        require(q['status']=='ready' and q['request_sha256'],'constructed open source must be available')
        require(p.get('run_id') and p['status'] in STATUSES-{'not_evaluable'},'open run/status')
        runs.add(p['run_id']);n=p.get('attempt_count');status=p['status'];failure=p.get('failure_kind')
        require(type(n) is int and 0<=n<=2,'invalid attempts')
        require(isinstance(p.get('output'),str),'open text output required')
        if status=='completed':
            require(n>0 and p.get('finish_reason') in ('eos','length') and failure is None,'unvalidated completion')
            row=action_score(t,p['output'])
        else:
            require(p['output']=='' and p.get('finish_reason') is None,'failed slot has output')
            if status=='missing':require(failure==('interrupted' if n else 'unattempted'),'invalid missing reason')
            elif status=='capacity_exceeded':require(n==0 and failure=='capacity_exceeded','capacity classification')
            else:require(n>0 and failure in FAILURES-{'unattempted','capacity_exceeded'},'failure classification')
            row=dict(variant_id=tid,group_id=t['group_id'],source_family=t['source_family'],parse_valid=None,
                     action_correct=None,semantic_success=None,natural_quality=None)
        if rmap[tid]:
            require(status=='completed','ratings for an uncompleted output')
            require(all(r.get('output_sha256')==digest(p['output']) for r in rmap[tid]),'rating/output hash mismatch')
            row.update(adjudicate_two(rmap[tid]))
        row.update(result_kind=kind,status=status,failure_kind=failure,attempt_count=n,method=method,model=model,
                   request_sha256=q['request_sha256'],run_id=p['run_id'])
        out.append(row)
    require(len(runs)==1,'mixed open runs')
    done=[r for r in out if r['status']=='completed'];known=[r for r in done if r['semantic_success'] is not None]
    groups=group_success(out);known_groups=[r for r in groups if r['status']=='completed']
    summary=dict(result_kind=kind,model_capability_result=kind=='model',planned=len(out),completed=len(done),
        completion_rate=len(done)/len(out) if out else None,technical_uncompleted=len(out)-len(done),
        technical_failures=dict(Counter(r['failure_kind'] for r in out if r['status']!='completed')),
        parse_failures=sum(not r['parse_valid'] for r in done),semantic_rated=len(known),semantic_unknown=len(out)-len(known),
        semantic_success_rate=sum(r['semantic_success'] for r in known)/len(known) if known else None,
        planned_groups=len(groups),complete_rated_groups=len(known_groups),
        matched_group_success=sum(r['correct'] for r in known_groups)/len(known_groups) if known_groups else None,
        semantic_unknown_bounds=[sum(r['semantic_success'] for r in known)/len(out),
                                (sum(r['semantic_success'] for r in known)+len(out)-len(known))/len(out)] if out else None)
    return out,summary
