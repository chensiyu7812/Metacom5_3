"""GE2 shared syntax, observation binding and bounded semantic query language.

No source lookup or evaluator is accepted here. Syntax masks never encode the
correct action, source or answer. Self-reported evidence states are diagnostics.
"""
from __future__ import annotations

from copy import deepcopy
import json
import re

from ..io import canonical_json
from .pomdp_controller_protocol import (
    ControllerConstraintProcessor, ControllerProtocolError, EOS_TOKEN_IDS,
    XGRAMMAR_VERSION, _pairs, _nonfinite,
)

PROTOCOL = 'pmrl1-j-ge2-controller-v1'
ROLES = ('LLMOneShot', 'LLMToolAgent')
HANDLE_PATTERN = r'^ge2:[0-9a-f]{24}:v[1-9][0-9]*$'
CONTROL_TOTAL_TOKENS = 768
MAX_TOOL_CALLS = 5
STATES = ('sufficient', 'insufficient', 'inapplicable', 'unconfirmable', 'unassessed')
COMMON_SYSTEM = """You manage memory acquisition for a companion answering the visible user conversation.
Choose acquisition only when it can help the current user goal; no memory and STOP are valid.
All source records are historical reports, not necessarily current facts. Keep speakers,
negation, reported dates, plans versus actions and unresolved events distinct. Queries may
be semantic paraphrases of the visible conversation and already read evidence. A guessed
query term is not evidence about the user. Never treat a supporter's question or suggestion
as a user's report. Do not invent source handles. Use only the supplied tool interface.
SEARCH returns up to four distinct sessions as adjacent original-turn windows; unread_only
excludes already fully read windows, not sources from the common pool. EXPAND reads the
neighbor window or entire parent of an observed handle. Repeated reads still cost an action.
There are at most five acquisition actions, a common source capacity, a real time budget,
and 768 total controller output tokens. Reserve time for the final answer. Read only as much
as needed. When the record cannot resolve a relevant fact, STOP and leave it unknown.
The evidence_state is your uncalibrated assessment for this visible goal, never a success
label. Use unassessed when unsure, and a short information_gap without inventing facts.
Return only the JSON object specified by the grammar. The final response is generated
separately with the same original conversation and evidence actually supplied."""
SYSTEMS = {
    'LLMOneShot': COMMON_SYSTEM + """
Commit the whole program now, without seeing later results. Return evidence_state and
actions (1..6 objects). EXPAND uses from_search (zero-based prior SEARCH index), hit_rank
(zero-based 0..3), and scope (neighbor or parent). SEARCH uses query and unread_only.
STOP has only action. No action may follow STOP. You may use up to five acquisitions.
Do not assume a future hit exists. An absent rank ends this precommitted path.""",
    'LLMToolAgent': COMMON_SYSTEM + """
Return evidence_state and one action for the actual current observation. SEARCH has query
and unread_only. EXPAND has an observed handle and scope (neighbor or parent).
STOP has only action. You may receive up to five controller calls including STOP, within
the same 768 total output tokens. Decide again only from actual returned observations.""",
}


def _object(properties):
    return dict(type='object', properties=properties, required=list(properties), additionalProperties=False)


def controller_schema(role):
    if role not in ROLES:
        raise ControllerProtocolError('GE2 controller role')
    stop = _object({'action': {'const': 'STOP'}})
    search = _object({'action': {'const': 'SEARCH'}, 'query': {'type': 'string', 'minLength': 1},
                      'unread_only': {'type': 'boolean'}})
    expand = {'action': {'const': 'EXPAND'}, 'scope': {'enum': ['neighbor', 'parent']}}
    if role == 'LLMOneShot':
        expand.update(from_search={'type': 'integer', 'minimum': 0, 'maximum': 4},
                      hit_rank={'type': 'integer', 'minimum': 0, 'maximum': 3})
    else:
        expand['handle'] = {'type': 'string', 'pattern': HANDLE_PATTERN}
    action = {'anyOf': [stop, search, _object(expand)]}
    assessment = _object({'status': {'enum': list(STATES)}, 'information_gap': {'type': 'string'}})
    return _object({'evidence_state': assessment,
                    ('actions' if role == 'LLMOneShot' else 'action'):
                        {'type': 'array', 'minItems': 1, 'maxItems': 6, 'items': action}
                        if role == 'LLMOneShot' else action})


def protocol_contract():
    return dict(protocol=PROTOCOL, schemas={r: controller_schema(r) for r in ROLES}, systems=SYSTEMS,
        xgrammar_version=XGRAMMAR_VERSION, eos_token_ids=list(EOS_TOKEN_IDS),
        common_total_controller_tokens=CONTROL_TOTAL_TOKENS, max_tool_controller_calls=MAX_TOOL_CALLS,
        max_oneshot_calls=1, max_acquisitions=5, max_plan_items=6,
        common_controller_decode={'no_repeat_ngram_size': 0, 'max_new_tokens': 'min(768, remaining output allowance)'},
        terminal_decode_modified=False, max_query_words=256, max_query_chars=4096,
        constraint_scope='syntax only; no task, gold, candidate or correct-action mask',
        parser_policy='strict bare JSON; duplicate keys/nonfinite/bool integers/extras rejected',
        query_policy='bounded plain text; semantic paraphrases allowed; provenance enforced by runtime inputs and source registry',
        evidence_assessment='unqualified controller self-report; never task success or reward',
        no_repair=True, no_retry=True, no_nonfinite_fallback=True)


def controller_decode(base_decode, role, remaining=CONTROL_TOTAL_TOKENS):
    if role not in ROLES or type(remaining) is not int or not 0 < remaining <= CONTROL_TOTAL_TOKENS:
        raise ControllerProtocolError('controller allowance')
    result = deepcopy(base_decode)
    result.update(max_new_tokens=remaining, no_repeat_ngram_size=0)
    return result


def messages(observation, role):
    if role not in ROLES or type(observation) is not dict:
        raise ControllerProtocolError('observation/role')
    return [{'role': 'system', 'content': SYSTEMS[role]},
            {'role': 'user', 'content': canonical_json(observation)}]


def query_shape(query):
    if (type(query) is not str or not query.strip() or len(query) > 4096
            or len(query.split()) > 256 or '\x00' in query):
        raise ControllerProtocolError('query type/length')


def _action(action, role):
    if type(action) is not dict:
        raise ControllerProtocolError('action object')
    kind = action.get('action')
    keys = {'STOP': {'action'}, 'SEARCH': {'action', 'query', 'unread_only'},
            'EXPAND': {'action', 'scope', 'from_search', 'hit_rank'} if role == 'LLMOneShot'
                      else {'action', 'scope', 'handle'}}
    if kind not in keys or set(action) != keys[kind]:
        raise ControllerProtocolError('action fields')
    if kind == 'SEARCH':
        query_shape(action['query'])
        if type(action['unread_only']) is not bool:
            raise ControllerProtocolError('unread_only bool')
    if kind == 'EXPAND':
        if action['scope'] not in ('neighbor', 'parent'):
            raise ControllerProtocolError('expansion scope')
        if role == 'LLMOneShot':
            if (type(action['from_search']) is not int or not 0 <= action['from_search'] <= 4
                    or type(action['hit_rank']) is not int or not 0 <= action['hit_rank'] <= 3):
                raise ControllerProtocolError('planned rank')
        elif type(action['handle']) is not str or not re.fullmatch(HANDLE_PATTERN, action['handle']):
            raise ControllerProtocolError('handle shape')
    return action


def parse(text, role):
    if role not in ROLES or type(text) is not str or len(text) > 65536:
        raise ControllerProtocolError('controller text/role')
    try:
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_nonfinite)
    except (ValueError, TypeError, RecursionError) as e:
        raise ControllerProtocolError('strict controller JSON') from e
    key = 'actions' if role == 'LLMOneShot' else 'action'
    if type(value) is not dict or set(value) != {'evidence_state', key}:
        raise ControllerProtocolError('outer controller fields')
    state = value['evidence_state']
    if (type(state) is not dict or set(state) != {'status', 'information_gap'}
            or state['status'] not in STATES or type(state['information_gap']) is not str
            or len(state['information_gap']) > 2048):
        raise ControllerProtocolError('evidence self-report')
    if role == 'LLMOneShot':
        actions = value[key]
        if type(actions) is not list or not 1 <= len(actions) <= 6:
            raise ControllerProtocolError('plan length')
        searches = accesses = 0
        stopped = False
        for action in actions:
            _action(action, role)
            if stopped:
                raise ControllerProtocolError('action after STOP')
            if action['action'] == 'STOP':
                stopped = True
            else:
                if action['action'] == 'EXPAND' and action['from_search'] >= searches:
                    raise ControllerProtocolError('forward search reference')
                searches += action['action'] == 'SEARCH'
                accesses += 1
        if accesses > 5:
            raise ControllerProtocolError('five acquisition cap')
    else:
        _action(value[key], role)
    return value


def validate_tool(text, observation):
    value = parse(text, 'LLMToolAgent')
    action = value['action']
    if action['action'] not in observation['action_mask']:
        raise ControllerProtocolError('action unavailable')
    if action['action'] == 'EXPAND' and action['handle'] not in {h['handle'] for h in observation['hits']}:
        raise ControllerProtocolError('unobserved handle')
    return value


def compile_grammar(role, tokenizer, *, vocab_size, eos_token_ids):
    import importlib.metadata
    import xgrammar as xg
    if importlib.metadata.version('xgrammar') != XGRAMMAR_VERSION or eos_token_ids != EOS_TOKEN_IDS:
        raise ControllerProtocolError('grammar dependency/EOS identity')
    info = xg.TokenizerInfo.from_huggingface(tokenizer, vocab_size=vocab_size, stop_token_ids=eos_token_ids)
    return xg.GrammarCompiler(info, max_threads=1).compile_json_schema(controller_schema(role), any_whitespace=True)
