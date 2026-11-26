"""Common syntax constraints, separate from state/action legality and gold.

This new controller identity does not modify terminal G or frozen SC36 code.
Imports of torch/xgrammar occur only when a caller explicitly constructs masks.
"""
from __future__ import annotations

from copy import deepcopy
import json
import re
from time import monotonic_ns

PROTOCOL = 'pmrl1-j-dynamic-controller-protocol-v1'
ROLES = ('LLMOneShot', 'LLMToolAgent')
EOS_TOKEN_IDS = [1, 106, 50]
XGRAMMAR_VERSION = '0.1.21'
# Native CPU replay found 15/18 specified legal JSON paths blocked by ngram=3.
# This common new controller decode is distinct from unchanged terminal G.
CONTROLLER_NO_REPEAT_NGRAM = 0
CAPS = {'LLMOneShot': 768, 'LLMToolAgent': 192}
HANDLE_PATTERN = r'^hit:[0-9a-f]{24}$'


class ControllerProtocolError(ValueError):
    """Invalid controller output: no repair, retry or substitute action."""


def query_tokens(text):
    # Same existing lexical function as pomdp_memory; contracts stay import-light.
    from .temporal_retrieval import words
    return words(text)


def _object(properties):
    return {'type': 'object', 'properties': properties,
            'required': list(properties), 'additionalProperties': False}


def controller_schema(role):
    if role not in ROLES:
        raise ControllerProtocolError('unknown controller role')
    stop = _object({'action': {'const': 'STOP'}})
    search = _object({'action': {'const': 'SEARCH'},
                      'query': {'type': 'string', 'minLength': 1}})
    if role == 'LLMOneShot':
        expand = _object({'action': {'const': 'EXPAND'},
                          'from_search': {'type': 'integer', 'minimum': 0, 'maximum': 3},
                          'hit_rank': {'type': 'integer', 'enum': [0, 1]}})
        return {'type': 'array', 'minItems': 1, 'maxItems': 5,
                'items': {'anyOf': [stop, search, expand]}}
    expand = _object({'action': {'const': 'EXPAND'},
                      'handle': {'type': 'string', 'pattern': HANDLE_PATTERN}})
    return {'anyOf': [stop, search, expand]}


def protocol_contract():
    return dict(protocol=PROTOCOL, schemas={r: controller_schema(r) for r in ROLES},
        xgrammar_version=XGRAMMAR_VERSION, eos_token_ids=list(EOS_TOKEN_IDS),
        output_caps=dict(CAPS), controller_decode_overrides={
            'no_repeat_ngram_size': CONTROLLER_NO_REPEAT_NGRAM},
        terminal_decode_modified=False, max_acquisitions=4, max_plan_items=5,
        max_query_words=256, constraint_scope='static syntax only; STOP always in schema',
        state_legality='separate parser + state validators; never grammar gold/answer masking',
        validators={'parser': 'parse_controller', 'oneshot': 'validate_oneshot',
                    'tool': 'validate_tool'},
        parser_policy='bare JSON; reject duplicate keys, nonfinite numbers, bool integers, extras',
        no_repair=True, no_retry=True, no_nonfinite_fallback=True,
        decode_composition='HF original processors then grammar; empty finite intersection raises',
        source_semantics='existing pomdp_memory.query_tokens and observation-only provenance')


def controller_decode(base_decode, role):
    if role not in ROLES or not isinstance(base_decode, dict):
        raise ControllerProtocolError('controller decode identity')
    result = deepcopy(base_decode)
    result['max_new_tokens'] = CAPS[role]
    result['no_repeat_ngram_size'] = CONTROLLER_NO_REPEAT_NGRAM
    return result


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ControllerProtocolError('duplicate JSON key')
        result[key] = value
    return result


def _nonfinite(value):
    raise ControllerProtocolError('nonfinite JSON number')


def _form(action, role):
    if type(action) is not dict or type(action.get('action')) is not str:
        raise ControllerProtocolError('action must be object with a string action')
    kind = action['action']
    expected = {'STOP': {'action'}, 'SEARCH': {'action', 'query'},
                'EXPAND': ({'action', 'from_search', 'hit_rank'} if role == 'LLMOneShot'
                           else {'action', 'handle'})}
    if kind not in expected or set(action) != expected[kind]:
        raise ControllerProtocolError('action field whitelist')
    if kind == 'SEARCH' and (type(action['query']) is not str or not action['query']):
        raise ControllerProtocolError('query must be a nonempty string')
    if kind == 'EXPAND':
        if role == 'LLMOneShot':
            if (type(action['from_search']) is not int or not 0 <= action['from_search'] <= 3
                    or type(action['hit_rank']) is not int or action['hit_rank'] not in (0, 1)):
                raise ControllerProtocolError('integer planned handle shape')
        elif type(action['handle']) is not str or not re.fullmatch(HANDLE_PATTERN, action['handle']):
            raise ControllerProtocolError('handle shape')
    return action


def parse_controller(text, role):
    """Syntax/type only. No query words, observed handles or current masks injected."""
    if role not in ROLES or type(text) is not str or len(text) > 65536:
        raise ControllerProtocolError('controller role/text size')
    try:
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_nonfinite)
    except (ValueError, TypeError, RecursionError) as exc:
        raise ControllerProtocolError('invalid strict JSON: ' + str(exc)) from exc
    if role == 'LLMOneShot':
        if type(value) is not list or not 1 <= len(value) <= 5:
            raise ControllerProtocolError('plan must contain 1..5 items')
        return [_form(action, role) for action in value]
    return _form(value, role)


def _query(query, allowed):
    words = query_tokens(query)
    if not words or len(query.split()) > 256 or not words <= allowed:
        raise ControllerProtocolError('query shape or unobserved query token')


def validate_oneshot(text, initial_query):
    if type(initial_query) is not str:
        raise ControllerProtocolError('initial query type')
    plan = parse_controller(text, 'LLMOneShot')
    searches = accesses = 0
    stopped = False
    for action in plan:
        if stopped:
            raise ControllerProtocolError('action after STOP')
        kind = action['action']
        if kind == 'STOP':
            stopped = True
        elif kind == 'SEARCH':
            _query(action['query'], query_tokens(initial_query))
            searches += 1
            accesses += 1
        else:
            if action['from_search'] >= searches:
                raise ControllerProtocolError('EXPAND must reference an earlier planned SEARCH')
            accesses += 1
    if accesses > 4:
        raise ControllerProtocolError('acquisition cap')
    return plan


def validate_tool(text, observation):
    action = parse_controller(text, 'LLMToolAgent')
    if type(observation) is not dict or type(observation.get('query')) is not str:
        raise ControllerProtocolError('observation query')
    mask = observation.get('action_mask')
    if type(mask) is not list or any(type(x) is not str for x in mask):
        raise ControllerProtocolError('observation mask')
    if action['action'] not in mask:
        raise ControllerProtocolError('action unavailable in current state')
    allowed = query_tokens(observation['query'])
    handles = set()
    hits = observation.get('hits', [])
    readings = observation.get('readings', [])
    if type(hits) is not list or type(readings) is not list:
        raise ControllerProtocolError('observation resource lists')
    for hit in hits:
        if type(hit) is not dict or type(hit.get('handle')) is not str:
            raise ControllerProtocolError('observed handle')
        handles.add(hit['handle'])
        for field in ('reading_text', 'expanded_text'):
            value = hit.get(field)
            if value is not None:
                if type(value) is not str:
                    raise ControllerProtocolError('observed reading type')
                allowed |= query_tokens(value)
    for reading in readings:
        if type(reading) is not dict or type(reading.get('reading_text')) is not str:
            raise ControllerProtocolError('reading text type')
        allowed |= query_tokens(reading['reading_text'])
    if action['action'] == 'SEARCH':
        _query(action['query'], allowed)
    if action['action'] == 'EXPAND' and action['handle'] not in handles:
        raise ControllerProtocolError('unobserved or foreign handle')
    return action


def compile_grammar(role, tokenizer, *, vocab_size, eos_token_ids):
    """CPU grammar compilation; accepts no task, pool, evaluator or right-action input."""
    import importlib.metadata
    import xgrammar as xg
    if importlib.metadata.version('xgrammar') != XGRAMMAR_VERSION:
        raise ControllerProtocolError('xgrammar version mismatch')
    if (type(vocab_size) is not int or vocab_size <= 0
            or type(eos_token_ids) is not list or eos_token_ids != EOS_TOKEN_IDS
            or any(type(x) is not int for x in eos_token_ids)):
        raise ControllerProtocolError('vocabulary/EOS identity')
    info = xg.TokenizerInfo.from_huggingface(tokenizer, vocab_size=vocab_size,
                                            stop_token_ids=eos_token_ids)
    return xg.GrammarCompiler(info, max_threads=1).compile_json_schema(
        controller_schema(role), any_whitespace=True)


class ControllerConstraintProcessor:
    """Single sequence; no unmasking even if another decode processor conflicts."""
    def __init__(self, compiled, *, prompt_length):
        import torch
        import xgrammar as xg
        if type(prompt_length) is not int or prompt_length < 1:
            raise ControllerProtocolError('prompt length')
        self.torch = torch
        self.vocab_size = compiled.tokenizer_info.vocab_size
        self.matcher = xg.GrammarMatcher(compiled)
        self.bitmask = xg.allocate_token_bitmask(1, self.vocab_size)
        self.shifts = torch.arange(32, dtype=torch.int64)
        self.prompt_length = prompt_length
        self.accepted = []
        self.calls = self.mask_cpu_ns = 0
        self.minimum_finite_allowed = None

    def _consume(self, generated):
        if generated[:len(self.accepted)] != self.accepted:
            raise ControllerProtocolError('generation prefix changed')
        for token in generated[len(self.accepted):]:
            if type(token) is not int or not self.matcher.accept_token(token):
                raise ControllerProtocolError('generated token violates grammar')
            self.accepted.append(token)

    def __call__(self, input_ids, scores):
        if (input_ids.ndim != 2 or input_ids.shape[0] != 1
                or input_ids.shape[1] < self.prompt_length
                or tuple(scores.shape) != (1, self.vocab_size)):
            raise ControllerProtocolError('single-sequence full-vocabulary scores required')
        start = monotonic_ns()
        self._consume(input_ids[0, self.prompt_length:].tolist())
        self.matcher.fill_next_token_bitmask(self.bitmask)
        allowed = ((self.bitmask.to(self.torch.int64).unsqueeze(-1) >> self.shifts) & 1)
        allowed = allowed.flatten()[:self.vocab_size].bool().to(scores.device).unsqueeze(0)
        if bool(self.torch.isnan(scores).any()) or bool(self.torch.isposinf(scores).any()):
            raise ControllerProtocolError('NaN or positive-infinite input logits')
        count = int((allowed & self.torch.isfinite(scores)).sum().item())
        self.mask_cpu_ns += monotonic_ns() - start
        self.calls += 1
        self.minimum_finite_allowed = count if self.minimum_finite_allowed is None else min(self.minimum_finite_allowed, count)
        if count == 0:
            raise ControllerProtocolError('empty finite grammar/decode intersection; no fallback')
        return scores.masked_fill(~allowed, float('-inf'))

    def finalize(self, token_ids):
        if type(token_ids) is not list:
            raise ControllerProtocolError('output token list')
        self._consume(token_ids)
        terminated = bool(self.matcher.is_terminated())
        completed = terminated
        if not terminated:
            self.matcher.fill_next_token_bitmask(self.bitmask)
            completed = any((int(self.bitmask[0, token // 32]) >> (token % 32)) & 1
                            for token in EOS_TOKEN_IDS)
        return dict(grammar_terminated=terminated,
                    grammar_completed=bool(completed),
                    accepted_generated_tokens=len(self.accepted))

    def measurement(self):
        return dict(mask_calls=self.calls, mask_observer_ns=self.mask_cpu_ns,
            minimum_finite_allowed=self.minimum_finite_allowed,
            timing_scope='host monotonic mask observer; includes score sync/transfer if needed',
            no_nonfinite_fallback=True)
