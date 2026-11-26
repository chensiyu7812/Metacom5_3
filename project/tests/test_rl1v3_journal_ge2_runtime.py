"""New GE2 CPU transport/state tests. Fixtures are never real model outputs."""
from collections import Counter
from copy import deepcopy
import json
import pytest

from metacom_pm.rl1v3.generator.g0e import DECODE
from metacom_pm.rl1v3.io import object_sha256
from metacom_pm.rl1v3.journal.ge2_memory import GE2Episode
from metacom_pm.rl1v3.journal import ge2_controller as C
from metacom_pm.rl1v3.journal.ge2_runtime import execute, terminal_slots, CallBudget, DynamicFailure
from metacom_pm.rl1v3.journal.ge2_worker import validate_generate_request, WorkerCallBudget
from metacom_pm.rl1v3.journal.pomdp_latency import MonotonicClock


class Clock(MonotonicClock):
    def __init__(self):
        self.value=1_000_000
        super().__init__(now=self.tick,boot_id='synthetic-ge2-boot')
    def tick(self):
        self.value+=1000
        return self.value


class Packet:
    renderer_id='synthetic-renderer'
    baseline_sha256='synthetic-baseline'
    def __init__(self,text):
        self.data=dict(messages=[dict(role='system',content='fixed synthetic system'),dict(role='user',content=text)],
                       input_ids=list(text.encode()),decode=dict(DECODE))
        self.input_ids=self.data['input_ids'];self.payload_sha256=object_sha256(self.data)
    def payload(self):return deepcopy(self.data)


class Tok:
    identity='synthetic-tokenizer'
    def count(self,text):return len(text.split())
    def encode_messages(self,messages):return list(json.dumps(messages).encode())
    def make_packet(self,views=()):return Packet('Visible synthetic task\n'+'\n'.join(v.reading_text for v in views))


def tasks():
    return [dict(task_id='synthetic-'+str(i),timestamp='2020-02-01',
        turns=[dict(role='seeker',text='Find the activity report.')],query='Find the activity report.',
        view_protocol='synthetic') for i in range(2)]


class Factory:
    def __init__(self,mode=None):self.mode=mode
    def __call__(self,task,method,*,clock,emit,deadline_ns):
        records=[dict(record_id='r'+str(i),head='MS',view='raw',owner_id='synthetic',source_rank=i,
            reported_at=dict(date='2020-01-0'+str(i+1),session_rank=i),parent_session_id='s'+str(i),
            reading_text='Exact source report '+str(i),
            source_refs=[dict(turn_index=0,speaker='seeker',exact_quote='Exact source report '+str(i))]) for i in range(4)]
        e=GE2Episode(task=task,records=records,tokenizer=Tok(),legal=lambda r:r['source_rank']<4,
                     episode_nonce=object_sha256([task['task_id'],method]),clock=clock)
        if self.mode=='source_failure' and method=='FixedTop4':e.legal=lambda r:False
        return e


class Backend:
    kind='cpu_protocol_fixture_not_model'
    scope_sha256='synthetic-scope'
    def __init__(self,mode=None):self.sent=[];self.used=Counter();self.mode=mode
    def generate(self,request,seconds):
        self.sent.append(deepcopy(request));role=request['role'];tid=request['binding']['task_id']
        self.used[(tid,role)]+=1
        if self.mode=='wire_failure':raise RuntimeError('synthetic wire failure')
        if role=='terminal':text='Synthetic transport fixture; not model-generated.'
        else:
            obs=json.loads(request['payload']['messages'][1]['content'])
            state=dict(status='unassessed',information_gap='Synthetic diagnostic only')
            if role=='oneshot':
                value=dict(evidence_state=state,actions=[dict(action='SEARCH',query='novel semantic status',unread_only=True),
                    dict(action='EXPAND',scope='parent',from_search=0,hit_rank=0),dict(action='STOP')])
            else:
                n=self.used[(tid,role)]
                action=(dict(action='SEARCH',query='novel semantic status',unread_only=True) if n==1
                    else dict(action='EXPAND',scope='neighbor',handle=obs['last_hits'][0]) if n==2
                    else dict(action='STOP'))
                value=dict(evidence_state=state,action=action)
            text=json.dumps(value)
            if self.mode=='oneshot_bad_json' and role=='oneshot':text='```json\n'+text+'\n```'
            if self.mode=='tool_foreign_handle' and role=='agent':
                text=json.dumps(dict(evidence_state=state,action=dict(action='EXPAND',scope='parent',handle='ge2:'+'f'*24+':v1')))
        ids=[17,1];finish='eos'
        if self.mode=='oneshot_length' and role=='oneshot':
            ids=[17]*request['payload']['decode']['max_new_tokens'];finish='length'
        result=dict(text=text,token_ids=ids,finish_reason=finish,seconds=.01,
                    input_tokens=len(request['payload']['input_ids']),request_sha256=object_sha256(request))
        if self.mode=='hash_mismatch':result['request_sha256']='bad'
        return result


def drive(backend=None,factory=None):
    events=[];clock=Clock();backend=backend or Backend()
    result=execute(tasks=tasks(),factory=factory or Factory(),backend=backend,
        slots=terminal_slots(tasks(),set()),emit=lambda event,**kw:events.append(dict(event=event,**kw)),
        clock=clock,deadline_ns=1200*10**9)
    return result,events,backend


def test_all_normal_slots_real_tools_and_snapshot_hashes():
    result,events,backend=drive()
    assert result['status']=='FINISHED' and len(result['results'])==8 and result['pending']==[]
    assert result['calls_by_role']==dict(terminal=8,oneshot=2,agent=6)
    assert all(r['status']=='cpu_fixture_transport_only' and not r['real_model_output'] for r in result['results'])
    assert all(r['formal_reward'] is None and not r['fallback_executed'] for r in result['results'])
    controls=[r for r in backend.sent if r['role']!='terminal']
    for request in controls:
        obs=json.loads(request['payload']['messages'][1]['content'])
        assert obs['snapshot_sha256']==object_sha256({k:v for k,v in obs.items() if k!='snapshot_sha256'})
        assert obs['content_sha256']==request['binding']['content_sha256']
        assert request['payload']['decode']['no_repeat_ngram_size']==0
    agent=[r for r in controls if r['role']=='agent']
    assert agent[0]['payload']['decode']['max_new_tokens']==768
    assert agent[1]['payload']['decode']['max_new_tokens']==766
    assert agent[2]['payload']['decode']['max_new_tokens']==764
    assert any(e['event']=='CONTROLLER_ACCEPTED' for e in events)
    assert sum(r['source_receipt']['accesses']==5 for r in result['results'])==2


@pytest.mark.parametrize('mode',['oneshot_bad_json','oneshot_length','tool_foreign_handle'])
def test_controller_failure_is_local_single_budgeted_terminal_fallback(mode):
    result,events,backend=drive(Backend(mode))
    assert result['status']=='FINISHED' and len(result['results'])==8 and not result['pending']
    degraded=[r for r in result['results'] if r['fallback_executed']]
    assert len(degraded)==2 and all(r['system_reliability']=='degraded_fallback' for r in degraded)
    assert result['calls_by_role']['terminal']==8 and result['retry_calls']==0
    assert len({(r['binding']['task_id'],r['binding']['method']) for r in backend.sent if r['role']=='terminal'})==8
    assert sum(e['event']=='CONTROLLER_PATH_FAILED' for e in events)==2


@pytest.mark.parametrize('mode',['wire_failure','hash_mismatch'])
def test_transport_or_identity_failure_stops_job_no_retry(mode):
    result,events,backend=drive(Backend(mode))
    assert result['status']=='TECHNICAL_UNFINISHED' and result['physical_calls']==1
    assert len(result['pending'])==8 and result['retry_calls']==0 and len(backend.sent)==1


def test_source_failure_does_not_silently_fallback():
    result,events,backend=drive(factory=Factory('source_failure'))
    assert result['status']=='TECHNICAL_UNFINISHED' and len(result['results'])==1
    assert len(result['pending'])==7 and result['physical_calls']==1


def test_independent_worker_limits_allowlists_and_shared_output_cap():
    _,_,backend=drive()
    worker=WorkerCallBudget({t['task_id']:object_sha256(t) for t in tasks()},backend.scope_sha256,
        dict(terminal=8,oneshot=2,agent=10),terminal_slots(tasks(),set()))
    for request in backend.sent:
        worker.claim(request);worker.settle(request,[17,1])
    assert worker.roles==dict(terminal=8,oneshot=2,agent=6)
    with pytest.raises(ValueError):worker.claim(backend.sent[0])


def test_worker_rejects_rehashed_stale_observation_snapshot():
    _,_,backend=drive()
    request=deepcopy(next(r for r in backend.sent if r['role']=='agent'))
    class T:
        def apply_chat_template(self,messages,**kw):return request['payload']['input_ids']
    assert validate_generate_request(request,dict(decode=DECODE),T(),boot_id='synthetic-ge2-boot',now_ns=1,deadline_ns=100)[0]=='agent'
    obs=json.loads(request['payload']['messages'][1]['content'])
    obs['controller_budget']['calls_remaining']-=1
    request['payload']['messages']=C.messages(obs,'LLMToolAgent')
    request['binding']['observation_sha256']=object_sha256(obs)
    request['binding']['payload_sha256']=object_sha256(request['payload'])
    request['request_id']='jge2:'+object_sha256({k:v for k,v in request.items() if k!='request_id'})
    with pytest.raises(ValueError,match='snapshot'):
        validate_generate_request(request,dict(decode=DECODE),T(),boot_id='synthetic-ge2-boot',now_ns=1,deadline_ns=100)


def test_static_grammar_does_not_encode_gold_or_source_identity():
    contract=C.protocol_contract()
    assert contract['constraint_scope']=='syntax only; no task, gold, candidate or correct-action mask'
    assert C.parse(json.dumps(dict(evidence_state=dict(status='unconfirmable',information_gap='new semantic paraphrase'),
        action=dict(action='SEARCH',query='semantic status never-seen-before',unread_only=True))),'LLMToolAgent')
    with pytest.raises(C.ControllerProtocolError,match='forward search'):
        C.parse(json.dumps(dict(evidence_state=dict(status='unassessed',information_gap=''),actions=[
            dict(action='EXPAND',scope='parent',from_search=0,hit_rank=0)])),'LLMOneShot')
    with pytest.raises(C.ControllerProtocolError,match='five acquisition'):
        C.parse(json.dumps(dict(evidence_state=dict(status='unassessed',information_gap=''),actions=[
            dict(action='SEARCH',query='query',unread_only=True)]*6)),'LLMOneShot')
