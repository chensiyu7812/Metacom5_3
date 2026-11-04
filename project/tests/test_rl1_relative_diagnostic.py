import json
import pytest
import torch

from metacom_pm.rl1.calibration_workflow import stamp
from metacom_pm.rl1.relative_diagnostic import parse,agreement,cost_return
from metacom_pm.rl1.reusable_latency import ppo_episode,estimate
from metacom_pm.rl1.observation_features import make_actor_critic
from metacom_pm.rl1.e0_learning import PPO
from metacom_pm.rl1.natural_batch import parameter_identity


def test_unknown_and_position_disagreement_are_not_zero():
    a=dict(verdict='A_better',risk_A='none_detected',risk_B='local')
    b=dict(verdict='B_better',risk_A='local',risk_B='none_detected')
    assert agreement(dict(identity='pair'),a,b)['gain']==1.
    assert agreement(dict(identity='pair'),a,a)['gain'] is None
    assert agreement(dict(identity='pair'),a,None)['gain'] is None
    assert cost_return(None,2.,.1) is None
    assert cost_return(0.,2.,.1)==-.2


def test_final_json_cannot_cite_missing_evidence_or_parse_thinking():
    evidence=dict(current_prefix=[dict(id='C:T000')],legal_past_sessions=[])
    obj=dict(verdict='near_equal',risk_A='none_detected',risk_B='none_detected',reason='both adequate',evidence_ids=['C:T000'])
    assert parse('<think>{"verdict":"A_better"}</think>'+json.dumps(obj),evidence)==obj
    obj['evidence_ids']=['future:1']
    with pytest.raises(ValueError,match='unknown cited'):parse(json.dumps(obj),evidence)


def test_session_scope_normalization_preserves_judgment_and_rejects_invented_ids():
    import importlib.util
    from pathlib import Path
    path=Path(__file__).resolve().parents[1]/'scripts/rl1/159_bounded_real_diagnostic.py'
    spec=importlib.util.spec_from_file_location('relative_runner_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    evidence=dict(current_prefix=[dict(id='C:T000')],legal_past_sessions=[dict(id='H001',turns=[dict(id='H001:T000')])])
    obj=dict(verdict='A_better',risk_A='none_detected',risk_B='material',reason='unsupported claim',evidence_ids=['C:T000','H001'])
    result,coarse=module.normalize_response(json.dumps(obj),evidence)
    assert result['verdict']==obj['verdict'] and result['reason']==obj['reason'] and coarse==['H001']
    obj['evidence_ids']=['H999']
    with pytest.raises(ValueError,match='unknown cited'):module.normalize_response(json.dumps(obj),evidence)


def test_closeout_preserves_legacy_json_bytes_on_repeat(tmp_path):
    import importlib.util
    from pathlib import Path
    path=Path(__file__).resolve().parents[1]/'scripts/rl1/158_try_relative_feedback.py'
    spec=importlib.util.spec_from_file_location('relative_closeout_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    for name,value in [('PAIRS_PRIVATE.json',[]),('REQUESTS_PRIVATE.json',[]),('EXPECTATIONS_PRIVATE.json',{})]:
        (tmp_path/name).write_text(json.dumps(value))
    (tmp_path/'responses').mkdir()
    first=module.analyze(tmp_path)
    target=tmp_path/'ANALYSIS.json'
    target.write_text(json.dumps(first,indent=4))  # Prior writer used a different representation.
    original=target.read_bytes()
    assert module.analyze(tmp_path)==first and module.analyze(tmp_path)==first
    assert target.read_bytes()==original


def model():
    return stamp(dict(coefficients=[.1,.15,3.,.2],sequential_overhead=dict(initial=.03,per_decision=.05,per_get=.06,terminal=.002),
        deployment_identity='frozen deployment',input_range=[200,6000],output_range=[10,300],validated_GET_counts=[6],scope='diagnostic'))


def test_model_cost_checks_deployment_and_keeps_method_and_extrapolation_visible():
    m=model();reply=dict(input_tokens=1000,output_tokens=50)
    c=estimate(m,reply,[3,0],deployment_identity='frozen deployment')
    assert c['acquisition_count_extrapolation'] and sum(c['step_seconds'])==c['seconds']
    assert c['cost_kind']=='predicted_components' and not c['behavior_parameter_binding_required']
    with pytest.raises(ValueError,match='deployment'):estimate(m,reply,[0],deployment_identity='changed')
    with pytest.raises(ValueError,match='unmeasured method'):estimate(m,reply,[0],deployment_identity='frozen deployment',path='OneShot')


def test_original_ppo_reuses_cost_after_weights_change_without_recharging_sunk_cost():
    torch.manual_seed(17);actor=make_actor_critic(3);ppo=PPO(actor)
    costs={tuple(a):estimate(model(),dict(input_tokens=1000,output_tokens=50),a,deployment_identity='frozen deployment') for a in ([0],[3,0])}
    seen=[];before=parameter_identity(actor)
    for version in range(2):
        batch=[]
        for i in range(16):
            ts=[];actions=[]
            for step in range(2):
                x=torch.tensor([1.,float(step),0.]);mask=torch.tensor([True,False,False,step==0,False])
                with torch.no_grad():dist,val=actor(x,mask);sample=dist.sample()
                ts.append(dict(observation=x,mask=mask,action=sample,old_log_prob=dist.log_prob(sample),old_value=val,forced=step==1))
                actions.append(int(sample))
                if not int(sample):break
            cost=costs[tuple(actions)]
            ep=ppo_episode(ts,gain=.5,cost=cost,weight=.05,policy_version=version)
            assert ep['transitions'][-1]['return']==pytest.approx(.5-.05*cost['step_seconds'][-1])
            batch.append(ep)
        seen.append(ppo.update(batch));assert ppo.version==version+1
    assert all(x['behavior_log_probability_max_error']<1e-5 for x in seen)
    assert cost['cost_model_identity']==model()['identity'] and parameter_identity(actor)!=before
