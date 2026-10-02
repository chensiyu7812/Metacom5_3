"""Source/time/role and budget regressions; synthetic fixtures, no model files."""
from dataclasses import replace
import json
import pytest

from metacom_pm.rl1.schema import Resource, PrefixSpec, PublicTurn, EpisodeSpec, digest
from metacom_pm.rl1.representation import AttributedRenderer, attributed_resource
from metacom_pm.rl1.render import Renderer
from metacom_pm.rl1.env import ResourceEnv
from metacom_pm.rl1.representation_direct import DirectReplyRenderer


def fixture():
    quote='I am thinking of calling my manager tomorrow.'
    session=dict(session_id='source',chronological_rank=1,timestamp='2024-01-01',
                 turns=[dict(idx=3,role='seeker',content=quote)])
    unit=dict(memory_id='unit',owner_id='PRIVATE_OWNER',source_session_id='source',
        source_session_rank=1,timestamp='2024-01-01',normalized_event='Talked to manager',
        supporting_spans=[dict(turn_index=3,start_char=0,end_char=len(quote),exact_text=quote)])
    resource=Resource('private_candidate','ME','OLD',.8,3,'PRIVATE_OWNER',1,'2024-01-01',
                      'previous_session',('unit','source'))
    return resource,unit,session


def renderer(cls=AttributedRenderer):
    return cls(count_text=len,count_chat=lambda m:len(json.dumps(m)),
               tokenizer_identity='fixture',context_limit=100000)


def test_intention_correction_preserves_source_and_does_not_leak_review_metadata():
    r,u,s=fixture()
    review=dict(unit_id='unit',unit_identity=digest(u),summary='Considering a call tomorrow.',
        action_stage='intention',observed_outcome=None,context_evidence=[],
        rationale='PRIVATE_REVIEW_REASON',reward=4)
    out=attributed_resource(r,unit=u,session=s,me_review=review,count_text=len)
    record=json.loads(out.content)
    assert record['action_stage']=='intention' and record['observed_outcome'] is None
    assert record['event_time'] is None and record['last_confirmed_at'] is None
    assert record['evidence'][0]['quote']==s['turns'][0]['content']
    assert 'PRIVATE' not in out.content and 'reward' not in record and 'rationale' not in record
    assert out.raw_tokens==len(out.content)


@pytest.mark.parametrize('field,value', [('source_session_rank',2),('owner_id','other'),
    ('timestamp','2025-01-01'),('memory_id','wrong')])
def test_wrong_source_binding_fails(field,value):
    r,u,s=fixture();u=dict(u,**{field:value})
    with pytest.raises(ValueError):attributed_resource(r,unit=u,session=s,count_text=len)


def test_changed_source_span_and_stale_semantic_review_fail():
    r,u,s=fixture();bad=dict(u,supporting_spans=[dict(u['supporting_spans'][0],exact_text='wrong')])
    with pytest.raises(ValueError):attributed_resource(r,unit=bad,session=s,count_text=len)
    with pytest.raises(ValueError):attributed_resource(r,unit=u,session=s,
        me_review=dict(unit_id='unit',unit_identity='stale'),count_text=len)


def test_profile_report_does_not_assert_currentness_or_reconfirmation():
    r,u,s=fixture();r=replace(r,head='MP');u=dict(u,profile_slot_key='employment',normalized_value='unemployed')
    out=attributed_resource(r,unit=u,session=s,count_text=len);record=json.loads(out.content)
    assert record['past_report']=='unemployed' and record['current_status']=='unknown'
    assert record['reported_at']=='2024-01-01' and record['last_confirmed_at'] is None
    assert 'Current profile' not in out.content


def test_full_ms_is_preserved_and_rs_substitution_is_explicit():
    r,_,_=fixture();raw='supporter: My mother had this problem.\nseeker: Thanks.'
    ms=attributed_resource(replace(r,head='MS',content=raw),count_text=len)
    assert json.loads(ms.content)['full_source_conversation']==raw
    rs=attributed_resource(replace(r,head='RS',content='Strategy family [Self Disclosure]: share personal experience'),count_text=len)
    record=json.loads(rs.content)
    assert 'hypothetical' in record['ai_action'] and record['historical_move'].endswith('share personal experience')


def test_historical_supporter_is_quoted_not_current_ai_assistant_role():
    r,_,_=fixture()
    p=PrefixSpec('PRIVATE_OWNER','now',2,2,'2024-02-01','train',
        (PublicTurn('seeker','Help'),PublicTurn('supporter','My mother is ill.'),PublicTurn('seeker','What now?')))
    spec=EpisodeSpec(p,((),(),(),(r,)),'retrieval','executor','judge','draw',10000)
    v2=renderer();messages=v2.messages(spec,(0,0,0,0))
    assert [m['role'] for m in messages]==['system','user']
    transcript=json.loads(messages[-1]['content'])
    assert transcript['quoted_history'][1]==dict(speaker='supporter',text='My mother is ill.')
    assert transcript['current_seeker_turn']=='What now?'
    assert v2.identity!=renderer(Renderer).identity


def test_attribution_counts_toward_budget_and_only_get_reveals_it():
    r,u,s=fixture();new=attributed_resource(r,unit=u,session=s,count_text=len)
    p=PrefixSpec('PRIVATE_OWNER','now',2,0,'2024-02-01','train',(PublicTurn('seeker','Help'),))
    spec=EpisodeSpec(p,((),(),(),(new,)),'retrieval','executor','judge','draw',10000)
    v2=renderer();env=ResourceEnv(spec,v2)
    assert 'thinking of calling' not in json.dumps(env.observe().__dict__,default=str)
    result=env.step(4,expected_state_hash=env.state_hash)
    assert 'thinking of calling' in result.observation.acquired[0].content
    assert result.reward==pytest.approx(-.05*v2.cost(spec,(0,0,0,1))/10000)
    too_small=replace(spec,resource_budget=v2.cost(spec,(0,0,0,1))-1)
    assert not ResourceEnv(too_small,v2).observe().action_mask[4]


def test_direct_interface_keeps_actual_current_user_separate_from_quoted_history():
    p=PrefixSpec('PRIVATE_OWNER','now',2,2,'2024-02-01','train',
        (PublicTurn('seeker','Help'),PublicTurn('supporter','My mother is ill.'),PublicTurn('seeker','How did you cope?')))
    spec=EpisodeSpec(p,((),(),(),()),'retrieval','executor','judge','draw',10000)
    direct=renderer(DirectReplyRenderer);quoted=renderer()
    messages=direct.messages(spec,(0,0,0,0))
    assert messages[-1]==dict(role='user',content='How did you cope?')
    assert 'My mother is ill.' in messages[0]['content'] and 'not your own past messages' in messages[0]['content']
    assert not any(m['role']=='assistant' for m in messages)
    assert direct.identity!=quoted.identity
    assert direct.cost(spec,(0,0,0,0))==quoted.cost(spec,(0,0,0,0))==0
