"""Actual small-network optimization on explicit engineering fixtures only."""
from copy import deepcopy
import torch
import pytest

from metacom_pm.rl1.learning_preparation import PolicyInputView
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.calibration_workflow import stamp
from metacom_pm.rl1.supervised_learning import (prepare_supervised,fit_supervised,
    load_initialization,OneShotReturnModel,NATURAL,ENGINEERING,plan_features)
from test_rl1_learning_handoff import inputs
from rl1_batch_fixtures import make_encoder


def prepared(method='BC-init'):
    torch.set_num_threads(1)
    cs,kw,_=inputs('final_train_union' if method in ('OneShot','BC-union') else 'initial_train')
    encoder,_=make_encoder();view=PolicyInputView(encoder,no_text=method=='PPO-NoText')
    data=prepare_supervised(cs,**kw,view=view,method=method)
    return data,view,kw


def test_measured_remaining_returns_do_not_charge_past_GETs_twice():
    data,_,kw=prepared();rows=data['rows']
    assert data['scope']==ENGINEERING
    assert rows[0]['return_target']<.5 and rows[1]['return_target']==pytest.approx(.5)
    assert [r['target'] for r in rows]==[1,0]
    assert all(set(r)=={'features','mask','target','return_target'} for r in rows)


def test_original_full_BC_and_value_training_reload_and_rng(tmp_path):
    data,_,_=prepared();before=torch.get_rng_state().clone()
    receipt=fit_supervised(data,seed=17,directory=tmp_path/'bc')
    assert torch.equal(before,torch.get_rng_state())
    assert receipt['optimizer_steps']==50 and receipt['value_steps']==500
    assert receipt['actor_unchanged_during_value_initialization']
    assert receipt['initial_parameters']!=receipt['after_supervision']!=receipt['final_parameters']
    assert receipt['last_supervised_loss']<receipt['first_supervised_loss']
    assert not receipt['research_checkpoint'] and receipt['natural_policy_updates']==0
    model,state=load_initialization(data,seed=17,path=tmp_path/'bc/checkpoint.pt',receipt=receipt)
    assert state['supervised_optimizer']['state'] and state['value_optimizer']['state']
    assert not state['ppo_optimizer']['state']
    assert state['ppo_optimizer']['param_groups'][0]['weight_decay']==0
    assert torch.equal(before,torch.get_rng_state())
    with pytest.raises(FileExistsError):fit_supervised(data,seed=17,directory=tmp_path/'bc')


def test_NoText_has_same_initial_random_weights_own_training_and_no_cross_load(tmp_path):
    full,_,_=prepared();no,_,_=prepared('PPO-NoText')
    a=fit_supervised(full,seed=17,directory=tmp_path/'full')
    b=fit_supervised(no,seed=17,directory=tmp_path/'no')
    assert a['initial_parameters']==b['initial_parameters']
    assert a['final_parameters']!=b['final_parameters']
    assert a['requirements']['supervision_identity']!=b['requirements']['supervision_identity']
    assert all(not any(r['features'][4:20]) for r in no['rows'])
    with pytest.raises(ValueError):load_initialization(no,seed=17,path=tmp_path/'full/checkpoint.pt',receipt=a)


def test_OneShot_trains_every_measured_return_and_masks_prediction(tmp_path):
    data,view,_=prepared('OneShot')
    assert len(data['rows'])==2 # both OFF and ON, not one winner class
    assert data['rows'][0]['return_target']==0
    assert data['rows'][1]['return_target']>0
    assert all(set(r)=={'features','plan','return_target'} for r in data['rows'])
    receipt=fit_supervised(data,seed=17,directory=tmp_path/'one')
    model,_=load_initialization(data,seed=17,path=tmp_path/'one/checkpoint.pt',receipt=receipt)
    assert isinstance(model,OneShotReturnModel) and receipt['value_steps']==0
    assert receipt['status']=='ONESHOT_REGRESSION_COMPLETED'
    assert model.choose(data['rows'][0]['features'],[True]+[False]*69)==(0,0,0,0)
    with pytest.raises(ValueError):plan_features((True,0,0,0))


def test_no_qualification_or_research_permission_means_no_model_or_training_file(tmp_path):
    cs,kw,_=inputs();encoder,_=make_encoder()
    kw['qualification_bundle']=None
    pending=prepare_supervised(cs,**kw,view=PolicyInputView(encoder),method='BC-init')
    with pytest.raises(ValueError):fit_supervised(pending,seed=17,directory=tmp_path/'pending')
    data,_,_=prepared()
    real=stamp({k:v for k,v in (data|dict(scope=NATURAL)).items() if k!='identity'})
    with pytest.raises(ValueError,match='authorization'):fit_supervised(real,seed=17,directory=tmp_path/'unauthorized')
    assert not list(tmp_path.iterdir())


def test_changed_labels_and_incomplete_value_checkpoint_are_rejected(tmp_path):
    data,_,_=prepared();bad=deepcopy(data);bad['rows'][0]['return_target']=100
    with pytest.raises(ValueError):fit_supervised(bad,seed=17,directory=tmp_path/'bad')
    receipt=fit_supervised(data,seed=17,directory=tmp_path/'good')
    bad_receipt=stamp({k:v for k,v in (receipt|dict(value_steps=0)).items() if k!='identity'})
    with pytest.raises(ValueError):load_initialization(data,seed=17,path=tmp_path/'good/checkpoint.pt',receipt=bad_receipt)
