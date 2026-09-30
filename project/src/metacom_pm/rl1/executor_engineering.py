"""Post-hoc engineering subset admission. NEVER qualifies a research executor.

Mechanical validation cannot substitute for the separately recorded AI review.
This module never calls a judge or infers semantic approval from q/m scores.
"""
from .schema import digest


def admitted_rows(contract, jobs, requests, raws, reviews):
    if contract.get('status')!='POST_HOC_ENGINEERING_ONLY' or contract.get('eligible_for_research_or_rl') is not False:
        raise ValueError('explicit engineering-only contract required')
    conditions = {(c['index'],c['condition']):c for c in contract['conditions']}
    ids = [j['request_id'] for j in jobs]
    if len(ids) != len(set(ids)) or set(ids) != set(reviews):
        raise ValueError('every attempted job needs exactly one review')
    rows=[]
    for job in jobs:
        key=job['request_id']; req=requests[key]; raw=raws[key]; review=reviews[key]
        condition=conditions[job['index'],job['condition']]
        if condition['split'] not in ('train','dev') or job['split']!=condition['split']:
            raise ValueError('test or changed split is prohibited')
        if (req['request_id']!=key or digest({k:v for k,v in req.items() if k!='request_id'})!=key
                or req['messages']!=condition['messages']
                or digest(req['messages'])!=condition['messages_identity']
                or raw['request_id']!=key or raw['runtime_identity']!=req['executor_identity']):
            raise ValueError('generation does not match exact visible input/runtime')
        if (review.get('request_identity')!=key or review.get('raw_identity')!=digest(raw)
                or review.get('messages_identity')!=digest(req['messages'])
                or not review.get('rationale') or not review.get('checks')):
            raise ValueError('review not bound to the actual answer and prompt')
        if review['status'] not in ('accept','reject','uncertain','technical_failure'):
            raise ValueError('invalid review status')
        if review['status']!='accept': continue
        if raw['finish_reason']!='natural_stop' or not raw['text'].strip():
            raise ValueError('technical failure cannot become supervision')
        if review.get('unresolved_claims') or any(v is not True for v in review['checks'].values()):
            raise ValueError('unresolved or failed admission checks')
        rows.append(dict(request_id=key,index=job['index'],owner=condition['owner'],split=condition['split'],
            condition=job['condition'],head=condition['head'],prefix_identity=condition['prefix_identity'],
            messages=req['messages'],response=raw['text'],messages_identity=digest(req['messages']),
            response_identity=digest(raw['text']),review_identity=digest(review),
            historical_uptake=review.get('historical_uptake',False)))
    expected=set(conditions)
    # Full factorial coverage remains required by the ORIGINAL research pilot.
    # This separate engineering exercise keeps every accepted row, allows empty
    # cells, and reports their exact absence. It does not reinterpret that gate.
    expected_owners={c['owner'] for c in conditions.values()}
    if {r['owner'] for r in rows}!=expected_owners:
        raise ValueError('engineering subset must retain every sampled owner')
    for split in ('train','dev'):
        if {r['condition'] for r in rows if r['split']==split}!={'OFF','R','L'}:
            raise ValueError('engineering subset must retain all condition labels per split')
    if len({r['index'] for r in rows if r['split']=='train' and r['historical_uptake']})<4:
        raise ValueError('insufficient explicitly reviewed historical resource uptake')
    train={r['owner'] for r in rows if r['split']=='train'}
    dev={r['owner'] for r in rows if r['split']=='dev'}
    if train & dev: raise ValueError('owner leakage')
    return rows


def accumulation_groups(examples, size):
    """The last partial group has its own denominator, never the full batch size."""
    if not examples or size<1: raise ValueError('empty training set or invalid accumulation')
    for start in range(0,len(examples),size):
        group=examples[start:start+size]
        tokens=sum(e.target_tokens for _,e in group)
        if tokens<=0: raise ValueError('no response tokens')
        yield group,tokens
