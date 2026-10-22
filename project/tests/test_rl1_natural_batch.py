from dataclasses import asdict, replace
from pathlib import Path
import json
import pytest
import torch

from metacom_pm.rl1.natural_batch import PendingBatch, FeedbackQueue, MOCK, parameter_identity, baseline_schedule
from metacom_pm.rl1.natural_runner import NaturalEpisode
from metacom_pm.rl1.observation_features import make_actor_critic
from rl1_batch_fixtures import episodes, make_encoder, answer, drain, complete
from metacom_pm.rl1.bound_generation import BoundResourceEnv
from metacom_pm.rl1.schema import digest


def setup(tmp_path, seed=17, no_text=False):
    torch.set_num_threads(1);torch.manual_seed(seed)
    encoder, seen=make_encoder();model=make_actor_critic(encoder.feature_dimension)
    return PendingBatch(model,encoder,tmp_path/'updates',no_text=no_text),FeedbackQueue(tmp_path/'feedback.sqlite'),seen


def test_autonomous_acquisition_pending_then_complete_batch_update(tmp_path):
    b,q,seen=setup(tmp_path);es=episodes();before=parameter_identity(b.model)
    b.collect(es,batch_id='one')
    assert not q.counts() # GET and STOP sampling do not call any provider.
    assert all('MOCK_PRIVATE' not in t and 'PRIVATE_EVIDENCE' not in t for t in seen)
    assert seen[0]=='seeker: Mock current task 0'
    assert any(e.steps[0]['action']!=0 for e in es)
    assert any(len(e.steps)>2 for e in es)
    assert all(len(e.steps)<=5 and e.steps[-1]['action']==0 for e in es)
    initial=b.poll(q)
    assert all(x['return_value'] is None for x in initial)
    with pytest.raises(ValueError,match='all 16'):b.update_once()
    assert parameter_identity(b.model)==before and b.trainer.version==0
    results=complete(b,q)
    assert all(x['return_value']==pytest.approx(sum(s['reward'] for s in x['steps'])) for x in results)
    receipt=b.update_once()
    assert receipt['before']!=receipt['after'] and receipt['policy_version']==1
    assert receipt['real_natural_updates']==0 and not receipt['qualification_granted']
    with pytest.raises(ValueError):b.update_once()


def test_pending_checkpoint_restores_trajectory_probability_and_no_redispatch(tmp_path):
    b,q,_=setup(tmp_path);b.collect(episodes(),batch_id='one');b.poll(q)
    outstanding=q.claim_next();assert outstanding
    drain(q);path=tmp_path/'pending.pt';b.save(path)
    original=[r['transitions'] for r in b.records]
    b2,q2,_=setup(tmp_path,seed=91);b2.restore(path,episodes())
    for a,c in zip(original,[r['transitions'] for r in b2.records]):
        assert len(a)==len(c)
        for x,y in zip(a,c):assert torch.equal(x['old_log_prob'],y['old_log_prob'])
    assert any(x['state']=='STARTED' for x in q2.counts())
    with pytest.raises(ValueError):b2.update_once()
    q2.settle(outstanding['id'],answer(outstanding));complete(b2,q2)
    ready=tmp_path/'ready.pt';b2.save(ready)
    receipt=b2.update_once();assert receipt['behavior_log_probability_max_error']<=1e-5
    # Reloading an older complete checkpoint cannot repeat its optimizer event.
    b3,_,_=setup(tmp_path);b3.restore(ready,episodes())
    with pytest.raises(FileExistsError):b3.update_once()
    after=tmp_path/'updates'/f'{b2.batch_id}.after.pt'
    b4,_,_=setup(tmp_path);b4.restore(after,episodes())
    assert b4.consumed and parameter_identity(b4.model)==receipt['after']


def test_completed_cache_reused_but_actions_are_resampled(tmp_path):
    b,q,_=setup(tmp_path);b.collect(episodes(empty=True),batch_id='one');complete(b,q)
    assert sum(x['count'] for x in q.counts() if x['kind']=='generation')==2
    assert sum(x['count'] for x in q.counts() if x['kind']=='measurement')==2
    b2,_,_=setup(tmp_path/'other');b2.collect(episodes(tag='new',empty=True),batch_id='two')
    assert all(x['phase']=='terminal' for x in b2.poll(q))
    assert q.claim_next() is None
    assert len(b2.records)==16 and all(r['transitions'][0]['forced'] for r in b2.records)
    receipt=b2.update_once();assert receipt['policy_version']==1


@pytest.mark.parametrize('status',['semantic_uncertainty','technical_failure'])
def test_unknown_and_failure_never_zero_or_drop(tmp_path,status):
    b,q,_=setup(tmp_path);b.collect(episodes(empty=True),batch_id='one');b.poll(q);drain(q);b.poll(q)
    while (item:=q.claim_next()) is not None:q.settle(item['id'],answer(item,status))
    rs=b.poll(q)
    assert all(x['return_value'] is None for x in rs)
    assert all(x['phase']==('pending_score' if status=='semantic_uncertainty' else 'technical_failure') for x in rs)
    assert len(b.records)==16
    with pytest.raises(ValueError):b.update_once()
    counts=q.counts();b.poll(q);assert q.counts()==counts and q.claim_next() is None


def test_queue_binding_immutable_unknown_and_started_not_retried(tmp_path):
    b,q,_=setup(tmp_path);b.collect(episodes(empty=True),batch_id='one');b.poll(q)
    first=q.claim_next();good=answer(first)
    with pytest.raises(ValueError):q.settle(first['id'],dict(good,request_id='wrong'))
    drain(q);assert q.claim_next() is None
    reopened=FeedbackQueue(q.path);assert reopened.claim_next() is None
    reopened.settle(first['id'],good);reopened.settle(first['id'],good)
    with pytest.raises(ValueError):reopened.settle(first['id'],dict(good,text='modified'))


def test_behavior_drift_and_duplicate_trajectories_rejected(tmp_path):
    b,q,_=setup(tmp_path);es=episodes()
    with pytest.raises(ValueError):b.collect([es[0]]*16,batch_id='duplicate')
    b.collect(es,batch_id='one')
    with torch.no_grad():next(b.model.parameters()).add_(.01)
    with pytest.raises(ValueError,match='behavior weights'):b.poll(q)


def test_mock_cannot_authorize_formal_episode_or_natural_updates(tmp_path):
    e=episodes()[0];b,_,_=setup(tmp_path)
    with pytest.raises(ValueError):
        PendingBatch(b.model,b.encoder,tmp_path/'formal',mode='NATURAL_TRAINING')
    with pytest.raises((KeyError,ValueError)):
        NaturalEpisode(e.spec,e.renderer,evidence=e.evidence,freeze=e.freeze,freeze_inputs={},
            qualification=e.qualification,trajectory_id='real')
    es=episodes();es[0].spec=replace(es[0].spec,executor_identity='actual-generator')
    with pytest.raises(ValueError):b.collect(es,batch_id='real')


def test_no_text_masks_acquired_vectors_and_checkpoint_identity(tmp_path):
    b,q,_=setup(tmp_path,no_text=True);b.collect(episodes(),batch_id='one')
    for r in b.records:
        for t in r['transitions']:assert torch.count_nonzero(t['observation'][4:20])==0
    path=tmp_path/'no_text.pt';b.save(path)
    other,_,_=setup(tmp_path/'other')
    with pytest.raises(ValueError,match='ablation'):other.restore(path,episodes())


def test_schedule_keeps_six_runs_twenty_test_instances_and_no_authorization():
    x=baseline_schedule({'test':'mock'},episodes_per_seed=128)
    assert len(x['train_runs'])==6 and len(x['test_instances'])==20
    assert all(r['dev_checkpoints']==[64,128] for r in x['train_runs'])
    assert not x['real_training_authorized']


def test_cache_rejects_cross_draw_and_cross_source_reuse(tmp_path):
    b,q,_=setup(tmp_path);es=episodes(empty=True)
    b.collect(es,batch_id='one');complete(b,q)
    original=es[0].env.generation_request()
    assert q.generate(original) is not None
    changed=BoundResourceEnv(replace(es[0].spec,draw_identity='MOCK:another-draw'),es[0].renderer)
    changed.step(0,expected_state_hash=changed.state_hash)
    assert q.generate(changed.generation_request()) is None
    old=es[0].score_receipts[0]['binding'];reply=es[0].env.snapshot()['generation']['text']
    evidence={'mock_only':'new private source'}
    assert q.measure(dict(old,evidence_identity=digest(evidence)),evidence,reply) is None
    with pytest.raises(ValueError):q.measure(old,evidence,reply)


@pytest.mark.parametrize('status',['semantic_uncertainty','technical_failure'])
def test_unmeasured_result_cannot_smuggle_numeric_reward(tmp_path,status):
    b,q,_=setup(tmp_path);b.collect(episodes(empty=True),batch_id='one');b.poll(q);drain(q);b.poll(q)
    while (item:=q.claim_next()) is not None:
        q.settle(item['id'],dict(answer(item,status),q=0,m=0))
    before=parameter_identity(b.model)
    with pytest.raises(ValueError,match='unmeasured response'):b.poll(q)
    assert parameter_identity(b.model)==before and b.trainer.version==0
