"""Portable reference-adapter checks with invented engineering fixtures only.

No private engine, research case, label, provider or model is loaded. The injected
extraction validator is a spy: this suite tests the reference adapter's own
binding/allowlist rules and delegation, not the private extraction parser.
"""
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from metacom_pm.rl1 import judge_completion_candidate as judge
from metacom_pm.rl1 import relation_reference as r, task_reference as t


@pytest.fixture
def inputs():
    item=dict(reply='We can explore this plan.', evidence=dict(current_date='2000-01-02',
        current_prefix=[dict(id='C:T000',role='seeker',text='I plan to talk tomorrow.')],
        legal_past_sessions=[]))
    fact=dict(source_id='C:T000',speaker='seeker',quote='I plan to talk tomorrow.')
    ref=dict(interface_version=r.INTERFACE,
        reply_text_sha256=hashlib.sha256(item['reply'].encode()).hexdigest(),
        evidence_identity=r.digest(item['evidence']),independent_gold=False,
        coverage='MOCK adapter fixture',verification_scope='MOCK, not semantic evidence',
        claims=[dict(claim_id='C001',response_unit_id='R001',response_quote=item['reply'],
            claim_type='tentative',claim='MOCK planning invitation',subject='MOCK user',
            action='talk',action_stage='intention',time='future',relation='supported',
            source_checks=[dict(fact,source_type='current',evidence_scope='current prefix',
                scope_status='analyst_proposed_relation_not_independent_gold')],
            researcher_confirmed_parts=[],analyst_interpretation='MOCK interpretation',
            limitations='Does not assert a completed action')])
    card=dict(interface_version=t.INTERFACE,evidence_identity=r.digest(item['evidence']),
        current_date='2000-01-02',source_facts=[fact],request_elements=['Discuss a plan'],
        role_application='MOCK role constraint',acceptable_options=['Explore the plan'],
        unresolved_importance=['No numerical target'],
        provenance='analyst_prepared_after_development_exposure_not_independent_gold',
        independent_gold=False)
    engine=SimpleNamespace(validate_extract=Mock(),input_guard=Mock(return_value={'mock':True}),
        payload=lambda row,component:judge.messages_and_schema(row['evidence'],row['reply']))
    return item,ref,card,engine


def test_valid_reference_delegates_bound_source_projection(inputs):
    item,ref,_,engine=inputs
    r.validate_reference(item,ref,engine)
    projected,source=engine.validate_extract.call_args.args
    assert source is item
    assert projected['claims'][0]['evidence']==[dict(source_id='C:T000',quote='I plan to talk tomorrow.')]
    assert projected['claims'][0]['action_stage']=='intention'
    assert projected['status']=='checked'


@pytest.mark.parametrize('field,value',[
    ('evidence_identity','wrong'),('reply_text_sha256','wrong'),('independent_gold',True)])
def test_relation_binding_rejected_before_downstream_validator(inputs,field,value):
    item,ref,_,engine=inputs;ref[field]=value
    with pytest.raises(ValueError):r.validate_reference(item,ref,engine)
    engine.validate_extract.assert_not_called()


@pytest.mark.parametrize('field,value',[
    ('quote','I already talked.'),('speaker','supporter'),('source_id','H999:T000'),
    ('scope_status','verified_gold')])
def test_relation_cannot_substitute_source_speaker_or_gold(inputs,field,value):
    item,ref,_,engine=inputs;ref['claims'][0]['source_checks'][0][field]=value
    with pytest.raises(ValueError):r.validate_reference(item,ref,engine)


@pytest.mark.parametrize('field',['q','m','expected_winner','human_preference'])
def test_reference_cannot_carry_score_or_preference(inputs,field):
    item,ref,card,engine=inputs
    ref['claims'][0][field]=4;card[field]=4
    with pytest.raises(ValueError):r.validate_reference(item,ref,engine)
    with pytest.raises(ValueError):t.validate_card(item,card)


@pytest.mark.parametrize('field,value',[
    ('quote','I already talked.'),('speaker','supporter'),('source_id','H999:T000')])
def test_task_card_requires_exact_current_source(inputs,field,value):
    item,_,card,_=inputs;t.validate_card(item,card)
    card['source_facts'][0][field]=value
    with pytest.raises(ValueError):t.validate_card(item,card)


def test_task_card_is_context_bound_and_cannot_self_certify(inputs):
    item,_,card,_=inputs
    for field,value in [('evidence_identity','wrong'),('current_date','2001-01-01'),
                        ('independent_gold',True),('provenance','independent_human')]:
        changed=deepcopy(card);changed[field]=value
        with pytest.raises(ValueError):t.validate_card(item,changed)


def test_intervention_preserves_full_user_and_schema_and_rejects_extra_message(inputs):
    item,ref,card,engine=inputs
    a=t.make_payload(item,ref,card,'A','MOCK fixed rubric',engine)
    b=t.make_payload(item,ref,card,'B','MOCK fixed rubric',engine)
    assert a['messages'][1]==b['messages'][1]
    assert a['schema']==b['schema']
    assert json.loads(b['messages'][1]['content'])['legal_evidence']==item['evidence']
    assert b['messages'][0]['content'].startswith(a['messages'][0]['content']+t.MARKER)
    t.validate_payload(item,ref,card,'B','MOCK fixed rubric',b,engine)
    b['messages'].append(dict(role='user',content='MOCK forbidden score target'))
    with pytest.raises(ValueError):t.validate_payload(item,ref,card,'B','MOCK fixed rubric',b,engine)


@pytest.mark.parametrize('adapter',[r,t])
def test_repeated_schedule_keeps_inputs_distinct_attempts_and_reversed_arms(inputs,adapter):
    item,*_=inputs;items={'first':item,'second':deepcopy(item)}
    rows=adapter.schedule(items,['first','second'],['first'])
    assert len(rows)==6
    assert len({row['slot_id'] for row in rows})==6
    first=[row for row in rows if row['material_id']=='first']
    assert [row['arm'] for row in first[:2]]==[row['arm'] for row in first[2:]][::-1]
    assert len({row['reply_identity'] for row in first})==1
