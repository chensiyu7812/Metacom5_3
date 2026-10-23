"""Interface checks on explicit engineering fixtures, without research training."""
from dataclasses import asdict, replace
import json
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch

from metacom_pm.rl1.env import ResourceEnv
from metacom_pm.rl1.learning_preparation import (TerminalCandidate, legal_path,
    compile_demonstration, select_bc_target, PolicyInputView, make_oneshot_policy,
    initialization_manifest)
from metacom_pm.rl1.learning_preparation import adapt_qualified_episode_feedback
from metacom_pm.rl1.schema import PLANS, digest
from test_rl1_environment import fixture_spec, renderer
from rl1_batch_fixtures import episodes, make_encoder


def labels():
    candidates = [TerminalCandidate('MOCK_PREFIX', 'train', p, t, 'MOCK:'+str(i),
        'MOCK_REPLY:'+str(i), 'MOCK_EVIDENCE', 'MOCK_EXECUTOR', 'MOCK_RENDERER')
        for i,(p,t) in enumerate([((0,0,0,0),0),((1,0,0,0),100),((0,1,0,0),100)])]
    q = dict(status='CALIBRATED_FOR_BOUNDED_STUDY', measurement_identity='MOCK_MEASUREMENT',
             provenance='UNIT_TEST_ONLY_NOT_A_REAL_QUALIFICATION')
    q['identity'] = digest(q)
    ms = {c.request_identity:dict(status='measured', uncertain=False,
        request_identity=c.request_identity, response_identity=c.response_identity,
        evidence_identity=c.evidence_identity, qualification_identity=q['identity'],
        measurement_identity=q['measurement_identity'], q=3 if i==0 else 4, misuse=0)
        for i,c in enumerate(candidates)}
    return candidates, ms, q


def test_missing_qualification_and_missing_scheduled_feedback_are_not_targets():
    cs,ms,q=labels()
    assert select_bc_target(cs,ms,qualification=None)['target'] is None
    del ms[cs[1].request_identity]
    result=select_bc_target(cs,ms,qualification=q)
    assert result['status']=='PENDING_SCHEDULED_FEEDBACK' and result['target'] is None


def test_natural_feedback_adapter_cannot_bypass_existing_measurement_freeze():
    cs,_,_=labels()
    with pytest.raises((ValueError,KeyError)):
        adapt_qualified_episode_feedback(cs[0],{},spec=fixture_spec(),freeze={},freeze_inputs={},qualification={})


def test_reward_and_frozen_tie_break_use_only_measured_plans():
    cs,ms,q=labels(); result=select_bc_target(cs,ms,qualification=q)
    assert result['target']==(0,1,0,0)
    assert result['reward']==pytest.approx(.25-.05*100/2048)
    assert result['measured_plans']==3 and not result['unmeasured_plans_are_negative']
    for m in ms.values():m['q']=3
    assert select_bc_target(cs,ms,qualification=q)['target']==(0,0,0,0)


@pytest.mark.parametrize('field,value',[('response_identity','wrong'),('evidence_identity','wrong'),
    ('measurement_identity','wrong'),('qualification_identity','wrong'),('q',True),('misuse',.5)])
def test_cross_identity_or_invalid_labels_cannot_create_BC_targets(field,value):
    cs,ms,q=labels();ms[cs[1].request_identity][field]=value
    with pytest.raises(ValueError):select_bc_target(cs,ms,qualification=q)


def test_test_labels_and_duplicate_plans_are_rejected():
    cs,ms,q=labels()
    with pytest.raises(ValueError):select_bc_target([replace(c,split='test') for c in cs],ms,qualification=q)
    with pytest.raises(ValueError):select_bc_target(cs+[cs[0]],ms,qualification=q)
    with pytest.raises(ValueError):select_bc_target(cs[1:],ms,qualification=q)


def test_identical_reply_cannot_receive_a_different_reward():
    cs,ms,q=labels();cs[1]=replace(cs[1],response_identity=cs[0].response_identity)
    ms[cs[1].request_identity]['response_identity']=cs[0].response_identity
    with pytest.raises(ValueError,match='identical'):select_bc_target(cs,ms,qualification=q)


def test_compiler_exposes_only_acquired_observations_and_legal_actions():
    spec=fixture_spec();factory=lambda:ResourceEnv(spec,renderer())
    ts=compile_demonstration(factory,(1,1,0,1))
    assert [a for _,a in ts]==[1,2,4,0]
    for o,a in ts:
        assert o.action_mask[a] and len(o.acquired)==sum(o.counts)
        public=json.dumps(asdict(o))
        assert 'PRIVATE_OWNER' not in public and 'PRIVATE_SOURCE' not in public
        assert 'HIDDEN_MS' not in public
    assert legal_path(factory,(0,0,0,0))==(0,)


def test_compiler_finds_alternate_path_under_nonmonotone_budget():
    class Nonmonotone(type(renderer())):
        def cost(self,s,c):
            if c==(1,0,0,0):return 3000
            return 100*sum(c)
    base=renderer();r=Nonmonotone(count_text=len,count_chat=lambda m:len(json.dumps(m)),
        tokenizer_identity='MOCK_NONMONOTONE',context_limit=100000)
    spec=replace(fixture_spec(),resource_budget=2048)
    factory=lambda:ResourceEnv(spec,r)
    assert legal_path(factory,(1,1,0,0))==(2,1,0)
    with pytest.raises(ValueError):legal_path(factory,(1,0,0,0))


def test_oneshot_shares_initial_inputs_and_forbids_post_get_inputs():
    e=episodes(n=1)[0];encoder,_=make_encoder();view=PolicyInputView(encoder)
    o=e.env.observe();x,mask=view.oneshot(o)
    assert x==view.sequential(o)[0] and len(mask)==70
    e.env.step(1,expected_state_hash=e.env.state_hash)
    with pytest.raises(ValueError):view.oneshot(e.env.observe())


def test_NoText_invariance_to_acquired_content_and_distinct_initialization():
    e=episodes(n=1)[0];encoder,_=make_encoder()
    e.env.step(1,expected_state_hash=e.env.state_hash);o=e.env.observe()
    changed=replace(o,acquired=(replace(o.acquired[0],content='DIFFERENT OBSERVED TEXT'),))
    yes=PolicyInputView(encoder);no=PolicyInputView(encoder,no_text=True)
    assert yes.sequential(o)[0]!=yes.sequential(changed)[0]
    assert no.sequential(o)==no.sequential(changed)
    assert all(x==0 for x in no.sequential(o)[0][encoder.dimension:5*encoder.dimension])
    m=initialization_manifest(method='PPO-NoText',seed=17,feature_identity=no.identity)
    assert m['acquired_text_zero_from_initialization'] and not m['checkpoint_exists']


def test_oneshot_architecture_masks_unreachable_plans_without_updates():
    e=episodes(n=1)[0];encoder,_=make_encoder();x,mask=PolicyInputView(encoder).oneshot(e.env.observe())
    model=make_oneshot_policy(len(x));mask=list(mask);mask[PLANS.index((1,1,0,0))]=False
    with torch.no_grad():d=model(torch.tensor(x),torch.tensor(mask))
    assert len(d.probs)==70 and d.probs[PLANS.index((1,1,0,0))]==0


def test_prepared_primary_delivers_complete_schema_and_original_rubric_sources():
    path=Path(__file__).resolve().parents[1]/'scripts/rl1/125_prepare_completion_stage.py'
    spec=importlib.util.spec_from_file_location('completion_preparation_test',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    schema={'oneOf':[{'type':'object','required':['q']},{'type':'object','required':['unknown']}]}
    item={'reply':'MOCK reply','evidence':{'MOCK':'full source'}}
    engine=SimpleNamespace(payload=lambda item,mode:([
        {'role':'system','content':'old'},
        {'role':'user','content':json.dumps({'reply':item['reply'],'legal_evidence':item['evidence']})}],schema))
    messages,returned=module.primary_payload(item,engine,'MOCK exact q/m anchors')
    assert returned==schema
    assert messages[0]['content'].startswith('MOCK exact q/m anchors\n')
    assert messages[0]['content'].endswith(json.dumps(schema,ensure_ascii=False))
    assert json.loads(messages[1]['content'])['legal_evidence']==item['evidence']
