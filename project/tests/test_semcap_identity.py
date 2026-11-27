"""Regression tests for the candidate identity contract (CPU, no model)."""
import pytest
from metacom_pm.rl1v3.semcap import identity as I

TURNS = [dict(role='seeker', text='My mom limits who I can be friends with.'),
         dict(role='supporter', text='My mom did that too when I was young.'),
         dict(role='seeker', text='Really? How did you deal with that?')]


def test_imported_supporter_never_native_assistant():
    msgs = I.render_current_dialogue(TURNS, I.IMPORTED_HUMAN)
    assert all(m['role'] == 'user' for m in msgs)
    assert 'previous human supporter (not you)' in msgs[0]['content']
    assert msgs[-1]['content'] == TURNS[-1]['text']
    assert 'My mom did that too' in msgs[0]['content']  # content kept, attribution explicit


def test_same_agent_history_keeps_native_roles():
    msgs = I.render_current_dialogue(TURNS, I.SAME_AGENT)
    assert [m['role'] for m in msgs] == ['user', 'assistant', 'user']


def test_unknown_source_is_attributed_not_native():
    msgs = I.render_current_dialogue(TURNS, I.UNKNOWN_SOURCE)
    assert all(m['role'] == 'user' for m in msgs)
    assert 'identity not established' in msgs[0]['content'] and 'not by you' not in msgs[0]['content']


def test_system_contract_by_situation():
    base = 'You are a supportive conversational assistant.'
    a = I.system_prompt(base, I.IMPORTED_HUMAN)
    assert 'not the human supporter' in a and 'briefly clarify' in a and 'unnecessarily' in a
    assert 'your interaction history' in I.system_prompt(base, I.SAME_AGENT)
    assert 'neither this user' in I.system_prompt(base, I.EXTERNAL_CASE)
    assert 'not established' in I.system_prompt(base, I.UNKNOWN_SOURCE)
    with pytest.raises(ValueError):
        I.system_prompt(base, 'unknown')


def test_external_case_is_not_current_dialogue_and_last_turn_user():
    with pytest.raises(ValueError):
        I.render_current_dialogue(TURNS, I.EXTERNAL_CASE)
    with pytest.raises(ValueError):
        I.render_current_dialogue(TURNS[:2], I.IMPORTED_HUMAN)


def test_history_attribution_labels():
    assert I.attribute_history('supporter', I.IMPORTED_HUMAN) == 'previous human supporter (not you)'
    assert I.attribute_history('supporter', I.SAME_AGENT).startswith('you')
    assert I.attribute_history('seeker', I.IMPORTED_HUMAN) == 'current user'
    # C: the external help-seeker is NOT the current user, the external supporter is NOT the AI
    ext_seeker = I.attribute_history('seeker', I.EXTERNAL_CASE)
    ext_supporter = I.attribute_history('supporter', I.EXTERNAL_CASE)
    assert 'not the current user' in ext_seeker and ext_seeker != 'current user'
    assert 'not you' in ext_supporter
    assert not I.is_current_user('seeker', I.EXTERNAL_CASE) and I.is_current_user('seeker', I.IMPORTED_HUMAN)
    with pytest.raises(ValueError):
        I.attribute_history('seeker', 'bogus')


def test_source_classification_from_provenance_only():
    assert I.classify_source('ESConv').situation == I.IMPORTED_HUMAN
    evo = I.classify_source('es_memeval_evoemo_public_v1')
    assert evo.situation == I.UNKNOWN_SOURCE and evo.basis == 'not_established'
    assumed = I.classify_source('es_memeval_evoemo_public_v1', assume_same_agent=True)
    assert assumed.situation == I.SAME_AGENT and assumed.basis == 'experimental_assumption'
    assert I.classify_source('any', agent_log_match=True).basis == 'host_provenance'
    assert I.classify_source('ESConv', external=True).situation == I.EXTERNAL_CASE
