"""Synthetic tests only; no natural corpus, weights, account or API access."""
from copy import deepcopy
import pytest
import torch
from rl1_batch_fixtures import episodes, make_encoder, answer
from metacom_pm.rl1.calibration_workflow import stamp
from metacom_pm.rl1.diagnostic_scope import (
    DIAGNOSTIC, DISPOSITIONS, DiagnosticEpisode, feedback_disposition, require_approval)
from metacom_pm.rl1.natural_batch import PendingBatch, FeedbackQueue, parameter_identity
from metacom_pm.rl1.observation_features import make_actor_critic
from metacom_pm.rl1.schema import digest


def fixture():
    encoder, _ = make_encoder()
    es = episodes('first') + episodes('second')
    e = es[0]
    p = stamp(dict(initialization='random_seed17_diagnostic_only',
        limits={'judge_calls':80, 'cumulative':305}, feedback_dispositions=DISPOSITIONS,
        reward={'alpha':1, 'lambda':.05, 'gamma':1, 'resource_tokens':2048},
        trajectory_manifest={x.trajectory_id:dict(prefix_identity=x.spec.prefix.identity,
            split='train', evidence_identity=digest(x.evidence)) for x in es},
        train_batches=[[x.trajectory_id for x in es[:16]], [x.trajectory_id for x in es[16:]]],
        executor_identity=e.spec.executor_identity, measurement_identity=e.spec.judge_identity,
        renderer_identity=e.renderer.identity, draw_identity=e.spec.draw_identity,
        rubric_identity='MOCK:rubric', encoder_identity=encoder.identity))
    a = dict(status='APPROVED', protocol_identity=p['identity'], scope=DIAGNOSTIC,
        natural_updates_authorized=True, model_requests_authorized=True,
        feedback_dispositions=DISPOSITIONS, old_stops_released=False, reward_qualified=False,
        max_trajectories=32, max_updates=2, retries=0, initialization=p['initialization'],
        limits=p['limits'], user_authorization_reference='SYNTHETIC TEST ONLY')
    reviews={}
    def build():
        return [DiagnosticEpisode(x.spec,x.renderer,evidence=x.evidence,protocol=p,approval=a,
            trajectory_id=x.trajectory_id,review_lookup=reviews.get) for x in es]
    return encoder,p,a,reviews,build


def reviewed(record, ambiguous=False):
    return dict(record_identity=digest(record), independent_human_reference=False,
        status='reviewer_ambiguity' if ambiguous else 'reviewed_no_confirmed_issue',
        confirmed_errors=[], ambiguities=[dict(type='interpretation_boundary',
            claim='MOCK disputed presupposition', reason='two admissible readings',
            original_criterion='MOCK rubric')] if ambiguous else [])


def finish(batch, queue, reviews):
    for _ in range(8):
        rs=batch.poll(queue)
        if all(x['phase']=='terminal' for x in rs):return
        while (item:=queue.claim_next()) is not None:
            rec=answer(item)
            if item['kind']=='measurement':reviews[digest(rec)]=reviewed(rec,True)
            queue.settle(item['id'],rec)
    raise AssertionError('not complete')


def test_categories_never_collapse():
    r={'measurement_status':'measured_candidate','q':3,'m':.25}
    assert feedback_disposition(r,None)=='pending_review'
    assert feedback_disposition(r,reviewed(r,True))=='allow_flagged_proxy'
    rv=reviewed(r,True);rv['confirmed_errors']=[dict(claim='X',source_ids=['C:T000'],
        original_criterion='MOCK attribution rule',reason='contradiction',
        target='measurement_decision',decision_error_type='wrong_subject_or_time')]
    assert feedback_disposition(r,rv)=='stop_before_update'
    rv['confirmed_errors'][0].pop('source_ids')
    with pytest.raises(ValueError):feedback_disposition(r,rv)
    for status,expected in [('semantic_uncertainty','pending_stop_stage'),('technical_failure','stop_stage')]:
        assert feedback_disposition(dict(measurement_status=status,q=None,m=None),None)==expected
        with pytest.raises(ValueError):feedback_disposition(dict(measurement_status=status,q=0,m=0),None)


def test_pending_approval_and_forged_bc_cannot_start():
    enc,p,a,rs,build=fixture()
    with pytest.raises(ValueError):require_approval(p,dict(a,status='PROPOSED'))
    p=deepcopy(p);p.pop('identity');p['initialization']='original_BC';p=stamp(p)
    with pytest.raises(ValueError,match='checkpoint'):
        require_approval(p,dict(a,protocol_identity=p['identity'],initialization='original_BC'))


def test_two_batches_resume_no_duplicate_update_no_qualification(tmp_path):
    torch.set_num_threads(1);torch.manual_seed(17)
    enc,p,a,reviews,build=fixture();es=build()
    model=make_actor_critic(enc.feature_dimension)
    b=PendingBatch(model,enc,tmp_path/'updates',mode=DIAGNOSTIC,protocol=p,approval=a)
    q=FeedbackQueue(tmp_path/'q.sqlite')
    b.collect(es[:16],batch_id='one');finish(b,q,reviews)
    old=tmp_path/'ready.pt';b.save(old);before=parameter_identity(model)
    receipt=b.update_once()
    assert receipt['before']==before and receipt['after']!=before
    assert receipt['qualification_granted'] is False
    other=PendingBatch(make_actor_critic(enc.feature_dimension),enc,tmp_path/'updates',
        mode=DIAGNOSTIC,protocol=p,approval=a)
    other.restore(old,build()[:16])
    with pytest.raises(FileExistsError):other.update_once()
    b.next_batch()
    with pytest.raises(ValueError):b.collect(build()[:16],batch_id='replay')
    # A rejected collect must not set a partially populated batch identity.
    assert b.batch_id is None
    b.collect(es[16:],batch_id='two');finish(b,q,reviews);b.update_once()
    assert b.trainer.version==2
    with pytest.raises(ValueError):b.next_batch()


def test_changed_review_blocks_update(tmp_path):
    torch.manual_seed(17);enc,p,a,reviews,build=fixture()
    b=PendingBatch(make_actor_critic(enc.feature_dimension),enc,tmp_path,mode=DIAGNOSTIC,protocol=p,approval=a)
    q=FeedbackQueue(tmp_path/'q');b.collect(build()[:16],batch_id='one');finish(b,q,reviews)
    reviews.clear()
    with pytest.raises(ValueError,match='review changed'):b.update_once()
    assert b.trainer.version==0
