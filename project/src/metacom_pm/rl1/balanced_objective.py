"""One quality/seconds objective for BC, program regression and PPO targets.

This is an explicit adapter, not a change to historical TokenCost executors.
Only exact, completed client traces can supply observed cost. Qualification
of quality remains with the existing feedback compiler; intervals stay bands.
"""
from dataclasses import asdict,dataclass
from copy import deepcopy
import math

from .calibration_workflow import stamp,verify_identity
from .client_latency import validate_trace
from .schema import Score,digest

VERSION='pmrl1-balanced-quality-seconds-v1'


@dataclass(frozen=True)
class BalancedObjective:
    seconds_weight: float
    regime_identity: str

    def __post_init__(self):
        if (type(self.seconds_weight) not in (int,float) or not math.isfinite(self.seconds_weight)
                or self.seconds_weight<0 or not self.regime_identity):
            raise ValueError('explicit finite seconds weight and deployment regime required')

    @property
    def identity(self): return digest(dict(version=VERSION,**asdict(self),token_cost=0,metric='client_completion_seconds'))

    def band(self,gain_interval,seconds):
        if gain_interval is None or seconds is None: return None
        if (len(gain_interval)!=2 or any(type(x) not in (int,float) or not math.isfinite(x) for x in (*gain_interval,seconds))
                or gain_interval[0]>gain_interval[1] or seconds<0):
            raise ValueError('ordered finite utility interval and observed seconds required')
        return tuple(x-self.seconds_weight*seconds for x in gain_interval)


def timing_receipt(endpoint,response,*,trace,raw,payload,path_family,source_identity,without_text=False):
    """Bind the same evidence acquisition AND exact reply to a measured path.

    An OFF request on a fixed path is not the sequential policy's STOP cost.
    OneShot search requires its own measured planning path; no substitution.
    """
    verify_identity(endpoint);validate_trace(trace)
    if path_family not in ('sequential','oneshot','fixed') or not source_identity or type(without_text) is not bool:
        raise ValueError('declared execution path and timing source required')
    request=endpoint['requests']['ON']; actual=raw.get('request')
    if (trace['status']!='natural_stop' or actual is None or raw.get('finish_reason')!='natural_stop'
            or trace['request_identity']!=digest(payload) or trace['server_result_identity']!=digest(raw)
            or trace['reply_identity']!=digest(raw['text']) or response.get('text')!=raw['text']
            or response.get('request_id')!=request['request_id']
            or response.get('finish_reason')!='natural_stop'
            or actual['messages']!=request['messages'] or actual['expected_input_tokens']!=request['expected_input_tokens']
            or any(actual['provenance'][k]!=request['provenance'][k] for k in request['provenance'] if k!='interface_identity')
            or raw['input_tokens']!=request['expected_input_tokens']
            or actual['request_id']!=digest({k:v for k,v in actual.items() if k!='request_id'})
            or raw['request_id']!=actual['request_id'] or raw['runtime_identity']!=actual['executor_identity']):
        raise ValueError('completed timing must match the exact source program and scored reply')
    stages=raw['stages']; actor=[e['start_ns'] for e in stages if e['stage'] in ('actor_forward_scripted_action','actor_decision')]
    if path_family=='sequential':
        if len(actor)!=len(endpoint['actions']): raise ValueError('one decision boundary per sequential action required')
        if any(not trace['send_ns']<=t<=trace['completion_ns'] for t in actor) or actor!=sorted(set(actor)):
            raise ValueError('invalid sequential decision order')
        # First transition includes initial setup so sum(costs) is the entire
        # request. Later returns exclude all already charged waiting time.
        cuts=[trace['send_ns'],*actor[1:],trace['completion_ns']]
        parts=[(b-a)/1e9 for a,b in zip(cuts,cuts[1:])]
    elif path_family=='oneshot':
        if not any(e['stage']=='oneshot_planning' for e in stages):
            raise ValueError('OneShot planning time must actually be included')
        parts=[trace['completion_seconds']]
    else:
        if actor or not any(e['stage']=='fixed_retrieval_and_render' for e in stages):
            raise ValueError('fixed path cannot hide sequential computation')
        parts=[trace['completion_seconds']]
    if not math.isclose(sum(parts),trace['completion_seconds'],rel_tol=1e-12,abs_tol=1e-12):
        raise ValueError('time allocation does not equal complete request latency')
    return stamp(dict(version=VERSION,endpoint_identity=endpoint['identity'],actions=endpoint['actions'],
        input_identity=digest(request['messages']),reply_identity=digest(response['text']),
        path_family=path_family,regime_identity=trace['regime_identity'],
        without_text=without_text,execution_path_identity=digest(dict(source=source_identity,path_family=path_family,
            variant=payload.get('path',path_family),without_text=without_text)),
        behavior_identity=raw.get('behavior_identity'),
        decision_mode=('scripted_replay' if any(e['stage']=='actor_forward_scripted_action' for e in stages)
            else raw.get('decision_mode')),
        completion_seconds=trace['completion_seconds'],step_seconds=parts,
        trace_identity=trace['identity'],source_identity=source_identity))


def rewards(gain,timing,*,objective,actions,path_family):
    verify_identity(timing)
    if (timing['version']!=VERSION or timing['regime_identity']!=objective.regime_identity
            or timing['path_family']!=path_family or timing['actions']!=list(actions)):
        raise ValueError('program/path/deployment cost mismatch')
    if gain is None: return None
    if type(gain) not in (int,float) or not math.isfinite(gain):
        raise ValueError('a qualified scalar quality gain is required; intervals are not averaged')
    if path_family=='sequential' and len(timing['step_seconds'])!=len(actions):
        raise ValueError('incomplete sequential cost allocation')
    if (any(type(t) not in (int,float) or not math.isfinite(t) or t<0 for t in timing['step_seconds'])
            or not timing['step_seconds'] or not math.isfinite(timing['completion_seconds'])
            or not math.isclose(sum(timing['step_seconds']),timing['completion_seconds'],abs_tol=1e-10)):
        raise ValueError('invalid allocation of observed seconds')
    result=[-objective.seconds_weight*t for t in timing['step_seconds']]
    result[-1]+=gain
    if not math.isclose(sum(result),gain-objective.seconds_weight*timing['completion_seconds'],abs_tol=1e-10):
        raise ValueError('balanced reward counted latency incorrectly')
    return result


def revalue_handoff(handoff,menu,*,timings,responses,objective,path_family):
    """All planned endpoints or pending. Recompute from q/m, not old net reward."""
    verify_identity(handoff);verify_identity(menu)
    base=dict(version=VERSION,quality_handoff_identity=handoff['identity'],menu_identity=menu['identity'],
        objective=asdict(objective),objective_identity=objective.identity,path_family=path_family)
    if handoff['menu_identity']!=menu['identity']: raise ValueError('different quality menu')
    if handoff['status']!='READY':
        return stamp(base|dict(status='PENDING_QUALITY',measured=[],targets=[],pending=handoff['pending']))
    endpoints={e['identity']:e for e in menu['endpoints']}
    if {r['endpoint_identity'] for r in handoff['measured']}!=set(endpoints): raise ValueError('quality pool was reduced')
    measured=[];pending=[];paths=set()
    for row in handoff['measured']:
        e=endpoints[row['endpoint_identity']]; t=timings.get(e['identity'])
        if t is None:
            pending.append(dict(endpoint=e['identity'],reason='missing_'+path_family+'_latency'));continue
        response=responses[e['requests']['ON']['request_id']]
        paths.add(t['execution_path_identity'])
        if len(paths)>1:raise ValueError('mixed implementations or text visibility in one method cost table')
        if (t['endpoint_identity']!=e['identity'] or t['input_identity']!=digest(e['requests']['ON']['messages'])
                or t['reply_identity']!=digest(response['text'])):
            raise ValueError('timing belongs to a different program or answer')
        labels=row['labels']
        on=Score(labels['ON']['q'],labels['ON']['m'],('qualified-handoff',))
        off=Score(labels['OFF']['q'],labels['OFF']['m'],('qualified-handoff',))
        gain=on.utility(1)-off.utility(1)
        rs=rewards(gain,t,objective=objective,actions=row['actions'],path_family=path_family)
        measured.append(dict(row,quality_gain=gain,rewards=rs,return_target=sum(rs),
            latency_seconds=t['completion_seconds'],latency_receipt_identity=t['identity'],
            cost_identity=objective.identity,legacy_token_reward_used=False))
    if pending: return stamp(base|dict(status='PENDING_LATENCY',measured=[],targets=[],pending=pending))
    targets=[]
    for pid in sorted({r['prefix_identity'] for r in measured}):
        xs=[r for r in measured if r['prefix_identity']==pid]
        targets.append(min(xs,key=lambda r:(-r['return_target'],r['latency_seconds'],tuple(r['actions']))))
    return stamp(base|dict(status='READY',measured=measured,targets=targets,pending=[],scope=handoff['scope'],
        execution_path_identity=next(iter(paths))))


def prepare_supervised(menu,*,factories,responses,receipts,view,method,timings,objective,union_proof=None):
    """Use original BC/OneShot optimizers with newly compiled balanced targets."""
    from .organized_supervision import prepare_supervised as original,prepare_targets
    from .organized_policy_interface import HeadSession
    if any(t['without_text']!=view.no_text for t in timings.values()):
        raise ValueError('timing text visibility differs from the trained method')
    base=original(menu,factories=factories,responses=responses,receipts=receipts,view=view,method=method,union_proof=union_proof)
    if base['status']!='READY': return base
    h=prepare_targets(menu,factories=factories,responses=responses,receipts=receipts,union_proof=union_proof)
    path='oneshot' if method=='OneShot' else 'sequential'
    balanced=revalue_handoff(h,menu,timings=timings,responses=responses,objective=objective,path_family=path)
    if balanced['status']!='READY':
        return stamp(dict(version=VERSION,status=balanced['status'],method=method,rows=[],handoff=balanced))
    rows=[];groups=[]
    for target in balanced['measured'] if method=='OneShot' else balanced['targets']:
        e=factories[target['prefix_identity']]();s=HeadSession(e.catalog,e.renderer,without_text=view.no_text);start=len(rows)
        if method=='OneShot':
            values,_=view.sequential(s.observe()); rows.append(dict(features=values,program=target['actions'],return_target=target['return_target']))
        else:
            for i,action in enumerate(target['actions']):
                values,mask=view.sequential(s.observe())
                if not mask[action]: raise ValueError('balanced BC selected an unavailable action')
                rows.append(dict(features=values,mask=mask,target=action,return_target=sum(target['rewards'][i:])))
                s.step(action)
        groups.append(dict(prefix_identity=target['prefix_identity'],endpoint_identity=target['endpoint_identity'],start=start,end=len(rows)))
    metadata={k:deepcopy(v) for k,v in base['metadata'].items() if k!='identity'}
    metadata.update(rows_identity=digest(rows),groups=groups,cost_identity=objective.identity,
        handoff_identity=balanced['identity'],balanced_objective=asdict(objective),
        reward_adapter=VERSION,path_family=path,legacy_quality_container_cost_identity=base['metadata']['cost_identity'],
        execution_path_identity=balanced['execution_path_identity'])
    return stamp({k:v for k,v in base.items() if k!='identity'}|dict(rows=rows,metadata=stamp(metadata),handoff_identity=balanced['identity']))


def ppo_targets(transitions,*,gain,timing,endpoint_identity,objective,policy_version,execution_path_identity,behavior_identity):
    """Compile original PPO inputs, replacing ALL old reward fields exactly once.

    Later state returns use only future charged cost; prior latency is sunk.
    The caller still owns on-policy collection, quality qualification, the
    complete 16-trajectory batch and update/recovery authorization.
    """
    if timing['endpoint_identity']!=endpoint_identity: raise ValueError('different trajectory endpoint')
    if timing['execution_path_identity']!=execution_path_identity:raise ValueError('different policy execution path')
    if (not behavior_identity or timing['behavior_identity']!=behavior_identity
            or timing['decision_mode'] not in ('sampled_policy','policy_replay','greedy_policy')):
        raise ValueError('latency must bind the current behavior parameters; scripted pilot is not policy feedback')
    actions=[int(t['action']) for t in transitions]
    if not transitions or actions[-1]!=0 or 0 in actions[:-1]: raise ValueError('complete on-policy trajectory required')
    rs=rewards(gain,timing,objective=objective,actions=actions,path_family='sequential')
    if rs is None: return None
    ts=deepcopy(transitions);remaining=0.
    for i in reversed(range(len(ts))):
        t=ts[i];t['reward']=rs[i];remaining+=rs[i]
        t['done']=i==len(ts)-1;t['return']=remaining;t['advantage']=remaining-float(t['old_value'])
    return dict(complete=True,policy_version=policy_version,transitions=ts,total_return=remaining,
        objective_identity=objective.identity,latency_receipt_identity=timing['identity'])
