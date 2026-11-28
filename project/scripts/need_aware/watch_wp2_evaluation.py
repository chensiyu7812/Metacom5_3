#!/usr/bin/env python3
"""CPU-only postprocessing: wait for B's terminal ledger, seal, score, render locally.

Does not launch/stop a model, alter conditions, publish results or choose WP3.
A terminal STOPPED run remains incomplete; read its failure/budget receipt before
interpreting the resulting scores. Resumed runs get a new immutable snapshot.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import time

def latest_events(root):
    events = []
    for path in sorted(Path(root).glob('LEDGER.*.jsonl')):
        for line in path.read_bytes().splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue  # progress only; seal_export validates the complete chain
            events.append({k: e.get(k) for k in ('event', 'event_sha256', 'model_label', 'status', 'utc')})
    return events


def run(a):
    root = Path(a.out); root.mkdir(parents=True, exist_ok=False); os.chmod(root, 0o700)
    start = time.monotonic()
    while time.monotonic()-start < a.wait_seconds:
        events = latest_events(a.ledger_root)
        c = Counter(e['event'] for e in events)
        progress = dict(physical_attempts=c['ATTEMPT_START'], validated_results=c['ATTEMPT_RESULT'],
                        failed_attempts=c['ATTEMPT_FAILED']+c['ATTEMPT_INVALID'],
                        per_model={m: sum(e['event'] == 'ATTEMPT_RESULT' and e['model_label'] == m for e in events)
                                   for m in ('Qwen35', 'G0e')},
                        last_event=events[-1] if events else None,
                        accuracy_inspected=False, gpu_owned_by='B only')
        (root/'PROGRESS.json').write_text(json.dumps(progress, indent=2)+'\n')
        print(json.dumps(progress), flush=True)
        if events and events[-1]['event'] == 'RUN_SUMMARY':
            # Load the evaluator at the actual scoring boundary, so the receipt's
            # checkout identity cannot describe an older module cached hours ago.
            from metacom_pm.need_aware.evaluation.export import seal_export
            from evaluate_wp2 import evaluate
            from report_wp2 import render
            seal_export(a.manifest_dir, a.ledger_root, root/'sealed', kind='model', final=True)
            score_args = argparse.Namespace(artifacts=a.artifacts, policy=a.policy, manifest_dir=a.manifest_dir,
                                            export_dir=str(root/'sealed'), out=str(root/'scored'), kind='model', allow_partial=False)
            evaluate(score_args)
            report = json.loads((root/'scored/aggregate.json').read_text())
            (root/'MODEL_STATISTICS.md').write_text(render(report))
            (root/'POSTPROCESS_COMPLETE.json').write_text(json.dumps(dict(
                status='terminal snapshot scored; scientific interpretation and WP3 still require review',
                terminal_run_status=events[-1]['status'], manifest_sha256=report['manifest_sha256'],
                aggregate=str(root/'scored/aggregate.json'), report=str(root/'MODEL_STATISTICS.md')), indent=2)+'\n')
            print('POSTPROCESS_COMPLETE', flush=True)
            return
        time.sleep(a.poll_seconds)
    raise SystemExit('CPU wait limit reached; no new GPU use or fabricated results')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('artifacts', 'policy', 'manifest-dir', 'ledger-root', 'out'):
        p.add_argument('--'+name, required=True)
    p.add_argument('--poll-seconds', type=float, default=60)
    p.add_argument('--wait-seconds', type=float, default=64800, help='CPU waiting only; does not extend B GPU caps')
    a = p.parse_args(); os.umask(0o077)
    if a.poll_seconds < 1 or a.wait_seconds <= 0:
        p.error('positive polling/wait limits required')
    run(a)
