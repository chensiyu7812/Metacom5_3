"""Finite development task preparation using bounded sources and existing reads.

No model execution. Private author recipes and evaluation are separated from
runtime task text before retrieval. Source-body and answer text never live here.
"""
from collections import Counter
from pathlib import Path
from time import perf_counter
import html
import json

from .. import contracts as K
from ..compile import asof as A
from ..io import canonical_json, decode_contract, file_sha256, object_sha256, write_json_once, write_jsonl_once
from ..retrieve.v0 import words
from ..sources import source_registry as S
from .memory_port import SnapshotPrefixPort
from .joint_task_port import TaskTokenizer
from .runtime_binding import VerifiedEpisode, binding_for, plain
from . import renderer, selective_memory
from .selective_memory_validation_policies import simple_visible_choice

PROTOCOL = 'pmrl1-j-selective-memory-validation-v1'
CHANNELS = ('fact', 'natural_support', 'joint')
SITUATIONS = ('current_sufficient', 'history_missing', 'partial_sufficient',
              'no_history_needed', 'update_or_conflict_unknown')
RUNTIME_KEYS = {'task_id', 'timestamp', 'turns', 'query', 'view_protocol'}
ARMS = ('STOP', 'MS')


def jl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def quote_in_display(quote, text):
    """Optional diagnostic only: one HTML decode; not a required answer literal."""
    return html.unescape(quote) in html.unescape(text)


def freeze_bundle(*, registry, design_path, policy_freeze_path, out):
    design_path, policy_freeze_path, out = map(Path, (design_path, policy_freeze_path, out))
    design = json.loads(design_path.read_text())
    if design['new_SC_output_read'] or design['new_task_output_exists'] or design['sealed_text_read']:
        raise ValueError('pre-outcome bounded development authoring required')
    if file_sha256(policy_freeze_path) != design['policy_freeze_sha256']:
        raise ValueError('policy freeze changed')
    frozen_policies = json.loads(policy_freeze_path.read_text())
    for key in ('C1', 'simple'):
        if file_sha256(frozen_policies[key]['path']) != frozen_policies[key]['sha256']:
            raise ValueError('frozen policy implementation changed')
    if len(design['cases']) != 5 or {c['situation'] for c in design['cases']} != set(SITUATIONS):
        raise ValueError('fixed five source situations required')
    if out.exists():
        raise FileExistsError(out)
    tasks, envelopes, evals, bindings, strata, policies = [], [], [], [], [], []
    for case in design['cases']:
        if {t['channel'] for t in case['tasks']} != set(CHANNELS) or len(case['tasks']) != 3:
            raise ValueError('three distinct channels per source situation required')
        prefix = registry.prefix(case['owner'], case['anchor_session'], case['cut_turn'])
        if prefix.fold == 6 or prefix.owner_id in design['excluded_J06_owners']:
            raise ValueError('sealed or excluded family')
        refs = []
        for ref in case['refs']:
            entry = registry.entry(ref['owner'], ref['session'])
            turn = entry.source.turns[ref['turn']]
            if ref['owner'] != case['owner'] or ref['expected_speaker'] != turn.role or ref['quote'] not in turn.text:
                raise ValueError('reference quote, owner, or speaker mismatch')
            same_current = ref['session'] == prefix.session_id and ref['turn'] <= prefix.cut_turn
            if not same_current and registry.reason(entry.source_id, prefix) is not None:
                raise ValueError('reference outside actual temporal prefix')
            start = turn.text.index(ref['quote'])
            refs.append(dict(ref, source_id=entry.source_id,
                source_span=plain(S.span(entry.source, ref['turn'])),
                selected_start=start, selected_end=start+len(ref['quote']),
                reported_at=plain(entry.reported_at), source_split=entry.source.source_split,
                source_family_id=entry.source.family_id,
                source_status='visible_current_prefix' if same_current else 'legal_strict_past'))
        for quote in case['current_quotes']:
            if not any(quote in r['source_span']['exact_quote'] for r in refs):
                raise ValueError('current quote lacks original source binding')
        binding = dict(case_id=case['case_id'], owner_id=case['owner'], actual_prefix=plain(prefix),
            asof_runtime_sha256=prefix.runtime_sha256, refs=refs,
            source_interpretation=case['source_interpretation'], temporal_relation=case['temporal_relation'])
        bindings.append(binding)
        for authored in case['tasks']:
            query = authored['query']
            if not isinstance(query, str) or not query.strip():
                raise ValueError('actual readable task text required')
            if authored['channel'] == 'natural_support' and authored['required_fact_ids']:
                raise ValueError('natural support cannot inherit an exhaustive fact checklist')
            if set(authored['required_fact_ids']) - {r['atom_id'] for r in refs}:
                raise ValueError('unknown required fact slot')
            task_id = 'smtask:' + object_sha256([PROTOCOL, case['case_id'], authored['channel'], query])[:24]
            task = dict(task_id=task_id, timestamp=prefix.timestamp, turns=[dict(role='seeker', text=query)],
                query=query, view_protocol='constructed-visible-request-real-prefix-asof-v1')
            if set(task) != RUNTIME_KEYS:
                raise ValueError('runtime allowlist')
            tasks.append(task)
            envelopes.append(dict(task_id=task_id, visible_task=task, visible_task_sha256=object_sha256(task),
                actual_prefix=plain(prefix), asof_runtime_sha256=prefix.runtime_sha256,
                source_case_id=case['case_id'], owner_id=case['owner'],
                anchor_scope='Source prefix binds legality only; its body is not the visible task or retrieval query.'))
            evals.append(dict(task_id=task_id, channel=authored['channel'], situation=case['situation'],
                source_case_id=case['case_id'], source_binding=binding, fact_references=refs,
                required_fact_ids=authored['required_fact_ids'], support_goal=authored['support_goal'],
                prohibitions=authored['prohibitions'], evaluation_rules=design['evaluation_contract'],
                formal_reward=None, independent_human_reference=False, reference_status='assistant_development_pending'))
            strata.append(dict(task_id=task_id, case_id=case['case_id'], channel=authored['channel'],
                situation=case['situation'], owner_id=case['owner'], fold=prefix.fold, source_split=prefix.split))
            policies.append(dict(task_id=task_id, query_sha256=object_sha256(query),
                STOP='STOP', MS='MS', C1=selective_memory.choose(query),
                simple_visible=simple_visible_choice(query), C1_visible_features=selective_memory.visible_features(query),
                no_outcomes_available=True))
    out.mkdir(parents=True)
    for name, rows in [('TASKS.runtime.jsonl', tasks), ('TASK_ENVELOPES.private.jsonl', envelopes),
                       ('EVALSPEC.private.jsonl', evals), ('SOURCE_BINDINGS.private.jsonl', bindings),
                       ('STRATA.private.jsonl', strata), ('POLICY_CHOICES.private.jsonl', policies)]:
        write_jsonl_once(out/name, rows)
    write_json_once(out/'EVALUATION_RULES_PRIVATE.json', design['evaluation_contract'])
    files = {p.name: file_sha256(p) for p in out.iterdir() if p.is_file()}
    manifest = dict(protocol=PROTOCOL, tasks=15, source_situations=5,
        family_components=design['source_families'], channels=dict(Counter(x['channel'] for x in strata)),
        situations=dict(Counter(x['situation'] for x in strata)), files_sha256=files,
        design_path=str(design_path.resolve()), design_sha256=file_sha256(design_path),
        policy_freeze_path=str(policy_freeze_path.resolve()), policy_freeze_sha256=file_sha256(policy_freeze_path),
        builder_sha256=file_sha256(__file__), original_splits_preserved=True, sealed_body_read=False,
        independently_unseen_sources=False, actual_model_calls=0, authorized=False)
    write_json_once(out/'MANIFEST.json', manifest)
    return manifest


class VisibleMemoryPort(SnapshotPrefixPort):
    """Existing snapshot port with query-only lexical search and task renderer."""
    def __init__(self, *, registry, prefix, snapshot, tokenizer, task, baseline_sha256):
        if set(task) != RUNTIME_KEYS or task['query'] != '\n'.join(t['text'] for t in task['turns']):
            raise ValueError('visible task allowlist/query mismatch')
        self.query = task['query']
        self.query_sha256 = object_sha256(task['turns'])
        self.private_rankings = {}
        tok = TaskTokenizer(tokenizer, task['turns'], baseline_sha256, file_sha256(renderer.__file__))
        super().__init__(registry, prefix, snapshot, tok, g_id=baseline_sha256, decode_id='frozen-G0e',
            step2_id=PROTOCOL+':'+object_sha256(dict(task_id=task['task_id'], query=self.query_sha256,
                implementation=file_sha256(__file__))), output_reserve_tokens=320)
        self.reader._search = self._search_visible

    @property
    def identity(self):
        result = super().identity
        result['renderer_id'] = self.tokenizer.make_packet().renderer_id
        return result

    def _search_visible(self, head):
        candidates = self.bank.candidates(head, self.prefix) if head == 'MS' else ()
        query_words = words(self.query)
        def score(record):
            return len(query_words & words(record.reading_text)) / max(1, len(query_words))
        ranked = sorted(candidates, key=lambda r: (-score(r), -r.source_rank, r.record_id))
        result = K.RetrievalResult(head=head, ranked=tuple(K.RankedCandidate(record_id=r.record_id,
            score=score(r), components=(K.ScoreComponent(name='lexical', score=score(r), rank=i+1),))
            for i, r in enumerate(ranked)), query_identity=object_sha256(dict(query=self.query_sha256,
                bank=self.bank.version, head=head)), filters_applied=('source_integrity', 'owner', 'strict_past',
                'reported_time', 'ready_at', 'visible_task_query_only'),
            bank_version=self.bank.version, index_version=self.bank.index_version)
        self.private_rankings[head] = plain(result)
        return result


def prepare_reads(*, registry, tokenizer, bundle, base_plan, out):
    """Reads only runtime/envelope: no evaluator or chosen-evidence locations."""
    bundle, base_plan, out = map(Path, (bundle, base_plan, out))
    manifest = json.loads((bundle/'MANIFEST.json').read_text())
    for name in ('TASKS.runtime.jsonl', 'TASK_ENVELOPES.private.jsonl'):
        if file_sha256(bundle/name) != manifest['files_sha256'][name]:
            raise ValueError('frozen input changed')
    tasks = jl(bundle/'TASKS.runtime.jsonl')
    envelopes = {r['task_id']: r for r in jl(bundle/'TASK_ENVELOPES.private.jsonl')}
    base = json.loads(base_plan.read_text())
    baseline = json.loads(Path(base['baseline_path']).read_text())
    if out.exists():
        raise FileExistsError(out)
    out.mkdir(parents=True)
    requests, checks, readings, pools = [], [], [], []
    for task in tasks:
        envelope = envelopes[task['task_id']]
        if object_sha256(task) != envelope['visible_task_sha256'] or task != envelope['visible_task']:
            raise ValueError('visible task/envelope changed')
        prefix = decode_contract(K.PrefixSpec, canonical_json(envelope['actual_prefix']))
        if prefix.runtime_sha256 != envelope['asof_runtime_sha256']:
            raise ValueError('source prefix identity changed')
        registry.context(prefix)
        entries = sorted((e for e in registry.entries if e.source.owner_id == prefix.owner_id
            and registry.reason(e.source_id, prefix) is None), key=lambda e:e.source.chronological_rank)
        writer = PROTOCOL+':full-legal-raw'
        ledger = A.Ledger(out/'ledgers'/task['task_id'].replace(':', '-'))
        for entry in entries:
            ledger.append(A.record_from_source(entry, kind='MS_RAW', writer=writer, subject='session'), registry)
        snapshot = A.materialize(registry, prefix, ledger, writer=writer)
        pools.append(dict(task_id=task['task_id'], owner_id=prefix.owner_id,
            source_session_ids=[e.source.session_id for e in entries], source_ids=[e.source_id for e in entries],
            asof_runtime_sha256=prefix.runtime_sha256, snapshot_sha256=snapshot['snapshot_sha']))
        for arm in ARMS:
            started = perf_counter()
            port = VisibleMemoryPort(registry=registry, prefix=prefix, snapshot=snapshot, tokenizer=tokenizer,
                task=task, baseline_sha256=baseline['binding_sha256'])
            binding = binding_for(registry, prefix, snapshot, port)
            episode = VerifiedEpisode(registry=registry, prefix=prefix, snapshot=snapshot, port=port, binding=binding)
            state = episode.reset()
            if arm == 'MS':
                state, info = episode.try_step(state, 'GET_MS')
                if 'MS' not in state.order:
                    raise ValueError('actual GET failed: '+str(info))
            terminal, _ = episode.try_step(state, 'STOP')
            if not terminal.done or episode.stop_value(terminal).status != 'pending':
                raise ValueError('terminal/reward status')
            _, invalid = episode.try_step(terminal, 'GET_MS')
            if invalid.reason != 'after_stop':
                raise ValueError('after-stop read allowed')
            views = tuple(r.public_view for r in state.readings)
            packet = port.tokenizer.make_packet(views)
            payload = packet.payload()
            selected = [record_id for r in state.readings for record_id in r.record_ids]
            selected_sources = [port.bank.by_id[r].parent_session_id for r in selected]
            requests.append(dict(domain='selective_memory_validation', task_id=task['task_id'], arm=arm,
                logical_id='selective-memory-validation:'+task['task_id']+':'+arm,
                request_id='jreq:'+packet.payload_sha256, payload_sha256=packet.payload_sha256,
                model_input=payload, input_ids_sha256=object_sha256(payload['input_ids']),
                input_tokens=len(payload['input_ids']), renderer_id=packet.renderer_id,
                baseline_sha256=baseline['binding_sha256'], task_query_sha256=port.query_sha256,
                source_port_binding_sha256=binding.sha256, authorized=False, model_called=False,
                endpoint_scope='constructed task/query/payload/renderer/evaluation; not the original dialogue endpoint'))
            checks.append(dict(task_id=task['task_id'], arm=arm, order=list(state.order),
                actual_input_tokens=len(payload['input_ids']), selected_record_ids=selected,
                selected_source_session_ids=selected_sources, source_port_binding_sha256=binding.sha256,
                asof_runtime_sha256=prefix.runtime_sha256, source_frontier_sha256=snapshot['source_frontier_sha256'],
                after_stop_rejected=True, pending_reward=True, query_is_source_prefix=False,
                policy_input_contains_evaluation=False, actual_path_cpu_ms=(perf_counter()-started)*1000,
                private_rankings=port.private_rankings))
            readings.append(dict(task_id=task['task_id'], arm=arm, selected_record_ids=selected,
                selected_source_session_ids=selected_sources, readings=[plain(v) for v in views]))
    for name, rows in [('REQUESTS_ALL.private.jsonl', requests), ('READ_CHECKS.private.jsonl', checks),
                       ('READINGS.private.jsonl', readings), ('LEGAL_POOLS.private.jsonl', pools)]:
        write_jsonl_once(out/name, rows)
    summary = dict(protocol=PROTOCOL, tasks=len(tasks), actual_CPU_paths=len(checks),
        successful_MS_reads=sum(bool(r['selected_record_ids']) for r in checks),
        unique_payloads=len({r['payload_sha256'] for r in requests}),
        actual_input_tokens=sum(r['input_tokens'] for r in requests),
        input_tokens_by_arm={a:sum(r['input_tokens'] for r in requests if r['arm']==a) for a in ARMS},
        input_tokens_min=min(r['input_tokens'] for r in requests), input_tokens_max=max(r['input_tokens'] for r in requests),
        CPU_paths_seconds=sum(r['actual_path_cpu_ms'] for r in checks)/1000,
        runtime_context_tokens=16384, max_output_tokens=320, actual_model_calls=0,
        parsed_evaluation_for_retrieval=False, sealed_body_read=False, authorized=False,
        files_sha256={p.name:file_sha256(p) for p in out.iterdir() if p.is_file()})
    write_json_once(out/'CPU_READ_SUMMARY.json', summary)
    return summary
