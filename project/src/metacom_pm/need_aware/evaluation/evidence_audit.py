"""Source-trace attribution, not a causal diagnosis or new retrieval selection."""
from collections import Counter

from ..data.history import HistoryResolver
from .wp2 import MODELS, ARMS, require, unique


def audit_evidence(tasks, runtime_root, direct_rows, requests):
    direct = unique(direct_rows, 'task_id')
    resolver = HistoryResolver(runtime_root)
    diagnostic = {}
    for task in tasks:
        d = direct[task.task_id]
        source = {r.source_id: r for r in resolver.resolve(task)}
        expected = {s['source_id']: s['original_text_sha256'] for s in d['spans']} if d['status'] == 'located_unique' else {}
        for sid, sha in expected.items():
            require(sid in source and source[sid].original_text_sha256 == sha, 'Direct source mismatch')
        by = {}
        for model in MODELS:
            delivered = {}
            for arm in ARMS:
                req = requests[f'{task.task_id}|{arm}|{model}']
                if req['status'] != 'ready':
                    continue
                trace = req['trace']
                ids, hashes = trace['delivered_ids'], trace['delivered_text_sha256']
                require(len(ids) == len(set(ids)) == len(hashes), 'duplicate/misaligned delivered evidence')
                delivered[arm] = dict(zip(ids, hashes))
                for sid, sha in delivered[arm].items():
                    require(sid in source and source[sid].original_text_sha256 == sha, 'delivered source is not legal history')
                if arm in 'CD':
                    require(delivered[arm] == expected, 'C/D differs from full legal Direct evidence')
            if expected:
                b = delivered['B']
                missing = [sid for sid in expected if sid not in b]
                user_missing = [sid for sid in missing if source[sid].speaker == 'user']
                label = ('missing_user_reference' if user_missing else 'missing_nonuser_reference'
                         if missing else 'all_reference_delivered')
                by[model] = dict(coverage_class=label, reference_units=len(expected),
                                 missing_reference_units=len(missing), missing_user_units=len(user_missing),
                                 delivered_units=len(b), nonreference_units=len(set(b)-set(expected)),
                                 full_reference_recall=(len(expected)-len(missing))/len(expected))
            else:
                by[model] = dict(coverage_class='direct_unlocated')
        diagnostic[task.task_id] = by
    return diagnostic


def attribute_results(diagnostic, cells):
    result = {}
    for model in MODELS:
        b, c, d = (unique(cells[f'{model}|{arm}'], 'task_id') for arm in 'BCD')
        buckets = {}
        for tid, info in diagnostic.items():
            bucket = info[model]['coverage_class']
            counter = buckets.setdefault(bucket, Counter())
            counter['planned_tasks'] += 1
            if b[tid]['status'] != 'completed' or c[tid]['status'] != 'completed':
                counter['not_complete_BC_pair'] += 1
                continue
            counter['complete_BC_pairs'] += 1
            counter['B_correct'] += bool(b[tid]['correct'])
            counter['C_correct'] += bool(c[tid]['correct'])
            counter['C_repairs_B'] += not b[tid]['correct'] and bool(c[tid]['correct'])
            counter['C_regresses_B'] += bool(b[tid]['correct']) and not c[tid]['correct']
            counter['both_wrong'] += not b[tid]['correct'] and not c[tid]['correct']
        result[model] = {k: dict(v) for k, v in sorted(buckets.items())}
    return dict(by_reference_coverage=result,
                interpretation='Coverage diagnoses availability only. Missing assistant/reference context and noise/use difficulty remain confounded in B-to-C; no causal allocation without an additional controlled comparison.')
