"""Weight-independent measured-component cost model for bounded diagnostics.

Output tokens are post-generation reward evidence, NEVER actor/critic inputs.
Training may reuse this cost environment across policy updates. Actual final
deployment latency remains a separately measured outcome.
"""
from copy import deepcopy
import math
import numpy as np
from scipy.optimize import nnls
from .calibration_workflow import stamp,verify_identity

VERSION='pmrl1-reusable-component-latency-v1'


def features(row):
    i,o=row['input_tokens'],row['output_tokens']
    if type(i) is not int or type(o) is not int or i<=0 or o<=0:raise ValueError('completed response token counts required')
    return [1.,i/1000,o/100,i*o/100000]


def fit(rows,pilots,*,source_identity,deployment_identity):
    """LOPO validates G costs; held-case pilots validate the available long path."""
    if not rows or not pilots or not source_identity or not deployment_identity:raise ValueError('measured sources required')
    x=np.array([features(r) for r in rows]);y=np.array([r['generation_seconds'] for r in rows]);g=np.array([r['prefix_identity'] for r in rows])
    if not np.isfinite(y).all() or min(y)<=0 or len(set(g))<3:raise ValueError('positive measured seconds and at least three groups required')
    predictions=np.empty(len(y))
    for pid in set(g):
        train=g!=pid;coef,_=nnls(x[train],y[train]);predictions[~train]=x[~train]@coef
    errors=abs(predictions-y);coef,_=nnls(x,y)
    def overhead(rs):
        totals={}
        for r in rs:
            for s in r['raw']['stages']:totals.setdefault(s['stage'],[]).append(s['seconds'])
        # Each acquisition has one stage; STOP's nearly free acquisition is
        # excluded from the GET estimate using total measured number of GETs.
        gets=sum(sum(s['stage']=='actor_forward_scripted_action' for s in r['raw']['stages'])-1 for r in rs)
        return dict(initial=float(np.mean(totals['initial_observation'])),
            per_decision=float(np.mean(totals['online_encoding'])+np.mean(totals['actor_forward_scripted_action'])),
            per_get=sum(totals['retrieval_and_observation'])/gets,
            terminal=float(np.mean(totals['terminal_render'])+np.mean(totals['request_binding'])))
    held={p['prefix_identity'] for p in pilots};train=np.array([p not in held for p in g])
    if sum(train)<3:raise ValueError('independent generation fit for pilot validation required')
    pilot_coef,_=nnls(x[train],y[train]);validation=[]
    for pid in held:
        other=[r for r in pilots if r['prefix_identity']!=pid]
        if not other:raise ValueError('at least two independent pilot contexts required')
        h=overhead(other)
        for r in pilots:
            if r['prefix_identity']!=pid:continue
            count=sum(s['stage']=='actor_forward_scripted_action' for s in r['raw']['stages'])-1
            prediction=float(np.array(features(r['raw']))@pilot_coef+h['initial']+h['terminal']+(count+1)*h['per_decision']+count*h['per_get'])
            validation.append(dict(prefix_identity=pid,GETs=count,predicted=prediction,
                observed=r['trace']['completion_seconds'],error=prediction-r['trace']['completion_seconds']))
    return stamp(dict(version=VERSION,source_identity=source_identity,deployment_identity=deployment_identity,
        coefficients=coef.tolist(),sequential_overhead=overhead(pilots),
        generator_validation=dict(scheme='leave-entire-prefix-out',rows=len(rows),prefixes=len(set(g)),
            MAE=float(errors.mean()),p90_absolute_error=float(np.quantile(errors,.9)),max_absolute_error=float(errors.max()),
            R_squared=float(1-np.sum((predictions-y)**2)/np.sum((y-y.mean())**2))),
        end_to_end_held_case_validation=validation,
        validated_GET_counts=sorted({r['GETs'] for r in validation}),
        input_range=[min(r['input_tokens'] for r in rows),max(r['input_tokens'] for r in rows)],
        output_range=[min(r['output_tokens'] for r in rows),max(r['output_tokens'] for r in rows)],
        policy_weight_independent=True,scope='REAL_DATA_COST_MODEL_DIAGNOSTIC'))


def estimate(model,response,actions,*,deployment_identity,path='sequential'):
    verify_identity(model)
    if deployment_identity!=model['deployment_identity']:raise ValueError('deployment changed; cost model needs revalidation')
    if not actions or actions[-1]!=0 or 0 in actions[:-1] or any(a not in range(5) for a in actions):raise ValueError('complete action sequence required')
    if path not in ('sequential','OFF'):raise ValueError('unmeasured method overhead; no cross-method substitution')
    if path=='OFF' and actions!=[0]:raise ValueError('OFF cannot acquire resources')
    if not model['input_range'][0]<=response['input_tokens']<=model['input_range'][1] or not model['output_range'][0]<=response['output_tokens']<=model['output_range'][1]:
        raise ValueError('generator features outside observed model range')
    g=float(np.array(features(response))@np.array(model['coefficients']));n=len(actions)-1;h=model['sequential_overhead']
    parts=[h['per_get']+h['per_decision']]*n+[g+h['per_decision']+h['terminal']]
    parts[0]+=h['initial']
    if path=='OFF':parts=[g]
    return stamp(dict(version=VERSION,cost_model_identity=model['identity'],path=path,actions=actions,
        deployment_identity=deployment_identity,step_seconds=parts,seconds=sum(parts),
        cost_kind='predicted_components',generator_seconds=g,overhead_seconds=sum(parts)-g,
        acquisition_count_extrapolation=n not in model['validated_GET_counts'],
        scope=model['scope'],behavior_parameter_binding_required=False))


def ppo_episode(transitions,*,gain,cost,weight,policy_version):
    """Reuse environment costs; the original PPO still checks sampled behavior."""
    verify_identity(cost)
    if gain is None:return None
    if not math.isfinite(gain) or not math.isfinite(weight) or weight<0:raise ValueError('explicit finite ordinal gain and seconds weight')
    if not transitions or [int(t['action']) for t in transitions]!=cost['actions'] or len(transitions)!=len(cost['step_seconds']):
        raise ValueError('cost is for a different trajectory')
    out=deepcopy(transitions);remaining=0.
    for i in reversed(range(len(out))):
        t=out[i];reward=-weight*cost['step_seconds'][i]+(gain if i==len(out)-1 else 0.)
        remaining+=reward;t.update(reward=reward,done=i==len(out)-1,return_value=remaining)
        t['return']=remaining;t['advantage']=remaining-float(t['old_value'])
    return dict(complete=True,policy_version=policy_version,transitions=out,total_return=remaining,
        cost_model_identity=cost['cost_model_identity'],cost_kind=cost['cost_kind'],scope='REAL_DATA_RELATIVE_FEEDBACK_DIAGNOSTIC')
