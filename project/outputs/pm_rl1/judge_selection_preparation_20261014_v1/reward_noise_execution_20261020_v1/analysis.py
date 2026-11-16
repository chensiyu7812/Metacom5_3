"""Descriptive disjoint-block statistics; no imputation or reward promotion."""
from fractions import Fraction

def utility(row):
    if not row or not row.get('technical_valid'):return None
    ev=row['evaluation']
    if ev.get('model_unknown') or ev.get('q') is None or ev.get('m') is None:return None
    return Fraction(str(ev['q']))/4-Fraction(str(ev['m']))

def mean_complete(values):
    return None if not values or any(x is None for x in values) else sum(values)/len(values)

def sign(x):return None if x is None else (1 if x>0 else -1 if x<0 else 0)
def value(x):return None if x is None else float(x)

def compare_blocks(ds):
    single=[ds[0],ds[2]]
    aggregate=[mean_complete(ds[:2]),mean_complete(ds[2:])]
    def pair(xs):
        complete=all(x is not None for x in xs)
        return dict(values=list(map(value,xs)),signs=list(map(sign,xs)),complete=complete,
            direction_changed=sign(xs[0])!=sign(xs[1]) if complete else None,
            strict_positive_negative_flip=sign(xs[0])*sign(xs[1])==-1 if complete else None,
            absolute_discrepancy=value(abs(xs[0]-xs[1])) if complete else None)
    return dict(single=pair(single),mean_two=pair(aggregate))

def calculate(proposal,protocol,results):
    by={(s['endpoint'],s['draw']):results.get(s['slot_id']) for s in protocol['schedule']}
    endpoints=[]
    for e in proposal['endpoints']:
        rows=[by.get((e['row_id'],r)) for r in range(1,5)]
        us=[utility(r) for r in rows]
        endpoints.append(dict(endpoint=e['row_id'],context_id=e['context_id'],counts=e['counts'],
            q=[r['evaluation'].get('q') if r else None for r in rows],
            m=[r['evaluation'].get('m') if r else None for r in rows],U=list(map(value,us)),
            technical_valid=[r.get('technical_valid',False) if r else None for r in rows],
            model_unknown=[r['evaluation'].get('model_unknown') if r else None for r in rows],
            m1_draws=[i+1 for i,r in enumerate(rows) if r and r['evaluation'].get('m')==1],
            complete_four=all(x is not None for x in us),
            U_range=value(max(us)-min(us)) if all(x is not None for x in us) else None,
            block_comparison=compare_blocks(us),reward_eligible=False))
    contrasts=[]
    for c in proposal['contrasts']:
        cost=Fraction(1,20)*c['resource_tokens']/2048
        ds=[]
        for draw in range(1,5):
            on=utility(by.get((c['on'],draw)));off=utility(by.get((c['off'],draw)))
            ds.append(None if on is None or off is None else on-off-cost)
        contrasts.append(dict(**c,D=list(map(value,ds)),blocks=compare_blocks(ds),
            human_direction=None,human_comparable=False,source_review_status='pending_separate_audit'))
    complete=[c for c in contrasts if c['blocks']['single']['complete'] and c['blocks']['mean_two']['complete']]
    contexts=[]
    for context in sorted({e['context_id'] for e in proposal['endpoints']}):
        subset=[c for c in contrasts if c['id'].startswith(context+'_')]
        paired=[c for c in subset if c in complete]
        available=len(paired)==len(subset)
        a=sum(c['blocks']['single']['absolute_discrepancy'] for c in paired) if available else None
        b=sum(c['blocks']['mean_two']['absolute_discrepancy'] for c in paired) if available else None
        contexts.append(dict(context_id=context,paired_contrasts=len(paired),planned=len(subset),
            single_absolute_discrepancy_sum=a,mean_two_absolute_discrepancy_sum=b,
            reduced=bool(b<a) if available else None,
            ranking_note='Two ON plans share the same OFF. Pair counts are not independent observations.'))
    summary=dict(planned_contrasts=len(contrasts),paired_complete=len(complete),
        single_complete=sum(c['blocks']['single']['complete'] for c in contrasts),
        mean_two_complete=sum(c['blocks']['mean_two']['complete'] for c in contrasts),
        single_direction_changes=sum(c['blocks']['single']['direction_changed'] for c in complete),
        mean_two_direction_changes=sum(c['blocks']['mean_two']['direction_changed'] for c in complete),
        single_positive_negative_flips=sum(c['blocks']['single']['strict_positive_negative_flip'] for c in complete),
        mean_two_positive_negative_flips=sum(c['blocks']['mean_two']['strict_positive_negative_flip'] for c in complete),
        single_discrepancy_sum=sum(c['blocks']['single']['absolute_discrepancy'] for c in complete),
        mean_two_discrepancy_sum=sum(c['blocks']['mean_two']['absolute_discrepancy'] for c in complete),
        reduced_contexts=sum(c['reduced'] is True for c in contexts),
        human_comparable=0,human_status='PENDING_NOT_IMPUTED',reward_eligible=False)
    return dict(endpoints=endpoints,contrasts=contrasts,contexts=contexts,summary=summary)
