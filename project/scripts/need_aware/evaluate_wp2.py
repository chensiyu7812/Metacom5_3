#!/usr/bin/env python3
"""Score a sealed B export in A's evaluation process; no model/GPU imports.

Raw scored rows stay in --out. Only aggregate.json is suitable for public review.
Requires EXPORT_SUMMARY.json to bind file bytes, manifest and ledger head.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from metacom_pm.need_aware.data.contracts import digest, load_runtime
from metacom_pm.need_aware.evaluation.score import load_eval
from metacom_pm.need_aware.evaluation.wp2 import (
    MODELS, ARMS, require, validate_population, validate_requests, score_cell, analyze,
)
from metacom_pm.need_aware.evaluation.evidence_audit import audit_evidence, attribute_results


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def jsonl(path):
    return [json.loads(s) for s in Path(path).read_text().splitlines() if s.strip()]


def bound(path, expected):
    require(sha(path) == expected, 'artifact hash mismatch: ' + str(path))


def evaluate(a):
    policy = read(a.policy)
    root = Path(a.artifacts)
    bound(root/'FREEZE.json', policy['dataset_freeze_sha256'])
    for relative, expected in read(root/'FREEZE.json')['artifacts'].items():
        bound(root/relative, expected)
    tasks = load_runtime(root/'runtime/tasks.mcq.jsonl')
    ev = load_eval(root/'evaluation/tasks.mcq.jsonl')
    validate_population(tasks, ev, policy)
    md = Path(a.manifest_dir)
    manifest = read(md/'MANIFEST.json')
    require(manifest['runtime_tasks_sha256'] == policy['runtime_tasks_sha256'], 'manifest runtime version')
    require(manifest['direct_sha256'] == policy['direct_manifest_sha256'], 'manifest Direct version')
    require(manifest['caps']['max_physical_calls'] == 1920 and manifest['caps']['max_gpu_seconds'] == 57600,
            'execution outside authorized WP2 bounds')
    requests_file = md/manifest['requests_file']
    bound(requests_file, manifest['requests_sha256'])
    requests = validate_requests(tasks, ev, jsonl(requests_file))
    export = Path(a.export_dir)
    seal_path = export/'EXPORT_SUMMARY.json'
    seal = read(seal_path)
    require(seal.get('result_kind') == a.kind, 'export provenance')
    require(seal.get('manifest_sha256') == digest(manifest), 'export manifest binding')
    require(bool(seal.get('ledger_head_sha256')), 'unsealed ledger head')
    if 'ledger_snapshot_sha256' in seal:
        bound(export/'LEDGER_SNAPSHOT.private.jsonl', seal['ledger_snapshot_sha256'])
    require(type(seal.get('final')) is bool, 'snapshot must state final/partial')
    require(seal['final'] or a.allow_partial, 'partial snapshot requires --allow-partial')
    require(set(seal['files']) == {f'{m}|{arm}' for m in MODELS for arm in ARMS}, 'eight export files required')
    cells = {}
    for model in MODELS:
        for arm in ARMS:
            key = f'{model}|{arm}'
            entry = seal['files'][key]
            # Resolve the filename within the handed-off snapshot, never follow
            # a stale absolute export path or arbitrary external file reference.
            path = export/Path(entry['path']).name
            require(path.resolve().parent == export.resolve(), 'export path escape')
            bound(path, entry['sha256'])
            rows = jsonl(path)
            require(len(rows) == entry['rows'] == 240, 'export row count')
            require(all(p['run_id'] == seal['run_id'] for p in rows), 'export run binding')
            cells[key] = score_cell(tasks, ev, requests, rows, model=model, arm=arm, kind=a.kind)
    attempts = sum(r['attempt_count'] for rows in cells.values() for r in rows if not r['reused_exact'])
    require(attempts <= 1920, 'physical attempt budget exceeded')
    if 'physical_calls' in seal:
        require(attempts == seal['physical_calls'], 'export/ledger physical counts differ')
    report = analyze(cells, ev, policy)
    diagnostic = audit_evidence(tasks, root/'runtime', jsonl(root/'direct/direct.jsonl'), requests)
    report['evidence_attribution'] = attribute_results(diagnostic, cells)
    report.update(result_kind=a.kind, model_capability_result=a.kind == 'model',
                  snapshot_final=seal['final'], run_id=seal['run_id'], physical_attempts=attempts,
                  evaluation_policy_sha256=sha(a.policy), dataset_freeze_sha256=sha(root/'FREEZE.json'),
                  manifest_sha256=digest(manifest), requests_sha256=manifest['requests_sha256'],
                  export_seal_sha256=sha(seal_path), ledger_head_sha256=seal['ledger_head_sha256'],
                  failed_attempt_events=seal.get('failed_attempt_events'),
                  execution_metrics=seal.get('execution_metrics'),
                  evaluator_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip())
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=False)
    os.chmod(out, 0o700)
    for key, rows in cells.items():
        (out/('scored.'+key.replace('|', '.')+'.private.jsonl')).write_text(
            ''.join(json.dumps(r, ensure_ascii=False, sort_keys=True)+'\n' for r in rows))
    (out/'aggregate.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    (out/'RECEIPT.json').write_text(json.dumps({k: v for k, v in report.items() if k not in {
        'cell_summaries', 'primary_paired', 'descriptive_paired', 'common_completed_tables', 'structural_missingness'}}, indent=2)+'\n')
    return {k: report[k] for k in ('result_kind', 'snapshot_final', 'physical_attempts', 'manifest_sha256', 'evaluation_policy_sha256')}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('artifacts', 'manifest-dir', 'export-dir', 'out', 'policy'):
        p.add_argument('--'+name, required=True)
    p.add_argument('--kind', choices=['model', 'plumbing'], required=True)
    p.add_argument('--allow-partial', action='store_true', help='sealed intermediate diagnostic; never change the experiment from interim accuracy')
    args = p.parse_args()
    os.umask(0o077)
    print(json.dumps(evaluate(args), indent=2))
