"""Resumable NAA batch driver: model-by-model, manifest order, full ledger, typed stops.

Order of guarantees per physical call: (1) exact request in approved scope,
(2) caps from ledger state (so resume cannot exceed), (3) ATTEMPT_START durable before
the call, (4) original returned output durable before validation, (5) every failure an
event. Exact duplicate requests are REUSE events, not calls.

v2 stop semantics:
  ModelStop   (model share, load cap, model consecutive failures, technical smoke):
              MODEL_STOP + session end + device released; the NEXT MODEL still runs.
  GlobalStop  (global GPU seconds, physical attempts, scope integrity) and SafetyStop
              (device/storage guards): GLOBAL_STOP; nothing else runs.
  RequestSkip (attempt cap / retry headroom): that request is EXHAUSTED; others continue.
Every session writes MODEL_SESSION_END in a finally block (also on interrupt).
Technical smoke: the first `smoke_calls` attempts of each model (after any earlier smoke
failure) must all return valid outputs with < `smoke_max_length_stops` length stops; it
checks transport/decoding only and never looks at answers.
"""
from __future__ import annotations

import math
import statistics
import time
import uuid

from ...rl1v3.generator.limited_run import AdmissionError, require
from .budget import GlobalStop, ModelStop, NAABatchBudget, RequestSkip, SafetyStop

ATTEMPT_END = ('ATTEMPT_RESULT', 'ATTEMPT_FAILED', 'ATTEMPT_INVALID')


def validate_output(request, result):
    ids = result.get('token_ids'); d = request['decode']
    require(isinstance(ids, list) and ids and all(type(x) is int and x >= 0 for x in ids), 'empty/invalid output IDs')
    require(len(ids) <= d['max_new_tokens'], 'output cap')
    require(result.get('input_tokens') == len(request['input_ids']), 'input token count')
    require(isinstance(result.get('text'), str), 'output text')
    eos = d['eos_token_id']
    require(not any(x in eos for x in ids[:-1]), 'tokens after first EOS')
    reason = 'eos' if ids[-1] in eos else 'length' if len(ids) == d['max_new_tokens'] else 'invalid'
    require(reason == result.get('finish_reason') and reason != 'invalid', 'finish reason does not match tokens')
    return reason


def _wire(row):
    return dict(request_sha256=row['request_sha256'], g_id=row['g_id'], messages=row['messages'],
                input_ids=row['input_ids'], decode=row['decode'])


def smoke_state(ledger, model_label, caps):
    """('passed'|'pending'|'complete', window) for the current smoke window of one model."""
    window = []
    for e in ledger.events:
        if e.get('model_label') != model_label:
            continue
        if e['event'] == 'SMOKE_PASSED':
            return 'passed', None
        if e['event'] == 'SMOKE_FAILED':
            window = []          # a fix was applied and the run resumed: a fresh window
            continue
        if e['event'] in ATTEMPT_END:
            window.append(e)
    n = caps.get('smoke_calls', 0)
    if not n or len(window) < n:
        return 'pending', window
    return 'complete', window[:n]


def evaluate_smoke(ledger, model_label, caps):
    status, window = smoke_state(ledger, model_label, caps)
    if status != 'complete':
        return status
    ok = [e for e in window if e['event'] == 'ATTEMPT_RESULT']
    bad = [e for e in window if e['event'] != 'ATTEMPT_RESULT']
    lengths = sum(e['finish_reason'] == 'length' for e in ok)
    empty = sum(not e['text'].strip() for e in ok)
    gen = [e['generation_ns'] / 1e9 for e in ok if e.get('generation_ns')]
    tps = [e['output_tokens'] / (e['generation_ns'] / 1e9) for e in ok if e.get('generation_ns')]
    detail = dict(calls=len(window), results=len(ok), failures=[e.get('error') for e in bad], length_stops=lengths,
                  empty_outputs=empty, generation_s_median=statistics.median(gen) if gen else None,
                  output_tokens_per_s_median=statistics.median(tps) if tps else None,
                  peak_reserved_bytes_max=max((e.get('peak_reserved_bytes') or 0) for e in ok) if ok else None,
                  scope='technical only: transport, native ids, EOS/decoding, timing; answers never inspected')
    passed = not bad and not empty and lengths < caps.get('smoke_max_length_stops', 8)
    ledger.add('SMOKE_PASSED' if passed else 'SMOKE_FAILED', model_label=model_label, **detail)
    return 'passed' if passed else 'failed'


def _pending(rows, ledger, caps, budget, model_label):
    done, tried = ledger.completed(), ledger.attempts()
    retries_used = sum(max(0, n - 1) for n in tried.values())
    recorded = {e['logical_id'] for e in ledger.events if e['event'] == 'EXHAUSTED'}
    out = []
    for r in rows:
        if r['model_label'] != model_label or r['status'] != 'ready' or 'duplicate_of' in r or r['request_sha256'] in done:
            continue
        n = tried[r['request_sha256']]
        reason = ('per-request attempt cap' if n >= caps['max_attempts_per_request'] else
                  'total retry cap' if n >= 1 and retries_used >= budget.max_retries_total else None)
        if reason:
            if r['logical_id'] not in recorded:
                ledger.add('EXHAUSTED', logical_id=r['logical_id'], task_id=r['task_id'], arm=r['arm'],
                           model_label=model_label, request_sha256=r['request_sha256'], attempts=n, reason=reason)
            continue
        out.append(r)
    return out


def run(manifest, approval, ledger, backend_factory, *, clock=time.monotonic, guard=lambda: None,
        result_kind='model', only_models=None):
    budget = NAABatchBudget(manifest, approval, ledger)
    caps = manifest['caps']
    rows = manifest['requests']
    ledger.add('RUN_START', result_kind=result_kind, approval_sha256=approval.get('_sha256'),
               models=list(approval['models']), resumed_events=len(ledger.events))
    settled = ledger.settled_logical()
    for row in rows:
        if row['logical_id'] not in settled and row['status'] != 'ready':
            ledger.add('NOT_EVALUABLE', logical_id=row['logical_id'], task_id=row['task_id'], arm=row['arm'],
                       model_label=row['model_label'], status=row['status'], reason=row.get('reason'))
    model_stops, global_stop = {}, None
    for model_label in manifest['model_order']:
        if model_label not in approval['models'] or (only_models and model_label not in only_models):
            continue
        try:
            _model(model_label, rows, manifest, ledger, budget, backend_factory, clock=clock, guard=guard, caps=caps)
        except ModelStop as exc:
            model_stops[model_label] = str(exc)
            ledger.add('MODEL_STOP', model_label=model_label, reason=str(exc),
                       pending=[r['logical_id'] for r in _pending(rows, ledger, caps, budget, model_label)])
        except GlobalStop as exc:
            global_stop = dict(scope=exc.scope, reason=str(exc), model_label=model_label)
            ledger.add('GLOBAL_STOP', **global_stop)
        _reuse(rows, ledger, model_label)
        if global_stop:
            break
    done = ledger.completed()
    remaining = [r['logical_id'] for r in rows if r['status'] == 'ready'
                 and r['model_label'] in approval['models'] and r['request_sha256'] not in done]
    summary = dict(status='FINISHED' if not remaining else 'STOPPED', model_stops=model_stops,
                   global_stop=global_stop, stop_reason=(global_stop or {}).get('reason') or
                   ('; '.join(f'{k}: {v}' for k, v in model_stops.items()) or None),
                   physical_calls=ledger.physical_calls(), gpu_seconds=ledger.gpu_seconds(),
                   completed_unique=len(done), pending_logical=remaining, result_kind=result_kind)
    ledger.add('RUN_SUMMARY', **summary)
    return summary


def _reuse(rows, ledger, model_label):
    done, settled = ledger.completed(), ledger.settled_logical()
    for row in rows:
        if (row['model_label'] == model_label and 'duplicate_of' in row and row['logical_id'] not in settled
                and row['request_sha256'] in done):
            ledger.add('REUSE', logical_id=row['logical_id'], task_id=row['task_id'], arm=row['arm'],
                       model_label=model_label, request_sha256=row['request_sha256'],
                       reused_from=row['duplicate_of'], independent_observation=False)


def _model(model_label, rows, manifest, ledger, budget, backend_factory, *, clock, guard, caps):
    if smoke_state(ledger, model_label, caps)[0] == 'complete':
        if evaluate_smoke(ledger, model_label, caps) == 'failed':
            raise ModelStop('technical smoke failed')
    consecutive = 0
    while True:
        queue = _pending(rows, ledger, caps, budget, model_label)
        if not queue:
            return                                      # never load a model only to find nothing may run
        budget.claim_load(model_label)                  # ModelStop / GlobalStop propagate
        consecutive = _session(model_label, queue, ledger, budget, backend_factory, clock=clock, guard=guard,
                               caps=caps, consecutive=consecutive)


def _session(model_label, queue, ledger, budget, backend_factory, *, clock, guard, caps, consecutive):
    session = 'sess-' + uuid.uuid4().hex[:12]
    t0 = clock()
    left = min(budget.seconds_left(model_label))
    backend = backend_factory(model_label, deadline=time.monotonic() + left, guard_bound_s=math.ceil(left))
    end = dict(reason='queue drained')
    elapsed = lambda: clock() - t0
    try:
        load_s = min(caps['load_seconds'], left)
        ledger.add('LOAD_START', model_label=model_label, session_id=session, session_elapsed_s=0., max_seconds=load_s)
        try:
            loaded = backend.load(load_s)
        except SafetyStop:
            raise
        except Exception as exc:
            ledger.add('LOAD_FAILED', model_label=model_label, session_id=session, session_elapsed_s=elapsed(),
                       error=type(exc).__name__ + ': ' + str(exc), wire_failure=getattr(backend, 'last_failure', None))
            consecutive += 1
            end = dict(reason='load failed')
            if consecutive >= caps['consecutive_failure_stop']:
                raise ModelStop(f'{consecutive} consecutive failures (load)')
            return consecutive
        ledger.add('LOAD_OK', model_label=model_label, session_id=session, session_elapsed_s=elapsed(),
                   measurement=loaded)
        queue = list(queue)
        while queue:
            row = queue[0]
            if row['request_sha256'] in ledger.completed():
                queue.pop(0); continue
            try:
                guard()
                attempt = budget.claim(row['request_sha256'], model_label, session_id=session,
                                       session_elapsed_s=elapsed())
            except RequestSkip as exc:
                ledger.add('EXHAUSTED', logical_id=row['logical_id'], task_id=row['task_id'], arm=row['arm'],
                           model_label=model_label, request_sha256=row['request_sha256'], reason=str(exc),
                           session_id=session, session_elapsed_s=elapsed())
                queue.pop(0); continue
            g, m = budget.seconds_left(model_label, session, elapsed())
            timeout = max(1., min(caps['request_seconds'], g, m))
            ledger.add('ATTEMPT_START', logical_id=row['logical_id'], task_id=row['task_id'], arm=row['arm'],
                       model_label=model_label, request_sha256=row['request_sha256'], attempt=attempt,
                       session_id=session, session_elapsed_s=elapsed(), input_tokens=len(row['input_ids']),
                       max_seconds=timeout)
            c0 = clock()
            try:
                result = backend.generate(_wire(row), timeout)
            except SafetyStop as exc:
                ledger.add('ATTEMPT_FAILED', logical_id=row['logical_id'], model_label=model_label,
                           request_sha256=row['request_sha256'], attempt=attempt, session_id=session,
                           session_elapsed_s=elapsed(), supervisor_seconds=clock() - c0,
                           error='SafetyStop: ' + str(exc), wire_failure=getattr(backend, 'last_failure', None))
                raise
            except Exception as exc:   # KeyboardInterrupt/SystemExit propagate; ATTEMPT_START stays durable
                ledger.add('ATTEMPT_FAILED', logical_id=row['logical_id'], model_label=model_label,
                           request_sha256=row['request_sha256'], attempt=attempt, session_id=session,
                           session_elapsed_s=elapsed(), supervisor_seconds=clock() - c0,
                           error=type(exc).__name__ + ': ' + str(exc),
                           wire_failure=getattr(backend, 'last_failure', None))
                consecutive += 1
                queue.pop(0)
                if attempt < caps['max_attempts_per_request']:
                    queue.append(row)       # one later retry, after the rest of the queue
                _smoke_gate(ledger, model_label, caps)
                if consecutive >= caps['consecutive_failure_stop']:
                    raise ModelStop(f'{consecutive} consecutive failures')
                if backend_dead(backend):
                    end = dict(reason='worker exited after failure; reload')
                    return consecutive
                continue
            ledger.add('ATTEMPT_RETURNED', logical_id=row['logical_id'], model_label=model_label,
                       request_sha256=row['request_sha256'], attempt=attempt, session_id=session,
                       session_elapsed_s=elapsed(), output=result)
            try:
                finish = validate_output(row, result)
            except AdmissionError as exc:
                ledger.add('ATTEMPT_INVALID', logical_id=row['logical_id'], model_label=model_label,
                           request_sha256=row['request_sha256'], attempt=attempt, session_id=session,
                           session_elapsed_s=elapsed(), error=str(exc))
                consecutive += 1; queue.pop(0)
                _smoke_gate(ledger, model_label, caps)
                if consecutive >= caps['consecutive_failure_stop']:
                    raise ModelStop(f'{consecutive} consecutive failures')
                continue
            consecutive = 0
            first = (result.get('first_output_observation') or {})
            ledger.add('ATTEMPT_RESULT', logical_id=row['logical_id'], task_id=row['task_id'], arm=row['arm'],
                       model_label=model_label, request_sha256=row['request_sha256'], attempt=attempt,
                       session_id=session, session_elapsed_s=elapsed(), finish_reason=finish,
                       text=result['text'], output_tokens=len(result['token_ids']),
                       input_tokens=result['input_tokens'], generation_ns=result.get('generation_ns'),
                       first_token_latency_ns=first.get('first_generated_token_latency_ns'),
                       peak_reserved_bytes=result.get('peak_reserved_bytes'),
                       supervisor_seconds=clock() - c0, plumbing=bool(result.get('plumbing')))
            queue.pop(0)
            _smoke_gate(ledger, model_label, caps)
        return consecutive
    except (ModelStop, GlobalStop) as exc:
        end = dict(reason=str(exc), scope=exc.scope)
        raise
    except BaseException as exc:
        end = dict(reason='interrupted: ' + type(exc).__name__)
        raise
    finally:
        # Teardown still holds the GPU: stamp it as an in-flight operation (charged with its bound
        # if the supervisor dies here), reap the worker, then record the occupied time incl. teardown.
        dead = backend_dead(backend)
        ledger.add('TEARDOWN_START', model_label=model_label, session_id=session, session_elapsed_s=elapsed(),
                   max_seconds=caps.get('teardown_seconds', TEARDOWN_SECONDS))
        c0 = clock()
        try:
            _close(backend)
        finally:
            ledger.add('MODEL_SESSION_END', model_label=model_label, session_id=session, session_elapsed_s=elapsed(),
                       teardown_s=clock() - c0, worker_dead=dead, **end)


def _smoke_gate(ledger, model_label, caps):
    if smoke_state(ledger, model_label, caps)[0] == 'complete' and evaluate_smoke(ledger, model_label, caps) == 'failed':
        raise ModelStop('technical smoke failed')


def backend_dead(backend):
    p = getattr(backend, 'p', None)
    return p is not None and p.poll() is not None


TEARDOWN_SECONDS = 10   # SubprocessHF.close: SIGTERM, wait 2 s, SIGKILL, wait 5 s


def _close(backend):
    try:
        backend.close()
    except Exception:
        pass
