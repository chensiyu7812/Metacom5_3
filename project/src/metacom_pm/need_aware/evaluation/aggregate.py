"""Persona-cluster paired comparisons; failures and missing pairs stay explicit."""
from collections import defaultdict
import random


def paired_cluster(left,right,*,seed=20261127,replicates=2000):
    def index(rows):
        result={r['task_id']:r for r in rows}
        if len(result)!=len(rows):raise ValueError('duplicate scored task')
        return result
    a,b=index(left),index(right)
    if set(a)!=set(b):raise ValueError('paired task populations differ')
    clusters=defaultdict(list);repair=regression=unchanged=missing=0
    for tid in a:
        x,y=a[tid],b[tid]
        if x['persona_group']!=y['persona_group']:raise ValueError('paired persona differs')
        if x['status']!='completed' or y['status']!='completed':missing+=1;continue
        delta=int(y['correct'])-int(x['correct']);clusters[x['persona_group']].append(delta)
        repair+=delta==1;regression+=delta==-1;unchanged+=delta==0
    n=sum(map(len,clusters.values()))
    result={'planned_pairs':len(a),'complete_pairs':n,'missing_or_failed_pairs':missing,
            'personas':len(clusters),'repairs':repair,'regressions':regression,'unchanged':unchanged,
            'paired_difference':(repair-regression)/n if n else None,'ci95':None,
            'inference_scope':'development paired comparison; no equivalence/noninferiority claim'}
    if len(clusters)<2:return result
    rng=random.Random(seed);owners=sorted(clusters);samples=[]
    for _ in range(replicates):
        chosen=[clusters[rng.choice(owners)] for _ in owners]
        samples.append(sum(map(sum,chosen))/sum(map(len,chosen)))
    samples.sort();result['ci95']=[samples[int(.025*(replicates-1))],samples[int(.975*(replicates-1))]]
    return result
