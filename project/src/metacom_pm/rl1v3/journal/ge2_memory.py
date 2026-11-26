"""Independent GE2 evidence environment over source-bound raw Memory records.

No model, evaluation reference, semantic approval or training label is accepted.
The trusted caller supplies an As-of/owner legality function from the existing
Registry/Ledger/PrefixPort. Queries are language, never facts. Evidence is exact
source text with original role/date/turn coordinates, unioned before rendering.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
import math

from .. import contracts as K
from ..io import object_sha256
from .ge2_retrieval import SharedRetrieval, RetrievalConfig, covered, union_intervals
from .pomdp_latency import MonotonicClock

PROTOCOL = 'pmrl1-j-goal-evidence-adaptive-v2'
TASK_KEYS = {'task_id', 'timestamp', 'turns', 'query', 'view_protocol'}


class RejectedAction(ValueError):
    pass


@dataclass(frozen=True)
class Limits:
    accesses: int = 5
    delivered_tokens: int = 4096
    context_tokens: int = 16384
    output_reserve: int = 320
    agent_seconds: float = 600.
    terminal_reserve_seconds: float = 300.
    query_words: int = 256
    query_characters: int = 4096
    controller_calls: int = 5
    controller_output_tokens: int = 768

    def __post_init__(self):
        integers = ('accesses', 'delivered_tokens', 'context_tokens', 'output_reserve',
                    'query_words', 'query_characters', 'controller_calls', 'controller_output_tokens')
        if any(type(getattr(self, k)) is not int or getattr(self, k) < 1 for k in integers):
            raise ValueError('positive GE2 integer limits required')
        if (not math.isfinite(self.agent_seconds) or not math.isfinite(self.terminal_reserve_seconds)
                or not 0 < self.terminal_reserve_seconds < self.agent_seconds):
            raise ValueError('GE2 time reserve must be finite and below agent budget')


class GE2Episode:
    def __init__(self, *, task, records, tokenizer, legal, episode_nonce,
                 limits=Limits(), retrieval_config=RetrievalConfig(), clock=None,
                 start_ns=None, source_identity=None, timing_spans=None, deadline_ns=None):
        if (not isinstance(task, dict) or set(task) - (TASK_KEYS | {'channel'})
                or not TASK_KEYS <= set(task) or not task['turns']
                or task['query'] != '\n'.join(t['text'] for t in task['turns'])
                or any(set(t) != {'role', 'text'} or t['role'] not in ('seeker', 'supporter')
                       or not isinstance(t['text'], str) for t in task['turns'])):
            raise ValueError('task allowlist/visible query binding')
        if not isinstance(episode_nonce, str) or not episode_nonce:
            raise ValueError('episode nonce required')
        self.task = deepcopy(task)
        self.tokenizer, self.legal, self.limits = tokenizer, legal, limits
        self.clock = clock or MonotonicClock()
        self.timing_spans = [] if timing_spans is None else timing_spans
        self.start_ns = self.clock.now_ns() if start_ns is None else start_ns
        if type(self.start_ns) is not int or self.start_ns > self.clock.now_ns():
            raise ValueError('episode start must be in current monotonic past')
        self.deadline_ns = (self.start_ns + int(limits.agent_seconds * 1e9)
                            if deadline_ns is None else deadline_ns)
        if type(self.deadline_ns) is not int or self.deadline_ns < self.start_ns:
            raise ValueError('episode deadline must use the current monotonic clock')
        self.retrieval = self._measure('retrieval_index_preparation',
                                      lambda: SharedRetrieval(records, retrieval_config))
        self.records = self.retrieval.records
        self.record_hashes = {rid: object_sha256(r) for rid, r in self.records.items()}
        for record in self.records.values():
            if not self.legal(record):
                raise ValueError('illegal source in GE2 pool')
        self.nonce = episode_nonce
        self.identity = object_sha256(dict(protocol=PROTOCOL, task=self.task,
            retrieval=self.retrieval.identity, tokenizer=tokenizer.identity,
            limits=asdict(limits), source_identity=source_identity))
        self.read_intervals = {}
        self.handles = {}
        self.handle_versions = {}
        self.last_hits = []
        self.trace = []
        self.failed_attempts = []
        self.accesses = 0
        self.successful_accesses = 0
        self.materialized_tokens = 0
        self.controller_calls_used = 0
        self.controller_output_tokens_used = 0
        self.done = False
        self.budget_exhausted = False
        self.status = 'acquiring'
        self.reward = None
        self._initial_payload = self.packet().payload_sha256
        if len(self.packet().input_ids) + limits.output_reserve > limits.context_tokens:
            raise ValueError('initial context exceeds capacity')

    def _measure(self, category, operation):
        def stamp():
            return dict(clock='CLOCK_MONOTONIC', boot_id=self.clock.boot_id,
                        monotonic_ns=self.clock.now_ns())
        start = stamp()
        ok = False
        try:
            result = operation()
            ok = True
            return result
        finally:
            end = stamp()
            self.timing_spans.append(dict(category=category, started=start, finished=end,
                elapsed_ns=end['monotonic_ns']-start['monotonic_ns'], ok=ok,
                aggregation='inclusive nested interval; do not sum overlapping components'))

    def _time(self):
        now = self.clock.now_ns()
        if now < self.start_ns:
            raise ValueError('monotonic clock moved backwards')
        elapsed = (now - self.start_ns) / 1e9
        remaining = max(0., min(self.limits.agent_seconds-elapsed, (self.deadline_ns-now)/1e9))
        return dict(clock='CLOCK_MONOTONIC', boot_id=self.clock.boot_id, monotonic_ns=now,
            elapsed_seconds=elapsed, agent_seconds_remaining=remaining,
            effective_deadline_ns=self.deadline_ns,
            terminal_reserve_seconds=self.limits.terminal_reserve_seconds,
            acquisition_seconds_remaining=max(0., remaining-self.limits.terminal_reserve_seconds))

    def _source_handle(self, rid):
        # Stable across policies for the same task/source; no nonce-dependent
        # resource text that would make otherwise equal terminal payloads differ.
        return 'source:' + object_sha256([PROTOCOL, rid, self.record_hashes[rid]])[:24]

    def _legal_record(self, record):
        rid = record['record_id']
        if self.record_hashes.get(rid) != object_sha256(record):
            raise RejectedAction('source_record_changed_after_binding')
        return self.legal(record)

    def _normalize_intervals(self, intervals):
        if not isinstance(intervals, dict) or set(intervals) - set(self.records):
            raise RejectedAction('foreign_interval_parent')
        result = {}
        for rid, spans in intervals.items():
            record = self.records[rid]
            if not self._legal_record(record):
                raise RejectedAction('source_no_longer_legal')
            known = {r['turn_index'] for r in record['source_refs']}
            normalized = union_intervals(spans)
            if any(lo not in known or hi not in known for lo, hi in normalized):
                raise RejectedAction('invalid_interval_coordinate')
            if normalized:
                result[rid] = normalized
        return result

    def _canonical_rows(self, intervals):
        intervals = self._normalize_intervals(intervals)
        result = []
        ordered = sorted(intervals, key=lambda rid: (self.records[rid]['reported_at']['date'],
                         self.records[rid]['source_rank'], rid))
        for rid in ordered:
            record = self.records[rid]
            refs = [ref for ref in record['source_refs'] if covered(ref['turn_index'], intervals[rid])]
            source = self._source_handle(rid)
            header = ('SOURCE_EXACT historical report; original roles; questions, advice and hypotheses '
                      'are not user actions; current validity unknown. Reported '
                      + record['reported_at']['date'] + '. Source ' + source + '.')
            text = header + '\n' + '\n'.join('[turn ' + str(ref['turn_index']) + '] '
                          + ref['speaker'] + ': ' + ref['exact_quote'] for ref in refs)
            result.append(dict(source_handle=source, reported_at=deepcopy(record['reported_at']),
                intervals=deepcopy(intervals[rid]),
                turn_coordinates=[dict(turn_index=r['turn_index'], speaker=r['speaker']) for r in refs],
                reading_text=text))
        return result

    def render_intervals(self, intervals):
        """Pure source renderer for separately identified Direct diagnostics.

        Revalidates legal source coordinates and does not mutate normal state.
        Caller must bind its independent recipe/identity and enforce capacity.
        """
        rows = self._canonical_rows(intervals)
        if not rows:
            return ()
        text = '\n\n'.join(row['reading_text'] for row in rows)
        return (K.ReadingView(head='MS', view='raw', ordinal=1, reading_text=text,
            reported_at=None, tokens=self.tokenizer.count(text), stage=None, expandable=False),)

    def packet(self):
        return self.tokenizer.make_packet(self.render_intervals(self.read_intervals))

    def _source_tokens(self, intervals=None):
        views = self.render_intervals(self.read_intervals if intervals is None else intervals)
        return views[0].tokens if views else 0

    @property
    def charged_tokens(self):
        return self._source_tokens()

    def content_state(self):
        """All causal state excluding advancing clock; no digest-as-posterior."""
        return dict(identity=self.identity, nonce=self.nonce, start_ns=self.start_ns, deadline_ns=self.deadline_ns,
            read_intervals=deepcopy(self.read_intervals), handles=deepcopy(self.handles),
            handle_order=list(self.handles), handle_versions=dict(self.handle_versions),
            last_hits=list(self.last_hits), accesses=self.accesses,
            successful_accesses=self.successful_accesses, materialized_tokens=self.materialized_tokens,
            controller_calls_used=self.controller_calls_used,
            controller_output_tokens_used=self.controller_output_tokens_used,
            limits=asdict(self.limits), done=self.done, status=self.status,
            budget_exhausted=self.budget_exhausted,
            action_history=[dict(action=deepcopy(t['action']), result=t['result']) for t in self.trace],
            failures=deepcopy(self.failed_attempts))

    def content_hash(self):
        return object_sha256(self.content_state())

    state_hash = content_hash

    def set_control_usage(self, *, calls, output_tokens):
        if (type(calls) is not int or type(output_tokens) is not int
                or not self.controller_calls_used <= calls <= self.limits.controller_calls
                or not self.controller_output_tokens_used <= output_tokens <= self.limits.controller_output_tokens):
            raise RejectedAction('controller_budget_or_nonmonotone_usage')
        self.controller_calls_used, self.controller_output_tokens_used = calls, output_tokens

    def _action_mask(self, timing):
        if self.done:
            return []
        result = ['STOP']
        if (not self.budget_exhausted and self.accesses < self.limits.accesses
                and timing['acquisition_seconds_remaining'] > 0):
            if self.records:
                result.append('SEARCH')
            if self.handles:
                result.append('EXPAND')
        return result

    def observe(self, *, no_text=False):
        timing = self._time()
        rows = self._canonical_rows(self.read_intervals)
        hits = [dict(handle=handle, source_handle=self._source_handle(item['record_id']),
                     version=item['version'], anchor_turn=item['anchor_turn'],
                     start_turn=item['start_turn'], end_turn=item['end_turn'],
                     reported_at=deepcopy(self.records[item['record_id']]['reported_at']),
                     scope=item['scope']) for handle, item in self.handles.items()]
        result = dict(protocol=PROTOCOL, turns=deepcopy(self.task['turns']),
            query=self.task['query'], goal=dict(text=self.task['query'], extraction='visible_text_only_unassessed'),
            current_time=self.task['timestamp'], hits=hits, last_hits=list(self.last_hits),
            action_history=[dict(action=deepcopy(t['action']), result=t['result']) for t in self.trace],
            access_budget=dict(used=self.accesses, remaining=self.limits.accesses-self.accesses),
            source_token_budget=dict(used=self._source_tokens(), limit=self.limits.delivered_tokens,
                                     scope='canonical_unique_rendered_source'),
            materialized_tokens_total=self.materialized_tokens,
            controller_budget=dict(calls_used=self.controller_calls_used,
                calls_remaining=self.limits.controller_calls-self.controller_calls_used,
                output_tokens_used=self.controller_output_tokens_used,
                output_tokens_remaining=self.limits.controller_output_tokens-self.controller_output_tokens_used),
            input_tokens=len(self.packet().input_ids), output_reserve_tokens=self.limits.output_reserve,
            decision_time=timing, action_mask=self._action_mask(timing),
            action_parameters=dict(SEARCH=dict(query='plain text; semantic new words allowed', unread_only=[True, False]),
                                   EXPAND=dict(handle='observed versioned handle only', scope=['neighbor', 'parent'])),
            masked_heads=['MP', 'ME', 'RS'], status=self.status,
            belief=dict(kind='operational_evidence_ledger_not_posterior', status='unassessed',
                        unknown_terminal_value=True, query_terms_are_evidence=False),
            content_sha256=self.content_hash())
        if not no_text:
            result['readings'] = rows
        else:
            result['readings_metadata'] = [{k: v for k, v in row.items() if k != 'reading_text'} for row in rows]
        result['snapshot_sha256'] = object_sha256(result)
        return result

    snapshot = observe

    def _ensure_action(self, action, expected_content_hash):
        if self.done:
            raise RejectedAction('after_stop')
        if expected_content_hash is not None and expected_content_hash != self.content_hash():
            raise RejectedAction('stale_content_snapshot')
        if not isinstance(action, dict):
            raise RejectedAction('action_schema')
        kind = action.get('action')
        keys = {'STOP': {'action'}, 'SEARCH': {'action', 'query', 'unread_only'},
                'EXPAND': {'action', 'handle', 'scope'}}
        if kind not in keys or set(action) != keys[kind]:
            raise RejectedAction('action_schema')
        if kind == 'STOP':
            return kind
        if self.accesses >= self.limits.accesses:
            raise RejectedAction('access_budget')
        if self.budget_exhausted:
            raise RejectedAction('budget_refusal_requires_stop')
        if self._time()['acquisition_seconds_remaining'] <= 0:
            raise RejectedAction('terminal_time_reserve')
        if kind == 'SEARCH':
            query = action['query']
            if (not isinstance(query, str) or not query.strip() or '\x00' in query
                    or len(query) > self.limits.query_characters
                    or len(query.split()) > self.limits.query_words
                    or type(action['unread_only']) is not bool):
                raise RejectedAction('query_shape')
        if kind == 'EXPAND' and (action['handle'] not in self.handles or action['scope'] not in ('neighbor', 'parent')):
            raise RejectedAction('unobserved_or_foreign_handle_or_scope')
        return kind

    def _add_handle(self, unit, scope):
        rid = unit['record_id']
        version = self.handle_versions.get(rid, 0) + 1
        self.handle_versions[rid] = version
        handle = 'ge2:' + object_sha256([self.nonce, rid])[:24] + ':v' + str(version)
        self.handles[handle] = dict(record_id=rid, version=version, anchor_turn=unit['anchor_turn'],
            start_turn=unit['start_turn'], end_turn=unit['end_turn'], scope=scope,
            source_unit_sha256=object_sha256(unit['source_refs']))
        return handle

    def _expand(self, action):
        item = self.handles[action['handle']]
        rid = item['record_id']
        record = self.records[rid]
        if not self._legal_record(record):
            raise RejectedAction('source_no_longer_legal')
        refs = record['source_refs']
        if action['scope'] == 'parent':
            selected = refs
        else:
            lower = next(i for i, r in enumerate(refs) if r['turn_index'] == item['start_turn'])
            upper = next(i for i, r in enumerate(refs) if r['turn_index'] == item['end_turn'])
            selected = refs[max(0, lower-1):min(len(refs), upper+2)]
        return dict(record_id=rid, anchor_turn=item['anchor_turn'], start_turn=selected[0]['turn_index'],
                    end_turn=selected[-1]['turn_index'], source_refs=deepcopy(selected))

    def step(self, action, *, expected_content_hash=None, no_text=False):
        kind = self._ensure_action(action, expected_content_hash)
        before = self.content_hash()
        start = self.clock.now_ns()
        if kind == 'STOP':
            self.done, self.status = True, 'pending_generation_and_evaluation'
            self.trace.append(dict(action=deepcopy(action), result='stopped', before=before,
                started_ns=start, finished_ns=self.clock.now_ns(), materialized_tokens=0,
                new_source_tokens=0, reward=None))
            self.trace[-1]['after'] = self.content_hash()
            return self.observe(no_text=no_text)
        self.accesses += 1  # attempted real retrieval/read is an access, including capacity refusal
        try:
            for record in self.records.values():
                if not self._legal_record(record):
                    raise RejectedAction('source_no_longer_legal')
            if kind == 'SEARCH':
                units = self._measure('retrieval_parent_ranking_and_window_selection',
                    lambda: self.retrieval.search(action['query'], read_intervals=self.read_intervals,
                                                 unread_only=action['unread_only']))
            else:
                units = [self._measure('source_expansion_selection', lambda: self._expand(action))]
            combined = deepcopy(self.read_intervals)
            materialized = {}
            for unit in units:
                rid = unit['record_id']
                pair = [unit['start_turn'], unit['end_turn']]
                combined[rid] = union_intervals(combined.get(rid, []) + [pair])
                materialized.setdefault(rid, []).append(pair)
            attempted_tokens = self._source_tokens(materialized)
            self.materialized_tokens += attempted_tokens
            old_tokens = self._source_tokens()
            views = self.render_intervals(combined)
            packet = self.tokenizer.make_packet(views)
            source_tokens = views[0].tokens if views else 0
            if self._time()['acquisition_seconds_remaining'] <= 0:
                self.budget_exhausted = True
                raise RejectedAction('terminal_time_reserve')
            if (source_tokens > self.limits.delivered_tokens
                    or len(packet.input_ids) + self.limits.output_reserve > self.limits.context_tokens):
                self.budget_exhausted = True
                raise RejectedAction('token_budget')
            self.read_intervals = combined
            self.last_hits = [self._add_handle(unit, 'window' if kind == 'SEARCH' else action['scope']) for unit in units]
            self.successful_accesses += 1
            self.trace.append(dict(action=deepcopy(action), result='read' if units else 'no_unread_hit',
                before=before, started_ns=start, finished_ns=self.clock.now_ns(),
                selected_units=deepcopy(units), handles=list(self.last_hits),
                materialized_tokens=attempted_tokens, new_source_tokens=source_tokens-old_tokens,
                canonical_source_tokens=source_tokens, content_payload_sha256=packet.payload_sha256, reward=None))
            self.trace[-1]['after'] = self.content_hash()
            return self.observe(no_text=no_text)
        except (RejectedAction, ValueError) as error:
            if isinstance(error, ValueError) and str(error).startswith('capacity:'):
                self.budget_exhausted = True
                reason = 'token_budget'
            else:
                reason = str(error)
            failed = dict(action=deepcopy(action), reason=reason, before=before,
                started_ns=start, finished_ns=self.clock.now_ns())
            self.failed_attempts.append(failed)
            self.trace.append(dict(action=deepcopy(action), result='refused', reason=reason,
                                  before=before, started_ns=start, finished_ns=failed['finished_ns']))
            self.trace[-1]['after'] = self.content_hash()
            raise RejectedAction(reason) from error

    def receipt(self):
        return dict(protocol=PROTOCOL, episode_identity=self.identity, task_id=self.task['task_id'],
            retrieval_identity=self.retrieval.identity, content_sha256=self.content_hash(),
            content_state=self.content_state(), trace=deepcopy(self.trace),
            trajectory_sha256=object_sha256(self.trace), read_intervals=deepcopy(self.read_intervals),
            accesses=self.accesses, successful_accesses=self.successful_accesses,
            canonical_source_tokens=self._source_tokens(), cumulative_materialized_tokens=self.materialized_tokens,
            content_payload_sha256=self.packet().payload_sha256, input_tokens=len(self.packet().input_ids),
            status=self.status, reward=None, formal_reward=None, model_generated=False,
            timing_spans=deepcopy(self.timing_spans),
            timing_scope='same-boot CLOCK_MONOTONIC nested actual CPU intervals; no model/client inference')


def environment_contract():
    return dict(protocol=PROTOCOL, limits=asdict(Limits()), action_schema={
        'STOP': ['action'], 'SEARCH': ['action', 'query', 'unread_only'],
        'EXPAND': ['action', 'handle', 'scope']}, expand_scopes=['neighbor', 'parent'],
        handle_pattern=r'ge2:[0-9a-f]{24}:v[1-9][0-9]*',
        neighbor='one original source turn on either side of that versioned handle interval',
        query='plain text bounded length; no word whitelist; no new personal facts asserted',
        source_tokens='canonical union rendering cap; cumulative materialized tokens reported separately',
        duplicate='all attempts consume access and measured work; unioned text occupies terminal context once',
        snapshot='full visible observation including sampled monotonic time; content version checked at action',
        time_budget='visible remaining=min(600-second path budget, admitted job deadline); reserve 300 seconds for terminal',
        evidence_status='unassessed operational ledger, never calibrated posterior or reward',
        masked_heads=['MP', 'ME', 'RS'])
