"""Balanced coordinator/update/recovery tests on explicitly synthetic material."""
import pytest

from metacom_pm.rl1.balanced_objective import BalancedObjective,prepare_supervised
from metacom_pm.rl1.balanced_learning import BalancedRun,episode_endpoint
from metacom_pm.rl1.natural_batch import FeedbackQueue
from metacom_pm.rl1.qualified_learning import make_run_manifest
from metacom_pm.rl1.supervised_learning import fit_supervised
from test_rl1_organized_supervision import materials
from test_rl1_organized_learning import artifacts as original_artifacts,episodes,drain
from test_rl1_balanced_objective import timing,timing_map


@pytest.fixture(scope='module')
def balanced(tmp_path_factory,original_artifacts):
    root=tmp_path_factory.mktemp('balanced_coordinator');old=original_artifacts['BC-init']
    menu,fs,rs,js,_=materials(programs=((0,),(2,0)))
    data=prepare_supervised(menu,factories=fs,responses=rs,receipts=js,view=old['view'],method='BC-init',
        timings=timing_map(menu,rs),objective=BalancedObjective(.05,'SYNTHETIC'))
    manifest=make_run_manifest(data,bindings=old['manifest']['train_bindings'],dev_bindings=old['manifest']['dev_bindings'],
        seed=17,qualification=old['base'].route.qualification,scale_evidence=old['manifest']['scale_evidence'])
    receipt=fit_supervised(data,seed=17,directory=root/'bc')
    return dict(old,data=data,manifest=manifest,directory=root/'bc',receipt=receipt)


def start(a,work):
    return BalancedRun(a['data'],manifest=a['manifest'],qualification_bundle=a['base'].route.bundle,
        view=a['view'],initialization_path=a['directory']/'checkpoint.pt',initialization_receipt=a['receipt'],workdir=work)


def lookup(e,behavior):
    assert behavior
    endpoint=episode_endpoint(e)
    return timing(endpoint,e.responses[e.requests['ON']['request_id']],1.+.2*(len(e.steps)-1),behavior=behavior)


def finish_quality(run,q):
    for _ in range(5):
        reports=run.poll(q)
        if all(r['phase']=='pending_latency' for r in reports):return
        drain(q)
    raise AssertionError('synthetic quality did not finish')


def test_all_16_costs_required_actual_update_and_next_collection(tmp_path,balanced):
    run=start(balanced,tmp_path/'run');q=FeedbackQueue(tmp_path/'q.sqlite')
    run.collect(episodes(balanced));finish_quality(run,q)
    with pytest.raises(ValueError,match='16 latency'):run.update_once()
    skipped=run.records[-1]['episode'].trajectory_id
    partial=run.poll(q,lambda e,b:None if e.trajectory_id==skipped else lookup(e,b))
    assert sum(r['phase']=='pending_latency' for r in partial)==1
    with pytest.raises(ValueError,match='16 latency'):run.update_once()
    complete=run.poll(q,lookup)
    assert all(r['phase']=='terminal' for r in complete)
    inputs=run._update_episodes()
    for r,t in zip(complete,inputs):assert r['return_value']==pytest.approx(t['total_return'])
    receipt=run.update_once()
    assert receipt['after']!=receipt['before'] and receipt['natural_policy_updates']==0
    assert len(receipt['training_feedback'])==32
    assert all(r['training_objective_identity']==run.objective.identity for r in receipt['training_feedback'])
    run.next_batch();run.collect(episodes(balanced,1))
    assert run.behavior==receipt['after']


def test_timing_is_checkpoint_bound_and_update_recovery_is_exact(tmp_path,balanced):
    q=FeedbackQueue(tmp_path/'q.sqlite')
    reference=start(balanced,tmp_path/'reference');reference.collect(episodes(balanced))
    finish_quality(reference,q);reference.poll(q,lookup);expected=reference.update_once()
    work=tmp_path/'interrupted';run=start(balanced,work)
    def stop(event,**kw):
        if event=='step_committed' and kw['steps']==4:raise RuntimeError('synthetic collection interruption')
    run.fault_hook=stop
    with pytest.raises(RuntimeError):run.collect(episodes(balanced))
    run=start(balanced,work);run.resume_collection(episodes(balanced));finish_quality(run,q);run.poll(q,lookup)
    def stop_update(event,**kw):
        if event=='optimized_before_checkpoint':raise RuntimeError('synthetic update interruption')
    run.fault_hook=stop_update;batch=run.batch_id
    with pytest.raises(RuntimeError):run.update_once()
    restored=start(balanced,work)
    actual=restored.recover_update(episodes(balanced),batch_id=batch)
    assert actual['after']==expected['after'] and actual['training_feedback']==expected['training_feedback']
    assert restored.recover_update(episodes(balanced),batch_id=batch)==actual


def test_fixed_endpoint_and_development_use_same_balanced_objective(tmp_path,balanced):
    run=start(balanced,tmp_path/'run');q=FeedbackQueue(tmp_path/'q.sqlite')
    for version in range(8):
        run.collect(episodes(balanced,version));finish_quality(run,q);run.poll(q,lookup);run.update_once()
        if (version+1)*16 in (64,128):
            dev=episodes(balanced,bindings=run.development_bindings())
            for _ in range(4):
                report=run.evaluate_development(dev,q,lookup)
                if report['status']=='DEVELOPMENT_COMPLETED':break
                drain(q)
            assert report['status']=='DEVELOPMENT_COMPLETED'
            assert all(r['objective_identity']==run.objective.identity for r in report['results'])
        if version<7:run.next_batch()
    done=run.finish()
    assert done['episodes']==128 and done['scope']=='ENGINEERING_ONLY'
