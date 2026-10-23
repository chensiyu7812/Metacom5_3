"""Synthetic engineering checks; no research labels, weights or training."""
from dataclasses import replace

import pytest

from metacom_pm.rl1.bound_generation import BoundResourceEnv
from metacom_pm.rl1.calibration_workflow import qualify, stamp
from metacom_pm.rl1.learning_handoff import (candidate_menu, prepare_handoff,
    compile_supervision, checkpoint_requirements, verify_checkpoint_receipt)
from metacom_pm.rl1.learning_preparation import TerminalCandidate, PolicyInputView
from metacom_pm.rl1.schema import PLANS, digest
from metacom_pm.rl1.measurement_identity import binding
from test_rl1_calibration_workflow import fixture
from test_rl1_environment import fixture_spec, renderer
from rl1_batch_fixtures import make_encoder


def inputs(scope='initial_train'):
    bundle=fixture(); freeze=bundle['freeze']
    spec=replace(fixture_spec(budget=2048),judge_identity=freeze['runtime_identity'])
    spec=replace(spec,prefix=replace(spec.prefix,split='train'))
    spec=replace(spec,inventory=tuple(tuple(replace(resource,
        coarse_age='not_applicable' if resource.head=='RS' else 'previous_session')
        for resource in head) for head in spec.inventory))
    r=renderer(); cs=[]; receipts={}
    evidence=digest('MOCK legal full source')
    for counts in ((0,0,0,0),(1,0,0,0)):
        env=BoundResourceEnv(spec,r)
        if counts[0]:env.step(1,expected_state_hash=env.state_hash)
        env.step(0,expected_state_hash=env.state_hash)
        rid=env.generation_request()['request_id']
        c=TerminalCandidate(spec.prefix.identity,'train',counts,r.cost(spec,counts),rid,
            digest('MOCK reply '+str(counts)),evidence,spec.executor_identity,r.identity)
        cs.append(c)
        receipts[rid]=dict(binding=binding(rid,c.response_identity,evidence,freeze,qualify(**bundle)),
            measurement_status='measured_candidate',q=4 if counts[0] else 2,m=0)
    menu=candidate_menu(cs,source_identity='MOCK frozen pool',scope=scope)
    kw=dict(menu=menu,receipts=receipts,qualification_bundle=bundle,
        episodes={spec.prefix.identity:(spec,r)})
    factories={spec.prefix.identity:lambda:BoundResourceEnv(spec,r)}
    return cs,kw,factories


def test_missing_qualification_needs_no_model_or_fake_feedback():
    cs,kw,_=inputs()
    report=prepare_handoff(cs,menu=kw['menu'],receipts={})
    assert report['status']=='PENDING_QUALIFICATION' and report['targets']==[]


def test_real_qualification_adapter_to_BC_rows_and_separate_NoText():
    cs,kw,factories=inputs(); report=prepare_handoff(cs,**kw)
    assert report['status']=='READY'
    encoder,_=make_encoder()
    rows,meta=compile_supervision(report,method='BC-init',view=PolicyInputView(encoder),env_factories=factories)
    masked,no_meta=compile_supervision(report,method='PPO-NoText',view=PolicyInputView(encoder,no_text=True),env_factories=factories)
    assert [r['target'] for r in rows]==[1,0]
    assert set(rows[0])=={'features','mask','target'}
    assert any(rows[1]['features'][4:20]) and not any(masked[1]['features'][4:20])
    assert meta['feature_identity']!=no_meta['feature_identity']
    assert meta['qualification_identity']==qualify(**kw['qualification_bundle'])['identity']


def test_full_menu_cannot_be_silently_reduced_and_missing_score_blocks_dataset():
    cs,kw,factories=inputs()
    with pytest.raises(ValueError,match='menu changed'):prepare_handoff(cs[:1],**kw)
    kw['receipts'].pop(cs[1].request_identity)
    report=prepare_handoff(cs,**kw)
    assert report['status']=='PENDING_SCHEDULED_FEEDBACK' and report['targets']==[]
    encoder,_=make_encoder()
    with pytest.raises(ValueError,match='scheduled'):
        compile_supervision(report,method='BC-init',view=PolicyInputView(encoder),env_factories=factories)


@pytest.mark.parametrize('which',['renderer','request','cost','source','qualification','unknown'])
def test_cross_stack_source_or_unqualified_values_never_become_targets(which):
    cs,kw,_=inputs()
    if which in ('renderer','request','cost'):
        change={'renderer':dict(renderer_identity='WRONG'),'request':dict(request_identity='WRONG'),
            'cost':dict(resource_tokens=99)}[which]
        cs[1]=replace(cs[1],**change)
        kw['menu']=candidate_menu(cs,source_identity='MOCK frozen pool',scope='initial_train')
    elif which=='source':kw['receipts'][cs[1].request_identity]['binding']['evidence_identity']='WRONG'
    elif which=='qualification':kw['qualification_bundle']['freeze']['status']='invented PASS'
    else:kw['receipts'][cs[1].request_identity].update(measurement_status='semantic_uncertainty',q=4)
    with pytest.raises(ValueError):prepare_handoff(cs,**kw)


def test_OneShot_requires_union_uses_seventy_plan_mask_and_original_target():
    cs,kw,factories=inputs(); initial=prepare_handoff(cs,**kw);encoder,_=make_encoder()
    with pytest.raises(ValueError,match='scope'):
        compile_supervision(initial,method='OneShot',view=PolicyInputView(encoder),env_factories=factories)
    cs,kw,factories=inputs('final_train_union');union=prepare_handoff(cs,**kw)
    rows,_=compile_supervision(union,method='OneShot',view=PolicyInputView(encoder),env_factories=factories)
    assert len(rows)==1 and len(rows[0]['mask'])==70
    assert rows[0]['target']==PLANS.index((1,0,0,0)) and rows[0]['mask'][rows[0]['target']]
    with pytest.raises(ValueError,match='NoText'):
        compile_supervision(union,method='BC-union',view=PolicyInputView(encoder,no_text=True),env_factories=factories)


def test_checkpoints_bind_method_seed_full_targets_and_completed_optimizer():
    cs,kw,factories=inputs(); report=prepare_handoff(cs,**kw);encoder,_=make_encoder()
    _,meta=compile_supervision(report,method='BC-init',view=PolicyInputView(encoder),env_factories=factories)
    req=checkpoint_requirements(meta,seed=17); sha='a'*64
    # Explicit mock receipt for verifier testing, no checkpoint/optimizer run.
    receipt=stamp(dict(status='BC_OPTIMIZATION_COMPLETED',requirements=req,
        checkpoint_sha256=sha,optimizer_steps=1,synthetic_engineering_fixture=True))
    assert verify_checkpoint_receipt(receipt,requirements=req,checkpoint_sha256=sha)
    for changes in (dict(optimizer_steps=0),dict(checkpoint_sha256='b'*64),
            dict(requirements=checkpoint_requirements(meta,seed=29))):
        bad=stamp({k:v for k,v in (receipt|changes).items() if k!='identity'})
        with pytest.raises(ValueError):verify_checkpoint_receipt(bad,requirements=req,checkpoint_sha256=sha)
