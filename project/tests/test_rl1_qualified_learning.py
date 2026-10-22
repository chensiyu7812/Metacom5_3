"""Full coordinator wiring on synthetic sources and mock provider records."""
from collections import Counter
from dataclasses import replace
from pathlib import Path
import json

import pytest
import torch

from metacom_pm.rl1.calibration_workflow import qualify
from metacom_pm.rl1.natural_runner import NaturalEpisode
from metacom_pm.rl1.natural_batch import FeedbackQueue,parameter_identity
from metacom_pm.rl1.qualified_learning import make_run_manifest,QualifiedRun
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.supervised_learning import fit_supervised
from test_rl1_supervised_learning import prepared


@pytest.fixture(scope='module')
def setup_artifacts(tmp_path_factory):
    root=tmp_path_factory.mktemp('qualified_learning_engineering')
    output={}
    for method in ('BC-init','PPO-NoText'):
        data,view,kw=prepared(method);bundle=kw['qualification_bundle'];q=qualify(**bundle)
        spec,r=next(iter(kw['episodes'].values()))
        specs={};bindings=[];dev=[];evidence='MOCK legal full source'
        for owner in range(12):
            for i in range(8):
                p=replace(spec.prefix,owner_id=spec.prefix.owner_id if owner==0 else f'MOCK_OWNER_{owner}',
                    session_id=spec.prefix.session_id if owner==0 and i==0 else f'MOCK_SESSION_{i}')
                inventory=tuple(tuple(replace(x,owner_id=p.owner_id if x.owner_id else None) for x in h) for h in spec.inventory)
                s=replace(spec,prefix=p,inventory=inventory)
                specs[p.identity]=(s,r)
                bindings.append(dict(prefix_identity=p.identity,owner=p.owner_id,spec_identity=s.identity,
                    renderer_identity=r.identity,evidence_identity=digest(evidence)))
        for owner in range(3):
            for i in range(6):
                p=replace(spec.prefix,owner_id=f'MOCK_DEV_OWNER_{owner}',session_id=f'MOCK_DEV_SESSION_{i}',split='dev')
                inventory=tuple(tuple(replace(x,owner_id=p.owner_id if x.owner_id else None) for x in h) for h in spec.inventory)
                s=replace(spec,prefix=p,inventory=inventory);specs[p.identity]=(s,r)
                dev.append(dict(prefix_identity=p.identity,owner=p.owner_id,spec_identity=s.identity,
                    renderer_identity=r.identity,evidence_identity=digest(evidence)))
        m=make_run_manifest(data,bindings=bindings,dev_bindings=dev,seed=17,qualification=q,
            scale_evidence=dict(hours_128=40,hours_384=120,source_identity='MOCK_NOT_REAL_THROUGHPUT'))
        directory=root/method;receipt=fit_supervised(data,seed=17,directory=directory)
        output[method]=dict(data=data,view=view,bundle=bundle,q=q,specs=specs,evidence=evidence,
            manifest=m,directory=directory,receipt=receipt)
    return output


def start(a,work):
    return QualifiedRun(a['data'],manifest=a['manifest'],qualification_bundle=a['bundle'],view=a['view'],
        initialization_path=a['directory']/'checkpoint.pt',initialization_receipt=a['receipt'],workdir=work)


def episodes(a,version=0):
    out=[]
    for b in a['manifest']['trajectories'][16*version:16*(version+1)]:
        spec,r=a['specs'][b['prefix_identity']]
        out.append(NaturalEpisode(spec,r,evidence=a['evidence'],freeze=a['bundle']['freeze'],
            freeze_inputs=a['bundle']['inputs'],qualification=a['q'],trajectory_id=b['trajectory_id']))
    return out


def answer(item,unknown=False):
    p=item['payload']
    if item['kind']=='generation':
        return dict(request_id=p['request_id'],runtime_identity=p['executor_identity'],
            text=json.dumps(p['provenance']['canonical_counts']),finish_reason='natural_stop')
    return dict(binding=p['binding'],measurement_status='semantic_uncertainty' if unknown else 'measured_candidate',
        q=None if unknown else (3 if sum(json.loads(p['reply'])) else 2),m=None if unknown else 0)


def drain(queue,unknown=False):
    while (item:=queue.claim_next()) is not None:queue.settle(item['id'],answer(item,unknown))


def complete(run,queue):
    for _ in range(6):
        result=run.poll(queue)
        if all(r['phase']=='terminal' for r in result):return result
        drain(queue)
    raise AssertionError('mock feedback did not complete')


def test_original_schedule_balanced_full_pass_and_scale_rule(setup_artifacts):
    a=setup_artifacts['BC-init'];m=a['manifest']
    assert len(m['trajectories'])==128 and len({x['trajectory_id'] for x in m['trajectories']})==128
    assert len({x['prefix_identity'] for x in m['trajectories'][:96]})==96
    assert set(Counter(x['owner'] for x in m['trajectories'][:96]).values())=={8}
    assert set(Counter(x['owner'] for x in m['trajectories'][96:]).values())=={2,3}
    m384=make_run_manifest(a['data'],bindings=m['train_bindings'],dev_bindings=m['dev_bindings'],seed=17,qualification=a['q'],
        scale_evidence=dict(hours_128=25,hours_384=80,source_identity='MOCK'))
    assert len(m384['trajectories'])==384 and m384['max_updates']==24
    assert all(len({r['prefix_identity'] for r in m384['trajectories'][i:i+96]})==96 for i in range(0,384,96))


@pytest.mark.parametrize('method',['BC-init','PPO-NoText'])
def test_actual_BC_to_full_batch_update_and_new_on_policy_batch(tmp_path,setup_artifacts,method):
    a=setup_artifacts[method];run=start(a,tmp_path/'run');queue=FeedbackQueue(tmp_path/'queue.sqlite')
    run.collect(episodes(a));assert queue.counts()==[]
    before=parameter_identity(run.model);run.poll(queue)
    with pytest.raises(ValueError,match='all 16'):run.update_once()
    assert parameter_identity(run.model)==before
    if method=='PPO-NoText':
        assert all(not torch.count_nonzero(t['observation'][4:20]) for r in run.records for t in r['transitions'])
    complete(run,queue);receipt=run.update_once()
    assert receipt['before']!=receipt['after'] and receipt['natural_policy_updates']==0
    assert receipt['behavior_log_probability_max_error']<=1e-5
    old=[r['episode'].trajectory_id for r in run.records]
    run.next_batch();run.collect(episodes(a,1))
    assert not set(old)&{r['episode'].trajectory_id for r in run.records}
    assert run.behavior==receipt['after']


def test_pending_restore_preserves_draws_unsettled_claim_and_blocks_double_update(tmp_path,setup_artifacts):
    a=setup_artifacts['BC-init'];work=tmp_path/'run';run=start(a,work);q=FeedbackQueue(tmp_path/'q.sqlite')
    run.collect(episodes(a));run.poll(q);item=q.claim_next();drain(q)
    saved=next(work.glob('*.feedback_0000.pt'));old=[r['transitions'] for r in run.records]
    restored=start(a,work);restored.restore(saved,episodes(a))
    for x,y in zip(old,[r['transitions'] for r in restored.records]):
        assert all(torch.equal(s['old_log_prob'],t['old_log_prob']) for s,t in zip(x,y))
    assert q.claim_next() is None and any(x['state']=='STARTED' for x in q.counts())
    with pytest.raises(ValueError,match='all 16'):restored.update_once()
    q.settle(item['id'],answer(item));complete(restored,q)
    ready=sorted(work.glob('*.feedback_*.pt'))[-1]
    receipt=restored.update_once()
    oldrun=start(a,work);oldrun.restore(ready,episodes(a))
    with pytest.raises(FileExistsError):oldrun.update_once()
    after=next(work.glob('*.after.pt'));finished=start(a,work);finished.restore(after,episodes(a))
    assert finished.consumed and parameter_identity(finished.model)==receipt['after']


def test_unknown_rewards_never_dropped_or_zeroed(tmp_path,setup_artifacts):
    a=setup_artifacts['BC-init'];run=start(a,tmp_path/'run');q=FeedbackQueue(tmp_path/'q.sqlite')
    run.collect(episodes(a));run.poll(q);drain(q);run.poll(q);drain(q,True);run.poll(q)
    assert len(run.records)==16
    with pytest.raises(ValueError,match='all 16'):run.update_once()
    assert run.trainer.version==0


def test_wrong_order_sources_and_behavior_drift_are_rejected(tmp_path,setup_artifacts):
    a=setup_artifacts['BC-init'];run=start(a,tmp_path/'run')
    with pytest.raises(ValueError):run.collect(list(reversed(episodes(a))))
    es=episodes(a);es[0].evidence='different source'
    with pytest.raises(ValueError):run.collect(es)
    run.collect(episodes(a))
    with torch.no_grad():next(run.model.parameters()).add_(.1)
    with pytest.raises(ValueError,match='behavior'):run.poll(FeedbackQueue(tmp_path/'q.sqlite'))


def test_fixed_endpoint_cannot_skip_development_or_stop_early(tmp_path,setup_artifacts):
    a=setup_artifacts['BC-init'];run=start(a,tmp_path/'run');q=FeedbackQueue(tmp_path/'q.sqlite')
    with pytest.raises(ValueError):run.finish()
    for version in range(8):
        run.collect(episodes(a,version));complete(run,q);run.update_once()
        count=16*(version+1)
        if count in (64,128):
            if count==64:
                with pytest.raises(ValueError,match='development'):run.next_batch()
            else:
                with pytest.raises(ValueError,match='development'):run.finish()
            dev=[]
            for b in run.development_bindings():
                spec,r=a['specs'][b['prefix_identity']]
                dev.append(NaturalEpisode(spec,r,evidence=a['evidence'],freeze=a['bundle']['freeze'],
                    freeze_inputs=a['bundle']['inputs'],qualification=a['q'],trajectory_id=b['trajectory_id']))
            before=parameter_identity(run.model);rng=run.rng_state.clone()
            for _ in range(6):
                result=run.evaluate_development(dev,q)
                if result['status']=='DEVELOPMENT_COMPLETED':break
                drain(q)
            assert result['status']=='DEVELOPMENT_COMPLETED'
            assert parameter_identity(run.model)==before and torch.equal(rng,run.rng_state)
            assert len(result['results'])==18
        if count<128:run.next_batch()
    done=run.finish()
    assert done['episodes']==128 and done['updates']==8 and done['scope']=='ENGINEERING_ONLY'
    assert not done['independent_test_evaluation_completed']
    with pytest.raises(ValueError):run.next_batch()


def test_interrupted_collection_at_five_resumes_same_actions_and_rng(tmp_path,setup_artifacts):
    a=setup_artifacts['BC-init'];reference=start(a,tmp_path/'reference');reference.collect(episodes(a))
    work=tmp_path/'interrupted';run=start(a,work)
    def crash(event,**detail):
        if event=='collected_episode' and detail['count']==5:raise KeyboardInterrupt()
    run.fault_hook=crash
    with pytest.raises(KeyboardInterrupt):run.collect(episodes(a))
    with pytest.raises(ValueError,match='complete pending'):run.poll(FeedbackQueue(tmp_path/'q.sqlite'))
    restored=start(a,work);restored.resume_collection(episodes(a))
    assert torch.equal(restored.rng_state,reference.rng_state)
    for row,expected in zip(restored.records,reference.records):
        assert row['episode'].snapshot()==expected['episode'].snapshot()
        for t,u in zip(row['transitions'],expected['transitions']):
            assert torch.equal(t['action'],u['action']) and torch.equal(t['old_log_prob'],u['old_log_prob'])


@pytest.mark.parametrize('boundary',['update_intent','optimized_before_checkpoint','checkpoint_before_receipt'])
def test_update_crash_recovery_is_one_logical_update(tmp_path,setup_artifacts,boundary):
    a=setup_artifacts['BC-init'];reference=start(a,tmp_path/'reference');queue=FeedbackQueue(tmp_path/'q.sqlite')
    reference.collect(episodes(a));complete(reference,queue);expected=reference.update_once()
    work=tmp_path/'interrupted';run=start(a,work);run.collect(episodes(a));complete(run,queue)
    def crash(event,**detail):
        if event==boundary:raise KeyboardInterrupt()
    run.fault_hook=crash;batch=run.batch_id
    with pytest.raises(KeyboardInterrupt):run.update_once()
    before_counts=queue.counts();restored=start(a,work)
    receipt=restored.recover_update(episodes(a),batch_id=batch)
    assert receipt['after']==expected['after'] and restored.trainer.version==1
    assert torch.equal(restored.rng_state,reference.rng_state)
    assert queue.counts()==before_counts and queue.claim_next() is None
    again=start(a,work)
    assert again.recover_update(episodes(a),batch_id=batch)==receipt
    assert len(list(work.glob('*.update_done.json')))==1
    with pytest.raises(ValueError):restored.update_once()


def test_unified_backend_BC_queue_recovery_full_batch_update_and_resampling(tmp_path,setup_artifacts):
    from test_rl1_measurement_backend import setup as backend_setup
    from metacom_pm.rl1.measurement_backend import QualifiedFeedbackBackend
    from metacom_pm.rl1.research_backend import ResearchBackend
    a=setup_artifacts['BC-init']
    q,_,kw=backend_setup(tmp_path,('format_failure',)+('valid',)*255,max_attempts=256,enqueue=False)
    kw['budget'].stage_cap=kw['budget'].trial_cap=kw['budget'].shared_cap=1000000
    w=QualifiedFeedbackBackend(q,**kw)
    backend=ResearchBackend(q,qualification_bundle=a['bundle'],measurement_worker=w)
    run=start(a,tmp_path/'learning');run.collect(episodes(a));old=run.behavior
    saw_recovery=False
    for _ in range(128):
        cycle=backend.learning_cycle(run)
        result=cycle['results']
        if cycle['status']=='FEEDBACK_COMPLETE':break
        while (item:=q.claim_next(kind='generation')) is not None:q.settle(item['id'],answer(item))
        progress=cycle['service']['measurement']
        if progress['status']=='PENDING_TECHNICAL_RECOVERY':
            saw_recovery=True
            assert any(r['phase']=='pending_score' for r in result)
            with pytest.raises(ValueError,match='all 16'):run.update_once()
        else:assert progress['status'] in ('LOGICAL_SETTLED','IDLE')
    assert all(r['phase']=='terminal' for r in result) and saw_recovery
    receipt=backend.learning_cycle(run,allow_update=True)['update']
    assert receipt['after']!=old and receipt['natural_policy_updates']==0
    assert len(receipt['training_feedback'])==32
    run.next_batch();run.collect(episodes(a,1))
    assert run.behavior==receipt['after'] and len(run.records)==16
