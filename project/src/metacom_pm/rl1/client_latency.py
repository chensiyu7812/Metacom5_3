"""Client-clock observations, separate from legacy token rewards.

The reference transport is a local queue, not a browser/network deployment.
No model loading, scoring, default utility exchange rate, or training lives here.
"""
import math
from queue import Empty, Queue
from threading import Lock, Thread
import time

from .schema import digest

VERSION = 'pmrl1-local-stream-client-latency-v1'


def _seconds_match(recorded, from_nanoseconds):
    """Accept float roundoff, not altered client-clock measurements.

    Identity and integer nanosecond timestamps are still checked separately.
    A 1e-12-second tolerance admits arithmetic ULP noise but excludes even
    a one-nanosecond timestamp discrepancy.
    """
    if from_nanoseconds is None:
        return recorded is None
    return (type(recorded) in (int, float) and math.isfinite(recorded)
            and math.isclose(recorded, from_nanoseconds, rel_tol=0.0, abs_tol=1e-12))


def validate_trace(row):
    if row.get('identity') != digest({k:v for k,v in row.items() if k != 'identity'}):
        raise ValueError('latency trace identity changed')
    if row['version'] != VERSION or row['surface'] != 'local_reference_queue_client':
        raise ValueError('explicit client measurement surface required')
    start, end = row['send_ns'], row['observed_end_ns']
    if any(type(t) is not int or t < 0 for t in (start,end)) or end < start:
        raise ValueError('invalid client clock order')
    first, last, complete = (row[k] for k in ('first_text_ns','last_text_ns','completion_ns'))
    if (first is None) != (last is None):
        raise ValueError('incomplete text timestamps')
    if first is not None and (any(type(t) is not int for t in (first,last)) or not start <= first <= last <= end):
        raise ValueError('invalid text clock order')
    natural = row['status'] == 'natural_stop'
    if natural != (complete is not None) or (natural and (first is None or complete != last)):
        raise ValueError('completion requires a confirmed natural, nonempty response')
    expected = dict(ttft_seconds=None if first is None else (first-start)/1e9,
        completion_seconds=None if complete is None else (complete-start)/1e9,
        observed_wait_seconds=(end-start)/1e9)
    if any(not _seconds_match(row[k], v) for k, v in expected.items()):
        raise ValueError('seconds disagree with actual client events')
    return row


class ReferenceStreamClient:
    """One resident worker, concurrency=1. Only reply text counts as first text.

    The service must return a natural-stop result matching the emitted text.
    A timeout retains observed wait and poisons this client: the in-flight
    call cannot be silently retried or overlapped by a later request.
    """
    def __init__(self, service, *, regime_identity, technical_timeout_seconds):
        if not regime_identity or not math.isfinite(technical_timeout_seconds) or technical_timeout_seconds <= 0:
            raise ValueError('bound regime and positive technical timeout required')
        self.service, self.regime = service, regime_identity
        self.timeout = technical_timeout_seconds
        self.work, self.lock, self.seen = Queue(), Lock(), set()
        self.closed = False
        self.worker = Thread(target=self._work, daemon=True)
        self.worker.start()

    def _work(self):
        while True:
            task = self.work.get()
            if task is None:
                return
            payload, events = task
            def emit(text):
                if not isinstance(text,str):
                    raise TypeError('stream text must be a string')
                events.put(('text',text))
            try:
                result = self.service(payload,emit)
                events.put(('done',result))
            except BaseException as exc:
                events.put(('error',dict(type=type(exc).__name__,message=str(exc))))

    def measure(self, payload, *, trace_id):
        if not self.lock.acquire(blocking=False):
            raise ValueError('reference regime allows one request at a time')
        try:
            if self.closed or not trace_id or trace_id in self.seen:
                raise ValueError('closed client or repeated trace; no implicit retry')
            self.seen.add(trace_id)
            events = Queue(); chunks = []; first = last = None; raw = None; error = None
            send = time.perf_counter_ns()
            self.work.put((payload,events))
            deadline = send/1e9+self.timeout
            while True:
                try:
                    kind,value = events.get(timeout=max(0.,deadline-time.perf_counter()))
                except Empty:
                    status = 'client_timeout'; self.closed = True; break
                now = time.perf_counter_ns()
                if kind == 'text':
                    chunks.append(value)
                    # Whitespace-only transport events are not a visible answer.
                    if value.strip():
                        first = now if first is None else first
                        last = now
                elif kind == 'error':
                    status = 'service_error'; error = value; break
                else:
                    raw = value
                    if ''.join(chunks).strip() != raw.get('text','').strip():
                        status = 'stream_result_mismatch'
                    elif raw.get('finish_reason') == 'natural_stop' and first is not None:
                        status = 'natural_stop'
                    elif raw.get('finish_reason') == 'natural_stop':
                        status = 'empty_output'
                    else:
                        status = raw.get('finish_reason','invalid_result')
                    break
            end = time.perf_counter_ns()
            complete = last if status == 'natural_stop' else None
            body = dict(version=VERSION,trace_id=trace_id,request_identity=digest(payload),
                regime_identity=self.regime,surface='local_reference_queue_client',concurrency=1,
                send_ns=send,first_text_ns=first,last_text_ns=last,completion_ns=complete,
                observed_end_ns=end,status=status,ttft_seconds=None if first is None else (first-send)/1e9,
                completion_seconds=None if complete is None else (complete-send)/1e9,
                observed_wait_seconds=(end-send)/1e9,reply_identity=digest(''.join(chunks).strip()),
                server_result_identity=digest(raw) if raw is not None else None,error=error)
            trace = dict(body,identity=digest(body)); validate_trace(trace)
            return trace, raw
        finally:
            self.lock.release()

    def close(self):
        self.closed = True; self.work.put(None); self.worker.join(timeout=1.)


def seconds_return(*, quality_gain, trace, seconds_weight, regime_identity):
    """Candidate terminal-only cost. Explicit rate; absent quality/time stays pending.

    This function does not qualify scores or insert targets into the PPO runner.
    No GET token penalty is added. Real deployment evidence must use its own
    regime; a reference-client observation does not transfer automatically.
    """
    if type(seconds_weight) not in (int,float) or not math.isfinite(seconds_weight) or seconds_weight < 0:
        raise ValueError('explicit finite nonnegative seconds exchange rate required')
    if trace is None:
        return dict(status='pending_latency',return_value=None)
    validate_trace(trace)
    if trace['regime_identity'] != regime_identity:
        raise ValueError('latency belongs to another deployment regime')
    if trace['completion_seconds'] is None:
        return dict(status='incomplete_latency',return_value=None)
    if quality_gain is None:
        return dict(status='pending_quality',return_value=None)
    if type(quality_gain) not in (int,float) or not math.isfinite(quality_gain):
        raise ValueError('finite, separately established quality gain required')
    cost = seconds_weight*trace['completion_seconds']
    return dict(status='candidate_not_training_qualified',quality_gain=quality_gain,
        latency_seconds=trace['completion_seconds'],latency_cost=cost,
        return_value=quality_gain-cost,trace_identity=trace['identity'],token_penalty=0.)
