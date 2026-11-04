"""Request-local memoization of exact renderer inputs; no semantic shortcuts.

The old renderer/interface identities describe delivered content, not runtime.
Callers must separately bind this implementation in the timing regime. Create
a new renderer for EVERY request; no cross-request/training cache is imported.
"""
from copy import deepcopy
from dataclasses import asdict, replace

from .organized_policy_interface import HeadSession
from .resource_organization import OrganizedRenderer
from .schema import Action, digest


class RequestRenderer(OrganizedRenderer):
    def __init__(self, original):
        if type(original) is not OrganizedRenderer:
            raise ValueError('fresh wrapper around the original renderer required')
        self._usage_cache = {}; self._chat_cache = {}; self._text_cache = {}
        self.stats = dict(usage_calls=0,usage_misses=0,chat_calls=0,chat_misses=0,text_calls=0,text_misses=0)
        def text(s):
            self.stats['text_calls'] += 1
            if s not in self._text_cache:
                self.stats['text_misses'] += 1; self._text_cache[s] = original.count_text(s)
            return self._text_cache[s]
        def chat(messages):
            # The full role/content sequence is the key, not length or counts.
            key = tuple(tuple(sorted(m.items())) for m in messages)
            self.stats['chat_calls'] += 1
            if key not in self._chat_cache:
                self.stats['chat_misses'] += 1; self._chat_cache[key] = original.count_chat(messages)
            return self._chat_cache[key]
        self.count_text,self.count_chat = text,chat
        self.context_limit,self.identity = original.context_limit,original.identity

    def usage(self,catalog,keys):
        self.stats['usage_calls'] += 1
        # Validate duplicates BEFORE canonicalizing the cache key.
        canonical = catalog.canonical(tuple(keys))
        key = (catalog.identity,tuple(x.key for x in canonical))
        if key not in self._usage_cache:
            self.stats['usage_misses'] += 1
            self._usage_cache[key] = super().usage(catalog,keys)
        return deepcopy(self._usage_cache[key])


class MemoizedHeadSession(HeadSession):
    """STOP changes no retrieved body or next-item metadata; do not rerank it."""
    def step(self,action,*,expected_observation=None):
        if type(action) not in (int,Action) or action not in tuple(Action):
            raise ValueError('one of STOP/GET_RS/GET_MP/GET_MS/GET_ME required')
        if action != Action.STOP:
            return super().step(action,expected_observation=expected_observation)
        before = self.observe()
        if expected_observation is not None and expected_observation != digest(asdict(before)):
            raise ValueError('stale observation; action not executed')
        if not before.action_mask[action]: raise ValueError('masked action')
        self._session.stop()
        # Preserve the full internal view even for persistent NoText.
        self._cached = replace(self._cached,stopped=True,action_mask=(False,)*5)
        after = self.observe()
        self._trace.append(dict(action=int(action),before=digest(asdict(before)),after=digest(asdict(after)),
            resource_token_delta=0,reward=None))
        return after
