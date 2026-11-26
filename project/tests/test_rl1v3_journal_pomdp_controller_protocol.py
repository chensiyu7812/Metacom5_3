"""CPU protocol boundaries; examples are synthetic, never research task gold."""
import json
import subprocess
import sys

import pytest

from metacom_pm.rl1v3.journal import pomdp_controller_protocol as P


@pytest.mark.parametrize('text,role', [
    ('{"action":"STOP","action":"SEARCH","query":"hobby"}', 'LLMToolAgent'),
    ('{"action":"STOP","unused":NaN}', 'LLMToolAgent'),
    ('{"action":"STOP","unused":Infinity}', 'LLMToolAgent'),
    ('{"action":"STOP","unused":-Infinity}', 'LLMToolAgent'),
    ('{"action":"STOP","query":"hobby"}', 'LLMToolAgent'),
    ('{"action":"SEARCH","query":true}', 'LLMToolAgent'),
    ('{"action":"EXPAND","handle":0}', 'LLMToolAgent'),
    ('{"action":"EXPAND","handle":"hit:xyz"}', 'LLMToolAgent'),
    ('{"action":"EXPAND","handle":"hit:' + 'a'*24 + '\\n"}', 'LLMToolAgent'),
    ('[{"action":"EXPAND","from_search":true,"hit_rank":0}]', 'LLMOneShot'),
    ('[{"action":"EXPAND","from_search":0,"hit_rank":false}]', 'LLMOneShot'),
    ('[{"action":"EXPAND","from_search":0.0,"hit_rank":0}]', 'LLMOneShot'),
    ('[{"action":"EXPAND","from_search":0,"hit_rank":2}]', 'LLMOneShot'),
    ('[{"action":"EXPAND","from_search":-1,"hit_rank":0}]', 'LLMOneShot'),
    ('[]', 'LLMOneShot'), ('null', 'LLMToolAgent'), ('true', 'LLMToolAgent'),
    ('```json\n{"action":"STOP"}\n```', 'LLMToolAgent'),
    ('thought\n{"action":"STOP"}', 'LLMToolAgent'),
    ('{"action":"STOP"} {"action":"STOP"}', 'LLMToolAgent'),
])
def test_strict_rejects_without_repair(text, role):
    with pytest.raises(P.ControllerProtocolError):
        P.parse_controller(text, role)


def test_syntax_does_not_inject_state_or_correct_action():
    raw = '{"action":"SEARCH","query":"unobservedword"}'
    assert P.parse_controller(raw, 'LLMToolAgent')['query'] == 'unobservedword'
    with pytest.raises(P.ControllerProtocolError, match='unobserved'):
        P.validate_tool(raw, obs())
    assert P.parse_controller('{"action":"STOP"}', 'LLMToolAgent') == {'action':'STOP'}
    with pytest.raises(P.ControllerProtocolError, match='unavailable'):
        P.validate_tool('{"action":"STOP"}', dict(obs(), action_mask=[]))


def obs():
    return {'query': 'Please recall my hobby', 'action_mask':['STOP','SEARCH','EXPAND'],
            'hits': [], 'readings': []}


def test_query_token_enters_only_after_observation():
    q = '{"action":"SEARCH","query":"Zephyr"}'
    before = obs()
    with pytest.raises(P.ControllerProtocolError):
        P.validate_tool(q, before)
    after = dict(before, readings=[{'ordinal':1,'reading_text':'The hobby was Zephyr knitting.'}])
    assert P.validate_tool(q, after)['query'] == 'Zephyr'
    with pytest.raises(P.ControllerProtocolError):
        P.validate_oneshot('['+q+']', before['query'])


def test_handle_foreign_and_budget_mask_rejected():
    h = 'hit:'+'a'*24
    text = json.dumps({'action':'EXPAND','handle':h})
    with pytest.raises(P.ControllerProtocolError, match='foreign'):
        P.validate_tool(text, obs())
    seen = dict(obs(), hits=[{'handle':h,'reading_text':'A visible report'}])
    assert P.validate_tool(text, seen)['handle'] == h
    with pytest.raises(P.ControllerProtocolError, match='unavailable'):
        P.validate_tool(text, dict(seen, action_mask=['STOP']))


@pytest.mark.parametrize('plan', [
    [{'action':'EXPAND','from_search':0,'hit_rank':0}],
    [{'action':'STOP'},{'action':'SEARCH','query':'hobby'}],
    [{'action':'SEARCH','query':'hobby'}]*5,
    [{'action':'SEARCH','query':'notobserved'}],
    [{'action':'SEARCH','query':' ' * 5}],
    [{'action':'SEARCH','query':'hobby '*257}],
])
def test_program_state_limits(plan):
    with pytest.raises(P.ControllerProtocolError):
        P.validate_oneshot(json.dumps(plan), 'hobby')


def test_plan_allows_exact_four_acquisitions_optional_stop_and_prior_rank():
    plan = [{'action':'SEARCH','query':'hobby'},
            {'action':'EXPAND','from_search':0,'hit_rank':1},
            {'action':'SEARCH','query':'recall'},
            {'action':'EXPAND','from_search':1,'hit_rank':0}, {'action':'STOP'}]
    assert P.validate_oneshot(json.dumps(plan), 'recall hobby') == plan
    assert P.validate_oneshot(json.dumps(plan[:-1]), 'recall hobby') == plan[:-1]


def test_decode_is_separate_copy_and_common_overrides_only():
    base={'max_new_tokens':320,'no_repeat_ngram_size':3,'do_sample':False,
          'eos_token_id':[1,106,50]}
    one=P.controller_decode(base,'LLMOneShot'); tool=P.controller_decode(base,'LLMToolAgent')
    assert one['max_new_tokens']==768 and tool['max_new_tokens']==192
    assert one['no_repeat_ngram_size']==tool['no_repeat_ngram_size']==P.CONTROLLER_NO_REPEAT_NGRAM
    one['eos_token_id'].append(999)
    assert base=={'max_new_tokens':320,'no_repeat_ngram_size':3,'do_sample':False,'eos_token_id':[1,106,50]}


def test_contracts_import_no_model_libraries():
    code = ('import sys,json; from metacom_pm.rl1v3.journal.pomdp_controller_protocol import protocol_contract; '
            'from metacom_pm.rl1v3.journal.pomdp_latency import latency_contract; '
            'json.dumps([protocol_contract(),latency_contract()]); '
            'assert not any(x in sys.modules for x in ["torch","transformers","xgrammar"])')
    subprocess.run([sys.executable,'-c',code],check=True)
