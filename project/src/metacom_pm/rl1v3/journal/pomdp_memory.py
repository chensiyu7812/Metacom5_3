"""Bounded SEARCH/EXPAND/STOP diagnostic, separate from FiniteHead.

No generator, scorer, training or psychological state model. Private pools are
obtained from the existing snapshot PrefixPort. Public observations contain only
the task and text actually delivered by an action. Unknown terminal value is None.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
import math
import re
from time import perf_counter

from .. import contracts as K
from ..io import object_sha256
from . import temporal_retrieval as T
from .runtime_binding import plain

PROTOCOL = 'pmrl1-j-pomdp-memory-cpu-v1'
RUNTIME_KEYS = {'task_id', 'timestamp', 'turns', 'query', 'view_protocol'}


class RejectedAction(ValueError):
    pass


@dataclass(frozen=True)
class Limits:
    accesses: int = 4
    delivered_tokens: int = 4096
    context_tokens: int = 16384
    output_reserve: int = 320
    hits_per_search: int = 2
    query_words: int = 256


def query_tokens(text):
    return T.words(text)


class SearchExpandEpisode:
    """A single bounded task. Environment state is private; observe is allowlisted.

    SEARCH reveals one complete source turn for each of at most two sessions.
    The turn maximizes query token overlap (tie: earliest source turn), independent
    of evaluation references. EXPAND reveals that hit's complete parent session.
    Duplicate delivery consumes access/token/wall budget although G content is
    canonicalized. No implicit reads occur during observation or action masking.
    """

    def __init__(self, *, task, records, tokenizer, legal, episode_nonce,
                 limits=Limits(), semantic_scores=None, semantic_identity=None):
        if set(task) != RUNTIME_KEYS or task['query'] != '\n'.join(t['text'] for t in task['turns']):
            raise ValueError('task allowlist/query binding')
        if not task['turns'] or any(set(t) != {'role', 'text'} for t in task['turns']):
            raise ValueError('turn allowlist')
        if limits.accesses < 1 or limits.delivered_tokens < 1 or limits.hits_per_search != 2:
            raise ValueError('invalid bounded configuration')
        if bool(semantic_scores) != bool(semantic_identity):
            raise ValueError('hybrid scoring requires a bound semantic identity')
        self.task = task
        self.tokenizer = tokenizer
        self.legal = legal
        self.limits = limits
        self.semantic_scores = semantic_scores
        self.semantic_identity = semantic_identity
        self.records = {r['record_id']: r for r in records}
        if len(self.records) != len(records):
            raise ValueError('duplicate record identity')
        for record in records:
            if record['head'] != 'MS' or record['view'] != 'raw' or not record['source_refs'] or not legal(record):
                raise ValueError('illegal source in pool')
        self.identity = object_sha256(dict(protocol=PROTOCOL, task=task,
            pool=[(r['record_id'], object_sha256(r)) for r in records], limits=asdict(limits),
            tokenizer=tokenizer.identity, retrieval=semantic_identity or 'existing-time-lexical-v1'))
        self.nonce = episode_nonce
        self.handles = {}
        self.contents = {}
        self.expanded = set()
        self.trace = []
        self.initial_tokens = query_tokens(task['query'])
        self.allowed_tokens = set(self.initial_tokens)
        self.accesses = 0
        self.charged_tokens = 0
        self.search_seconds = 0.0
        self.done = False
        self.status = 'acquiring'
        self.reward = None
        self.last_hits = []
        self.failed_attempts = []
        self.budget_exhausted = False
        self._initial_payload = self.packet().payload_sha256
        if len(self.packet().input_ids) + limits.output_reserve > limits.context_tokens:
            raise ValueError('initial context exceeds capacity')

    def _views(self, content=None):
        items = self.contents if content is None else content
        if not items:
            return ()
        # Existing renderer has one view per head. A single MS block contains
        # explicitly separated source spans/parents, each with its report date.
        text='\n\n'.join(v['text'] for _, v in sorted(items.items()))
        return (K.ReadingView(head='MS', view='raw', ordinal=1, reading_text=text,
            reported_at=None, tokens=self.tokenizer.count(text), stage=None, expandable=False),)

    def packet(self):
        return self.tokenizer.make_packet(self._views())

    def observe(self, *, no_text=False):
        hits = []
        for h, item in self.handles.items():
            row = dict(handle=h, observed_ordinal=item['ordinal'],
                expanded=h in self.expanded, delivered_tokens=item['tokens'])
            if not no_text:
                row['reading_text'] = item['span_text']
                row['expanded_text'] = item.get('expanded_text')
            hits.append(row)
        result = dict(protocol=PROTOCOL, turns=[dict(t) for t in self.task['turns']],
            query=self.task['query'], hits=hits, last_hits=list(self.last_hits),
            accesses_used=self.accesses, accesses_remaining=self.limits.accesses-self.accesses,
            delivered_tokens_used=self.charged_tokens,
            delivered_tokens_remaining=self.limits.delivered_tokens-self.charged_tokens,
            input_tokens=len(self.packet().input_ids),
            action_mask=[] if self.done else ['STOP'] + (['SEARCH'] if not self.budget_exhausted and self.accesses < self.limits.accesses and self.records else [])
                + (['EXPAND'] if not self.budget_exhausted and self.accesses < self.limits.accesses and self.handles else []),
            masked_heads=['MP', 'ME', 'RS'], status=self.status,
            belief=dict(kind='operational-evidence-ledger-not-posterior',
                observed_units=len(self.contents), unknown_terminal_value=True))
        if not no_text:
            result['readings'] = [dict(ordinal=i+1, reading_text=v['text'])
                for i, (_, v) in enumerate(sorted(self.contents.items()))]
        return result

    def _ensure_action(self, action, no_text):
        if self.done:
            raise RejectedAction('after_stop')
        kind = action.get('action')
        keys = {'STOP': {'action'}, 'SEARCH': {'action', 'query'}, 'EXPAND': {'action', 'handle'}}
        if kind not in keys or set(action) != keys[kind]:
            raise RejectedAction('action_schema')
        if kind != 'STOP' and self.accesses >= self.limits.accesses:
            raise RejectedAction('access_budget')
        if kind != 'STOP' and self.budget_exhausted:
            raise RejectedAction('budget_refusal_requires_stop')
        if kind == 'SEARCH':
            query = action['query']
            if not isinstance(query, str) or not query_tokens(query) or len(query.split()) > self.limits.query_words:
                raise RejectedAction('query_shape')
            allowed = self.initial_tokens if no_text else self.allowed_tokens
            if not query_tokens(query) <= allowed:
                raise RejectedAction('unread_query_token')
        if kind == 'EXPAND' and action['handle'] not in self.handles:
            raise RejectedAction('unobserved_or_foreign_handle')
        return kind

    def _rank(self, query):
        records = list(self.records.values())
        for r in records:
            if not self.legal(r):
                raise RejectedAction('source_no_longer_legal')
        ranked, scores = T.lexical(records, query)
        if self.semantic_scores:
            semantic = self.semantic_scores(records, query)
            if set(semantic) != set(self.records) or any(not math.isfinite(x) for x in semantic.values()):
                raise RejectedAction('invalid_hybrid_scores')
            ranked, scores, _ = T.hybrid(records, query, {'upper': None}, scores, semantic)
        return ranked[:self.limits.hits_per_search], scores

    def _span(self, record, query):
        spans = record['source_refs']
        selected = min(spans, key=lambda r: (-len(query_tokens(query) & query_tokens(r['exact_quote'])), r['turn_index']))
        text = ('SOURCE_EXACT RAW-SPAN; one complete historical source turn, not a session summary. '
                'Original speaker; present validity unknown. Reported '+record['reported_at']['date']+'.\n'
                + selected['speaker'] + ': ' + selected['exact_quote'])
        return selected, text

    def step(self, action, *, no_text=False):
        before = self.state_hash()
        start = perf_counter()
        kind = self._ensure_action(action, no_text)
        if kind == 'STOP':
            self.done = True
            self.status = 'pending_generation_and_evaluation'
            self.trace.append(dict(action=dict(action), before=before, after=self.state_hash(),
                elapsed_seconds=perf_counter()-start, delivered_tokens=0, reward=None,
                content_payload_sha256=self.packet().payload_sha256))
            return self.observe(no_text=no_text)
        pending, hits, private = {}, [], {}
        if kind == 'SEARCH':
            selected, scores = self._rank(action['query'])
            for r in selected:
                span, text = self._span(r, action['query'])
                handle = 'hit:'+object_sha256([self.nonce, r['record_id']])[:24]
                key = object_sha256([r['record_id'], span['turn_index'], text])
                pending[key] = dict(text=text, reported_at=r['reported_at'],
                    record_id=r['record_id'], scope='RAW-SPAN', span=span)
                hits.append(dict(handle=handle, record_id=r['record_id'], span_text=text,
                    tokens=self.tokenizer.count(text), span=span))
            private['ranking'] = [(r['record_id'], scores[r['record_id']]) for r in selected]
        else:
            observed = self.handles[action['handle']]
            r = self.records[observed['record_id']]
            if not self.legal(r):
                raise RejectedAction('source_no_longer_legal')
            key = object_sha256([r['record_id'], 'complete_parent'])
            pending[key] = dict(text='Complete parent session; reported '+r['reported_at']['date']+':\n'+r['reading_text'], reported_at=r['reported_at'],
                record_id=r['record_id'], scope='MS-RAW-complete-parent', spans=r['source_refs'])
            private['parent_record_id'] = r['record_id']
        charge = sum(self.tokenizer.count(v['text']) for v in pending.values())
        combined = dict(self.contents, **pending)
        renderer_capacity=False
        try:
            native = len(self.tokenizer.make_packet(self._views(combined)).input_ids)
        except ValueError as error:
            if not str(error).startswith('capacity:'):
                raise
            native=None
            renderer_capacity=True
        if renderer_capacity or self.charged_tokens + charge > self.limits.delivered_tokens or native + self.limits.output_reserve > self.limits.context_tokens:
            # Pre-delivery refusal is not a successful information acquisition.
            # Its compute is still recorded; callers must not retry to probe size.
            elapsed = perf_counter()-start
            self.failed_attempts.append(dict(action=dict(action), reason='token_budget', elapsed_seconds=elapsed))
            self.search_seconds += elapsed
            self.budget_exhausted = True
            raise RejectedAction('token_budget')
        self.contents = combined
        for item in hits:
            handle = item.pop('handle')
            if handle not in self.handles:
                self.handles[handle] = dict(item, ordinal=len(self.handles)+1)
        self.last_hits = []
        if kind == 'SEARCH':
            self.last_hits = ['hit:'+object_sha256([self.nonce, r['record_id']])[:24] for r in selected]
        else:
            self.expanded.add(action['handle'])
            self.handles[action['handle']]['expanded_text'] = next(iter(pending.values()))['text']
        for value in pending.values():
            self.allowed_tokens.update(query_tokens(value['text']))
        self.accesses += 1
        self.charged_tokens += charge
        elapsed = perf_counter()-start
        self.search_seconds += elapsed
        self.trace.append(dict(action=dict(action), before=before, after=self.state_hash(),
            elapsed_seconds=elapsed, delivered_tokens=charge, canonical_input_tokens=native,
            delivered=list(pending.values()), private=private, reward=None))
        return self.observe(no_text=no_text)

    def state_hash(self):
        return object_sha256(dict(identity=self.identity, nonce=self.nonce, content=self.contents,
            handles=self.handles, expanded=sorted(self.expanded), accesses=self.accesses,
            charged_tokens=self.charged_tokens, done=self.done, budget_exhausted=self.budget_exhausted))

    def receipt(self):
        return dict(protocol=PROTOCOL, task_id=self.task['task_id'], identity=self.identity,
            state_sha256=self.state_hash(), trajectory_sha256=object_sha256(self.trace),
            content_payload_sha256=self.packet().payload_sha256, trace=self.trace,
            failed_attempts=self.failed_attempts, accesses=self.accesses,
            delivered_tokens=self.charged_tokens, canonical_input_tokens=len(self.packet().input_ids),
            acquisition_seconds=self.search_seconds, status=self.status, reward=None,
            model_called=False, no_psychological_state_or_calibrated_posterior=True)


POLICIES = ('STOP', 'FixedTopK', 'OneShot', 'SequentialRule', 'SequentialNoText')


def run_cpu_policy(episode, policy):
    """Frozen transparent comparators; no evaluator/pool accessor is passed in.

    FixedTopK: one initial search, expand both ranked handles.
    OneShot: initial commitment to two queries (full goal and final nonempty
    sentence), each followed by expansion of its first not-yet-expanded handle.
    SequentialRule: search, expand first, form a second query from newly observed
    capitalized tokens (up to 8 in source order), expand a newly returned parent.
    NoText: same count/access domain; initial query only, expand observed handles
    in order; no hidden entity extraction, text features or query rewriting.
    None of these rules claim task correctness or semantic sufficiency.
    """
    if policy not in POLICIES:
        raise ValueError('unknown frozen policy')
    no_text = policy == 'SequentialNoText'
    observation = episode.observe(no_text=no_text)
    commitment = None
    if policy == 'OneShot':
        sentences=[s.strip() for s in re.split(r'(?<=[.!?])\s+',observation['query']) if s.strip()]
        fixed_second=sentences[-1]
        commitment = [('SEARCH', observation['query']), ('EXPAND_FIRST_UNEXPANDED', None),
            ('SEARCH',fixed_second),('EXPAND_FIRST_UNEXPANDED',None),('STOP', None)]
    if policy != 'STOP':
        try:
            observation = episode.step(dict(action='SEARCH', query=observation['query']), no_text=no_text)
            first_handles = list(observation['last_hits'])
            if first_handles:
                observation = episode.step(dict(action='EXPAND', handle=first_handles[0]), no_text=no_text)
            if policy in ('FixedTopK', 'SequentialNoText') and len(first_handles) > 1:
                observation = episode.step(dict(action='EXPAND', handle=first_handles[1]), no_text=no_text)
            if policy == 'OneShot':
                observation=episode.step(dict(action='SEARCH',query=fixed_second))
                expanded={h['handle'] for h in observation['hits'] if h['expanded']}
                remaining=[h for h in observation['last_hits'] if h not in expanded]
                if remaining and observation['accesses_remaining']:
                    episode.step(dict(action='EXPAND',handle=remaining[0]))
            if policy == 'SequentialRule' and first_handles:
                read = ' '.join(v['reading_text'] for v in observation['readings'])
                candidates = re.findall(r"\b[A-Z][a-z]{2,}\b", read)
                excluded = {w.casefold() for w in T.ENTITY_EXCLUSIONS} | {'source', 'exact', 'raw', 'span', 'original', 'completed', 'historical', 'statements'}
                terms = list(dict.fromkeys(w for w in candidates if w.casefold() not in excluded
                    and w.casefold() not in query_tokens(observation['query'])
                    and query_tokens(w) <= query_tokens(read)))[:8]
                # Keep only source-visible words; this capitalization proxy may be useless.
                query = observation['query'] + (' ' + ' '.join(terms) if terms else '')
                observation = episode.step(dict(action='SEARCH', query=query), no_text=False)
                expanded = {h['handle'] for h in observation['hits'] if h['expanded']}
                remaining = [h for h in observation['last_hits'] if h not in expanded]
                if remaining and observation['accesses_remaining']:
                    episode.step(dict(action='EXPAND', handle=remaining[0]))
        except RejectedAction as error:
            if str(error) != 'token_budget':
                raise
    episode.step(dict(action='STOP'), no_text=no_text)
    return dict(episode.receipt(), policy=policy, initial_program=commitment)
