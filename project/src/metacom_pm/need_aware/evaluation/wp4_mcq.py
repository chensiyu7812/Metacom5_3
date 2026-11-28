"""Pre-output WP4 modified-MCQ rules with owner/history-family clustered inference."""
from collections import defaultdict
import random
from .short_mcq import score_short,PROTOCOL
from .wp2 import require,unique,score_cell,counts
from ..data.contracts import digest
from ..agent.reply_protocol import ARMS
from ..runtime.requests import physical_identity

# Display aliases only: retain B's original logical/request identities in scoring.
ARM_ALIASES={'NoMem':'No-memory','OptOnly':'Options-only'}
DIAGNOSTIC_ARMS=tuple(method+':'+view for method in ('U2','U3') for view in ('NoMem','OptOnly'))
ALLOWED_ARMS=(*ARMS,*ARM_ALIASES,'U2','U3',*DIAGNOSTIC_ARMS)
ALLOWED_MODELS=('Qwen35','Qwen35+U2','Qwen35+U3')


def validate_cell_binding(request, model, arm):
    require(model in ALLOWED_MODELS and arm in ALLOWED_ARMS,'unplanned WP4 cell')
    if arm.split(':')[0] in ('U2','U3'):
        require(model=='Qwen35+'+arm.split(':')[0],'adapted method/model mismatch')
    else:
        require(model=='Qwen35','control must use base Qwen35')
    require(request.get('model_label')==model,'request model label mismatch')
    require(request.get('g_id','').startswith('naag:'+model+':'),'unbound generator identity')
    require(request['request_sha256']==physical_identity(request['g_id'],request['messages'],
        request['input_ids'],request['decode']),'physical request hash mismatch')

POLICY=dict(protocol='naa-wp4-reply-mcq-policy-v1',scoring_protocol=PROTOCOL,
    primary='U3-U2 on whole frozen development set',
    secondary=['U1+-U1','U1-U0','U0-No-memory','No-memory-Options-only','U2-U0','U3-U1+'],
    secondary_inference='descriptive paired cluster intervals; no unadjusted secondary significance claims',
    target_categories=['who:others (metadata, not verified third-party)','pref_type:forget','sensitive_info:True'],
    meaningful_difference=.05,overall_noninferiority_margin=-.05,
    noninferiority='lower bound of paired owner-cluster CI > -0.05; not established by nonsignificance',
    missing='complete-pair accuracy plus fixed-evaluable-denominator failures-as-zero sensitivity and unknown bounds',
    bootstrap_seed=20261128,bootstrap_replicates=10000,confidence=.95,
    unit='connected owner/history-family component',
    claims='development evidence only; small cluster count limits power; no equivalence claim from nonsignificance',
    updated_forget_overlap='not general temporal preference updating',
    protocol_pooling='never pool with original official reasoning protocol')


def clusters(tasks):
    """Union owners sharing a history-family, rather than assuming one-to-one."""
    parent={t.persona_group:t.persona_group for t in tasks}
    def find(x):
        while parent[x]!=x:parent[x]=parent[parent[x]];x=parent[x]
        return x
    families={}
    for t in tasks:
        if t.source_family in families:parent[find(t.persona_group)]=find(families[t.source_family])
        families[t.source_family]=t.persona_group
    return {t.task_id:find(t.persona_group) for t in tasks}


def score(tasks,evaluations,requests,predictions,*,model,arm,kind='model'):
    require(arm in ALLOWED_ARMS,'unplanned condition')
    ix={k:dict(v) for k,v in unique(requests,'logical_id').items()}
    pm=unique(predictions,'task_id')
    for t in tasks:
        r=ix[f'{t.task_id}|{arm}|{model}']
        validate_cell_binding(r,model,arm)
        require(r['scoring_protocol']==PROTOCOL and r['task_sha256']==digest(t.to_dict()),'task/protocol changed')
        require(r['status'] in ('ready','capacity_exceeded'),'WP4 has no structural Direct holes')
        if r['status']=='capacity_exceeded':
            cap=r.get('capacity',{})
            require(cap.get('fits') is False and (cap.get('input_tokens',0)>cap.get('input_cap',float('inf'))
                or cap.get('input_tokens',0)+64>cap.get('backend_cap',float('inf'))),'native over-cap proof required')
            require(pm[t.task_id]['status']=='capacity_exceeded','capacity-overflow request was executed')
            r['status']='ready'  # evaluation copy only: predefined denominator is retained
        require(r.get('decode',{}).get('max_new_tokens')==64,'frozen short cap changed')
    result=score_cell(tasks,evaluations,ix,predictions,model=model,arm=arm,kind=kind,
        allowed_arms=ALLOWED_ARMS,allowed_models=ALLOWED_MODELS,score_function=score_short)
    c=clusters(tasks)
    for row in result:row['cluster']=c[row['task_id']]
    return result


def paired(left,right,*,replicates=None):
    a,b=unique(left,'task_id'),unique(right,'task_id')
    require(set(a)==set(b),'compare same frozen tasks only')
    require(all(a[t]['eligible']==b[t]['eligible'] for t in a),'unequal planned denominators')
    eligible=[t for t in sorted(a) if a[t]['eligible']]
    ids=[t for t in eligible if a[t]['status']==b[t]['status']=='completed']
    grouped=defaultdict(list)
    for t in ids:
        require(a[t]['cluster']==b[t]['cluster'],'cluster mismatch')
        grouped[a[t]['cluster']].append(int(b[t]['correct'])-int(a[t]['correct']))
    groups=list(grouped.values());rng=random.Random(POLICY['bootstrap_seed'])
    n=sum(map(len,groups));draws=[];macros=[]
    for _ in range(replicates or POLICY['bootstrap_replicates']):
        if not groups:break
        sample=[rng.choice(groups) for _ in groups]
        draws.append(sum(map(sum,sample))/sum(map(len,sample)))
        macros.append(sum(sum(g)/len(g) for g in sample)/len(sample))
    def ci(values):
        if len(groups)<2:return None
        v=sorted(values);return [v[int(.025*len(v))],v[min(len(v)-1,int(.975*len(v)))]]
    zero=lambda r:int(bool(r['correct'])) if r['status']=='completed' else 0
    low=sum(zero(b[t])-(zero(a[t]) if a[t]['status']=='completed' else 1) for t in eligible)
    high=sum((zero(b[t]) if b[t]['status']=='completed' else 1)-zero(a[t]) for t in eligible)
    return dict(planned_pairs=len(a),predefined_evaluable_pairs=len(eligible),complete_pairs=n,
        complete_clusters=len(groups),repairs=sum(not a[t]['correct'] and b[t]['correct'] for t in ids),
        regressions=sum(a[t]['correct'] and not b[t]['correct'] for t in ids),
        left_accuracy_on_pairs=sum(a[t]['correct'] for t in ids)/n if n else None,
        right_accuracy_on_pairs=sum(b[t]['correct'] for t in ids)/n if n else None,
        micro_difference=sum(map(sum,groups))/n if n else None,micro_cluster_ci95=ci(draws),
        owner_macro_difference=sum(sum(g)/len(g) for g in groups)/len(groups) if groups else None,
        owner_macro_cluster_ci95=ci(macros),
        fixed_denominator_difference_sensitivity=sum(zero(b[t])-zero(a[t]) for t in eligible)/len(eligible) if eligible else None,
        unknown_difference_bounds=[low/len(eligible),high/len(eligible)] if eligible else None)


def summarize(rows):
    result=counts(rows)
    # iid Wilson intervals are invalid here because multiple tasks share owners.
    result.pop('completed_wilson_ci95')
    grouped=defaultdict(list)
    for r in rows:
        if r['eligible'] and r['status']=='completed':grouped[r['cluster']].append(r['correct'])
    result['completed_clusters']=len(grouped)
    result['owner_macro_accuracy']=sum(sum(v)/len(v) for v in grouped.values())/len(grouped) if grouped else None
    return result
