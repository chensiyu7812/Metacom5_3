"""Read-only verification and collection of the frozen dynamic HF journals.

No inference, device access, retries, repair of model output, or reward scoring.
Public exports use an explicit allowlist; private input/output text stays private.
"""
from __future__ import annotations
from collections import Counter
import json
from pathlib import Path
import re

from ..io import object_sha256, file_sha256, write_json_once, write_jsonl_once
from ..generator import limited_run as L
from . import pomdp_dynamic_run as R
from .pomdp_dynamic_worker import validate_generate_request
from .pomdp_controller_protocol import validate_oneshot, validate_tool
from .pomdp_latency import duration_ns

PROTOCOL='pmrl1-j-dynamic-results-v1'


class IntegrityError(ValueError):pass


def require(value,message):
    if not value:raise IntegrityError(message)


def read(path):return json.loads(Path(path).read_text())
def rows(path):return [json.loads(x) for x in Path(path).read_text().splitlines()]


def display_artifacts(text):
    """Literal presentation diagnostics only; never clean text or score quality."""
    return dict(leading_literal_thought_marker=bool(re.match(r'\A\s*thought(?:\r?\n|$)',text)),
        leading_markdown_fence=bool(re.match(r'\A\s*```',text)))


def commitment_key(event,current):
    # Frozen emitter records task_id but omits method on ONESHOT_COMMITTED.
    # Only the active, verified OneShot path may supply that context.
    expected=(event['task_id'],'LLMOneShot')
    require(current==expected and event.get('method','LLMOneShot')=='LLMOneShot','OneShot commitment outside active path')
    return expected


def interval(start,end,outer=None):
    value=duration_ns(start,end)
    if outer:
        duration_ns(outer[0],start);duration_ns(end,outer[1])
    return value


def journal(job):
    """Verify file bytes and sequence, including retained partial attempt logs."""
    job=Path(job)
    summary=read(job/'SUMMARY.json') if (job/'SUMMARY.json').exists() else None
    paths=sorted((p for p in job.glob('*.json') if re.match(r'^\d{3,}-[A-Z_]+\.json$',p.name)),
        key=lambda p:int(p.name.split('-')[0]))
    require(bool(paths),'missing immutable journal')
    result=[];previous=None;last=None
    for index,p in enumerate(paths):
        row=read(p)
        require(row['seq']==index and int(p.name.split('-')[0])==index,'journal sequence gap')
        require(row['previous_event_sha256']==previous,'journal byte hash chain')
        require(p.name==('%03d-%s.json'%(index,row['event'])),'journal filename/event mismatch')
        if last is not None:interval(last,row['stamp'])
        else:interval(row['stamp'],row['stamp'])
        previous=file_sha256(p);last=row['stamp']
        result.append(dict(row,journal_file_sha256=previous))
    if summary:
        require(summary['last_journal_sha256']==previous,'summary journal tail mismatch')
        require(summary.get('backend')=='hf_dynamic_real','CPU fixture/non-HF summary rejected')
        require(summary.get('formal_reward') is None,'automatic reward qualification forbidden')
        require(summary['wall_ns']==interval(summary['started'],summary['ended']),'summary wall mismatch')
        interval(summary['started'],result[0]['stamp']);interval(result[-1]['stamp'],summary['ended'])
        runtime=summary.get('runtime')
        if runtime is not None:
            require(runtime.get('backend')=='hf_dynamic_real','CPU fixture runtime rejected')
            require(runtime.get('cache_policy')=='disabled_for_latency_measurement','cache reuse forbidden')
    return result,summary


def _worker_return(request,returned,start,end,tokenizer):
    require(not returned.get('fixture') and returned.get('actual_model_called') is not False,'CPU fixture output rejected')
    require(returned.get('request_sha256')==object_sha256(request),'worker request binding')
    contract_error=None
    try:L.validate_result({'model_input':request['payload']},returned)
    except ValueError as error:contract_error=type(error).__name__+': '+str(error)
    require(tokenizer is not None,'native tokenizer required for actual returned output')
    require(tokenizer.decode(returned['token_ids'],skip_special_tokens=True)==returned['text'],'native output decode differs')
    ns=interval(returned['started'],returned['finished'],(start,end))
    require(abs(returned['seconds']-ns/1e9)<=1e-9,'worker seconds/ns mismatch')
    require(returned['role']==request['role'],'worker role binding')
    ordinal=request['binding']['physical_ordinal']
    require(returned['inference_ordinal']==ordinal and returned['first_inference_after_load']==(ordinal==1),'cold/ordinal binding')
    observed=returned['passive_output_observer']
    require(observed['generated_token_count']==len(returned['token_ids']) and observed['stream_ended'],'observer output count/end')
    require(returned.get('client_ttft_ns') is None and observed.get('client_ttft_ns') is None,'unobserved client TTFT')
    require(observed['events']['generate_start']==returned['started'],'observer generation start')
    for name,stamp in observed['events'].items():
        if stamp is not None:
            elapsed=interval(returned['started'],stamp,(returned['started'],returned['finished']))
            key=name+'_latency_ns'
            if key in observed:require(observed[key]==elapsed,'observer latency differs')
    observed_order=[observed['events'].get(k) for k in ('generate_start','prompt_callback','first_generated_token',
        'first_non_special_token','first_nonempty_decoded_text','stream_end')]
    observed_order=[s for s in observed_order if s is not None]
    for a,b in zip(observed_order,observed_order[1:]):interval(a,b)
    require(0<=observed['callback_work_ns']<=ns,'observer callback time bounds')
    for label in ('request_validation','generation_preparation'):
        measured=interval(returned[label+'_started'],returned[label+'_finished'],(start,returned['started']))
        require(measured==returned[label+'_ns'],label+' interval mismatch')
    exchange=returned['supervisor_exchange']
    require(exchange['elapsed_ns']==interval(exchange['started'],exchange['finished'],(start,end)),'parent exchange interval')
    return dict(generation_ns=ns,supervisor_call_ns=interval(start,end),
        input_tokens=len(request['payload']['input_ids']),output_tokens=len(returned['token_ids']),
        request_validation_ns=returned['request_validation_ns'],
        generation_preparation_ns=returned['generation_preparation_ns'],
        supervisor_exchange_ns=exchange['elapsed_ns'],callback_work_ns=observed['callback_work_ns'],
        first_generated_token_ns=observed.get('first_generated_token_latency_ns'),
        first_nonempty_decoded_text_ns=observed.get('first_nonempty_decoded_text_latency_ns'),
        client_ttft_ns=None,semantic_text_validity='not_machine_qualified',return_contract_error=contract_error)


def _request(request,event,plan,tasks,baseline,tokenizer):
    require(event['request_sha256']==object_sha256(request),'journal request SHA')
    b=request['binding'];role=request['role'];task_id=b['task_id']
    require(task_id in plan['task_ids'] and b['method'] in R.ARMS,'request task/arm')
    require(b['task_sha256']==object_sha256(tasks[task_id])==plan['task_sha256'][task_id],'task input SHA')
    require(b['scope_sha256']==plan['scope_sha256'],'comparison scope')
    require(b['boot_id']==event['stamp']['boot_id'],'request boot')
    require(event['role']==role and event['physical_ordinal']==b['physical_ordinal'],'request ordinal event')
    require(role=='terminal' or (role,b['method']) in (('oneshot','LLMOneShot'),('agent','LLMToolAgent')),'controller role/method')
    require(tokenizer is not None,'native tokenizer required for request verification')
    validate_generate_request(request,baseline['spec'],tokenizer,boot_id=b['boot_id'],
        now_ns=event['stamp']['monotonic_ns'],deadline_ns=b['deadline_ns'])
    return task_id,b['method']


def audit_job(plan,job,tasks,baseline,tokenizer):
    """Validate one real job; all semantic labels remain unassessed.

    `tokenizer` is the local frozen native tokenizer, not a model. Synthetic unit
    tests supply a deterministic tokenizer solely to exercise verification.
    """
    job=Path(job);events,summary=journal(job);first=events[0]
    require(first['event']=='RUN_START' and first['plan_sha256']==object_sha256(plan),'job plan/start binding')
    R.admit(plan,first['approval'])  # read-only proof of the independent approval
    require(job.name=='job-'+object_sha256(first['approval']),'approval/job directory binding')
    if summary:require(summary['plan_sha256']==object_sha256(plan),'summary plan mismatch')
    start=first['stamp'];end=summary['ended'] if summary else events[-1]['stamp'];outer=(start,end)
    paths={};calls={};roles=Counter();per_task=Counter();order=[];phase_spans=[];load=None
    latest_observation={};latest_state={};guards={};tools={};macro_starts={};initial={}
    for row in rows(plan['initial_controllers_path']):initial[(row['task_id'],row['method'])]=row
    known={(r['task_id'],r['arm']):r for r in rows(plan['known_requests_path'])}
    phase_begin={};current=None
    for event in events:
        name=event['event'];stamp=event['stamp'];interval(start,stamp,outer)
        key=(event.get('task_id'),event.get('method'))
        if name in ('MODEL_BYTES_VERIFY_START','SOURCE_STARTUP_START','LOAD_START'):phase_begin[name]=event
        elif name in ('MODEL_BYTES_VERIFIED','SOURCE_STARTUP_FINISHED','LOAD_OK'):
            opening={'MODEL_BYTES_VERIFIED':'MODEL_BYTES_VERIFY_START','SOURCE_STARTUP_FINISHED':'SOURCE_STARTUP_START','LOAD_OK':'LOAD_START'}[name]
            require(opening in phase_begin,'phase end without start')
            a=phase_begin[opening]['stamp'];phase_spans.append(dict(category=opening.lower(),started=a,finished=stamp,elapsed_ns=interval(a,stamp)))
            if name=='LOAD_OK':
                require(load is None,'multiple model loads');load=event['measurement']
                for label in ('worker_spawn','supervisor_load'):
                    require(load[label+'_ns']==interval(load[label+'_started'],load[label+'_finished'],(a,stamp)),label+' load interval')
                interval(load['started'],load['finished'],(a,stamp))
                require(load['grammar_compile_ns']==interval(load['grammar_compile_started'],load['grammar_compile_finished'],(load['started'],load['finished'])),'grammar compile interval')
                require(load['model_loads']==1 and load['warmup_calls']==0,'load/warmup count')
        elif name=='AGENT_PATH_START':
            require(load is not None,'path without real load event')
            require(key not in paths and key[0] in plan['task_ids'] and key[1] in R.ARMS,'duplicate/foreign path')
            require(event['task_sha256']==plan['task_sha256'][key[0]],'path task SHA')
            expected=[(t,m) for t in plan['task_ids'] for m in R.ARMS][len(paths)]
            require(key==expected,'fixed execution order changed')
            paths[key]=dict(start=event,events=[],tool_spans=[],guard_spans=[],calls=[],terminal_bound=None,end=None)
            current=key
        if current is not None:paths[current]['events'].append(event)
        if name=='EXPERIMENT_GUARD_START':guards[(key,event['role'])]=event
        elif name in ('EXPERIMENT_GUARD_RETURNED','EXPERIMENT_GUARD_FAILED'):
            opened=guards.pop((key,event['role']),None);require(opened is not None,'guard return without start')
            ns=interval(opened['stamp'],stamp);require(ns==event['elapsed_ns'],'guard elapsed')
            paths[key]['guard_spans'].append(dict(started=opened['stamp'],finished=stamp,elapsed_ns=ns,status=name))
        elif name=='TOOL_START':
            require(key not in tools,'nested tool start');tools[key]=event
            if key in latest_state:require(event['state_sha256']==latest_state[key],'tool prior state changed')
            if key in latest_observation:require(event['observation_sha256']==object_sha256(latest_observation[key]),'tool input observation differs')
        elif name in ('TOOL_RETURNED','TOOL_REJECTED'):
            opened=tools.pop(key,None);require(opened is not None,'tool result without start')
            require(event['action']==opened['action'] and event['before_state_sha256']==opened['state_sha256'],'tool action/state mismatch')
            ns=interval(opened['stamp'],stamp);require(ns==event['elapsed_ns'],'tool elapsed')
            latest_state[key]=event['after_state_sha256']
            if name=='TOOL_RETURNED':
                require(object_sha256(event['observation'])==event['observation_sha256'],'tool observation SHA')
                tr=event['private_transition'];require(tr['before']==event['before_state_sha256'] and tr['after']==event['after_state_sha256'] and tr['action']==event['action'],'transition mismatch')
                latest_observation[key]=event['observation']
            else:latest_observation.pop(key,None)  # a refusal can change its action mask
            paths[key]['tool_spans'].append(dict(started=opened['stamp'],finished=stamp,elapsed_ns=ns,action=event['action']['action'],status=name))
        elif name=='MACRO_SEARCH_START':macro_starts[key]=event
        elif name=='MACRO_SEARCH_RETURNED':
            require(key in macro_starts,'macro return without start');a=macro_starts.pop(key)['stamp']
            require(event['elapsed_ns']==interval(a,stamp),'macro search elapsed')
            paths[key]['tool_spans'].append(dict(started=a,finished=stamp,elapsed_ns=event['elapsed_ns'],action='MACRO_SEARCH',status=name))
        elif name=='MACRO_PARENT_RETURNED':
            require(event['elapsed_ns']>=0,'macro parent negative duration')
            a=dict(stamp,monotonic_ns=stamp['monotonic_ns']-event['elapsed_ns']);interval(paths[key]['start']['stamp'],a)
            paths[key]['tool_spans'].append(dict(started=a,finished=stamp,elapsed_ns=event['elapsed_ns'],action='MACRO_PARENT',status=name,origin='start reconstructed from directly logged elapsed_ns, not throughput'))
        elif name=='TERMINAL_INPUT_BOUND':
            p=paths[key];require(p['terminal_bound'] is None,'duplicate terminal bind')
            receipt=event['source_receipt'];require(event['source_receipt_sha256']==object_sha256(receipt),'source receipt SHA')
            if 'content_payload_sha256' in receipt:require(receipt['content_payload_sha256']==event['payload_sha256'],'canonical content binding')
            if 'trace' in receipt:require(object_sha256(receipt['trace'])==receipt['trajectory_sha256'],'trajectory SHA')
            for span in receipt.get('timing_spans',[]):require(span['elapsed_ns']==interval(span['started'],span['finished'],(p['start']['stamp'],stamp)),'nested component interval')
            p['terminal_bound']=event
        elif name=='PM_FINISHED':
            p=paths[key];require(p['terminal_bound'] is not None,'PM end before terminal binding')
            require(event['pm_elapsed_ns']==interval(p['start']['stamp'],stamp),'PM wall mismatch');p['pm_end']=event
        elif name=='ONESHOT_COMMITTED':
            key=commitment_key(event,current)
            require(event['plan_sha256']==object_sha256(event['plan']),'OneShot commitment SHA')
            selected=[calls[r] for r in paths[key]['calls'] if calls[r]['request']['role']=='oneshot']
            require(len(selected)==1 and selected[0]['effective_event'] is not None,'commitment before valid program')
            c=selected[0];obs=json.loads(c['request']['payload']['messages'][1]['content'])
            require(validate_oneshot(c['return_event']['output']['text'],obs['query'])==event['plan'],'committed program differs')
        elif name=='MODEL_REQUEST_START':
            require(load is not None,'call without model load');request=event['request'];rid=request['request_id']
            pair=_request(request,event,plan,tasks,baseline,tokenizer);require(pair==current,'request outside current path')
            require(rid not in calls,'duplicate physical request');role=request['role'];b=request['binding']
            require(b['physical_ordinal']==len(calls)+1,'physical ordinal sequence')
            require(b['deadline_ns']==start['monotonic_ns']+plan['global_seconds']*10**9,'job deadline binding')
            roles[role]+=1;per_task[(pair[0],role)]+=1
            require(len(calls)<22 and roles[role]<=R.ROLE_CAPS[role] and per_task[(pair[0],role)]<={'terminal':6,'oneshot':1,'agent':4}[role],'call budget exceeded')
            if role=='terminal':
                bound=paths[pair]['terminal_bound'];require(bound is not None,'terminal request without bind')
                require(bound['payload_sha256']==b['payload_sha256'] and bound['source_receipt_sha256']==b['source_receipt_sha256'] and bound['renderer_id']==b['renderer_id'],'terminal source/render binding')
                if pair in known:require(request['payload']==known[pair]['model_input'],'frozen deterministic terminal payload changed')
            else:
                obs=json.loads(request['payload']['messages'][1]['content'])
                if pair not in latest_observation:require(request['payload']['messages']==initial[pair]['messages'],'initial controller differs')
                else:require(obs==latest_observation[pair],'controller sees a different observation')
                if pair in latest_state:require(b['state_sha256']==latest_state[pair],'controller state differs')
            calls[rid]=dict(request=request,start_event=event,return_event=None,failure_event=None,validated_event=None,effective_event=None,timing=None)
            paths[pair]['calls'].append(rid);order.append(rid)
        elif name in ('MODEL_REQUEST_RETURNED','MODEL_REQUEST_FAILED','MODEL_REQUEST_VALIDATED','CONTROLLER_ACTION_VALIDATED','CONTROLLER_PROGRAM_VALIDATED'):
            rid=event['request_id'];require(rid in calls,'return without physical start');call=calls[rid]
            interval(call['start_event']['stamp'],stamp)
            if name=='MODEL_REQUEST_RETURNED':
                require(call['return_event'] is None and call['failure_event'] is None,'duplicate return/failure')
                require(event['output_sha256']==object_sha256(event['output']),'output SHA')
                call['timing']=_worker_return(call['request'],event['output'],call['start_event']['stamp'],stamp,tokenizer)
                call['return_event']=event
            elif name=='MODEL_REQUEST_FAILED':
                require(call['return_event'] is None and call['failure_event'] is None,'duplicate failure')
                require(event['elapsed_ns']==interval(call['start_event']['stamp'],stamp),'failed elapsed mismatch')
                require(event['partial_generated_output'] is None and event['first_effective_output'] is None,'invented failed partial output')
                proof=event.get('wire_failure')
                if proof:
                    f=Path(proof['path']).resolve();require(f.is_relative_to(job.resolve()) and file_sha256(f)==proof['sha256'],'wire failure identity')
                    record=read(f);require(record['request_id']==rid and record['elapsed_ns']==interval(record['started'],record['finished'],(call['start_event']['stamp'],stamp)),'wire failure timing/binding')
                    if record.get('worker_response') is not None:
                        require(json.loads(bytes.fromhex(record['raw_response_line_hex']))==record['worker_response'],'raw failure wire differs')
                        when=record['worker_response'].get('failure_stamp')
                        if when is not None:interval(record['started'],when,(record['started'],record['finished']))
                call['failure_event']=event
            elif name=='MODEL_REQUEST_VALIDATED':
                require(call['return_event'] is not None and call['validated_event'] is None,'validation without unique return')
                require(call['timing']['return_contract_error'] is None,'invalid return was marked validated')
                output=call['return_event']['output'];require(event['finish_reason']==output['finish_reason'] and event['output_tokens']==len(output['token_ids']),'validation output mismatch')
                call['validated_event']=event
            else:
                require(call['validated_event'] is not None and call['effective_event'] is None,'effective action without validated model response')
                obs=json.loads(call['request']['payload']['messages'][1]['content']);text=call['return_event']['output']['text']
                if name=='CONTROLLER_ACTION_VALIDATED':require(validate_tool(text,obs)==event['action'],'effective action differs')
                else:validate_oneshot(text,obs['query'])
                call['effective_event']=event
        elif name in ('AGENT_PATH_COMPLETED','AGENT_PATH_INCOMPLETE'):
            require(paths[key]['end'] is None,'duplicate path completion');paths[key]['end']=event
            require(event['agent_to_reply_ns']==interval(paths[key]['start']['stamp'],stamp),'Agent wall mismatch')
    if summary and summary.get('runtime') is not None:
        runtime=summary['runtime'];require(runtime['physical_calls']==len(calls) and runtime['calls_by_role']=={r:roles[r] for r in R.ROLE_CAPS},'runtime call counts')
        bypair={(r['task_id'],r['method']):r for r in runtime['results']}
        require(len(bypair)==len(runtime['results']),'duplicate summary endpoint')
        for key,row in bypair.items():
            require(row.get('backend')=='hf_dynamic_real' and row.get('real_model_output') is True,'non-real endpoint rejected')
            require(row['cache_reused'] is False and row['formal_reward'] is None,'cache/reward endpoint violation')
            require(key in paths and paths[key]['end'] is not None,'summary endpoint lacks committed event')
            require(object_sha256(row)==paths[key]['end']['endpoint_sha256'],'endpoint summary/hash mismatch')
            rid=row['request_id'];require(rid in calls and calls[rid]['validated_event'] is not None,'endpoint missing validated call')
            require(row['output']==calls[rid]['return_event']['output'] and object_sha256(row['output'])==row['output_sha256'],'endpoint output mismatch')
            require(row['source_receipt']==paths[key]['terminal_bound']['source_receipt'],'endpoint source receipt differs')
    else:bypair={}
    endpoint_rows=[]
    for slot in R.terminal_slots(plan['task_ids']):
        key=(slot['task_id'],slot['method']);path=paths.get(key);terminal=None
        if path:
            terminal_calls=[calls[r] for r in path['calls'] if calls[r]['request']['role']=='terminal']
            require(len(terminal_calls)<=1,'terminal retry or duplication');terminal=terminal_calls[0] if terminal_calls else None
        status='unexecuted'
        if path:status='path_started_no_terminal'
        if terminal:status='terminal_started_no_return'
        if terminal and terminal['failure_event']:status='terminal_technical_failure'
        if terminal and terminal['return_event']:
            status='returned_unvalidated'
            if terminal['validated_event']:status='returned_length' if terminal['return_event']['output']['finish_reason']=='length' else 'returned_eos'
        if summary is not None and path and terminal is None:status='path_technical_failure'
        if summary is not None and terminal and terminal['return_event'] is None and terminal['failure_event'] is None:status='terminal_technical_unfinished'
        stop_events=[] if not path else [e for e in path['events'] if e['event'] in ('FORCED_STOP','DYNAMIC_STOP','TOOL_REJECTED','ONESHOT_ABSENT_HIT_STOP','MACRO_BUDGET_STOP','SUPERVISOR_STOP')]
        row=dict(slot,batch=plan['batch_number'],status=status,technical_status=status,semantic_status='not_evaluated',formal_reward=None,
            backend='hf_dynamic_real',real_model_output=bool(terminal and terminal['return_event']),
            endpoint_committed=key in bypair,cache_reused=False,request=None if not terminal else terminal['request'],
            output=None if not terminal or not terminal['return_event'] else terminal['return_event']['output'],
            source_receipt=None if not path or not path['terminal_bound'] else path['terminal_bound']['source_receipt'],
            path_started=None if not path else path['start']['stamp'],path_finished=None if not path or not path['end'] else path['end']['stamp'],
            pm_ns=None if not path or not path.get('pm_end') else path['pm_end']['pm_elapsed_ns'],
            agent_to_reply_ns=None if not path or not path['end'] else path['end']['agent_to_reply_ns'],
            observed_partial_path_ns=None if not path or path['end'] else interval(path['start']['stamp'],path['events'][-1]['stamp']),
            terminal_timing=None if not terminal else terminal['timing'],stop_events=stop_events,
            tool_spans=[] if not path else path['tool_spans'],guard_spans=[] if not path else path['guard_spans'])
        row.update(request_id=None if not terminal else terminal['request']['request_id'],
            request_sha256=None if not terminal else object_sha256(terminal['request']),
            payload_sha256=None if not terminal else terminal['request']['binding']['payload_sha256'],
            output_sha256=None if row['output'] is None else object_sha256(row['output']),
            evalspec_sha256=plan['files_sha256'][plan['review_path']],
            model_input=None if not terminal else terminal['request']['payload'],
            logging_wall_ns=None,logging_scope='not independently instrumented; do not identify residual time as logging')
        row['display_artifacts']=None if row['output'] is None else display_artifacts(row['output']['text'])
        controls=[] if not path else [calls[r] for r in path['calls'] if calls[r]['request']['role']!='terminal']
        row['controller_starts']=len(controls)
        row['controller_generation_ns_observed']=(sum(c['timing']['generation_ns'] for c in controls if c['timing'] is not None)
            if any(c['timing'] is not None for c in controls) else None)
        row['controller_output_tokens_returned']=(sum(len(c['return_event']['output']['token_ids']) for c in controls if c['return_event'])
            if any(c['return_event'] for c in controls) else None)
        endpoint_rows.append(row)
    call_rows=[]
    for rid in order:
        c=calls[rid];req=c['request'];ret=c['return_event'];failure=c['failure_event']
        call_rows.append(dict(request_id=rid,batch=plan['batch_number'],task_id=req['binding']['task_id'],method=req['binding']['method'],role=req['role'],
            status='failed' if failure else 'returned_validated' if c['validated_event'] else 'returned_unvalidated' if ret else 'started_no_return',
            request=req,output=None if not ret else ret['output'],started=c['start_event']['stamp'],returned=None if not ret else ret['stamp'],
            failure=failure,timing=c['timing'],effective_output_stamp=None if not c['effective_event'] else c['effective_event']['stamp'],
            effective_output_latency_ns=None if not c['effective_event'] else interval(c['start_event']['stamp'],c['effective_event']['stamp']),
            semantic_status='not_evaluated',formal_reward=None))
        call_rows[-1]['controller_protocol_status']=('not_applicable' if req['role']=='terminal' else
            'accepted' if c['effective_event'] else 'not_accepted' if summary else 'not_observed_or_pending')
    timing=dict(batch=plan['batch_number'],job_path=str(job),summary_present=summary is not None,
        job_status=None if summary is None else summary['status'],started=start,ended=None if summary is None else summary['ended'],
        job_wall_ns=None if summary is None else summary['wall_ns'],observed_journal_ns=interval(start,events[-1]['stamp']),
        model_load=load,phase_spans=phase_spans,supervisor_stops=[e for e in events if e['event']=='SUPERVISOR_STOP'],
        dynamic_stops=[e for e in events if e['event']=='DYNAMIC_STOP'],physical_starts=len(calls),calls_by_role={r:roles[r] for r in R.ROLE_CAPS},
        all_endpoint_slots=12,committed_endpoints=len(bypair),formal_reward=None,
        interval_rule='nested intervals are inclusive and must not be summed across levels; client TTFT unobserved')
    timing.update(logging_wall_ns=None,logging_scope='not independently measured; included in surrounding wall intervals')
    return dict(endpoints=endpoint_rows,calls=call_rows,timing=timing,
        events=[dict(e,batch=plan['batch_number'],job_path=str(job)) for e in events],summary=summary)


def collect(*,catalog_path,runs_root,out):
    """Collect zero to four completed/partial jobs without touching their files."""
    catalog_path=Path(catalog_path);catalog=read(catalog_path);runs_root=Path(runs_root);out=Path(out)
    require(not out.exists(),'new collection directory required')
    require(catalog['protocol']==R.PROTOCOL and len(catalog['batches'])==4,'fixed dynamic catalog')
    endpoints=[];calls=[];events=[];timings=[];inputs={str(catalog_path):file_sha256(catalog_path)};tokenizers={};labels={}
    for batch in catalog['batches']:
        plan_path=Path(batch['plan_path']);plan=read(plan_path)
        require(file_sha256(plan_path)==batch['plan_file_sha256'] and object_sha256(plan)==batch['plan_object_sha256'],'catalog plan SHA')
        require(plan['catalog_path']==str(catalog_path),'catalog path mismatch')
        require(plan['scope_sha256']==catalog['scope_sha256'],'catalog comparison scope')
        for key in ('task_manifest_path','initial_controllers_path','known_requests_path','baseline_path','review_path','source_config_path'):
            require(file_sha256(plan[key])==plan['files_sha256'][plan[key]],'collector bound input changed')
            inputs[plan[key]]=file_sha256(plan[key])
        inputs[str(plan_path)]=file_sha256(plan_path)
        for tid in plan['task_ids']:
            if tid not in labels:labels[tid]='T%02d'%(len(labels)+1)
        base=runs_root/('DR%d_run1'%batch['batch']);jobs=sorted(base.glob('job-*')) if base.exists() else []
        require(len(jobs)<=1,'multiple jobs/retry candidates')
        if not jobs:
            endpoints.extend(dict(slot,batch=batch['batch'],status='unexecuted',technical_status='unexecuted',semantic_status='not_evaluated',formal_reward=None,
                backend=None,real_model_output=False,endpoint_committed=False,request=None,output=None,source_receipt=None,
                agent_to_reply_ns=None,pm_ns=None,terminal_timing=None,stop_events=[],tool_spans=[],guard_spans=[]) for slot in R.terminal_slots(plan['task_ids']))
            timings.append(dict(batch=batch['batch'],job_status='unexecuted',job_wall_ns=None,model_load=None,physical_starts=0,calls_by_role={r:0 for r in R.ROLE_CAPS}))
            continue
        tasks={r['task_id']:r for r in rows(plan['task_manifest_path'])};baseline=read(plan['baseline_path'])
        # NativeTokenizer loads only local tokenizer assets; no weights or device.
        cache=(plan['model_path'],plan['source_config_path'])
        if cache not in tokenizers:
            from ..retrieve.native_tokens import NativeTokenizer
            source=read(plan['source_config_path'])
            require(file_sha256(source['asset_manifest_path'])==plan['files_sha256'][source['asset_manifest_path']],'native tokenizer asset binding')
            tokenizers[cache]=NativeTokenizer(plan['model_path'],source['asset_manifest_path']).tokenizer
        result=audit_job(plan,jobs[0],tasks,baseline,tokenizers[cache])
        endpoints.extend(result['endpoints']);calls.extend(result['calls']);events.extend(result['events']);timings.append(result['timing'])
        for e in result['events']:
            p=jobs[0]/('%03d-%s.json'%(e['seq'],e['event']));inputs[str(p)]=e['journal_file_sha256']
            if e['event']=='MODEL_REQUEST_FAILED' and e.get('wire_failure'):
                inputs[e['wire_failure']['path']]=e['wire_failure']['sha256']
        if result['summary'] is not None:inputs[str(jobs[0]/'SUMMARY.json')]=file_sha256(jobs[0]/'SUMMARY.json')
    require(len(endpoints)==48 and len({r['slot_id'] for r in endpoints})==48,'all 48 terminal slots')
    public_rows=[];public_calls=[];public_jobs=[]
    for row in endpoints:
        timing=row['terminal_timing'] or {}
        public_rows.append(dict(task=labels[row['task_id']],source_group='G%02d'%row['batch'],method=row['method'],
            status=row['status'],endpoint_committed=row['endpoint_committed'],semantic_status='not_evaluated',formal_reward=None,
            real_model_output=row['real_model_output'],input_tokens=timing.get('input_tokens'),output_tokens=timing.get('output_tokens'),
            agent_to_reply_ns=row.get('agent_to_reply_ns'),pm_ns=row.get('pm_ns'),generation_ns=timing.get('generation_ns'),
            terminal_first_token_ns=timing.get('first_generated_token_ns'),terminal_first_text_ns=timing.get('first_nonempty_decoded_text_ns'),
            guard_count=len(row['guard_spans']),guard_wall_ns=sum(s['elapsed_ns'] for s in row['guard_spans']) if row['guard_spans'] else None,
            tool_event_count_including_stop=len(row['tool_spans']),client_ttft_ns=None))
        tool_counts=Counter(s['action'] for s in row['tool_spans'] if s['status']!='TOOL_REJECTED')
        receipt=row.get('source_receipt') or {}
        public_rows[-1].update(source_receipt_accesses=receipt.get('accesses'),
            search_calls=tool_counts['SEARCH'],expand_calls=tool_counts['EXPAND'],
            stop_events=tool_counts['STOP'],macro_search_calls=tool_counts['MACRO_SEARCH'],
            macro_parent_reads=tool_counts['MACRO_PARENT'],macro_primitive_operations=receipt.get('primitive_operations'),
            delivered_tokens=receipt.get('delivered_tokens',receipt.get('delivery_tokens')))
        public_rows[-1]['logging_wall_ns']=None
        public_rows[-1]['display_artifacts']=row.get('display_artifacts')
        for field in ('controller_starts','controller_generation_ns_observed','controller_output_tokens_returned'):
            public_rows[-1][field]=row.get(field)
        first_text=None if row['output'] is None else row['output']['passive_output_observer']['events'].get('first_nonempty_decoded_text')
        public_rows[-1]['agent_to_first_terminal_nonempty_text_ns']=(interval(row['path_started'],first_text)
            if first_text is not None and row.get('path_started') is not None else None)
    for row in calls:
        public_calls.append(dict(task=labels[row['task_id']],source_group='G%02d'%row['batch'],method=row['method'],role=row['role'],
            physical_ordinal=row['request']['binding']['physical_ordinal'],status=row['status'],
            controller_protocol_status=row['controller_protocol_status'],
            request_input_tokens=len(row['request']['payload']['input_ids']),
            returned_output_tokens=None if row['output'] is None else len(row['output']['token_ids']),
            timing=row['timing'],effective_output_latency_ns=row['effective_output_latency_ns'],
            failed_call_elapsed_ns=None if row['failure'] is None else row['failure']['elapsed_ns'],
            first_inference_after_load=None if row['output'] is None else row['output']['first_inference_after_load'],
            display_artifacts=None if row['output'] is None else display_artifacts(row['output']['text']),
            formal_reward=None,semantic_status='not_evaluated'))
    for row in timings:
        load=row.get('model_load')
        public_jobs.append(dict(source_group='G%02d'%row['batch'],job_status=row['job_status'],
            job_wall_ns=row['job_wall_ns'],physical_starts=row['physical_starts'],calls_by_role=row['calls_by_role'],
            phase_durations_ns={s['category']:s['elapsed_ns'] for s in row.get('phase_spans',[])},
            worker_spawn_syscall_ns=None if load is None else load['worker_spawn_ns'],
            supervisor_load_ns=None if load is None else load['supervisor_load_ns'],
            worker_load_including_tokenizer_compile_weights_transfer_ns=None if load is None else interval(load['started'],load['finished']),
            grammar_compile_ns=None if load is None else load['grammar_compile_ns'],
            logging_wall_ns=None,client_ttft_ns=None,hard_limit_ns=1200*10**9,
            job_wall_exceeds_limit=None if row['job_wall_ns'] is None else row['job_wall_ns']>1200*10**9))
    public=dict(protocol=PROTOCOL,catalog_sha256=file_sha256(catalog_path),terminal_slots=48,
        status_counts=dict(Counter(r['status'] for r in endpoints)),physical_request_starts=len(calls),
        calls_by_role=dict(Counter(r['role'] for r in calls)),call_status_counts=dict(Counter(r['status'] for r in calls)),
        actual_returned_calls=sum(r['output'] is not None for r in calls),formal_reward=None,semantic_evaluation_performed=False,
        terminal_literal_artifact_counts={k:sum(bool((r.get('display_artifacts') or {}).get(k)) for r in endpoints)
            for k in ('leading_literal_thought_marker','leading_markdown_fence')},
        generation_ns_observed=sum(r['timing']['generation_ns'] for r in calls if r['timing'] is not None) if any(r['timing'] for r in calls) else None,
        input_tokens_returned=sum(r['timing']['input_tokens'] for r in calls if r['timing'] is not None),
        output_tokens_returned=sum(r['timing']['output_tokens'] for r in calls if r['timing'] is not None),
        job_wall_ns_complete=sum(t['job_wall_ns'] for t in timings if t.get('job_wall_ns') is not None) if any(t.get('job_wall_ns') is not None for t in timings) else None,
        limitations=['Missing/failed timing is null, never an imputed zero. Returned totals exclude unknown incomplete output.',
            'No semantic qualification or reward assignment. Output format and tool use are not task success.',
            'Inclusive nested intervals overlap. Guards/logging/callback work remain within observed wall time.',
            'Fixed arm order and first-inference cold status preclude an unqualified causal latency claim.',
            'Literal thought/fence diagnostics preserve full text and do not imply task failure. First text may be a presentation marker.',
            'Worker first nonempty text is not semantic success or client delivery; client TTFT remains null.'])
    out.mkdir(parents=True)
    for name,data in [('ALL_48_ENDPOINTS_PRIVATE.jsonl',endpoints),('ALL_MODEL_CALLS_PRIVATE.jsonl',calls),('ALL_EVENTS_PRIVATE.jsonl',events),('FOUR_JOBS_TIMING_PRIVATE.jsonl',timings),('ALL_48_ENDPOINTS_PUBLIC.jsonl',public_rows),('ALL_MODEL_CALLS_PUBLIC.jsonl',public_calls),('FOUR_JOBS_TIMING_PUBLIC.jsonl',public_jobs)]:write_jsonl_once(out/name,data)
    write_json_once(out/'SUMMARY_PUBLIC.json',public)
    manifest=dict(protocol=PROTOCOL,collector_sha256=file_sha256(__file__),input_files_sha256=inputs,
        files_sha256={p.name:file_sha256(p) for p in out.iterdir() if p.is_file()},formal_reward=None)
    write_json_once(out/'COLLECTION_MANIFEST_PRIVATE.json',manifest)
    return public
