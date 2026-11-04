"""Synthetic quality/time fixtures only; no natural learning evidence."""
from copy import deepcopy

import pytest
import torch

from metacom_pm.rl1.balanced_objective import (BalancedObjective,timing_receipt,revalue_handoff,
    prepare_supervised,ppo_targets,rewards)
from metacom_pm.rl1.calibration_workflow import stamp
from metacom_pm.rl1.client_latency import VERSION as CLIENT_VERSION
from metacom_pm.rl1.e0_learning import PPO
from metacom_pm.rl1.natural_batch import parameter_identity
from metacom_pm.rl1.organized_supervision import prepare_targets,comparison_union,endpoint
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.supervised_learning import fit_supervised,load_initialization
from test_rl1_organized_supervision import materials,complete_comparison
from test_rl1_organized_learning_bridge import view,raw as response_fixture


def timing(e,response,seconds,*,path='sequential',behavior='SYNTHETIC behavior'):
    # Artificial monotonic ticks, explicitly within ENGINEERING_ONLY fixtures.
    payload=dict(fixture=True,endpoint=e['identity']); start=10**9;end=start+int(seconds*1e9)
    request=e['requests']['ON'];n=len(e['actions'])
    stages=([dict(stage='actor_decision',start_ns=start+int(i*seconds/n*1e9)) for i in range(n)]
        if path=='sequential' else [dict(stage='oneshot_planning' if path=='oneshot' else 'fixed_retrieval_and_render',start_ns=start)])
    raw=dict(response,request=request,stages=stages,behavior_identity=behavior,decision_mode='policy_replay')
    trace=stamp(dict(version=CLIENT_VERSION,trace_id='synthetic',request_identity=digest(payload),
        regime_identity='SYNTHETIC',surface='local_reference_queue_client',concurrency=1,
        send_ns=start,first_text_ns=end-1,last_text_ns=end,completion_ns=end,observed_end_ns=end+1,
        status='natural_stop',ttft_seconds=(end-1-start)/1e9,completion_seconds=seconds,
        observed_wait_seconds=(end+1-start)/1e9,reply_identity=digest(response['text']),server_result_identity=digest(raw),error=None))
    return timing_receipt(e,response,trace=trace,raw=raw,payload=payload,path_family=path,source_identity='SYNTHETIC timing')


def timing_map(menu,responses,*,path='sequential'):
    return {e['identity']:timing(e,responses[e['requests']['ON']['request_id']],1. if e['actions']==[0] else 5.,path=path) for e in menu['endpoints']}


def test_global_weight_changes_balance_and_token_penalty_is_replaced():
    menu,fs,rs,js,_=materials(programs=((0,),(2,0)))
    h=prepare_targets(menu,factories=fs,responses=rs,receipts=js);ts=timing_map(menu,rs)
    low=revalue_handoff(h,menu,timings=ts,responses=rs,objective=BalancedObjective(.05,'SYNTHETIC'),path_family='sequential')
    high=revalue_handoff(h,menu,timings=ts,responses=rs,objective=BalancedObjective(.2,'SYNTHETIC'),path_family='sequential')
    assert low['targets'][0]['actions']==[2,0] and high['targets'][0]['actions']==[0]
    for row in low['measured']:
        assert row['return_target']==pytest.approx(row['quality_gain']-.05*row['latency_seconds'])
        assert row['legacy_token_reward_used'] is False
    # Same seconds weight, different quality evidence: selected behavior changes.
    changed=deepcopy(js)
    for e in menu['endpoints']:
        if e['actions']!=[0]: changed[e['requests']['ON']['request_id']]['q']=2
    h2=prepare_targets(menu,factories=fs,responses=rs,receipts=changed)
    assert revalue_handoff(h2,menu,timings=ts,responses=rs,objective=BalancedObjective(.05,'SYNTHETIC'),path_family='sequential')['targets'][0]['actions']==[0]


def test_missing_quality_or_timing_cannot_shrink_the_pool():
    menu,fs,rs,js,_=materials(programs=((0,),(2,0)))
    h=prepare_targets(menu,factories=fs,responses=rs,receipts=js);ts=timing_map(menu,rs)
    ts.pop(next(iter(ts)))
    result=revalue_handoff(h,menu,timings=ts,responses=rs,objective=BalancedObjective(.1,'SYNTHETIC'),path_family='sequential')
    assert result['status']=='PENDING_LATENCY' and result['measured']==result['targets']==[]
    h=prepare_targets(menu,factories=fs,responses=rs,receipts={})
    assert revalue_handoff(h,menu,timings={},responses=rs,objective=BalancedObjective(.1,'SYNTHETIC'),path_family='sequential')['status']=='PENDING_QUALITY'


def test_intervals_remain_intervals_and_methods_need_their_own_cost():
    objective=BalancedObjective(.1,'SYNTHETIC')
    assert objective.band((0.,.2),3.)==pytest.approx((-.3,-.1))
    assert objective.band(None,3.) is None
    menu,fs,rs,js,_=materials(programs=((0,),(2,0)))
    e=menu['endpoints'][0];t=timing(e,rs[e['requests']['ON']['request_id']],1.,path='fixed')
    with pytest.raises(ValueError,match='path'): rewards(0.,t,objective=objective,actions=e['actions'],path_family='sequential')
    with pytest.raises(ValueError,match='intervals'): rewards((0.,.2),t,objective=objective,actions=e['actions'],path_family='fixed')
    with pytest.raises(ValueError,match='deployment'): rewards(0.,t,objective=BalancedObjective(.1,'browser'),actions=e['actions'],path_family='fixed')


def test_bc_and_oneshot_use_original_optimizers_with_balanced_targets(tmp_path):
    menu,fs,rs,js,exports=materials(programs=((0,),(2,0)))
    objective=BalancedObjective(.05,'SYNTHETIC');v=view(tmp_path)
    data=prepare_supervised(menu,factories=fs,responses=rs,receipts=js,view=v,method='BC-init',
        timings=timing_map(menu,rs),objective=objective)
    assert data['rows'][0]['return_target']==pytest.approx(.25)
    assert data['rows'][-1]['return_target']==pytest.approx(.375)
    receipt=fit_supervised(data,seed=17,directory=tmp_path/'bc')
    assert receipt['scope']=='ENGINEERING_ONLY' and receipt['optimizer_steps']==50
    model,_=load_initialization(data,seed=17,path=tmp_path/'bc/checkpoint.pt',receipt=receipt)
    assert parameter_identity(model)==receipt['final_parameters']
    final,rs,js,proof=comparison_union(**complete_comparison(menu,fs,exports))
    one=prepare_supervised(final,factories=fs,responses=rs,receipts=js,view=v,method='OneShot',
        timings=timing_map(final,rs,path='oneshot'),objective=objective,union_proof=proof)
    assert sorted(r['return_target'] for r in one['rows'])==pytest.approx([-.05,.25])
    rec=fit_supervised(one,seed=17,directory=tmp_path/'one')
    assert rec['status']=='ONESHOT_REGRESSION_COMPLETED' and len(one['rows'])==2


def test_implementation_and_visibility_costs_cannot_be_pooled(tmp_path):
    menu,fs,rs,js,_=materials(programs=((0,),(2,0)))
    h=prepare_targets(menu,factories=fs,responses=rs,receipts=js);ts=timing_map(menu,rs)
    key=next(iter(ts));old=ts[key]
    ts[key]=stamp({k:v for k,v in old.items() if k!='identity'}|dict(execution_path_identity='another implementation'))
    with pytest.raises(ValueError,match='mixed implementations'):
        revalue_handoff(h,menu,timings=ts,responses=rs,objective=BalancedObjective(.1,'SYNTHETIC'),path_family='sequential')
    ts[key]=stamp({k:v for k,v in old.items() if k!='identity'}|dict(without_text=True))
    with pytest.raises(ValueError,match='text visibility'):
        prepare_supervised(menu,factories=fs,responses=rs,receipts=js,view=view(tmp_path),method='BC-init',
            timings=ts,objective=BalancedObjective(.1,'SYNTHETIC'))


@pytest.mark.parametrize('change',[dict(behavior_identity='older parameters'),dict(decision_mode='scripted_replay')])
def test_timing_of_scripted_or_different_behavior_is_not_ppo_feedback(change):
    menu,fs,rs,js,_=materials(programs=((0,),(2,0)))
    e=menu['endpoints'][0];t=timing(e,rs[e['requests']['ON']['request_id']],1.)
    bad=stamp({k:v for k,v in t.items() if k!='identity'}|change)
    with pytest.raises(ValueError,match='current behavior'):
        ppo_targets([dict(action=a) for a in e['actions']],gain=0.,timing=bad,endpoint_identity=e['identity'],
            objective=BalancedObjective(.1,'SYNTHETIC'),policy_version=0,
            execution_path_identity=t['execution_path_identity'],behavior_identity='SYNTHETIC behavior')


def test_future_returns_do_not_recharge_elapsed_time_and_original_ppo_updates(tmp_path):
    menu,fs,rs,js,_=materials(programs=((0,),(2,0)))
    e=next(e for e in menu['endpoints'] if e['actions']==[2,0])
    t=timing(e,rs[e['requests']['ON']['request_id']],5.)
    transitions=[dict(observation=torch.zeros(3),mask=torch.ones(5,dtype=torch.bool),action=torch.tensor(a),
        old_log_prob=torch.tensor(-1.6),old_value=torch.tensor(0.),reward=-999.,forced=False) for a in [2,0]]
    objective=BalancedObjective(.1,'SYNTHETIC')
    target=ppo_targets(transitions,gain=.5,timing=t,endpoint_identity=e['identity'],objective=objective,policy_version=0,execution_path_identity=t['execution_path_identity'],behavior_identity='SYNTHETIC behavior')
    assert target['total_return']==pytest.approx(0.)
    assert target['transitions'][-1]['return']==pytest.approx(.25)
    later=stamp({k:v for k,v in t.items() if k!='identity'}|dict(step_seconds=[10.5,2.5],completion_seconds=13.))
    changed=ppo_targets(transitions,gain=.5,timing=later,endpoint_identity=e['identity'],objective=objective,policy_version=0,execution_path_identity=t['execution_path_identity'],behavior_identity='SYNTHETIC behavior')
    assert changed['transitions'][-1]['return']==target['transitions'][-1]['return']
    from metacom_pm.rl1.observation_features import make_actor_critic
    v=view(tmp_path);actor=make_actor_critic(v.feature_dimension);trainer=PPO(actor)
    factory=next(iter(fs.values()))
    def collect(version):
        episodes=[]
        for i in range(16):
            ep=factory();ts=[];actions=[]
            while ep.phase=='acquiring':
                values,mask=v.sequential(ep.session.observe())
                values=torch.tensor(values,dtype=torch.float32);mask=torch.tensor(mask)
                with torch.no_grad():dist,value=actor(values,mask);action=dist.sample()
                ts.append(dict(observation=values,mask=mask,action=action,old_log_prob=dist.log_prob(action).detach(),
                    old_value=value.detach(),forced=int(mask.sum())==1,reward=-999.))
                actions.append(int(action));ep.step(int(action))
            bound,_=endpoint(factory,actions)
            reply=response_fixture(bound['requests']['ON'],'SYNTHETIC answer')
            cost=timing(bound,reply,1.+.2*(len(actions)-1),behavior=parameter_identity(actor))
            episodes.append(ppo_targets(ts,gain=.5 if 2 in actions else 0.,timing=cost,
                endpoint_identity=bound['identity'],objective=objective,policy_version=version,execution_path_identity=cost['execution_path_identity'],behavior_identity=parameter_identity(actor)))

        return episodes
    episodes=collect(0);before=parameter_identity(actor)
    with pytest.raises(ValueError,match='16 complete'):trainer.update(episodes[:15])
    result=trainer.update(episodes)
    assert parameter_identity(actor)!=before and trainer.version==1
    assert result['behavior_log_probability_max_error']<1e-5
    again=collect(1)
    assert len(again)==16 and all(e['policy_version']==1 for e in again)
    assert transitions[0]['reward']==-999.  # source record never mutated
