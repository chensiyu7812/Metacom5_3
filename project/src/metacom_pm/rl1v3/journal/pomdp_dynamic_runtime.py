"""Live bounded controller -> actual tool -> Generator runtime.

No model imports, authorization, reward computation or environment mutation at
import. Historical prototype/renderer/worker remain unchanged. The supervisor
owns approval, one model load, device/storage guards and process termination.
"""
from __future__ import annotations
from collections import Counter
from pathlib import Path
import json

from .. import contracts as K
from ..compile import asof as A
from ..generator import limited_run as L
from ..generator.g0e import DECODE
from ..io import canonical_json,decode_contract,file_sha256,object_sha256
from . import pomdp_memory as P,renderer
from .pomdp_memory_prepare import tool_messages
from .pomdp_memory_proposal import ONESHOT_SYSTEM
from .joint_task_port import TaskTokenizer
from .memory_port import SnapshotPrefixPort
from .runtime_binding import binding_for,plain

PROTOCOL='pmrl1-j-pomdp-dynamic-runtime-v1'
ARMS=('STOP','FixedTop4Macro','LLMOneShot','LLMToolAgent','SequentialRule','SequentialNoText')
ROLE_CAPS={'terminal':12,'oneshot':2,'agent':8}
ROLE_OF={'LLMOneShot':'oneshot','LLMToolAgent':'agent'}


class DynamicFailure(RuntimeError):pass


def _stamp(clock):
    stamp=clock.stamp()
    if stamp.get('clock')!='CLOCK_MONOTONIC' or not stamp.get('boot_id') or type(stamp.get('monotonic_ns')) is not int:
        raise DynamicFailure('invalid monotonic clock identity')
    return stamp


def _deadline(clock,deadline_ns):
    stamp=_stamp(clock)
    if stamp['monotonic_ns']>=deadline_ns:raise DynamicFailure('global wall deadline')
    return stamp


def _measure(clock,spans,category,operation):
    start=_stamp(clock);ok=False
    try:
        value=operation();ok=True;return value
    finally:
        end=_stamp(clock)
        spans.append(dict(category=category,started=start,finished=end,
            elapsed_ns=end['monotonic_ns']-start['monotonic_ns'],ok=ok,
            aggregation='inclusive nested interval; do not sum overlapping components'))


class TimedTaskTokenizer(TaskTokenizer):
    def __init__(self,original,clock,spans):
        super().__init__(original.native,original.turns,original.baseline_sha256,original.renderer_sha256)
        self.clock,self.spans=clock,spans
    def count(self,text):
        return _measure(self.clock,self.spans,'token_count',lambda:super(TimedTaskTokenizer,self).count(text))
    def encode_messages(self,messages):
        return _measure(self.clock,self.spans,'native_chat_tokenization',lambda:super(TimedTaskTokenizer,self).encode_messages(messages))
    def make_packet(self,readings=()):
        return _measure(self.clock,self.spans,'renderer_including_tokenization',lambda:super(TimedTaskTokenizer,self).make_packet(readings))


class LiveEpisode(P.SearchExpandEpisode):
    """Same tool semantics, with independent monotonic event measurement."""
    def __init__(self,*args,emit,clock,deadline_ns,method,timing_spans=None,**kwargs):
        self.emit,self.clock,self.deadline_ns,self.method=emit,clock,deadline_ns,method
        self.timing_spans=[] if timing_spans is None else timing_spans
        super().__init__(*args,**kwargs)

    def _rank(self,query):
        return _measure(self.clock,self.timing_spans,'retrieval_including_legality',lambda:super(LiveEpisode,self)._rank(query))

    def _span(self,record,query):
        return _measure(self.clock,self.timing_spans,'raw_span_selection',lambda:super(LiveEpisode,self)._span(record,query))

    def receipt(self):
        return dict(super().receipt(),timing_spans=list(self.timing_spans),
            timing_scope='new monotonic intervals are online measurements; historical trace elapsed_seconds is not used for latency aggregation')

    def step(self,action,*,no_text=False):
        started=_deadline(self.clock,self.deadline_ns)
        timing_cursor=len(self.timing_spans)
        before=self.state_hash()
        self.emit('TOOL_START',task_id=self.task['task_id'],method=self.method,
            stamp=started,action=dict(action),state_sha256=before,
            observation_sha256=object_sha256(self.observe(no_text=no_text)))
        try:
            result=super().step(action,no_text=no_text)
        except BaseException as error:
            ended=_stamp(self.clock)
            self.emit('TOOL_REJECTED',task_id=self.task['task_id'],method=self.method,
                stamp=ended,action=dict(action),reason=str(error),before_state_sha256=before,
                after_state_sha256=self.state_hash(),elapsed_ns=ended['monotonic_ns']-started['monotonic_ns'],
                private_failed_attempts=self.failed_attempts,timing_spans=self.timing_spans[timing_cursor:])
            raise
        ended=_deadline(self.clock,self.deadline_ns)
        self.emit('TOOL_RETURNED',task_id=self.task['task_id'],method=self.method,
            stamp=ended,action=dict(action),before_state_sha256=before,after_state_sha256=self.state_hash(),
            elapsed_ns=ended['monotonic_ns']-started['monotonic_ns'],observation=result,
            observation_sha256=object_sha256(result),private_transition=self.trace[-1],
            timing_spans=self.timing_spans[timing_cursor:])
        return result


class LiveEpisodeFactory:
    """Prepare source-only ledgers once, then validate/re-read per real path.

    Optional old pools are a consistency assertion, never cached G payloads or
    retrieval results. Actual SEARCH/EXPAND always run again against this bank.
    """
    def __init__(self,*,registry,tokenizer,baseline_sha256,envelopes,ledger_root,frozen_pools_path=None):
        self.registry,self.tokenizer,self.baseline_sha256=registry,tokenizer,baseline_sha256
        self.envelopes=envelopes;self.ledger_root=Path(ledger_root);self.prepared={}
        self.frozen_pools={} if frozen_pools_path is None else {
            r['task_id']:r for r in (json.loads(s) for s in Path(frozen_pools_path).read_text().splitlines())}

    def prepare(self,tasks):
        for task in tasks:
            if task['task_id'] in self.prepared:raise DynamicFailure('duplicate prepare')
            envelope=self.envelopes[task['task_id']]
            if task!=envelope['visible_task'] or object_sha256(task)!=envelope['visible_task_sha256']:
                raise DynamicFailure('visible task/envelope mismatch')
            prefix=decode_contract(K.PrefixSpec,canonical_json(envelope['actual_prefix']))
            if prefix.runtime_sha256!=envelope['asof_runtime_sha256']:raise DynamicFailure('asof identity')
            self.registry.context(prefix)
            entries=sorted((e for e in self.registry.entries if e.source.owner_id==prefix.owner_id
                and self.registry.reason(e.source_id,prefix) is None),key=lambda e:e.source.chronological_rank)
            writer=P.PROTOCOL+':legal-raw'
            ledger=A.Ledger(self.ledger_root/task['task_id'].replace(':','-'))
            for entry in entries:
                ledger.append(A.record_from_source(entry,kind='MS_RAW',writer=writer,subject='session'),self.registry)
            snapshot=A.materialize(self.registry,prefix,ledger,writer=writer)
            tok=TaskTokenizer(self.tokenizer,task['turns'],self.baseline_sha256,file_sha256(renderer.__file__))
            port=SnapshotPrefixPort(self.registry,prefix,snapshot,tok,g_id=self.baseline_sha256,
                decode_id='frozen-G0e',step2_id=P.PROTOCOL,output_reserve_tokens=320)
            binding=binding_for(self.registry,prefix,snapshot,port)
            records=[plain(r) for r in port.bank.candidates('MS',prefix)]
            old=self.frozen_pools.get(task['task_id'])
            if old and (records!=old['records'] or binding.sha256!=old['source_port_binding_sha256']):
                raise DynamicFailure('live source pool differs from frozen prototype')
            self.prepared[task['task_id']]=(task,prefix,snapshot,tok,port,binding,records)
        return dict(tasks=len(tasks),source_counts={t['task_id']:len(self.prepared[t['task_id']][-1]) for t in tasks},
            generator_loaded=False,source_only=True)

    def __call__(self,task,method,*,emit,clock,deadline_ns):
        _deadline(clock,deadline_ns)
        spans=[]
        bound,prefix,snapshot,tok,port,binding,records=self.prepared[task['task_id']]
        if task!=bound:raise DynamicFailure('task changed after preparation')
        current=_measure(clock,spans,'source_binding_legality',lambda:binding_for(self.registry,prefix,snapshot,port))
        if current!=binding:raise DynamicFailure('source binding changed')
        ids={r['record_id'] for r in records}
        def legal(record):
            def check():
                entry=self.registry.entry(record['owner_id'],record['parent_session_id'])
                return (record['record_id'] in ids and record['owner_id']==prefix.owner_id
                    and record['source_rank']<prefix.cutoff_rank and self.registry.reason(entry.source_id,prefix) is None)
            return _measure(clock,spans,'source_legality_check',check)
        timed=TimedTaskTokenizer(tok,clock,spans)
        return LiveEpisode(task=task,records=records,tokenizer=timed,legal=legal,
            episode_nonce=object_sha256([task['task_id'],method,P.PROTOCOL]),limits=P.Limits(),
            emit=emit,clock=clock,deadline_ns=deadline_ns,method=method,timing_spans=spans)


def _top4(episode,emit,clock,deadline_ns):
    """Same frozen Top4 macro; five operations remain explicit, no snippet reads."""
    started=_deadline(clock,deadline_ns)
    emit('MACRO_SEARCH_START',task_id=episode.task['task_id'],method='FixedTop4Macro',stamp=started,
        query=episode.task['query'],query_sha256=object_sha256(episode.task['query']))
    records=list(episode.records.values())
    if any(not episode.legal(r) for r in records):raise DynamicFailure('illegal macro pool')
    ranked,_=_measure(clock,episode.timing_spans,'macro_retrieval',lambda:P.T.lexical(records,episode.task['query']))
    ended=_deadline(clock,deadline_ns)
    emit('MACRO_SEARCH_RETURNED',task_id=episode.task['task_id'],method='FixedTop4Macro',stamp=ended,
        elapsed_ns=ended['monotonic_ns']-started['monotonic_ns'],private_ranked_ids=[r['record_id'] for r in ranked])
    selected=[];charged=0;items={}
    for record in ranked[:4]:
        start=_deadline(clock,deadline_ns)
        if not episode.legal(record):raise DynamicFailure('illegal macro parent')
        text='Complete parent session; reported '+record['reported_at']['date']+':\n'+record['reading_text']
        count=episode.tokenizer.count(text)
        if charged+count>4096:
            emit('MACRO_BUDGET_STOP',task_id=episode.task['task_id'],method='FixedTop4Macro',stamp=_stamp(clock),
                attempted_record_id=record['record_id'],candidate_tokens=count,charged_tokens=charged)
            break
        key=object_sha256([record['record_id'],'complete_parent'])
        items[key]=dict(text=text,reported_at=record['reported_at'],record_id=record['record_id'],scope='MS-RAW-complete-parent',spans=record['source_refs'])
        selected.append(record['record_id']);charged+=count
        end=_deadline(clock,deadline_ns)
        emit('MACRO_PARENT_RETURNED',task_id=episode.task['task_id'],method='FixedTop4Macro',stamp=end,
            elapsed_ns=end['monotonic_ns']-start['monotonic_ns'],delivered_tokens=count,private_delivered=items[key])
    packet=episode.tokenizer.make_packet(episode._views(items))
    if len(packet.input_ids)+320>16384:raise DynamicFailure('macro capacity')
    receipt=dict(protocol='pmrl1-j-pomdp-static-top4-pressure-v1',task_id=episode.task['task_id'],
        selected_record_ids=selected,delivery_tokens=charged,retrieval_calls=1,whole_parent_reads=len(selected),
        primitive_operations=1+len(selected),scope='different macro operator; no SEARCH snippets',reward=None,
        timing_spans=list(episode.timing_spans))
    return packet,receipt


def _control_payload(episode,method,observation):
    from .pomdp_controller_protocol import controller_decode
    messages=tool_messages(observation)
    if method=='LLMOneShot':messages[0]['content']=ONESHOT_SYSTEM
    ids=list(episode.tokenizer.encode_messages(messages));decode=controller_decode(dict(DECODE),method)
    if len(ids)+decode['max_new_tokens']>16384:raise DynamicFailure('controller native context capacity')
    return dict(messages=messages,input_ids=ids,decode=decode)


class CallBudget:
    def __init__(self):self.used=Counter();self.task_used=Counter();self.outputs=Counter();self.physical=0
    def claim(self,role,task_id):
        if role not in ROLE_CAPS or self.physical>=22 or self.used[role]>=ROLE_CAPS[role]:raise DynamicFailure('physical/role call budget')
        cap={'terminal':6,'oneshot':1,'agent':4}[role]
        if self.task_used[(task_id,role)]>=cap:raise DynamicFailure('per-task role budget')
        self.physical+=1;self.used[role]+=1;self.task_used[(task_id,role)]+=1
        return self.physical
    def settle(self,role,task_id,result):
        self.outputs[(task_id,role)]+=len(result['token_ids'])
        if role!='terminal' and self.outputs[(task_id,role)]>768:raise DynamicFailure('controller total output budget')


def execute_source_pair(*,tasks,factory,backend,emit,clock,deadline_ns,guard=lambda:None,terminal_cache=None):
    """Execute one admitted two-goal job, without load/close or implicit retries.

    Cache is disabled for online timing. Every terminal is physically generated.
    Exceptions stop the entire job; uncompleted endpoints retain technical state.
    """
    if terminal_cache is not None:raise DynamicFailure('cache disabled for latency measurement')
    if len(tasks)!=2 or len({t['task_id'] for t in tasks})!=2:raise DynamicFailure('one two-goal source pair required')
    budget=CallBudget();results=[];completed=set();current=None
    start=_deadline(clock,deadline_ns);boot=start['boot_id']
    def call(role,task,method,payload,binding):
        guard_start=_deadline(clock,deadline_ns)
        emit('EXPERIMENT_GUARD_START',stamp=guard_start,task_id=task['task_id'],method=method,role=role)
        try:guard()
        except BaseException as error:
            end=_stamp(clock)
            emit('EXPERIMENT_GUARD_FAILED',stamp=end,task_id=task['task_id'],method=method,role=role,
                elapsed_ns=end['monotonic_ns']-guard_start['monotonic_ns'],reason=str(error))
            raise
        stamp=_deadline(clock,deadline_ns)
        emit('EXPERIMENT_GUARD_RETURNED',stamp=stamp,task_id=task['task_id'],method=method,role=role,
            elapsed_ns=stamp['monotonic_ns']-guard_start['monotonic_ns'],
            timing_scope='experimental storage/device guard including its event overhead; part of Agent wall time, not model reasoning')
        if stamp['boot_id']!=boot:raise DynamicFailure('clock boot changed')
        ordinal=budget.claim(role,task['task_id'])
        request=dict(role=role,payload=payload,binding=dict(binding,task_id=task['task_id'],method=method,
            physical_ordinal=ordinal,payload_sha256=object_sha256(payload),task_sha256=object_sha256(task),
            boot_id=boot,deadline_ns=deadline_ns,scope_sha256=backend.scope_sha256))
        request['request_id']='jdynamic:'+object_sha256(request)
        emit('MODEL_REQUEST_START',stamp=stamp,request=request,request_sha256=object_sha256(request),
            role=role,physical_ordinal=ordinal)
        try:response=backend.generate(request,min(300,(deadline_ns-stamp['monotonic_ns'])/1e9))
        except BaseException as error:
            failed=_stamp(clock)
            emit('MODEL_REQUEST_FAILED',stamp=failed,request_id=request['request_id'],role=role,
                elapsed_ns=failed['monotonic_ns']-stamp['monotonic_ns'],
                error=type(error).__name__+': '+str(error),wire_failure=getattr(backend,'last_failure',None),
                partial_generated_output=None,first_effective_output=None,retry_calls=0)
            raise
        returned=_stamp(clock)
        emit('MODEL_REQUEST_RETURNED',stamp=returned,request_id=request['request_id'],role=role,
            output=response,output_sha256=object_sha256(response))
        _deadline(clock,deadline_ns)
        if response.get('request_sha256')!=object_sha256(request):raise DynamicFailure('backend request binding mismatch')
        if backend.kind=='hf_dynamic_real':
            from .pomdp_latency import duration_ns
            for field in ('started','finished'):
                if response.get(field,{}).get('boot_id')!=boot:raise DynamicFailure('worker timing boot mismatch')
            ns=duration_ns(response['started'],response['finished'])
            if not stamp['monotonic_ns']<=response['started']['monotonic_ns']<=response['finished']['monotonic_ns']<=returned['monotonic_ns']:
                raise DynamicFailure('worker timing outside actual supervisor call')
            if abs(response['seconds']-ns/1e9)>1e-9:raise DynamicFailure('worker seconds/ns mismatch')
            observed=response['passive_output_observer']
            if observed['generated_token_count']!=len(response['token_ids']) or not observed['stream_ended']:
                raise DynamicFailure('worker observer/output mismatch')
            if response.get('client_ttft_ns') is not None:raise DynamicFailure('unmeasured client TTFT')
            if response.get('inference_ordinal')!=ordinal or response.get('first_inference_after_load')!=(ordinal==1):
                raise DynamicFailure('worker inference ordinal/cold-start mismatch')
            for event,when in observed['events'].items():
                if when is not None and (when['boot_id']!=boot or not response['started']['monotonic_ns']<=when['monotonic_ns']<=response['finished']['monotonic_ns']):
                    raise DynamicFailure('worker callback clock outside generation')
            native=factory.tokenizer.native.tokenizer
            if native.decode(response['token_ids'],skip_special_tokens=True)!=response['text']:
                raise DynamicFailure('returned text differs from native output tokens')
        finish=L.validate_result({'model_input':payload},response)
        if role!='terminal' and finish!='eos':raise DynamicFailure('technical incomplete controller generation: '+finish)
        budget.settle(role,task['task_id'],response)
        emit('MODEL_REQUEST_VALIDATED',stamp=_stamp(clock),request_id=request['request_id'],role=role,
            finish_reason=finish,output_tokens=len(response['token_ids']))
        return response,request
    terminal_lengths=0
    try:
        for task in tasks:
            for method in ARMS:
                current=(task['task_id'],method)
                path_start=_deadline(clock,deadline_ns)
                emit('AGENT_PATH_START',stamp=path_start,task_id=task['task_id'],method=method,
                    task_sha256=object_sha256(task),cache_policy='disabled_for_latency_measurement')
                episode=factory(task,method,emit=emit,clock=clock,deadline_ns=deadline_ns)
                if method=='FixedTop4Macro':packet,receipt=_top4(episode,emit,clock,deadline_ns)
                elif method in ('STOP','SequentialRule','SequentialNoText'):
                    receipt=P.run_cpu_policy(episode,method);packet=episode.packet()
                else:
                    from .pomdp_controller_protocol import validate_oneshot,validate_tool
                    if method=='LLMOneShot':
                        obs=episode.observe();payload=_control_payload(episode,method,obs)
                        response,control_request=call('oneshot',task,method,payload,dict(observation_sha256=object_sha256(obs),state_sha256=episode.state_hash()))
                        plan=validate_oneshot(response['text'],obs['query'])
                        emit('CONTROLLER_PROGRAM_VALIDATED',stamp=_stamp(clock),request_id=control_request['request_id'],
                            task_id=task['task_id'],method=method,first_effective_output_scope='complete strict program accepted after return; no streaming action parsing')
                        emit('ONESHOT_COMMITTED',stamp=_stamp(clock),task_id=task['task_id'],plan=plan,plan_sha256=object_sha256(plan))
                        searches=[]
                        for planned in plan:
                            action=planned
                            if planned['action']=='EXPAND':
                                candidates=searches[planned['from_search']]
                                if planned['hit_rank']>=len(candidates):
                                    emit('ONESHOT_ABSENT_HIT_STOP',stamp=_stamp(clock),task_id=task['task_id'],planned=planned)
                                    break
                                action=dict(action='EXPAND',handle=candidates[planned['hit_rank']])
                            try:visible=episode.step(action)
                            except P.RejectedAction as error:
                                if str(error)=='token_budget':break
                                raise
                            if planned['action']=='SEARCH':searches.append(list(visible['last_hits']))
                            if episode.done:break
                    else:
                        for _ in range(4):
                            obs=episode.observe()
                            if obs['action_mask']==['STOP']:break
                            payload=_control_payload(episode,method,obs)
                            response,control_request=call('agent',task,method,payload,dict(observation_sha256=object_sha256(obs),state_sha256=episode.state_hash()))
                            action=validate_tool(response['text'],obs)
                            emit('CONTROLLER_ACTION_VALIDATED',stamp=_stamp(clock),request_id=control_request['request_id'],
                                task_id=task['task_id'],method=method,action=action,
                                first_effective_output_scope='complete strict state-legal action accepted after return; no streaming action parsing')
                            try:episode.step(action)
                            except P.RejectedAction as error:
                                if str(error)=='token_budget':break
                                raise
                            if episode.done:break
                    if not episode.done:
                        emit('FORCED_STOP',stamp=_stamp(clock),task_id=task['task_id'],method=method,
                            reason='tool_token_budget' if episode.budget_exhausted else 'program_end_or_control_access_cap',model_selected_stop=False)
                        episode.step(dict(action='STOP'))
                    receipt=episode.receipt();packet=episode.packet()
                payload=packet.payload()
                if payload['decode']!=DECODE:raise DynamicFailure('terminal decode changed')
                emit('TERMINAL_INPUT_BOUND',stamp=_stamp(clock),task_id=task['task_id'],method=method,
                    payload_sha256=packet.payload_sha256,renderer_id=packet.renderer_id,
                    source_receipt=receipt,source_receipt_sha256=object_sha256(receipt))
                pm_end=_deadline(clock,deadline_ns)
                emit('PM_FINISHED',stamp=pm_end,task_id=task['task_id'],method=method,
                    pm_elapsed_ns=pm_end['monotonic_ns']-path_start['monotonic_ns'],
                    timing_scope='Agent start through actual terminal binding/log; includes controller/tool/render and preceding experimental guards')
                response,request=call('terminal',task,method,payload,dict(renderer_id=packet.renderer_id,
                    baseline_sha256=packet.baseline_sha256,source_receipt_sha256=object_sha256(receipt)))
                end=_deadline(clock,deadline_ns)
                incomplete=response['finish_reason']=='length';terminal_lengths+=incomplete
                real_output=backend.kind=='hf_dynamic_real'
                row=dict(task_id=task['task_id'],method=method,
                    status='technical_length' if incomplete else ('generated_pending_evaluation' if real_output else 'cpu_fixture_transport_only'),
                    backend=backend.kind,real_model_output=real_output,formal_reward=None,
                    request_id=request['request_id'],payload_sha256=packet.payload_sha256,output_sha256=object_sha256(response),
                    output=response,source_receipt=receipt,path_started=path_start,path_finished=end,
                    pm_finished=pm_end,pm_elapsed_ns=pm_end['monotonic_ns']-path_start['monotonic_ns'],
                    agent_to_reply_ns=end['monotonic_ns']-path_start['monotonic_ns'],cache_reused=False,
                    latency_scope='actual observed path; worker internal first token is not client-visible TTFT')
                results.append(row)
                if not incomplete:completed.add(current)
                emit('AGENT_PATH_INCOMPLETE' if incomplete else 'AGENT_PATH_COMPLETED',stamp=end,task_id=task['task_id'],method=method,
                    agent_to_reply_ns=row['agent_to_reply_ns'],endpoint_sha256=object_sha256(row))
                if terminal_lengths>=3:raise DynamicFailure('third terminal length stop')
        status='FINISHED';reason=None
    except BaseException as error:
        status='TECHNICAL_UNFINISHED';reason=type(error).__name__+': '+str(error)
        emit('DYNAMIC_STOP',stamp=_stamp(clock),reason=reason,current=current,no_retry=True,formal_reward=None,
            failed_attempt_effective_output=None)
    end=_stamp(clock)
    return dict(protocol=PROTOCOL,status=status,reason=reason,backend=backend.kind,
        physical_calls=budget.physical,calls_by_role={r:budget.used[r] for r in ROLE_CAPS},results=results,
        pending=[dict(task_id=t['task_id'],method=m,status='technical_unfinished_or_unattempted',formal_reward=None)
            for t in tasks for m in ARMS if (t['task_id'],m) not in completed],
        started=start,finished=end,wall_ns=end['monotonic_ns']-start['monotonic_ns'],
        cache_policy='disabled_for_latency_measurement',terminal_length_count=terminal_lengths,retry_calls=0,formal_reward=None)
