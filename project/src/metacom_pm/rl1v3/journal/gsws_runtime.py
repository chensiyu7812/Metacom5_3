"""Fixed evidence schedule -> actual interpreter -> identical PM/G shared view.

Phase 1 is a semantic mechanism experiment, not an adaptive policy experiment.
No evaluator, gold, Direct recipe, or future task is accepted by this module.
"""
from ..generator.g0e import DECODE
from ..io import object_sha256
from . import gsws as S
from .ge2_memory import RejectedAction
from .ge2_runtime import validate_response
from .pomdp_dynamic_runtime import _deadline, DynamicFailure
from .pomdp_latency import duration_ns

ROLE_MAP={'oneshot':'A1_READING_NOTES','agent':'A2_GSWS'}  # wire role names only; neither is a controller here


def slots(tasks):
    return [dict(task_id=t['task_id'],stage=s,arm=a,method=f'{a}:S{s}',
                 slot_id='gsws:'+object_sha256([S.PROTOCOL,t['task_id'],s,a]))
            for t in tasks for s in (0,1) for a in S.ARMS]


def interpreter_decode(base, arm):
    if arm not in S.ARMS[1:]:raise ValueError('interpreter identity')
    return dict(base,max_new_tokens=S.INTERPRETER_TOKENS,no_repeat_ngram_size=0)


def acquire(episode, task, stage):
    """Identical original-query BM25 Top4/parent schedule for all arms; no gold."""
    if stage==0:return episode.receipt()
    if stage!=1:raise ValueError('stage')
    try:
        observed=episode.step(dict(action='SEARCH',query=task['query'],unread_only=True),
                              expected_content_hash=episode.content_hash())
        handles=list(observed['last_hits'])
        for handle in handles:
            episode.step(dict(action='EXPAND',handle=handle,scope='parent'),
                         expected_content_hash=episode.content_hash())
    except RejectedAction:
        pass  # keep genuine source-capacity/time rejection and its actual partial evidence
    return episode.receipt()


def payload(episode, messages, decode):
    ids=list(episode.tokenizer.encode_messages(messages))
    if len(ids)+decode['max_new_tokens']>16384:raise DynamicFailure('GSWS native context capacity')
    return dict(messages=messages,input_ids=ids,decode=decode)


def execute(*,tasks,factory,backend,slots,emit,clock,deadline_ns,guard=lambda:None):
    from .gsws_worker import WorkerCallBudget
    budget=WorkerCallBudget({t['task_id']:object_sha256(t) for t in tasks},backend.scope_sha256,
                           {'terminal':12,'oneshot':4,'agent':4},slots)
    completed=[];states={}; prior_cost={}; evidence_by_state={}
    def call(role,task,stage,arm,p,observation,extra):
        guard_start=_deadline(clock,deadline_ns);guard();start=_deadline(clock,deadline_ns)
        emit('EXPERIMENT_GUARD',elapsed_ns=duration_ns(guard_start,start),task_id=task['task_id'],stage=stage,arm=arm)
        binding=dict(task_id=task['task_id'],task_sha256=object_sha256(task),stage=stage,arm=arm,
            method=f'{arm}:S{stage}',scope_sha256=backend.scope_sha256,boot_id=start['boot_id'],
            deadline_ns=deadline_ns,payload_sha256=object_sha256(p),
            observation_sha256=object_sha256(observation),observation=observation,content_sha256=observation['content_sha256'],**extra)
        request=dict(role=role,payload=p,binding=binding)
        request['request_id']='jgsws:'+object_sha256(request)
        budget.claim(request);emit('MODEL_CALL_START',request=request,stamp=start,ordinal=budget.total)
        response=backend.generate(request,min(300,(deadline_ns-clock.now_ns())/1e9))
        end=_deadline(clock,deadline_ns)
        emit('MODEL_CALL_RETURNED',request_id=request['request_id'],output=response,stamp=end,
             validation_pending=True)
        validate_response(response,request,factory=factory,backend=backend,start=start,end=end,ordinal=budget.total)
        budget.settle(request,response['token_ids'])
        emit('MODEL_CALL_FINISHED',request_id=request['request_id'],output=response,stamp=end)
        return response,request,duration_ns(start,end)
    for task in tasks:
        for stage in (0,1):
            for arm in S.ARMS:
                entry=_deadline(clock,deadline_ns);tid=task['task_id'];method=f'{arm}:S{stage}'
                emit('AGENT_ENTER',stamp=entry,task_id=tid,stage=stage,arm=arm)
                episode=factory(task,method,clock=clock,emit=emit,deadline_ns=deadline_ns)
                receipt=acquire(episode,task,stage)
                prior=states.get((tid,arm));obs=S.project(task,episode,stage,prior)
                # Source equality is checked on coordinates/text, not nonce/time dependent hashes.
                evidence_sha=object_sha256([{k:v for k,v in e.items() if k!='source_handle'} for e in obs['evidence']])
                key=(tid,stage)
                if key in evidence_by_state and evidence_by_state[key]!=evidence_sha:
                    raise DynamicFailure('unequal actual evidence across arms; stop comparison')
                evidence_by_state[key]=evidence_sha
                state=None;interpretation_ns=0;failure=None;interp=None
                raw=episode.packet().payload()['messages']
                if arm!='A0_RAW':
                    role=next(k for k,v in ROLE_MAP.items() if v==arm)
                    ip=payload(episode,S.interpreter_messages(obs,arm),interpreter_decode(DECODE,arm))
                    interp,_,interpretation_ns=call(role,task,stage,arm,ip,obs,dict())
                    try:
                        if interp['finish_reason']!='eos':raise ValueError('interpreter length termination')
                        state=S.accept_interpretation(interp['text'],arm,obs,model_output_sha256=object_sha256(interp),
                                                      fixture=backend.kind!='hf_dynamic_real')
                    except ValueError as error:
                        failure=str(error)  # allocated terminal falls back to RAW; no repair or retry
                    if state is not None:states[(tid,arm)]=state
                    else:states.pop((tid,arm),None)
                pm_view=S.shared_view(obs,state);g_view=S.shared_view(obs,state)
                if pm_view!=g_view:raise DynamicFailure('shared state mismatch')
                emit('SEMANTIC_STATE',task_id=tid,stage=stage,arm=arm,observation=obs,state=state,
                     pm_view=pm_view,g_view=g_view,source_receipt=receipt,interpreter_failure=failure,
                     prior_interpreter_parent_ns=prior_cost.get((tid,arm),0))
                p=payload(episode,S.final_messages(raw,task,state),DECODE)
                pm_end=_deadline(clock,deadline_ns)
                reply,request,terminal_ns=call('terminal',task,stage,arm,p,obs,
                    dict(raw_messages=raw,task=task,state=state))
                end=_deadline(clock,deadline_ns)
                item=dict(task_id=tid,stage=stage,arm=arm,request_id=request['request_id'],output=reply,
                    agent_enter=entry,pm_end=pm_end,agent_finished=end,local_agent_ns=duration_ns(entry,end),
                    pm_ns=duration_ns(entry,pm_end),interpreter_parent_ns=interpretation_ns,
                    previous_interpreter_parent_ns=prior_cost.get((tid,arm),0),terminal_parent_ns=terminal_ns,
                    prior_counterfactual_terminal_in_online_cost=False,interpreter_failure=failure,
                    terminal_technical_complete=reply['finish_reason']=='eos',source_receipt=receipt,
                    source_evidence_sha256=evidence_sha,source_timing_spans=episode.timing_spans,
                    model_load_in_online_latency=False,formal_reward=None)
                prior_cost[(tid,arm)]=interpretation_ns
                completed.append(item);emit('ENDPOINT',**item)
    return dict(status='FINISHED',actual_model_calls=budget.total if backend.kind=='hf_dynamic_real' else 0,
                backend_calls=budget.total,actual_terminal_slots=len(completed) if backend.kind=='hf_dynamic_real' else 0,
                fixture_terminal_slots=len(completed) if backend.kind!='hf_dynamic_real' else 0,
                role_calls=dict(budget.roles),endpoints=completed,formal_reward=None)
