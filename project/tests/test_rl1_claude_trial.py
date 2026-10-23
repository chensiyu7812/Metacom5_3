from copy import deepcopy
from io import BytesIO
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

from metacom_pm.rl1.claude_trial import Collector, Transport, nominal_nanodollars, budget_class, VERSION
from metacom_pm.rl1.claude_delivery import prepare_request
from metacom_pm.rl1.schema import digest


def prepared():
    schema=dict(type='object',properties=dict(status=dict(enum=['scored','uncertain']),
        reason=dict(type='string',minLength=1)),required=['status','reason'],additionalProperties=False)
    info=dict(id='claude-sonnet-5-5',max_tokens=128000,capabilities=dict(
        structured_outputs=dict(supported=True),thinking=dict(types=dict(adaptive=dict(supported=True))),
        effort=dict(high=dict(supported=True))))
    msgs=[dict(role='system',content=json.dumps(schema,ensure_ascii=False)),dict(role='user',content='MOCK complete source')]
    return prepare_request(msgs,schema,info),schema


def events(text='{"assessment":{"status":"scored","reason":"source"}}'):
    return [dict(type='message_start',message=dict(id='mock-msg',model='claude-sonnet-5-5',content=[],
                stop_reason=None,usage=dict(input_tokens=1000,output_tokens=1))),
        dict(type='content_block_start',index=0,content_block=dict(type='thinking',thinking='',signature='')),
        dict(type='content_block_delta',index=0,delta=dict(type='thinking_delta',thinking='not answer')),
        dict(type='content_block_delta',index=0,delta=dict(type='signature_delta',signature='opaque')),
        dict(type='content_block_stop',index=0),
        dict(type='content_block_start',index=1,content_block=dict(type='text',text='')),
        dict(type='content_block_delta',index=1,delta=dict(type='text_delta',text=text)),
        dict(type='content_block_stop',index=1),
        dict(type='message_delta',delta=dict(stop_reason='end_turn'),usage=dict(output_tokens=10000)),
        dict(type='message_delta',delta={},usage=dict(output_tokens=20000)),dict(type='message_stop')]


def test_stream_lossless_cumulative_usage_and_native_wire(tmp_path):
    p,_=prepared()
    payload=b''.join(('data: '+json.dumps(e)+'\n\n').encode() for e in events())
    class Response(BytesIO):
        headers={'request-id':'mock'}
    class Opener:
        def open(self,request,timeout):
            assert request.full_url=='https://api.anthropic.com/v1/messages'
            assert json.loads(request.data)==p['wire_body']
            assert request.get_header('X-api-key')=='MOCK'
            return Response(payload)
    path=tmp_path/'raw.sse'
    result=Transport('MOCK',opener=Opener()).send(p,path)
    assert path.read_bytes()==payload
    assert result['message']['usage']['output_tokens']==20000
    assert nominal_nanodollars(result['message'])==202000000
    assert result['message']['content'][0]['thinking']=='not answer'


def test_missing_final_usage_and_incomplete_stream_fail():
    c=Collector()
    for e in events()[:-1]:c.feed(e)
    with pytest.raises(ValueError):c.complete()
    c=Collector()
    for e in events()[:-3]:c.feed(e)
    with pytest.raises(ValueError):c.feed(dict(type='message_stop'))


@pytest.mark.parametrize('change',[dict(model='other'),dict(usage=dict(input_tokens=1)),
    dict(usage=dict(input_tokens=1,output_tokens=1,cache_creation_input_tokens=1)),
    dict(usage=dict(input_tokens=1,output_tokens=1,inference_geo='us'))])
def test_unpriced_or_incomplete_usage_not_zero(change):
    c=Collector()
    for e in events():c.feed(e)
    raw=c.complete();raw.update(change)
    with pytest.raises(ValueError):nominal_nanodollars(raw)


@pytest.fixture
def entry(monkeypatch):
    project=Path(__file__).resolve().parents[1]
    spec=importlib.util.spec_from_file_location('claude_pilot_entry',project/'scripts/rl1/127_run_claude_pilot.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    from metacom_pm.rl1 import diagnostic_engine
    monkeypatch.setattr(m,"engine",lambda:diagnostic_engine)
    return m


def setup_run(entry,tmp_path):
    p,schema=prepared();engine=entry.engine()
    slots=[dict(slot_id=x,input_identity=p['identity'],config_identity='mock-config',role='development') for x in ('a','b')]
    pr=dict(identity='mock-protocol',slots=slots,reserve_usd='3.28',limits=dict(max_attempts=4,recovery_cap=2,
        baseline_attempts=307),schemas={x:schema for x in ('a','b')})
    budget=budget_class(engine)(tmp_path/'money.jsonl',trial='mock-trial',study=VERSION,
        stage_cap=engine.s.nanodollars(6),trial_cap=engine.s.nanodollars(6),shared_cap=engine.s.nanodollars(20),
        baseline=0,opening=0)
    return pr,p,budget


def test_real_budget_adapter_failure_isolated_and_immutable_close(entry,tmp_path):
    pr,p,budget=setup_run(entry,tmp_path)
    class Fake:
        calls=0
        def send(self,*args):
            self.calls+=1;c=Collector()
            text='bad JSON' if self.calls==1 else '{"assessment":{"status":"scored","reason":"source"}}'
            for e in events(text):c.feed(e)
            return dict(http_status=200,message=c.complete())
    transport=Fake()
    result=entry.execute(pr,tmp_path,{p['identity']:p},{'a':{},'b':{}},budget,transport,
        lambda *_:{'measurement_status':'measured_candidate'},lambda:None,mode='mock')
    assert result['attempts']==3 and transport.calls==3
    assert result['first_technical_valid']==1 and result['first_attempts']==2
    assert result['states']=={'a':'VALID','b':'VALID'}
    assert result['unsettled_reservations']==0
    assert entry.execute(pr,tmp_path,{p['identity']:p},{},budget,transport,None,None,mode='mock')==result
    assert transport.calls==3
    reservations=[e for e in budget.events() if e['event']=='RESERVED']
    assert all(e['provider']=='Anthropic official API' for e in reservations)
    assert reservations[-1]['call_class']=='TECHNICAL_RECOVERY'


def test_unknown_delivery_retains_liability_no_retry(entry,tmp_path):
    pr,p,budget=setup_run(entry,tmp_path)
    class Fake:
        def send(self,*_):raise TimeoutError()
    result=entry.execute(pr,tmp_path,{p['identity']:p},{'a':{},'b':{}},budget,Fake(),None,lambda:None,mode='mock')
    assert result['attempts']==1 and result['unsettled_reservations']==1
    assert result['stage_cost_or_liability_usd']=='3.28'


def test_explicit_rejection_settles_zero_and_closes(entry,tmp_path):
    pr,p,budget=setup_run(entry,tmp_path)
    transport=SimpleNamespace(send=lambda *_:dict(http_status=400))
    result=entry.execute(pr,tmp_path,{p['identity']:p},{'a':{},'b':{}},budget,transport,None,lambda:None,mode='mock')
    assert result['attempts']==1 and result['stage_cost_or_liability_usd']=='0'
    assert result['unsettled_reservations']==0
    assert result['stop_reason']=='EXPLICIT_PROVIDER_REJECTION_400'


def test_reserve_checks_shared_caps_and_never_reuses_attempt(entry,tmp_path):
    _,_,budget=setup_run(entry,tmp_path)
    claim=dict(slot_id='a',input_identity='x',ordinal=0,study=VERSION)
    budget.reserve('one',3280000000,claim)
    with pytest.raises(ValueError):budget.reserve('one',3280000000,claim)
    with pytest.raises(ValueError):budget.reserve('two',3280000000,claim)
    budget.settle('one',3000000000,'valid')
    with pytest.raises(ValueError,match='stage'):budget.reserve('two',3280000000,claim)
