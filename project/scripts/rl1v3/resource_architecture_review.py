#!/usr/bin/env python3
"""Read-only CPU architecture audit and proposed experiment enumeration.

Consumes existing, Git-pinned evidence. Never builds a bank, imports a model,
retokenizes, generates replies, scores utility, or changes a production port.
The proposed jobs are NOT executable generation requests or authorizations.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter, defaultdict
import html
import json
from pathlib import Path
import subprocess

from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.io import canonical_json, decode_contract, file_sha256, object_sha256
from metacom_pm.rl1v3.bank import bank_v0
from metacom_pm.rl1v3.sources import source_registry
from metacom_pm.rl1v3.retrieve.v0 import search

BASE = '320a33d1d871199d171f998300ce926b341ca1a8'
CANDIDATE = '8ba20d21da4bdcbb552946241563bd41dbe46c6c'
V3 = 'project/outputs/pm_rl1/v3/'
PROTOCOL = 'pmrl1v3-resource-architecture-review-1'
DOCS = [
    'project/docs/PM_V1_TO_V1_5_GLOBAL_FAILURE_LEDGER_ZH.md',
    'project/docs/PM_V1_5_MEMORY_FAILURE_ROOT_CAUSE_20260802_ZH.md',
    'project/docs/PM_V1_5_V5_3_CONSOLIDATED_FINDINGS_20260806_ZH.md',
    'project/docs/PM_V1_5_STRATEGY_RAG_REQUIREMENTS_AND_ESCONV_ADEQUACY_ZH.md',
    'project/docs/PM_V1_5_RS_CARD_QUALITY_ZH.md',
    'project/docs/PM_RL1_SOLUTION_PLAN_V3_20261116_ZH.md',
    'project/docs/plans/pm_rl1_v3_20261116/RESOURCE_SPEC_ZH.md',
]


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


class Inputs:
    def __init__(self):
        self.files = []

    def pin(self, root, ref, relative):
        path = root / relative
        blob = subprocess.check_output(['git', '-C', str(root), 'show', f'{ref}:{relative}'])
        require(path.read_bytes() == blob, 'input differs from pinned commit: '+relative)
        self.files.append(dict(commit=ref, path=relative, sha256=file_sha256(path), bytes=len(blob)))
        return path


def literal(path, name):
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError('missing literal '+name)


def record_text(record):
    stamp = record.reported_at.date if record.reported_at and record.reported_at.date else 'unknown'
    return (f'[{record.head}; reported {stamp}' +
            (f'; stage {record.stage}' if record.stage else '') + ']\n'+record.reading_text)


def check_request(row, binding, bank, prefix, system, notes):
    """Exact whitelist reconstruction, not a substring/ID blacklist heuristic."""
    key = decode_contract(K.TerminalKey, canonical_json(binding['new_key']))
    trace = decode_contract(K.ExecutionTrace, canonical_json(binding['new_trace']))
    trace.verify_key(key)
    require(key.sha256 == row['terminal_key_sha256'] == binding['new_key_sha256'], 'terminal identity')
    require((key.prefix_id, key.owner_id, key.prefix_context_sha256) ==
            (prefix.prefix_id, prefix.owner_id, prefix.runtime_sha256), 'prefix binding')
    require((key.bank_version, key.index_version) == (bank.version, bank.index_version), 'bank binding')
    for reading, group in zip(trace.readings, trace.acquired):
        require(len(group) == 1, 'v0 unit must be one whole record')
        record = bank.by_id[group[0]]
        ranked = search(bank, reading.head, prefix).ranked
        require(ranked and ranked[0].record_id == record.record_id, 'not actual legal top-1')
        require(reading.reading_text == record_text(record), 'unread/altered text')
        require(reading.head == record.head and reading.reported_at == record.reported_at and
                reading.stage == record.stage, 'public attribution differs')
    expected = [dict(role='system', content=system)]
    if trace.readings:
        blocks = ['<resource head="'+v.head+'">'+html.escape(v.reading_text)+'</resource>'
                  for v in sorted(trace.readings, key=lambda v: K.HEAD_ORDER.index(v.head))]
        expected.append(dict(role='user', content=notes+'<Notes>\n'+'\n'.join(blocks)+'\n</Notes>'))
    expected.extend(dict(role='user' if t.role == 'seeker' else 'assistant', content=t.text) for t in prefix.turns)
    require(row['messages'] == expected, 'model messages differ from legal visible projection')
    ledger = binding['token_ledger']
    require(len(row['input_ids']) == row['input_tokens'] == ledger['input_tokens'], 'stored token count')
    require(row['input_tokens'] + row['max_new_tokens'] <= row['context_limit'], 'capacity')
    require(binding['terminal_status'] == 'pending', 'CPU record claims generated terminal')
    return key


def proposed_jobs(requests):
    """Existing OFF/singles plus two interactions; no fabricated unreachable arm."""
    by_prefix = defaultdict(dict)
    for row in requests:
        require(row['subset'] not in by_prefix[row['prefix_id']], 'duplicate prefix/subset')
        by_prefix[row['prefix_id']][row['subset']] = row
    jobs, missing = [], []
    for prefix_id, available in sorted(by_prefix.items()):
        require('OFF' in available, 'paired design needs OFF')
        for subset in ['OFF', 'RS', 'MP', 'ME', 'MS', 'MP+MS', 'ME+MS']:
            if subset not in available:
                missing.append(dict(prefix_id=prefix_id, subset=subset, status='unreachable_not_zero'))
                continue
            r = available[subset]
            job = dict(prefix_id=prefix_id, owner_id=r['owner_id'], subset=subset,
                       layer='D' if '+' not in subset else 'E',
                       existing_request_id=r['request_id'], terminal_key_sha256=r['terminal_key_sha256'],
                       input_tokens=r['input_tokens'], result=None, status='proposed_not_authorized',
                       independent_gold=False, quality=None, generation_calls_executed=0)
            jobs.append(dict(job, plan_job_id='proposal:'+object_sha256(job)))
    return dict(protocol=PROTOCOL, scope='exposed_development_only; not B6e execution',
                source_prefix_count=len(by_prefix), jobs=jobs, unreachable=missing,
                by_layer=dict(Counter(j['layer'] for j in jobs)),
                generator_calls_executed=0, approved_gpu_requests=0,
                other_arms_require_new_identity_and_materials=['bounded_reading', 'F-resident',
                    'method_only', 'method_plus_case', 'SupportPlan', 'trained_G1'],
                promotion='A mechanical checks never qualify B/C/D/E/F or natural support')


def audit(root, candidate):
    pins = Inputs()
    pin = lambda p: pins.pin(root, BASE, p)
    cpin = lambda p: pins.pin(candidate, CANDIDATE, p)
    for path in DOCS:
        pin(path)
    for path in ['contracts.py', 'io.py', 'sources/source_registry.py', 'bank/bank_v0.py',
                 'bank/rs_v0_catalog.py', 'retrieve/v0.py', 'bank/v0_port.py', 'render/v0.py']:
        pin('project/src/metacom_pm/rl1v3/'+path)
    cfg = json.loads(pin('project/configs/rl1v3/bank_v0_port.json').read_text())
    for folder, names in [(cfg['registry_dir'], ['registry.json', 'sources.jsonl']),
                          (cfg['bank_dir'], ['bank.json', 'index.json', 'records.jsonl', 'migration.jsonl'])]:
        for name in names:
            pin(folder+'/'+name)
    registry = source_registry.load(root/cfg['registry_dir'])
    bank = bank_v0.load(root/cfg['bank_dir'], registry, expected_version=cfg['expected_bank'])
    require((registry.version, bank.index_version) == (cfg['expected_source'], cfg['expected_index']), 'source/index')
    coverage = lines(pin(V3+'B1/coverage_sample_v1.jsonl'))
    prefixes = {p['prefix_id']: registry.prefix(p['owner_id'], p['session_id'], p['cut_turn']) for p in coverage}
    heads = {}
    for head in K.HEAD_ORDER:
        rows = [r for r in bank.records if r.head == head]
        heads[head] = dict(records=len(rows), views=dict(Counter(r.view for r in rows)),
                          stage=dict(Counter(str(r.stage) for r in rows)),
                          review=dict(Counter(r.review_status for r in rows)),
                          populated={f:sum(getattr(r, f) not in (None, ()) for r in rows) for f in
                              ['subject_id', 'entity_ids', 'event_time', 'valid_from', 'valid_to',
                               'invalid_at', 'parent_event_id', 'related_claim_ids', 'index_keys']},
                          span_occurrences=sum(len(r.source_refs) for r in rows),
                          semantic_support_confirmed=sum(r.evidence_status == 'semantically_supported' for r in rows))
    samples = lines(cpin(V3+'relevance_review_20261118/REVIEW_SAMPLES.jsonl'))
    sample_checks = []
    for row in samples:
        p = row['prefix']; prefix = registry.prefix(p['owner_id'], p['session_id'], p['cut_turn'])
        require(prefix.fold in range(1, 6), 'review attempted held-out fold')
        require(prefix.prefix_id == p['prefix_id'], 'sample prefix')
        result = search(bank, row['head'], prefix)
        require([(r.record_id, r.score) for r in result.ranked] ==
                [(r['record_id'], r['score']) for r in row['legal_candidates']], 'changed ranking/candidates')
        require(result.query_identity == row['query_identity'], 'query identity')
        require(row['query_text'] == '\n'.join(t.text for t in prefix.turns[-3:]), 'query drift')
        selected = result.ranked[0].record_id if result.ranked else None
        require(selected == row['selected_record_id'], 'selection')
        if selected:
            require(row['reading_text'] == record_text(bank.by_id[selected]), 'sample reading')
        sample_checks.append(dict(sample_id=row['sample_id'], prefix_id=prefix.prefix_id, head=row['head'],
                                  candidate_count=len(result.ranked), selection_unchanged=True))
    renderer = cpin('project/src/metacom_pm/rl1v3/render/request_packet.py')
    system = literal(cpin('project/src/metacom_pm/rl1v3/generator/preflight.py'), 'PROMPT')
    notes = literal(renderer, 'NOTES')
    for path in ['generator/g0e.py', 'generator/g0e_port.py', 'generator/replay_binding.py']:
        cpin('project/src/metacom_pm/rl1v3/'+path)
    cpin('project/configs/rl1v3/G0e.json')
    requests = lines(cpin(V3+'G0e_binding_20261118/CPU_REQUESTS_ONLY.jsonl'))
    bindings = lines(cpin(V3+'G0e_binding_20261118/KEY_BINDINGS.jsonl'))
    require(len(requests) == len(bindings), 'request/binding count')
    by_request = {b['request_sha256']: b for b in bindings}
    require(len(by_request) == len(bindings), 'duplicate request binding')
    for row in requests:
        require(row['request_id'] in by_request, 'missing binding')
        check_request(row, by_request[row['request_id']], bank, prefixes[row['prefix_id']], system, notes)
    legacy = json.loads(pin(V3+'A1b_preparation/measured_v1/ASSET_CONVERSION_SCORECARD.json').read_text())
    compiled = lines(pin('project/data/paper1_public_memory/es_memeval_public_multi_view_session_results_v1.jsonl'))
    units = {u['memory_id']:u for session in compiled for u in session['accepted_units']}
    quarantined = [r for r in bank.ledger if r['old_head'] == 'MP' and r['status'] == 'quarantine']
    later_replacement = 0
    for row in quarantined:
        unit = units[row['old_id'].split('::')[1]]
        ranks = [units[r.split('::')[1]]['source_session_rank'] for r in row['replacement_ids']]
        later_replacement += bool(ranks and min(ranks) > unit['source_session_rank'])
    summary = dict(protocol=PROTOCOL, base_commit=BASE, candidate_commit=CANDIDATE,
                   scope='CPU architecture audit; no source truth or quality qualification',
                   source_version=registry.version, bank_version=bank.version, index_version=bank.index_version,
                   source_counts=dict(Counter(e.source.dataset for e in registry.entries)), heads=heads,
                   source_span_occurrences_verified=sum(v['span_occurrences'] for v in heads.values()),
                   administrative_operations=len(registry.operations), excluded_families=len(registry.excluded_families),
                   migration=dict(Counter(r['old_head']+':'+r['status'] for r in bank.ledger)),
                   quarantined_mp_with_later_full_history_replacement=later_replacement,
                   legal_ranking_rechecks=len(sample_checks), request_whitelist_rechecks=len(requests),
                   request_prefixes=len({r['prefix_id'] for r in requests}),
                   stored_native_ids_count_checked=True, tokenizer_run=False,
                   historical_read_metrics=legacy['read_metrics'],
                   historical_metrics_rerun=False, recall_accuracy=None, resource_incremental_quality=None,
                   model_calls=0, gpu_calls=0, training_runs=0, paid_calls=0)
    return summary, proposed_jobs(requests), sample_checks, pins.files


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[3])
    p.add_argument('--candidate-root', type=Path, required=True, help='checkout containing pinned PR #12 evidence')
    p.add_argument('--out', type=Path, required=True, help='new output directory, never overwrite')
    args = p.parse_args()
    require(not args.out.exists(), 'output exists; keep old evidence immutable')
    summary, plan, checks, inputs = audit(args.root, args.candidate_root)
    args.out.mkdir(parents=True)
    for name, value in [('AUDIT.json', summary), ('PROPOSED_JOBS.json', plan), ('CANDIDATE_CHECKS.json', checks)]:
        (args.out/name).write_text(canonical_json(value)+'\n')
    manifest = dict(protocol=PROTOCOL, inputs=inputs, script_sha256=file_sha256(Path(__file__)),
                    outputs={p.name:file_sha256(p) for p in sorted(args.out.iterdir())},
                    generated_responses=0, evidence_level='mechanical_only; semantic and causal checks pending')
    (args.out/'MANIFEST.json').write_text(canonical_json(manifest)+'\n')
    print(json.dumps(dict(bank_records=sum(h['records'] for h in summary['heads'].values()),
                          ranked_samples=summary['legal_ranking_rechecks'],
                          request_projections=summary['request_whitelist_rechecks'],
                          proposed_jobs=len(plan['jobs']), executed_model_calls=0)))


if __name__ == '__main__':
    main()
