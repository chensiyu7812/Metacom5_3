from dataclasses import replace
import pytest
import torch
from metacom_pm.rl1.schema import Observation,PublicTurn,AcquiredText
from metacom_pm.rl1.observation_features import ObservedFeatureEncoder,make_actor_critic
from metacom_pm.rl1.observation_features import PlanAwareFeatureEncoder
from metacom_pm.rl1.schema import PLANS


def setup():
    calls=[]
    def encode(texts):
        calls.extend(texts)
        return [[float(len(t)),float(sum(map(ord,t))%97)] for t in texts]
    encoder=ObservedFeatureEncoder(encode,embedding_dimension=2,text_encoder_identity='test')
    o=Observation((PublicTurn('seeker','Help'),),(),(0,0,0,0),2048,4,(4,4,4,4),
        ((None,)*4,)*4,(True,True,True,True,True),(True,)*70)
    return encoder,o,calls


def test_only_public_type_is_accepted_and_unacquired_text_is_not_encoded():
    e,o,calls=setup();a=e.encode(o)
    assert calls==['seeker: Help'] and len(a.values)==e.feature_dimension
    with pytest.raises(TypeError):e.encode({'observation':o,'inventory':'hidden'})
    b=e.encode(o);assert a==b and len(calls)==1


def test_text_becomes_visible_only_after_get_and_cache_does_not_leak_back():
    e,o,calls=setup();before=e.encode(o)
    after=replace(o,acquired=(AcquiredText('MP',1,'visible fact','2024-01-01'),),counts=(0,1,0,0),remaining_gets=3)
    assert e.encode(after).values!=before.values and len(calls)==2
    assert 'visible fact' in calls[-1] and e.encode(o)==before


def test_equal_acquired_sets_have_equal_features_independent_of_path_order():
    e,o,calls=setup();items=(AcquiredText('MP',1,'profile',None),AcquiredText('RS',1,'move',None))
    o=replace(o,acquired=items,counts=(1,1,0,0),remaining_gets=2)
    assert e.encode(o)==e.encode(replace(o,acquired=tuple(reversed(items))))


def test_extra_or_skipped_acquired_rank_is_rejected():
    e,o,_=setup()
    with pytest.raises(ValueError):e.encode(replace(o,acquired=(AcquiredText('MP',2,'hidden',None),)))
    with pytest.raises(ValueError):e.encode(replace(o,acquired=(AcquiredText('MP',2,'hidden',None),),counts=(0,1,0,0),remaining_gets=3))


def test_actor_mask_and_parameter_shape():
    e,o,_=setup();r=e.encode(replace(o,action_mask=(True,False,True,False,False)))
    model=make_actor_critic(e.feature_dimension)
    distribution,value=model(torch.tensor(r.values),torch.tensor(r.action_mask))
    assert distribution.probs[1]==0 and distribution.probs[3]==0 and distribution.probs[4]==0
    assert value.shape==torch.Size([])


def test_bad_embedding_and_terminal_observations_fail_closed():
    e,o,_=setup()
    with pytest.raises(ValueError):e.encode(replace(o,action_mask=(False,)*5))
    broken=ObservedFeatureEncoder(lambda ts:[[float('nan'),0] for t in ts],embedding_dimension=2,text_encoder_identity='bad')
    with pytest.raises(ValueError):broken.encode(o)


def test_v2_exposes_shared_plan_feasibility_without_encoding_unacquired_text():
    old,o,calls=setup()
    v2=PlanAwareFeatureEncoder(old.encode_texts,embedding_dimension=2,text_encoder_identity='test')
    first=v2.encode(o)
    mask=list(o.initial_plan_mask);mask[PLANS.index((1,1,1,1))]=False
    other=v2.encode(replace(o,initial_plan_mask=tuple(mask)))
    assert first.values[:-70]==other.values[:-70] and first.values[-70:]!=other.values[-70:]
    assert len(first.values)==old.feature_dimension+70 and calls==['seeker: Help']
    assert v2.identity!=old.identity


@pytest.mark.parametrize('mask',[(True,)*69,(1,)*70,(False,)+(True,)*69])
def test_v2_rejects_malformed_initial_plan_mask(mask):
    old,o,_=setup();v2=PlanAwareFeatureEncoder(old.encode_texts,embedding_dimension=2,text_encoder_identity='test')
    with pytest.raises(ValueError):v2.encode(replace(o,initial_plan_mask=mask))
