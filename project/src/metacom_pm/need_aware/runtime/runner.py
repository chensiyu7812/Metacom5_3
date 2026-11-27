"""Resumable NAA batch driver: model-by-model, one load each, manifest order, full ledger.

Order of guarantees per physical call: (1) exact request in approved scope,
(2) caps from ledger state (so resume cannot exceed), (3) ATTEMPT_START durable before
the call, (4) original returned output durable before validation, (5) every failure an
event. Exact duplicate requests are REUSE events, not calls. Stops on caps, on N
consecutive failures, or on load-cap exhaustion; pending work is listed, never dropped.
"""
from __future__ import annotations

import math
import time
import uuid

from ...rl1v3.generator.limited_run import AdmissionError, require
from .budget import NAABatchBudget


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


def run(manifest, approval, ledger, backend_factory, *, clock=time.monotonic, guard=lambda: None,
        result_kind='model', only_models=None):
    budget = NAABatchBudget(manifest, approval, ledger)
    caps = manifest['caps']
    rows = manifest['requests']
    ledger.add('RUN_START', result_kind=result_kind, approval_sha256=approval.get('_sha256'),
               models=list(approval['models']), resumed_events=len(ledger.events))
    # Logical slots that need no physical call are settled first (complete denominator).
    settled = ledger.settled_logical()
    for row in rows:
        if row['logical_id'] in settled:
            continue
        if row['status'] != 'ready':
            ledger.add('NOT_EVALUABLE', logical_id=row['logical_id'], task_id=row['task_id'], arm=row['arm'],
                       model_label=row['model_label'], status=row['status'], reason=row.get('reason'))
    stop_reason = None
    for model_label in manifest['model_order']:
        if model_label not in approval['models'] or (only_models and model_label not in only_models):
            continue
        model_rows = [r for r in rows if r['model_label'] == model_label and r['status'] == 'ready']
        done, tried = ledger.completed(), ledger.attempts()
        pending = [r for r in model_rows if 'duplicate_of' not in r and r['request_sha256'] not in done]
        exhausted = [r for r in pending if tried[r['request_sha256']] >= caps['max_attempts_per_request']]
        recorded = {e['logical_id'] for e in ledger.events if e['event'] == 'EXHAUSTED'}
        for r in exhausted:
            if r['logical_id'] not in recorded:
                ledger.add('EXHAUSTED', logical_id=r['logical_id'], task_id=r['task_id'], arm=r['arm'],
                           model_label=model_label, request_sha256=r['request_sha256'], attempts=tried[r['request_sha256']])
        pending = [r for r in pending if tried[r['request_sha256']] < caps['max_attempts_per_request']]
        if pending:  # never load a model only to discover that nothing may run
            stop_reason = _model_session(model_label, pending, manifest, ledger, budget, backend_factory,
                                         clock=clock, guard=guard, caps=caps)
        done = ledger.completed()
        settled = ledger.settled_logical()
        for row in model_rows:
            if 'duplicate_of' in row and row['logical_id'] not in settled and row['request_sha256'] in done:
                ledger.add('REUSE', logical_id=row['logical_id'], task_id=row['task_id'], arm=row['arm'],
                           model_label=model_label, request_sha256=row['request_sha256'],
                           reused_from=row['duplicate_of'], independent_observation=False)
        if stop_reason:
            break
    done = ledger.completed()
    remaining = [r['logical_id'] for r in rows if r['status'] == 'ready'
                 and r['model_label'] in approval['models'] and r['request_sha256'] not in done]
    summary = dict(status='FINISHED' if not remaining else 'STOPPED', stop_reason=stop_reason,
                   physical_calls=ledger.physical_calls(), gpu_seconds=ledger.gpu_seconds(),
                   completed_unique=len(done), pending_logical=remaining, result_kind=result_kind)
    ledger.add('RUN_SUMMARY', **summary)
    return summary


def _model_session(model_label, pending, manifest, ledger, budget, backend_factory, *, clock, guard, caps):
    consecutive = 0
    queue = list(pending)
    while queue:
        try:
            budget.claim_load(model_label)
        except AdmissionError as exc:
            return f'{model_label}: {exc}'
        session = 'sess-' + uuid.uuid4().hex[:12]
        t0 = clock()
        left = budget.seconds_left(model_label)
        if left <= 0:
            return 'GPU seconds cap'
        backend = backend_factory(model_label, deadline=time.monotonic() + left, guard_bound_s=math.ceil(left))
        ledger.add('LOAD_START', model_label=model_label, session_id=session, session_elapsed_s=0.)
        try:
            loaded = backend.load(min(caps['load_seconds'], left))
        except Exception as exc:
            ledger.add('LOAD_FAILED', model_label=model_label, session_id=session,
                       session_elapsed_s=clock() - t0, error=type(exc).__name__ + ': ' + str(exc))
            _close(backend)
            consecutive += 1
            if consecutive >= caps['consecutive_failure_stop']:
                return f'{model_label}: consecutive failures at load'
            continue
        ledger.add('LOAD_OK', model_label=model_label, session_id=session, session_elapsed_s=clock() - t0,
                   measurement=loaded)
        worker_dead = False
        while queue and not worker_dead:
            row = queue[0]
            if row['request_sha256'] in ledger.completed():
                queue.pop(0); continue
            try:
                guard()
                attempt = budget.claim(row['request_sha256'], model_label, session_id=session,
                                       session_elapsed_s=clock() - t0)
            except AdmissionError as exc:
                ledger.add('STOP', model_label=model_label, session_id=session, session_elapsed_s=clock() - t0,
                           reason=str(exc), pending=[r['logical_id'] for r in queue])
                _close(backend)
                return f'{model_label}: {exc}'
            ledger.add('ATTEMPT_START', logical_id=row['logical_id'], task_id=row['task_id'], arm=row['arm'],
                       model_label=model_label, request_sha256=row['request_sha256'], attempt=attempt,
                       session_id=session, session_elapsed_s=clock() - t0, input_tokens=len(row['input_ids']))
            c0 = clock()
            try:
                result = backend.generate(_wire(row), max(1., min(caps['request_seconds'],
                                          budget.seconds_left(model_label, session, clock() - t0))))
            except Exception as exc:   # KeyboardInterrupt/SystemExit propagate; ATTEMPT_START stays durable
                ledger.add('ATTEMPT_FAILED', logical_id=row['logical_id'], model_label=model_label,
                           request_sha256=row['request_sha256'], attempt=attempt, session_id=session,
                           session_elapsed_s=clock() - t0, supervisor_seconds=clock() - c0,
                           error=type(exc).__name__ + ': ' + str(exc),
                           wire_failure=getattr(backend, 'last_failure', None))
                consecutive += 1
                queue.pop(0)
                if attempt < caps['max_attempts_per_request']:
                    queue.append(row)       # one later retry, after the rest of the queue
                if consecutive >= caps['consecutive_failure_stop']:
                    _close(backend)
                    return f'{model_label}: {consecutive} consecutive failures'
                worker_dead = backend_dead(backend)
                continue
            ledger.add('ATTEMPT_RETURNED', logical_id=row['logical_id'], model_label=model_label,
                       request_sha256=row['request_sha256'], attempt=attempt, session_id=session,
                       session_elapsed_s=clock() - t0, output=result)
            try:
                finish = validate_output(row, result)
            except AdmissionError as exc:
                ledger.add('ATTEMPT_INVALID', logical_id=row['logical_id'], model_label=model_label,
                           request_sha256=row['request_sha256'], attempt=attempt, session_id=session,
                           session_elapsed_s=clock() - t0, error=str(exc))
                consecutive += 1; queue.pop(0)
                if consecutive >= caps['consecutive_failure_stop']:
                    _close(backend)
                    return f'{model_label}: {consecutive} consecutive failures'
                continue
            consecutive = 0
            first = (result.get('first_output_observation') or {})
            ledger.add('ATTEMPT_RESULT', logical_id=row['logical_id'], task_id=row['task_id'], arm=row['arm'],
                       model_label=model_label, request_sha256=row['request_sha256'], attempt=attempt,
                       session_id=session, session_elapsed_s=clock() - t0, finish_reason=finish,
                       text=result['text'], output_tokens=len(result['token_ids']),
                       input_tokens=result['input_tokens'], generation_ns=result.get('generation_ns'),
                       first_token_latency_ns=first.get('first_generated_token_latency_ns'),
                       supervisor_seconds=clock() - c0, plumbing=bool(result.get('plumbing')))
            queue.pop(0)
        ledger.add('MODEL_SESSION_END', model_label=model_label, session_id=session,
                   session_elapsed_s=clock() - t0, worker_dead=worker_dead)
        _close(backend)
    return None


def backend_dead(backend):
    p = getattr(backend, 'p', None)
    return p is not None and p.poll() is not None


def _close(backend):
    try:
        backend.close()
    except Exception:
        pass
