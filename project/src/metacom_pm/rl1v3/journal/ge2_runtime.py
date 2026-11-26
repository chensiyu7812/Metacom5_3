"""One GE2 runtime for retrieval/use/decision attribution, with bounded fallback.

The runtime never loads an EvalSpec or constructs a task-success label. Protocol
failure ends that acquisition path; one already-budgeted terminal fallback may
use its validated evidence. Integrity/device/transport failures stop the job.
"""
from __future__ import annotations

from collections import Counter

from ..generator import limited_run as L
from ..generator.g0e import DECODE
from ..io import object_sha256
from . import ge2_controller as C
from .pomdp_dynamic_runtime import _stamp, _deadline, DynamicFailure
from .pomdp_latency import duration_ns

PROTOCOL = 'pmrl1-j-ge2-online-v1'
ARMS = ('STOP', 'FixedTop4', 'LLMOneShot', 'LLMToolAgent')
DIRECT = 'DirectEvidence'


def terminal_slots(tasks, direct_ids):
    return [dict(task_id=t['task_id'], method=m,
                 slot_id='ge2:' + object_sha256([PROTOCOL, t['task_id'], m]))
            for t in tasks for m in (*ARMS, *((DIRECT,) if t['task_id'] in direct_ids else ()))]


class CallBudget:
    def __init__(self, slots):
        self.allowed = {(r['task_id'], r['method']) for r in slots}
        self.terminals = set()
        self.used = Counter()
        self.task_used = Counter()
        self.output_used = Counter()
        self.physical = 0
        n = len({r['task_id'] for r in slots})
        self.caps = {'terminal': len(slots), 'oneshot': n, 'agent': n * 5}

    def remaining(self, task, role):
        return C.CONTROL_TOTAL_TOKENS - self.output_used[(task, role)]

    def claim(self, role, task, method):
        if role not in self.caps or self.used[role] >= self.caps[role]:
            raise DynamicFailure('GE2 physical role budget')
        key = (task, role)
        if self.task_used[key] >= {'terminal': 5, 'oneshot': 1, 'agent': 5}[role]:
            raise DynamicFailure('GE2 per-task call budget')
        if role == 'terminal':
            slot = (task, method)
            if slot not in self.allowed or slot in self.terminals:
                raise DynamicFailure('terminal allowlist/no retry')
            self.terminals.add(slot)
        elif self.remaining(task, role) <= 0:
            raise DynamicFailure('controller output allowance')
        self.physical += 1
        self.used[role] += 1
        self.task_used[key] += 1
        return self.physical

    def settle(self, role, task, response):
        if role != 'terminal':
            self.output_used[(task, role)] += len(response['token_ids'])
            if self.output_used[(task, role)] > C.CONTROL_TOTAL_TOKENS:
                raise DynamicFailure('controller cumulative output cap')


def control_payload(episode, role, observation, remaining):
    messages = C.messages(observation, role)
    ids = list(episode.tokenizer.encode_messages(messages))
    decode = C.controller_decode(DECODE, role, remaining)
    if len(ids) + decode['max_new_tokens'] > 16384:
        raise C.ControllerProtocolError('controller context capacity')
    return dict(messages=messages, input_ids=ids, decode=decode)


def validate_response(response, request, *, factory, backend, start, end, ordinal):
    if response.get('request_sha256') != object_sha256(request):
        raise DynamicFailure('GE2 backend request binding')
    if backend.kind == 'hf_dynamic_real':
        a, b = response['started'], response['finished']
        ns = duration_ns(a, b)
        if (a['boot_id'] != start['boot_id'] or not start['monotonic_ns'] <= a['monotonic_ns']
                <= b['monotonic_ns'] <= end['monotonic_ns']):
            raise DynamicFailure('GE2 worker timing outside call')
        if b['monotonic_ns'] > request['binding']['deadline_ns']:
            raise DynamicFailure('GE2 worker completed after request deadline')
        if abs(response['seconds'] - ns / 1e9) > 1e-9:
            raise DynamicFailure('GE2 worker seconds binding')
        observer = response['passive_output_observer']
        if observer['generated_token_count'] != len(response['token_ids']) or not observer['stream_ended']:
            raise DynamicFailure('GE2 observer/output mismatch')
        if response.get('client_ttft_ns') is not None:
            raise DynamicFailure('unobserved client TTFT')
        if response['inference_ordinal'] != ordinal or response['first_inference_after_load'] != (ordinal == 1):
            raise DynamicFailure('GE2 inference ordinal')
        for stamp in observer['events'].values():
            if stamp is not None and (stamp['boot_id'] != start['boot_id'] or not a['monotonic_ns'] <= stamp['monotonic_ns'] <= b['monotonic_ns']):
                raise DynamicFailure('GE2 callback clock')
        if factory.tokenizer.native.tokenizer.decode(response['token_ids'], skip_special_tokens=True) != response['text']:
            raise DynamicFailure('GE2 native token/text binding')
    return L.validate_result({'model_input': request['payload']}, response)


def execute(*, tasks, factory, backend, slots, emit, clock, deadline_ns, guard=lambda: None):
    from .ge2_memory import RejectedAction
    expected_ids = {t['task_id'] for t in tasks}
    if len(tasks) != 2 or len(expected_ids) != 2 or any(r['task_id'] not in expected_ids for r in slots):
        raise DynamicFailure('GE2 two-task job scope')
    budget = CallBudget(slots)
    by_id = {t['task_id']: t for t in tasks}
    completed = set()
    results = []
    start = _deadline(clock, deadline_ns)
    boot = start['boot_id']
    current = None

    def call(role, task, method, payload, binding, path_deadline):
        guard_start = _deadline(clock, min(deadline_ns, path_deadline))
        emit('EXPERIMENT_GUARD_START', stamp=guard_start, task_id=task['task_id'], method=method, role=role)
        try:
            guard()
        except BaseException as e:
            end = _stamp(clock)
            emit('EXPERIMENT_GUARD_FAILED', stamp=end, elapsed_ns=duration_ns(guard_start, end), reason=str(e))
            raise
        stamp = _deadline(clock, min(deadline_ns, path_deadline))
        emit('EXPERIMENT_GUARD_RETURNED', stamp=stamp, task_id=task['task_id'], method=method,
             role=role, elapsed_ns=duration_ns(guard_start, stamp))
        if stamp['boot_id'] != boot:
            raise DynamicFailure('GE2 clock boot changed')
        remaining = budget.remaining(task['task_id'], role) if role != 'terminal' else None
        ordinal = budget.claim(role, task['task_id'], method)
        bound = dict(binding, task_id=task['task_id'], method=method,
            physical_ordinal=ordinal, payload_sha256=object_sha256(payload), task_sha256=object_sha256(task),
            boot_id=boot, deadline_ns=min(deadline_ns, path_deadline), scope_sha256=backend.scope_sha256)
        if remaining is not None:
            bound['control_tokens_remaining'] = remaining
        request = dict(role=role, payload=payload, binding=bound)
        request['request_id'] = 'jge2:' + object_sha256(request)
        emit('MODEL_REQUEST_START', stamp=stamp, request=request, request_sha256=object_sha256(request),
             role=role, physical_ordinal=ordinal)
        try:
            response = backend.generate(request, min(300, (bound['deadline_ns'] - stamp['monotonic_ns']) / 1e9))
        except BaseException as e:
            end = _stamp(clock)
            emit('MODEL_REQUEST_FAILED', stamp=end, request_id=request['request_id'], role=role,
                 elapsed_ns=duration_ns(stamp, end), error=type(e).__name__ + ': ' + str(e),
                 wire_failure=getattr(backend, 'last_failure', None), partial_generated_output=None,
                 retry_calls=0, stop_scope='job: transport/device/model state not assumed reusable')
            raise
        returned = _stamp(clock)
        emit('MODEL_REQUEST_RETURNED', stamp=returned, request_id=request['request_id'], role=role,
             output=response, output_sha256=object_sha256(response))
        finish = validate_response(response, request, factory=factory, backend=backend,
                                   start=stamp, end=returned, ordinal=ordinal)
        budget.settle(role, task['task_id'], response)
        emit('MODEL_REQUEST_VALIDATED', stamp=_stamp(clock), request_id=request['request_id'],
             finish_reason=finish, role=role, output_tokens=len(response['token_ids']))
        _deadline(clock, deadline_ns)
        return response, request

    try:
        for slot in slots:
            tid, method = slot['task_id'], slot['method']
            task = by_id[tid]
            current = (tid, method)
            path_start = _deadline(clock, deadline_ns)
            path_deadline = min(deadline_ns, path_start['monotonic_ns'] + 600 * 10**9)
            emit('AGENT_PATH_START', stamp=path_start, task_id=tid, method=method, task_sha256=object_sha256(task),
                 cache_policy='disabled', source_scope='Direct diagnostic' if method == DIRECT else 'normal acquisition')
            episode = factory(task, method, clock=clock, emit=emit, deadline_ns=path_deadline)
            controller_failure = None
            stop_reason = None
            assessments = []

            def act(action):
                before = episode.content_hash()
                a = _deadline(clock, path_deadline)
                emit('TOOL_START', stamp=a, task_id=tid, method=method, action=action, content_sha256=before)
                try:
                    value = episode.step(action, expected_content_hash=before)
                except RejectedAction as error:
                    b = _stamp(clock)
                    emit('TOOL_REJECTED', stamp=b, task_id=tid, method=method, action=action,
                         elapsed_ns=duration_ns(a, b), reason=str(error), source_receipt=episode.receipt())
                    raise
                b = _deadline(clock, path_deadline)
                emit('TOOL_RETURNED', stamp=b, task_id=tid, method=method, action=action,
                     elapsed_ns=duration_ns(a, b), observation=value, observation_sha256=object_sha256(value),
                     content_sha256=episode.content_hash())
                return value

            if method == DIRECT:
                packet, receipt = factory.direct(task, episode)
                stop_reason = 'direct_evidence_diagnostic_no_policy'
            else:
                try:
                    if method == 'STOP':
                        act({'action': 'STOP'})
                        stop_reason = 'fixed_no_acquisition'
                    elif method == 'FixedTop4':
                        obs = act(dict(action='SEARCH', query=task['query'], unread_only=True))
                        # Rank order is committed before any EXPAND. All arms have
                        # the same SEARCH, parent-read, action and source capacity.
                        chosen = list(obs['last_hits'])
                        for handle in chosen:
                            act(dict(action='EXPAND', handle=handle, scope='parent'))
                        stop_reason = 'fixed_program_complete'
                    elif method in ('LLMOneShot', 'LLMToolAgent'):
                        role = 'oneshot' if method == 'LLMOneShot' else 'agent'
                        for _ in range(1 if role == 'oneshot' else C.MAX_TOOL_CALLS):
                            obs = episode.snapshot()
                            # Acquisition time includes all preceding control/tool
                            # latency; the terminal reserve is an explicit contract.
                            if (path_deadline - clock.now_ns()) / 1e9 <= 300:
                                stop_reason = 'time_reserve'; break
                            if obs['action_mask'] == ['STOP']:
                                stop_reason = 'environment_only_stop'; break
                            remaining = budget.remaining(tid, role)
                            if remaining <= 0:
                                stop_reason = 'controller_token_cap'; break
                            obs = dict(obs, controller_budget=dict(output_tokens_remaining=remaining,
                                calls_remaining=(1 if role == 'oneshot' else 5) - budget.task_used[(tid, role)]))
                            obs['snapshot_sha256'] = object_sha256({k: v for k, v in obs.items() if k != 'snapshot_sha256'})
                            payload = control_payload(episode, method, obs, remaining)
                            response, request = call(role, task, method, payload,
                                dict(observation_sha256=object_sha256(obs), content_sha256=episode.content_hash()), path_deadline)
                            episode.set_control_usage(calls=budget.task_used[(tid, role)],
                                output_tokens=budget.output_used[(tid, role)])
                            if response['finish_reason'] != 'eos':
                                raise C.ControllerProtocolError('technical controller length')
                            value = C.parse(response['text'], method) if role == 'oneshot' else C.validate_tool(response['text'], obs)
                            assessments.append(value['evidence_state'])
                            emit('CONTROLLER_ACCEPTED', stamp=_stamp(clock), task_id=tid, method=method,
                                 request_id=request['request_id'], output=value,
                                 evidence_state_is_qualified=False, first_effective_output='complete accepted JSON after return')
                            if role == 'oneshot':
                                emit('ONESHOT_COMMITTED', stamp=_stamp(clock), task_id=tid,
                                     program=value, program_sha256=object_sha256(value))
                                searches = []
                                for planned in value['actions']:
                                    action = planned
                                    if planned['action'] == 'EXPAND':
                                        hits = searches[planned['from_search']]
                                        if planned['hit_rank'] >= len(hits):
                                            stop_reason = 'absent_precommitted_hit'; break
                                        action = dict(action='EXPAND', handle=hits[planned['hit_rank']], scope=planned['scope'])
                                    visible = act(action)
                                    if planned['action'] == 'SEARCH':
                                        searches.append(list(visible['last_hits']))
                                    if planned['action'] == 'STOP':
                                        stop_reason = 'model_active_stop'; break
                                stop_reason = stop_reason or 'oneshot_program_end'
                                break
                            act(value['action'])
                            if value['action']['action'] == 'STOP':
                                stop_reason = 'model_active_stop'; break
                        stop_reason = stop_reason or 'controller_call_cap'
                    else:
                        raise DynamicFailure('unbound arm')
                except C.ControllerProtocolError as error:
                    controller_failure = str(error)
                    stop_reason = 'controller_protocol_failure_fallback'
                    emit('CONTROLLER_PATH_FAILED', stamp=_stamp(clock), task_id=tid, method=method,
                         reason=str(error), retry_calls=0, fallback='one already-budgeted terminal using validated evidence')
                except RejectedAction as error:
                    reason = str(error)
                    # A vanished source or identity failure must never be treated
                    # as a harmless language mistake with an evidence fallback.
                    if any(w in reason for w in ('illegal', 'integrity', 'source_no_longer', 'binding', 'stale')):
                        raise DynamicFailure('GE2 source/state integrity: ' + reason) from error
                    stop_reason = 'tool_refusal:' + reason
                    controller_failure = reason if method.startswith('LLM') else None
                if not episode.done:
                    act({'action': 'STOP'})
                receipt = episode.receipt()
                packet = episode.packet()
            if packet.payload()['decode'] != DECODE:
                raise DynamicFailure('GE2 changed terminal G')
            if method != DIRECT:
                receipt = dict(receipt, timing_spans=list(episode.timing_spans))
            bound_at = _stamp(clock)
            emit('TERMINAL_INPUT_BOUND', stamp=bound_at, task_id=tid, method=method,
                 payload_sha256=packet.payload_sha256, source_receipt=receipt,
                 source_receipt_sha256=object_sha256(receipt), stop_reason=stop_reason,
                 model_assessments=assessments, formal_reward=None)
            pm_end = _deadline(clock, path_deadline)
            emit('PM_FINISHED', stamp=pm_end, task_id=tid, method=method, pm_elapsed_ns=duration_ns(path_start, pm_end))
            response, request = call('terminal', task, method, packet.payload(),
                dict(renderer_id=packet.renderer_id, baseline_sha256=packet.baseline_sha256,
                     source_receipt_sha256=object_sha256(receipt)), path_deadline)
            end = _deadline(clock, deadline_ns)
            real = backend.kind == 'hf_dynamic_real'
            status = ('technical_length' if response['finish_reason'] == 'length' else
                      'generated_pending_evaluation' if real else 'cpu_fixture_transport_only')
            first = response.get('passive_output_observer', {}).get('events', {}).get('first_nonempty_decoded_text')
            row = dict(task_id=tid, method=method, status=status, real_model_output=real,
                output=response, request_id=request['request_id'], payload_sha256=packet.payload_sha256,
                source_receipt=receipt, stop_reason=stop_reason, controller_failure=controller_failure,
                fallback_executed=controller_failure is not None, system_reliability='degraded_fallback' if controller_failure else 'normal',
                path_started=path_start, pm_finished=pm_end, path_finished=end,
                pm_elapsed_ns=duration_ns(path_start, pm_end), agent_to_reply_ns=duration_ns(path_start, end),
                agent_to_worker_first_nonempty_text_ns=duration_ns(path_start, first) if first else None,
                client_first_text_ns=None, useful_text_or_audio_ns=None, cache_reused=False, formal_reward=None)
            results.append(row)
            completed.add(current)
            emit('AGENT_PATH_COMPLETED', stamp=end, task_id=tid, method=method, endpoint=row)
        status, reason = 'FINISHED', None
    except BaseException as error:
        status, reason = 'TECHNICAL_UNFINISHED', type(error).__name__ + ': ' + str(error)
        emit('GE2_JOB_STOP', stamp=_stamp(clock), current=current, reason=reason, retry_calls=0,
             completed_slots=len(results), formal_reward=None)
    end = _stamp(clock)
    return dict(protocol=PROTOCOL, status=status, reason=reason, results=results,
        physical_calls=budget.physical, calls_by_role=dict(budget.used),
        pending=[dict(s, status='technical_unfinished_or_unattempted', formal_reward=None)
                 for s in slots if (s['task_id'], s['method']) not in completed],
        started=start, finished=end, wall_ns=duration_ns(start, end),
        retry_calls=0, terminal_cache=False, formal_reward=None)
