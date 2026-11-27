#!/usr/bin/env python3
"""Materialize the frozen error-review census after final model export only.

Produces source-bound PRIVATE packets and public-safe observable count tables.
Never launches inference, changes scoring, or infers semantic causes by keyword.
"""
import argparse
import json
import os
from pathlib import Path

from evaluate_wp2 import read, jsonl, sha, bound
from metacom_pm.need_aware.data.contracts import load_runtime, digest
from metacom_pm.need_aware.data.history import HistoryResolver
from metacom_pm.need_aware.evaluation.score import load_eval
from metacom_pm.need_aware.evaluation.wp2 import MODELS, ARMS, require, validate_requests, score_cell
from metacom_pm.need_aware.evaluation.review import error_census


def prepare(a):
    report = read(a.scored_dir/'aggregate.json')
    require(report['result_kind'] == 'model' and report['snapshot_final'], 'final model evaluation required')
    bound(a.export_dir/'EXPORT_SUMMARY.json', report['export_seal_sha256'])
    seal = read(a.export_dir/'EXPORT_SUMMARY.json')
    require(seal['final'] and seal['result_kind'] == 'model', 'final model seal required')
    manifest = read(a.manifest_dir/'MANIFEST.json')
    require(digest(manifest) == report['manifest_sha256'] == seal['manifest_sha256'], 'manifest binding')
    bound(a.artifacts/'FREEZE.json', report['dataset_freeze_sha256'])
    for relative, expected in read(a.artifacts/'FREEZE.json')['artifacts'].items():
        bound(a.artifacts/relative, expected)
    bound(a.manifest_dir/manifest['requests_file'], manifest['requests_sha256'])
    tasks = load_runtime(a.artifacts/'runtime/tasks.mcq.jsonl')
    ev = load_eval(a.artifacts/'evaluation/tasks.mcq.jsonl')
    requests = validate_requests(tasks, ev, jsonl(a.manifest_dir/manifest['requests_file']))
    cells, outputs = {}, {}
    for model in MODELS:
        for arm in ARMS:
            key = model+'|'+arm
            entry = seal['files'][key]
            path = a.export_dir/Path(entry['path']).name
            bound(path, entry['sha256'])
            predictions = jsonl(path)
            require(all(p['run_id'] == seal['run_id'] for p in predictions), 'export run binding')
            cells[key] = score_cell(tasks, ev, requests, predictions, model=model, arm=arm)
            require(cells[key] == jsonl(a.scored_dir/('scored.'+model+'.'+arm+'.private.jsonl')), 'scored rows changed')
            outputs[key] = {p['task_id']: p for p in predictions}
    queue, counts = error_census(cells)
    by_id = {t.task_id: t for t in tasks}
    scored = {k: {r['task_id']: r for r in rows} for k, rows in cells.items()}
    direct = {r['task_id']: r for r in jsonl(a.artifacts/'direct/direct.jsonl')}
    resolver = HistoryResolver(a.artifacts/'runtime')
    packets = []
    for tid, reasons in queue.items():
        task = by_id[tid]
        sources = [r.to_dict() for r in resolver.resolve_direct(task, direct[tid], 'C')]
        model_results = {}
        for model in MODELS:
            model_results[model] = {
                arm: dict(score=scored[model+'|'+arm][tid], prediction=outputs[model+'|'+arm][tid])
                for arm in 'BCD'}
        packets.append(dict(task_id=tid, review_reasons=reasons, task=task.to_dict(),
                            evaluation=ev[tid].to_dict(), legal_direct_sources=sources,
                            model_results=model_results,
                            actual_D_messages={m: requests[f'{tid}|D|{m}']['messages'] for m in MODELS},
                            attribution_status='requires_source_review; no automatic semantic label'))
    a.out.mkdir(parents=True, exist_ok=False)
    os.chmod(a.out, 0o700)
    private = a.out/'ERROR_REVIEW.private.jsonl'
    private.write_text(''.join(json.dumps(r, ensure_ascii=False, sort_keys=True)+'\n' for r in packets))
    counts.update(result_kind='model', snapshot_final=True, aggregate_sha256=sha(a.scored_dir/'aggregate.json'),
                  export_seal_sha256=report['export_seal_sha256'],
                  evaluation_policy_sha256=report['evaluation_policy_sha256'],
                  manifest_sha256=report['manifest_sha256'],
                  review_packets_sha256=sha(private), privacy='Packets contain raw outputs/gold/history and must never be uploaded.')
    (a.out/'ERROR_CENSUS.json').write_text(json.dumps(counts, ensure_ascii=False, indent=2)+'\n')
    return dict(review_tasks=len(packets), review_packets_sha256=sha(private), semantic_review_completed=False)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('artifacts', 'manifest-dir', 'export-dir', 'scored-dir', 'out'):
        p.add_argument('--'+name, type=Path, required=True)
    os.umask(0o077)
    print(json.dumps(prepare(p.parse_args()), indent=2))
