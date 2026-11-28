#!/usr/bin/env python3
"""Reconcile this terminal WP2 v2 ledger without inference or score changes.

The v2 runner writes session end before close. For its sequential, single-session
execution, the gap to the next LOAD_START/RUN_SUMMARY conservatively includes
close and scheduling. This is not a precise teardown measurement.
"""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path

from metacom_pm.need_aware.data.contracts import digest
from metacom_pm.need_aware.evaluation.export import read_ledger
from metacom_pm.need_aware.evaluation.wp2 import require


def close(manifest, report, events):
    require(report['result_kind'] == 'model' and report['snapshot_final'], 'final model report required')
    require(digest(manifest) == report['manifest_sha256'], 'manifest binding')
    terminal = events[-1]
    require(terminal['event'] == 'RUN_SUMMARY' and terminal['result_kind'] == 'model', 'terminal ledger required')
    require(terminal['event_sha256'] == report['ledger_head_sha256'], 'ledger/report binding')
    cells = [v['all'] for v in report['cell_summaries'].values()]
    failures = Counter()
    for cell in cells:
        failures.update(cell['failures'])
    completed = sum(v['completed'] for v in cells)
    eligible = sum(v['predefined_evaluable'] for v in cells)
    physical = sum(e['event'] == 'ATTEMPT_START' for e in events)
    require(completed == terminal['completed_unique'], 'completion mismatch')
    require(physical == terminal['physical_calls'] == report['physical_attempts'], 'attempt mismatch')
    require(eligible-completed == len(terminal['pending_logical']) == sum(failures.values()), 'pending mismatch')
    costs = {}
    for model in manifest['model_order']:
        ends = [e for e in events if e['event'] == 'MODEL_SESSION_END' and e['model_label'] == model]
        starts = [e for e in events if e['event'] == 'LOAD_START' and e['model_label'] == model]
        require(len(ends) == len(starts) == 1, 'this closeout covers single-session v2 only')
        end = ends[0]
        boundary = next(e for e in events if e['seq'] > end['seq'] and e['event'] in {'LOAD_START', 'RUN_SUMMARY'})
        gap = (datetime.fromisoformat(boundary['utc'])-datetime.fromisoformat(end['utc'])).total_seconds()
        require(gap >= 0, 'nonmonotonic wall-clock boundary')
        measured = end['session_elapsed_s']
        require(measured == report['execution_metrics']['per_model'][model]['ledger_accounted_gpu_seconds'], 'cost mismatch')
        cap = manifest['caps']['per_model_gpu_seconds']
        costs[model] = dict(ledger_gpu_seconds=measured, close_and_scheduling_upper_seconds=gap,
                            conservative_gpu_seconds_upper=measured+gap, per_model_cap=cap,
                            ledger_cap_excess_seconds=max(0., measured-cap),
                            conservative_cap_excess_seconds_upper=max(0., measured+gap-cap))
    return dict(protocol='naa-wp2-terminal-reconciliation-v1', result_kind='model', final=True,
        manifest_sha256=report['manifest_sha256'], export_seal_sha256=report['export_seal_sha256'],
        evaluation_policy_sha256=report['evaluation_policy_sha256'], ledger_head_sha256=report['ledger_head_sha256'],
        terminal_status=terminal['status'],
        counts=dict(logical_slots=sum(c['planned_slots'] for c in cells), eligible=eligible,
                    completed=completed, completion_rate=completed/eligible,
                    structural_not_evaluable=sum(c['structural_not_evaluable'] for c in cells),
                    physical_attempts=physical, retries=sum(c['retries'] for c in cells),
                    technical_uncompleted=eligible-completed, failures=dict(failures)),
        cost_by_model=costs, ledger_gpu_seconds=sum(c['ledger_gpu_seconds'] for c in costs.values()),
        conservative_gpu_seconds_upper=sum(c['conservative_gpu_seconds_upper'] for c in costs.values()),
        total_cap=manifest['caps']['max_gpu_seconds'], physical_cap=manifest['caps']['max_physical_calls'],
        cost_scope='v2 sequential single-session run; UTC inter-event gap bounds include close plus scheduling, not measured teardown; monotonic session seconds retained. Small G0e per-model overrun is disclosed, never rounded away.',
        failure_interpretation=f"{failures['unattempted']} eligible slots were never attempted; attempted failures retain their frozen adapter classes. The actual v2 budget-edge subtype is documented separately in A report and B handoff, without score reclassification. Structural slots are separate.",
        no_new_execution=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('manifest', 'aggregate', 'ledger-dir', 'out'):
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args()
    report = json.loads(a.aggregate.read_text())
    events, tails = read_ledger(a.ledger_dir, report['manifest_sha256'])
    require(not tails, 'partial ledger tail')
    result = close(json.loads(a.manifest.read_text()), report, events)
    result['aggregate_sha256'] = hashlib.sha256(a.aggregate.read_bytes()).hexdigest()
    result['ledger_segments_sha256'] = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(a.ledger_dir.glob('LEDGER.*.jsonl'))}
    a.out.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
