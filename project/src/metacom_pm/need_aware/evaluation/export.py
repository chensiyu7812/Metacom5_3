"""Read-only adapter from B's hash-chained ledger to immutable evaluator exports.

No gold, runtime history, model or GPU access. First validated result wins, exactly
as B Ledger.completed(). The caller explicitly identifies final vs partial snapshots.
"""
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
import math

from ..data.contracts import digest
from .wp2 import require, unique


def execution_metrics(events, arms=('A', 'B', 'C', 'D')):
    """Aggregate timings/attempt failures, without exporting text, task IDs or errors."""
    def quantile(values, q):
        values = sorted(values)
        return values[max(0, math.ceil(q*len(values))-1)] if values else None
    def dist(values):
        return dict(n=len(values), p50=quantile(values, .5), p95=quantile(values, .95), total=sum(values))
    by_model, by_cell = {}, {}
    for model in ('G0e', 'Qwen35'):
        rows = [e for e in events if e.get('model_label') == model]
        sessions, last, ended = {}, {}, set()
        for e in rows:
            sid = e.get('session_id')
            if sid is None or 'session_elapsed_s' not in e:
                continue
            sessions[sid] = max(sessions.get(sid, 0.), e['session_elapsed_s']); last[sid] = e
            if e['event'] == 'MODEL_SESSION_END': ended.add(sid)
        accounted = sum(v+(last[s].get('max_seconds', 0.) if s not in ended and last[s]['event'] in {'ATTEMPT_START', 'LOAD_START'} else 0.)
                        for s, v in sessions.items())
        by_model[model] = dict(ledger_accounted_gpu_seconds=accounted,
                              physical_attempts=sum(e['event'] == 'ATTEMPT_START' for e in rows),
                              loads=sum(e['event'] == 'LOAD_START' for e in rows),
                              load_failures=sum(e['event'] == 'LOAD_FAILED' for e in rows),
                              failed_attempts=sum(e['event'] in {'ATTEMPT_FAILED', 'ATTEMPT_INVALID'} for e in rows),
                              smoke=[{k: e.get(k) for k in ('event', 'calls', 'results', 'length_stops', 'empty_outputs')}
                                     for e in rows if e['event'] in {'SMOKE_PASSED', 'SMOKE_FAILED'}])
        for arm in arms:
            result = [e for e in rows if e['event'] == 'ATTEMPT_RESULT' and e['arm'] == arm]
            by_cell[model+'|'+arm] = dict(completed=len(result),
                input_tokens=dist([e['input_tokens'] for e in result]),
                output_tokens=dist([e['output_tokens'] for e in result]),
                generation_seconds=dist([e['generation_ns']/1e9 for e in result if e.get('generation_ns') is not None]),
                internal_first_token_seconds=dist([e['first_token_latency_ns']/1e9 for e in result if e.get('first_token_latency_ns') is not None]),
                length_stops=sum(e['finish_reason'] == 'length' for e in result))
    return dict(per_model=by_model, per_cell=by_cell,
                ledger_accounted_gpu_seconds=sum(x['ledger_accounted_gpu_seconds'] for x in by_model.values()),
                timing_scope='Worker generation/internal first-token observations, not client end-to-end. v2 session-end stamps precede worker close; teardown cost is not measured here and must be reconciled by B.')


def read_ledger(root, manifest_sha256):
    events, previous = [], None
    files = sorted(Path(root).glob('LEDGER.*.jsonl'))
    require(bool(files), 'no ledger segments')
    tails = []
    for path in files:
        raw = path.read_bytes()  # a stable prefix even when the writer appends later
        lines = raw.split(b'\n')
        for i, line in enumerate(lines):
            if not line:
                continue
            try:
                e = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                require(i == len(lines)-1, 'corrupt interior ledger line')
                tails.append(dict(file=path.name, sha256=hashlib.sha256(line).hexdigest(), bytes=len(line)))
                continue
            require(e['manifest_sha256'] == manifest_sha256 and e['previous_event_sha256'] == previous,
                    'ledger manifest/chain mismatch')
            require(e['seq'] == len(events), 'ledger sequence mismatch')
            require(digest({k: v for k, v in e.items() if k != 'event_sha256'}) == e['event_sha256'], 'ledger hash mismatch')
            previous = e['event_sha256']; events.append(e)
    return events, tails


def predictions_from_ledger(requests, events, *, kind):
    require(kind in {'model', 'plumbing'}, 'explicit result kind required')
    require(events and any(e['event'] == 'RUN_START' for e in events), 'run never started')
    require(all(e['result_kind'] == kind for e in events if e['event'] == 'RUN_START'), 'ledger provenance mismatch')
    unique(requests, 'logical_id')
    physical = {r['request_sha256']: r for r in requests if r['status'] == 'ready' and not r.get('duplicate_of')}
    attempts, first, ends, starts = Counter(), {}, {}, {}
    for e in events:
        name = e['event']
        if name not in {'ATTEMPT_START', 'ATTEMPT_RESULT', 'ATTEMPT_FAILED', 'ATTEMPT_INVALID'}:
            continue
        sha = e['request_sha256']
        require(sha in physical, 'ledger contains request outside manifest')
        r = physical[sha]
        require(e['model_label'] == r['model_label'] and e['logical_id'] == r['logical_id'], 'ledger request identity mismatch')
        if name == 'ATTEMPT_START':
            require(sha not in first, 'successful request was attempted again')
            attempts[sha] += 1; starts[sha] = e
            require(e['attempt'] == attempts[sha], 'attempt sequence mismatch')
        else:
            require(sha in starts and starts[sha]['attempt'] == e['attempt'], 'attempt ended without matching start')
            require(sha not in ends or ends[sha]['attempt'] != e['attempt'], 'two terminal outcomes for one attempt')
            ends[sha] = e
            if name == 'ATTEMPT_RESULT':
                require(bool(e.get('plumbing')) == (kind == 'plumbing'), 'result provenance mismatch')
                first.setdefault(sha, e)
    run_id = 'naarun:'+digest([events[0]['event_sha256']])
    rows = []
    for r in requests:
        sha = r.get('request_sha256')
        result, end, start = first.get(sha), ends.get(sha), starts.get(sha)
        n, failure = attempts[sha], None
        if r['status'] != 'ready':
            require(n == 0, 'ineligible request attempted')
            status = 'not_evaluable' if r['status'] == 'not_evaluable' else 'capacity_exceeded'
            failure = None if status == 'not_evaluable' else 'capacity_exceeded'
        elif result:
            status = 'completed'
        elif not start:
            status, failure = 'missing', 'unattempted'
        elif end is None or end['seq'] < start['seq']:
            status, failure = 'missing', 'interrupted'
        else:
            status = 'failed'
            failure = ('invalid_output' if end['event'] == 'ATTEMPT_INVALID' else 'timeout'
                       if re.search(r'timeout|timed out|deadline', end.get('error', ''), re.I) else 'runtime_error')
        rows.append(dict(task_id=r['task_id'], logical_id=r['logical_id'], arm=r['arm'], model_label=r['model_label'],
                         model_id=r['model_id'], result_kind=kind, run_id=run_id, request_sha256=sha,
                         status=status, output=result['text'] if result else '',
                         reused_exact=bool(r.get('duplicate_of')), finish_reason=result['finish_reason'] if result else None,
                         attempt_count=n, failure_kind=failure))
    return rows, run_id


def seal_export(manifest_dir, ledger_root, out, *, kind, final=False):
    md = Path(manifest_dir)
    manifest = json.loads((md/'MANIFEST.json').read_text())
    raw = (md/manifest['requests_file']).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == manifest['requests_sha256'], 'request file hash mismatch')
    requests = [json.loads(s) for s in raw.splitlines() if s.strip()]
    events, tails = read_ledger(ledger_root, digest(manifest))
    if final:
        require(events[-1]['event'] == 'RUN_SUMMARY' and not tails, 'final export requires a complete terminal run summary')
    predictions, run_id = predictions_from_ledger(requests, events, kind=kind)
    groups = defaultdict(list)
    for p in predictions:
        groups[p['model_label']+'|'+p['arm']].append(p)
    out = Path(out); out.mkdir(parents=True, exist_ok=False); os.chmod(out, 0o700)
    def write(name, data):
        p = out/name; p.write_bytes(data); p.chmod(0o400)
        return hashlib.sha256(data).hexdigest()
    files = {}
    for cell, rows in sorted(groups.items()):
        name = 'predictions.'+cell.replace('|', '.')+'.jsonl'
        h = write(name, ''.join(json.dumps(r, ensure_ascii=False, sort_keys=True)+'\n' for r in rows).encode())
        files[cell] = dict(path=name, sha256=h, rows=len(rows), status=dict(Counter(r['status'] for r in rows)))
    ledger_sha = write('LEDGER_SNAPSHOT.private.jsonl', ''.join(json.dumps(e, ensure_ascii=False, sort_keys=True)+'\n' for e in events).encode())
    seal = dict(protocol='naa-evaluation-export-v1', result_kind=kind, run_id=run_id, final=final,
                manifest_sha256=digest(manifest), ledger_head_sha256=events[-1]['event_sha256'],
                ledger_events=len(events), ledger_snapshot_sha256=ledger_sha, ignored_torn_tails=tails,
                physical_calls=sum(e['event'] == 'ATTEMPT_START' for e in events),
                failed_attempt_events=dict(Counter(e['event'] for e in events if e['event'] in {'ATTEMPT_FAILED', 'ATTEMPT_INVALID', 'LOAD_FAILED'})),
                execution_metrics=execution_metrics(events, arms=sorted({r['arm'] for r in requests})),
                files=files, source='B validated first-result ledger; read-only A export adapter; no answer-dependent selection')
    write('EXPORT_SUMMARY.json', (json.dumps(seal, indent=2)+'\n').encode())
    return seal
