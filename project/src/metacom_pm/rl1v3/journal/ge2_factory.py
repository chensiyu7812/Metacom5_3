"""SourceRegistry -> As-of Ledger -> PrefixPort -> shared GE2 evidence adapter.

Official end-history QA and genuine dialogue prefixes retain separate envelopes.
Evaluation is never loaded. A separate, explicitly diagnostic Direct recipe is
source coordinates only and is never passed to normal acquisition policies.
"""
from __future__ import annotations

from pathlib import Path

from ..io import object_sha256
from .ge2_memory import GE2Episode, Limits
from .ge2_retrieval import RetrievalConfig
from .ge2_sources import load_factory_inputs, prepare_source_port
from .runtime_binding import binding_for
from .pomdp_dynamic_runtime import TimedTaskTokenizer, _measure, DynamicFailure


class GE2Factory:
    def __init__(self, *, source_config, envelopes, tokenizer, baseline, ledger_root,
                 retrieval_config=RetrievalConfig(backend='bm25')):
        self.envelopes = envelopes
        self.registry = load_factory_inputs(source_config, envelopes)
        self.tokenizer, self.baseline = tokenizer, baseline
        self.ledger_root = Path(ledger_root)
        self.retrieval_config = retrieval_config
        self.prepared = {}
        self.direct_provider = None

    def prepare(self, tasks):
        for task in tasks:
            tid = task['task_id']
            if tid in self.prepared:
                raise DynamicFailure('GE2 duplicate task preparation')
            envelope = self.envelopes[tid]
            if envelope['visible_task'] != task or envelope['visible_task_sha256'] != object_sha256(task):
                raise DynamicFailure('GE2 task envelope binding')
            pair = prepare_source_port(task, envelope, self.registry, self.tokenizer,
                                       self.baseline, self.ledger_root)
            self.prepared[tid] = pair
        return dict(tasks=len(tasks), source_counts={t['task_id']: len(self.prepared[t['task_id']][0][-1]) for t in tasks},
                    model_loads=0, source_only=True)

    def __call__(self, task, method, *, clock, emit, deadline_ns):
        started = clock.now_ns()
        prepared, registry = self.prepared[task['task_id']]
        bound, prefix, snapshot, tok, port, binding, records = prepared
        if task != bound:
            raise DynamicFailure('GE2 task changed after preparation')
        spans = []
        current = _measure(clock, spans, 'source_binding_legality',
                           lambda: binding_for(registry, prefix, snapshot, port))
        if current != binding:
            raise DynamicFailure('GE2 source binding drift')
        ids = {r['record_id']: object_sha256(r) for r in records}
        def legal(record):
            def check():
                entry = registry.entry(record['owner_id'], record['parent_session_id'])
                return (ids.get(record['record_id']) == object_sha256(record)
                        and record['owner_id'] == prefix.owner_id
                        and record['source_rank'] < prefix.cutoff_rank
                        and registry.reason(entry.source_id, prefix) is None)
            return _measure(clock, spans, 'source_legality_check', check)
        timed = TimedTaskTokenizer(tok, clock, spans)
        episode = GE2Episode(task=task, records=records, tokenizer=timed, legal=legal,
            episode_nonce=object_sha256(['GE2', task['task_id'], method]), limits=Limits(),
            retrieval_config=self.retrieval_config, clock=clock, start_ns=started,
            source_identity=binding.sha256, timing_spans=spans, deadline_ns=deadline_ns)
        return episode

    def direct(self, task, episode):
        if self.direct_provider is None:
            raise DynamicFailure('Direct diagnostic not configured')
        return self.direct_provider.packet(task, episode)


class DirectProvider:
    """Source-only coordinates, independent from all deployed-policy inputs."""
    def __init__(self, recipes):
        self.recipes = {}
        for row in recipes:
            if set(row) != {'task_id', 'source_units', 'protocol'} or row.get('protocol') != 'ge2-direct-source-only-exact-turn-recipe-v1' or row['task_id'] in self.recipes:
                raise DynamicFailure('Direct recipe allowlist; no answers or eval fields')
            self.recipes[row['task_id']] = row

    def packet(self, task, episode):
        recipe = self.recipes[task['task_id']]
        intervals = {}
        for unit in recipe['source_units']:
            if set(unit) != {'record_id', 'start_turn', 'end_turn'}:
                raise DynamicFailure('Direct source coordinates only')
            intervals.setdefault(unit['record_id'], []).append([unit['start_turn'], unit['end_turn']])
        views = episode.render_intervals(intervals)
        if sum(v.tokens for v in views) > episode.limits.delivered_tokens:
            raise DynamicFailure('Direct capacity; do not silently trim diagnostic evidence')
        packet = episode.tokenizer.make_packet(views)
        if len(packet.input_ids) + episode.limits.output_reserve > episode.limits.context_tokens:
            raise DynamicFailure('Direct native capacity')
        return packet, dict(protocol='pmrl1-j-ge2-direct-source-v1', task_id=task['task_id'],
            source_recipe=recipe, source_recipe_sha256=object_sha256(recipe),
            canonical_source_tokens=sum(v.tokens for v in views), input_tokens=len(packet.input_ids),
            content_payload_sha256=packet.payload_sha256,
            diagnostic_only=True, evidence_sufficiency='evaluation-side pending; coordinates do not establish success',
            normal_policy_actions=0, formal_reward=None, timing_spans=episode.timing_spans)
