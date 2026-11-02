"""Synthetic forward/queue/optimizer tests; no pretrained models or providers."""
from copy import deepcopy
import json

import pytest
import torch

from metacom_pm.rl1.calibration_workflow import qualify, stamp
from metacom_pm.rl1.e0_learning import PPO
from metacom_pm.rl1.natural_batch import FeedbackQueue, parameter_identity
from metacom_pm.rl1.observation_features import make_actor_critic
from metacom_pm.rl1.organized_encoding import BlockCache, EncodedHeadView, forward_blocks
from metacom_pm.rl1.organized_feedback import (OrganizedEpisode, TokenCost, QualifiedRoute,
    bind_generation_result, visible_generation_request, domain_identity)
from metacom_pm.rl1.organized_policy_interface import HeadSession
from metacom_pm.rl1.organized_rollout import OrganizedRollout
from metacom_pm.rl1.schema import Action, digest
from test_rl1_organized_policy_interface import item, setup, feature_encoder
from test_rl1_calibration_workflow import fixture


def evidence_for(c):
    e=dict(current_date=c.prefix.timestamp,legal_past_sessions=[],current_prefix=[
        dict(id=f'C:T{i:03d}',role=t.role,text=t.content) for i,t in enumerate(c.prefix.turns)])
    return e,dict(prefix_identity=c.prefix.identity,evidence_identity=digest(e),source_identity='MOCK strict-past source')


def route_for(c,r):
    bundle=fixture();q=qualify(**bundle)
    use=stamp(dict(status='QUALIFIED_MEASUREMENT_USE',qualification_identity=q['identity'],
        domain_identity=domain_identity(c,r,'MOCK:G'),review_reference='MOCK compatibility review',
        coverage_evidence_identities=['MOCK synthetic evidence only']))
    return QualifiedRoute(bundle,use)


def episode(c,r,route=None,tid='synthetic-0',no_text=False):
    e,source=evidence_for(c)
    return OrganizedEpisode(c,r,executor_identity='MOCK:G',draw_identity='MOCK:canonical',
        trajectory_id=tid,evidence=e,evidence_source=source,cost=TokenCost(.05,2048),
        route=route,without_text=no_text)


def raw(request, text='MOCK identical answer'):
    visible=visible_generation_request(request)
    return bind_generation_result(request,dict(request_id=visible['request_id'],
        runtime_identity=request['executor_identity'],input_tokens=request['expected_input_tokens'],
        finish_reason='natural_stop',text=text,api_cost_usd=0))


def drain(queue, *, unknown=False):
    while (row:=queue.claim_next()) is not None:
        p=row['payload']
        value=raw(p) if row['kind']=='generation' else dict(binding=p['binding'],
            measurement_status='semantic_uncertainty' if unknown else 'measured_candidate',
            q=None if unknown else 3,m=None if unknown else 0)
        queue.settle(row['id'],value)


def view(tmp_path, *, no_text=False, invoke=None):
    f=feature_encoder(window=256)
    cache=BlockCache(tmp_path/'blocks.sqlite',encoder_identity='fixture',dimension=2,native_window=f.window)
    return EncodedHeadView(f,cache,encoder_identity='fixture',without_text=no_text,batch_size=4,
        invoke=invoke or (lambda bs:[[sum(b)/len(b)/1000.,float(b[-2])/1000.] for b in bs]))


def test_forward_preserves_ids_attention_tail_and_normalizes():
    class Model:
        device='cpu'
        def eval(self): return self
        def __call__(self,x):
            self.last=deepcopy(x)
            n=x['attention_mask'].sum(1)
            ids=x['input_ids']*x['attention_mask']
            return {'sentence_embedding':torch.stack((ids.sum(1).float(),n.float()),dim=1)}
    m=Model();out=forward_blocks(m,[[1,8,3,19],[1,7]],native_window=4,dimension=2,pad_token_id=0)
    assert m.last['input_ids'].tolist()==[[1,8,3,19],[1,7,0,0]]
    assert m.last['attention_mask'].tolist()==[[1,1,1,1],[1,1,0,0]]
    assert torch.allclose(torch.tensor(out).norm(dim=1),torch.ones(2))
    with pytest.raises(ValueError,match='native-window'):
        forward_blocks(m,[[1]*5],native_window=4,dimension=2,pad_token_id=0)


def test_cache_reuses_content_across_restarts_and_keeps_policy_rng(tmp_path):
    cache=BlockCache(tmp_path/'cache.sqlite',encoder_identity='x',dimension=2,native_window=8)
    calls=[]
    def encode(bs):
        calls.append(bs);torch.manual_seed(999);return [[1.,2.] for b in bs]
    state=torch.get_rng_state().clone()
    vectors,stats=cache.encode([[1,2],[3],[1,2]],invoke=encode,encoder_identity='x',batch_size=2)
    assert len(vectors)==3 and stats['physical_forward_batches']==1 and stats['new_blocks']==2
    assert torch.equal(state,torch.get_rng_state())
    restored=BlockCache(cache.path,encoder_identity='x',dimension=2,native_window=8)
    _,stats=restored.encode([[3],[1,2]],invoke=encode,encoder_identity='x')
    assert len(calls)==1 and stats['new_blocks']==0 and stats['cached_unique_blocks']==2
    with pytest.raises(ValueError,match='identity'):
        restored.encode([[3]],invoke=encode,encoder_identity='other')
    with restored.db() as db:db.execute("UPDATE blocks SET vector='[5.0,6.0]'")
    with pytest.raises(ValueError,match='cached vector'):
        restored.encode([[3]],invoke=encode,encoder_identity='x')


def test_unknown_forward_is_not_automatically_repeated(tmp_path):
    cache=BlockCache(tmp_path/'cache.sqlite',encoder_identity='x',dimension=2,native_window=8)
    calls=[]
    def fail(bs):calls.append(bs);raise RuntimeError('synthetic process lost')
    with pytest.raises(RuntimeError):cache.encode([[1]],invoke=fail,encoder_identity='x')
    with pytest.raises(ValueError,match='unknown'):
        cache.encode([[1]],invoke=fail,encoder_identity='x')
    assert len(calls)==1


def test_complete_features_cache_and_persistent_notext(tmp_path):
    c,r=setup([item('long',text='whole text '*200)])
    full=HeadSession(c,r);hidden=HeadSession(c,r,without_text=True)
    v=view(tmp_path);nv=view(tmp_path,no_text=True)
    v.sequential(full.observe());base=v.last_receipt['new_blocks']
    nv.sequential(hidden.observe());assert nv.last_receipt['new_blocks']==0
    full.step(Action.GET_MS);hidden.step(Action.GET_MS)
    values,_=v.sequential(full.observe());assert v.last_receipt['new_blocks']>1
    no,_=nv.sequential(hidden.observe())
    assert no[2:10]==(0.,)*8 and values[6:8]!=(0.,0.) and nv.last_receipt['new_blocks']==0
    with pytest.raises(ValueError,match='NoText'):nv.sequential(full.observe())


def test_same_counts_different_read_order_produce_different_source_bound_requests():
    c,r=setup([item('a','RS','kindness'),item('z','RS','cycling'),item('p','MP','cycling')])
    x,y=episode(c,r),episode(c,r,tid='other')
    for a in (Action.GET_MP,Action.GET_RS,Action.STOP):x.step(a)
    for a in (Action.GET_RS,Action.GET_MP,Action.STOP):y.step(a)
    assert x.session.observe().counts==y.session.observe().counts
    assert x.requests['ON']['request_id']!=y.requests['ON']['request_id']
    assert x.requests['OFF']['request_id']==y.requests['OFF']['request_id']
    assert x.requests['OFF']['provenance']['selected_keys']==[]


def test_unqualified_feedback_never_dispatched_or_filled_zero(tmp_path):
    c,r=setup([item('p','MP')]);e=episode(c,r);q=FeedbackQueue(tmp_path/'q.sqlite')
    e.step(Action.GET_MP);e.step(Action.STOP)
    def forbidden(*a):raise AssertionError('unqualified scoring must not be queued')
    e.advance(q.generate,forbidden);drain(q)
    result=e.advance(q.generate,forbidden)
    assert result['phase']=='pending_qualification' and result['return_value'] is None
    assert result['steps'][-1]['reward'] is None and len(q.counts())==1


def test_content_score_reuse_keeps_unequal_cost_and_complete_evidence(tmp_path):
    c,r=setup([item('p','MP')]);route=route_for(c,r)
    e=episode(c,r,route);q=FeedbackQueue(tmp_path/'q.sqlite')
    e.step(Action.GET_MP);e.step(Action.STOP)
    for _ in range(3):e.advance(q.generate,q.measure);drain(q)
    assert e.phase=='terminal' and e.terminal_reward==0
    assert e.result()['return_value']==-.05*e.session.observe().resource_tokens/2048
    assert [x for x in q.counts() if x['kind']=='measurement'][0]['count']==1
    rows=e.feedback_export();assert len(rows)==2 and rows[0]['actions']==[2,0]
    assert rows[0]['receipt']['content_receipt_identity']==rows[1]['receipt']['content_receipt_identity']


def test_unknown_stays_missing_and_qualification_cannot_cross_new_renderer(tmp_path):
    c,r=setup([item('p','MP')]);route=route_for(c,r);e=episode(c,r,route)
    q=FeedbackQueue(tmp_path/'q.sqlite');e.step(Action.STOP)
    for _ in range(3):e.advance(q.generate,q.measure);drain(q,unknown=True)
    assert e.phase=='pending_score' and e.result()['return_value'] is None
    c2,r2=setup([item('p','MP')],limit=99999)
    with pytest.raises(ValueError,match='covered'):episode(c2,r2,route)


def test_new_episode_waits_for_existing_backend_finite_recovery(tmp_path):
    from metacom_pm.rl1.measurement_backend import QualifiedFeedbackBackend
    from test_rl1_measurement_backend import setup as backend_setup
    q,_,kw=backend_setup(tmp_path,outcomes=('format_failure','valid'),enqueue=False)
    c,r=setup([item('p','MP')]);e=episode(c,r,route_for(c,r))
    e.step(Action.GET_MP);e.step(Action.STOP)
    e.advance(q.generate,q.measure)
    while (row:=q.claim_next(kind='generation')) is not None:
        q.settle(row['id'],raw(row['payload']))
    e.advance(q.generate,q.measure)
    worker=QualifiedFeedbackBackend(q,**kw)
    assert worker.step()['status']=='PENDING_TECHNICAL_RECOVERY'
    assert e.advance(q.generate,q.measure)['phase']=='pending_score'
    assert e.steps[-1]['reward'] is None
    resumed=QualifiedFeedbackBackend(FeedbackQueue(q.path),**kw)
    assert resumed.step()['status']=='LOGICAL_SETTLED'
    assert e.advance(q.generate,q.measure)['phase']=='terminal'
    assert len(kw['transport'].calls)==2 and e.terminal_reward==0


def test_generation_projection_rejects_wrong_provenance_or_input_length():
    c,r=setup([]);e=episode(c,r);e.step(Action.STOP);req=e.requests['ON']
    bad=raw(req);bad['source_provenance_identity']='another source'
    with pytest.raises(ValueError,match='exact acquired'):e.advance(lambda _:bad,lambda *a:None)
    visible=visible_generation_request(req)
    with pytest.raises(ValueError,match='input length'):
        bind_generation_result(req,dict(request_id=visible['request_id'],runtime_identity='MOCK:G',input_tokens=1,api_cost_usd=0))


def test_variable_six_read_batch_recovers_then_uses_existing_PPO_and_resamples(tmp_path):
    c,r=setup([item(str(i),text='x'*500) for i in range(6)]);route=route_for(c,r)
    v=view(tmp_path);torch.manual_seed(17);model=make_actor_critic(v.feature_dimension)
    with torch.no_grad():model.policy.weight.zero_();model.policy.bias.fill_(-15);model.policy.bias[3]=15
    def episodes():return [episode(c,r,route,tid=f'MOCK-{i}') for i in range(16)]
    def run(root):return OrganizedRollout(model,v,root,run_identity='MOCK-run',policy_version=0,seed=17)
    interrupted=run(tmp_path/'interrupted');es=episodes()
    def crash(event,**kw):
        if kw['steps']==5:raise RuntimeError('injected after fifth GET')
    interrupted.fault_hook=crash
    with pytest.raises(RuntimeError):interrupted.collect(es)
    resumed=run(tmp_path/'interrupted');es=episodes();resumed.collect(es)
    uninterrupted=run(tmp_path/'reference');ref=episodes();uninterrupted.collect(ref)
    assert resumed.records==uninterrupted.records and resumed.rng==uninterrupted.rng
    assert all(len(t)==7 for t in resumed.records)
    assert all(e.session.observe().resource_tokens>2048 for e in es)
    q=FeedbackQueue(tmp_path/'q.sqlite')
    with pytest.raises(ValueError,match='all 16'):resumed.ppo_inputs(es)
    for _ in range(3):resumed.poll(es,q);drain(q)
    inputs=resumed.ppo_inputs(es)
    assert all(len(e['transitions'])==7 for e in inputs)
    before=parameter_identity(model);trainer=PPO(model);stats=trainer.update(inputs)
    assert trainer.version==1 and stats['behavior_log_probability_max_error']<1e-5
    assert parameter_identity(model)!=before
    with pytest.raises(ValueError,match='parameters'):resumed.ppo_inputs(es)
    newer=OrganizedRollout(model,v,tmp_path/'next',run_identity='MOCK-run',policy_version=1,seed=29)
    newer.collect(episodes());assert newer.version==1 and newer.behavior!=before
    assert all(x['new_blocks']==0 for x in newer.encoding)


def test_no_text_rollout_does_not_tokenize_acquired_body(tmp_path):
    c,r=setup([item('p','MP','secret-resource-text')]);v=view(tmp_path,no_text=True)
    model=make_actor_critic(v.feature_dimension)
    with torch.no_grad():model.policy.weight.zero_();model.policy.bias.fill_(-15);model.policy.bias[2]=15
    es=[episode(c,r,tid=f'MOCK-{i}',no_text=True) for i in range(16)]
    run=OrganizedRollout(model,v,tmp_path/'r',run_identity='MOCK',policy_version=0,seed=17)
    run.collect(es)
    assert all(t['observation'][2:10]==[0.]*8 for row in run.records for t in row)
    assert all(e.requests['ON']['provenance']['selected_keys']==['p'] for e in es)
