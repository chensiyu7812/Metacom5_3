"""Synthetic immutable journal tests; no model output or scientific score."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from metacom_pm.rl1v3.io import object_sha256,file_sha256
from metacom_pm.rl1v3.generator.g0e import DECODE
from metacom_pm.rl1v3.journal import pomdp_dynamic_results as C


def stamp(n):return dict(clock='CLOCK_MONOTONIC',boot_id='synthetic-boot',monotonic_ns=n*1000000,pid=123)


class Tokenizer:
    def apply_chat_template(self,messages,**kw):return list(json.dumps(messages,sort_keys=True).encode())
    def decode(self,ids,**kw):return bytes([x for x in ids if x!=1]).decode()


def synthetic(tmp_path,*,mode='complete'):
    tasks={t:dict(task_id=t,query='Synthetic fact',turns=[dict(role='seeker',text='Synthetic fact')]) for t in ('a','b')}
    baseline={'spec':{'decode':DECODE,'system_prompt':'Synthetic fixed instruction'}}
    catalog=tmp_path/'catalog.json';catalog.write_text('{}')
    initial=tmp_path/'initial.jsonl';initial.write_text('')
    known=tmp_path/'known.jsonl';known.write_text('')
    review=tmp_path/'review.json';review.write_text('{}')
    decision=tmp_path/'decision.txt';decision.write_text('synthetic CPU test approval, not a real model authorization')
    plan=dict(batch_number=1,task_ids=['a','b'],task_sha256={t:object_sha256(v) for t,v in tasks.items()},scope_sha256='synthetic-scope',
        catalog_path=str(catalog),global_seconds=1200,initial_controllers_path=str(initial),known_requests_path=str(known),
        review_path=str(review),files_sha256={str(review):file_sha256(review)})
    approval=dict(protocol=C.R.PROTOCOL,job_kind=C.R.JOB_KIND,authorized=True,plan_sha256=object_sha256(plan),
        catalog_file_sha256=file_sha256(catalog),max_calls=22,max_model_loads=1,global_seconds=1200,warmup_calls=0,retry_calls=0,
        gpu_uuid=C.L.GPU,researcher='synthetic CPU test',decision_evidence=str(decision),decision_evidence_sha256=file_sha256(decision))
    job=tmp_path/('job-'+object_sha256(approval));job.mkdir()
    event_rows=[]
    def event(name,n,**fields):event_rows.append(dict(event=name,stamp=stamp(n),**fields))
    event('RUN_START',1,plan_sha256=object_sha256(plan),approval=approval)
    event('MODEL_BYTES_VERIFY_START',2);event('MODEL_BYTES_VERIFIED',3)
    event('SOURCE_STARTUP_START',4);event('SOURCE_STARTUP_FINISHED',5)
    event('LOAD_START',6)
    load=dict(worker_spawn_started=stamp(7),worker_spawn_finished=stamp(8),worker_spawn_ns=10**6,
        supervisor_load_started=stamp(6),supervisor_load_finished=stamp(19),supervisor_load_ns=13*10**6,
        started=stamp(9),finished=stamp(18),grammar_compile_started=stamp(10),grammar_compile_finished=stamp(11),grammar_compile_ns=10**6,
        model_loads=1,warmup_calls=0)
    event('LOAD_OK',20,measurement=load)
    pair=dict(task_id='a',method='STOP')
    event('AGENT_PATH_START',30,**pair,task_sha256=plan['task_sha256']['a'])
    messages=[dict(role='system',content=baseline['spec']['system_prompt']),dict(role='user',content='Synthetic fact')]
    payload=dict(messages=messages,input_ids=Tokenizer().apply_chat_template(messages),decode=DECODE)
    receipt=dict(task_id='a',timing_spans=[])
    bound=dict(**pair,payload_sha256=object_sha256(payload),source_receipt_sha256=object_sha256(receipt),renderer_id='synthetic-renderer',source_receipt=receipt)
    event('TERMINAL_INPUT_BOUND',40,**bound)
    event('PM_FINISHED',45,**pair,pm_elapsed_ns=15*10**6)
    binding=dict(**pair,payload_sha256=object_sha256(payload),source_receipt_sha256=object_sha256(receipt),renderer_id='synthetic-renderer',
        physical_ordinal=1,task_sha256=plan['task_sha256']['a'],scope_sha256=plan['scope_sha256'],boot_id='synthetic-boot',deadline_ns=stamp(1)['monotonic_ns']+1200*10**9)
    request=dict(role='terminal',payload=payload,binding=binding);request['request_id']='jdynamic:'+object_sha256(request)
    event('MODEL_REQUEST_START',50,request=request,request_sha256=object_sha256(request),role='terminal',physical_ordinal=1)
    output=None;endpoint=None
    if mode=='failure':
        event('MODEL_REQUEST_FAILED',90,request_id=request['request_id'],role='terminal',elapsed_ns=40*10**6,error='synthetic timeout',wire_failure=None,partial_generated_output=None,first_effective_output=None,retry_calls=0)
        event('DYNAMIC_STOP',100,reason='synthetic timeout')
    elif mode!='partial':
        text='Synthetic response';ids=list(text.encode())+[1]
        obs_events=dict(generate_start=stamp(60),prompt_callback=stamp(61),first_generated_token=stamp(62),first_non_special_token=stamp(62),first_nonempty_decoded_text=stamp(63),stream_end=stamp(69))
        obs=dict(events=obs_events,generated_token_count=len(ids),stream_ended=True,callback_work_ns=1000,client_ttft_ns=None,
            **{k+'_latency_ns':v['monotonic_ns']-stamp(60)['monotonic_ns'] for k,v in obs_events.items() if k!='generate_start'})
        output=dict(text=text,token_ids=ids,finish_reason='eos',seconds=.01,input_tokens=len(payload['input_ids']),request_sha256=object_sha256(request),role='terminal',
            started=stamp(60),finished=stamp(70),inference_ordinal=1,first_inference_after_load=True,client_ttft_ns=None,passive_output_observer=obs,
            request_validation_started=stamp(52),request_validation_finished=stamp(53),request_validation_ns=10**6,
            generation_preparation_started=stamp(54),generation_preparation_finished=stamp(55),generation_preparation_ns=10**6,
            supervisor_exchange=dict(started=stamp(51),finished=stamp(80),elapsed_ns=29*10**6))
        if mode=='fixture':output.update(fixture=True,actual_model_called=False)
        if mode=='length':
            output.update(token_ids=[17]*DECODE['max_new_tokens'],text=Tokenizer().decode([17]*DECODE['max_new_tokens']),finish_reason='length')
            output['passive_output_observer']['generated_token_count']=DECODE['max_new_tokens']
        event('MODEL_REQUEST_RETURNED',90,request_id=request['request_id'],role='terminal',output=output,output_sha256=object_sha256(output))
        event('MODEL_REQUEST_VALIDATED',95,request_id=request['request_id'],role='terminal',finish_reason=output['finish_reason'],output_tokens=len(output['token_ids']))
        endpoint=dict(**pair,backend='hf_dynamic_real',real_model_output=True,cache_reused=False,formal_reward=None,
            request_id=request['request_id'],output=output,output_sha256=object_sha256(output),source_receipt=receipt)
        event('AGENT_PATH_INCOMPLETE' if mode=='length' else 'AGENT_PATH_COMPLETED',100,**pair,agent_to_reply_ns=70*10**6,endpoint_sha256=object_sha256(endpoint))
    previous=None
    for seq,row in enumerate(event_rows):
        row.update(seq=seq,previous_event_sha256=previous,utc='synthetic')
        p=job/('%03d-%s.json'%(seq,row['event']));p.write_text(json.dumps(row,sort_keys=True)+'\n');previous=file_sha256(p)
    if mode!='partial':
        summary=dict(backend='hf_dynamic_real',formal_reward=None,last_journal_sha256=previous,started=stamp(1),ended=stamp(110),wall_ns=109*10**6,
            plan_sha256=object_sha256(plan),status='FINISHED' if endpoint else 'STOPPED',runtime=dict(backend='hf_dynamic_real',cache_policy='disabled_for_latency_measurement',
                physical_calls=1,calls_by_role=dict(terminal=1,oneshot=0,agent=0),results=[] if endpoint is None else [endpoint]))
        (job/'SUMMARY.json').write_text(json.dumps(summary))
    return plan,job,tasks,baseline,Tokenizer()


def test_real_shape_all_slots_private_output_and_inclusive_timing(tmp_path):
    result=C.audit_job(*synthetic(tmp_path))
    assert len(result['endpoints'])==12 and len(result['calls'])==1
    first=result['endpoints'][0]
    assert first['status']=='returned_eos' and first['endpoint_committed'] and first['real_model_output']
    assert first['semantic_status']=='not_evaluated' and first['formal_reward'] is None
    assert first['pm_ns']==15*10**6 and first['agent_to_reply_ns']==70*10**6
    assert first['terminal_timing']['generation_ns']==10*10**6
    assert first['request_sha256']==object_sha256(first['request'])
    assert first['logging_wall_ns'] is None
    assert all(r['status']=='unexecuted' and r['agent_to_reply_ns'] is None for r in result['endpoints'][1:])


@pytest.mark.parametrize('mode,expected',[('partial','terminal_started_no_return'),('failure','terminal_technical_failure'),('length','returned_length')])
def test_partial_failure_length_not_zero_or_semantic_failure(tmp_path,mode,expected):
    result=C.audit_job(*synthetic(tmp_path,mode=mode));first=result['endpoints'][0]
    assert first['status']==expected and first['semantic_status']=='not_evaluated' and first['formal_reward'] is None
    if mode!='length':
        assert first['output'] is None and first['terminal_timing'] is None and first['agent_to_reply_ns'] is None
    if mode=='failure':assert result['calls'][0]['failure']['elapsed_ns']==40*10**6


def test_cpu_fixture_return_is_rejected_even_under_hf_label(tmp_path):
    with pytest.raises(C.IntegrityError,match='fixture'):C.audit_job(*synthetic(tmp_path,mode='fixture'))


@pytest.mark.parametrize('field,value',[('previous_event_sha256','wrong'),('seq',999)])
def test_hash_chain_or_sequence_tampering_rejected(tmp_path,field,value):
    args=synthetic(tmp_path);p=next(args[1].glob('003-*.json'));row=json.loads(p.read_text());row[field]=value;p.write_text(json.dumps(row))
    with pytest.raises(C.IntegrityError):C.audit_job(*args)


def test_same_boot_and_containment_not_cross_clock_arithmetic():
    with pytest.raises(ValueError):C.interval(stamp(1),dict(stamp(2),boot_id='different'))
    with pytest.raises(ValueError):C.interval(stamp(1),stamp(3),(stamp(1),stamp(2)))


def test_rejects_legacy_actual_source_cpu_fixture_receipt(tmp_path):
    # Real retained fixture receipt may lack a journal; rejection must be fail-closed.
    job=tmp_path/'fixture';job.mkdir()
    (job/'SUMMARY.json').write_text(json.dumps(dict(backend='cpu_protocol_fixture_not_model')))
    with pytest.raises(C.IntegrityError,match='journal'):C.journal(job)


def test_worker_native_text_and_clock_tamper_rejected(tmp_path):
    args=synthetic(tmp_path);result=C.audit_job(*args);call=result['calls'][0]
    bad=deepcopy(call['output']);bad['text']='Changed text'
    with pytest.raises(C.IntegrityError,match='decode'):
        C._worker_return(call['request'],bad,call['started'],call['returned'],Tokenizer())
    bad=deepcopy(call['output']);bad['passive_output_observer']['events']['stream_end']=stamp(200)
    with pytest.raises(ValueError):C._worker_return(call['request'],bad,call['started'],call['returned'],Tokenizer())


def test_artifacts_are_literal_diagnostics_not_cleanup_or_quality():
    original='thought\nA synthetic response.'
    assert C.display_artifacts(original)['leading_literal_thought_marker']
    assert not C.display_artifacts('I thought about it.')['leading_literal_thought_marker']
    assert C.display_artifacts('```json\n{}\n```')['leading_markdown_fence']
    assert original=='thought\nA synthetic response.'


def test_frozen_commit_event_without_method_requires_active_oneshot_context():
    event=dict(event='ONESHOT_COMMITTED',task_id='synthetic-task')
    assert C.commitment_key(event,('synthetic-task','LLMOneShot'))==('synthetic-task','LLMOneShot')
    with pytest.raises(C.IntegrityError):C.commitment_key(event,('synthetic-task','LLMToolAgent'))
    with pytest.raises(C.IntegrityError):C.commitment_key(event,('other-task','LLMOneShot'))
