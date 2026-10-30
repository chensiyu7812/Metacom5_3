import hashlib
import io
import json
import socket

import pytest

from metacom_pm.rl1.development_dispatch import DeepSeekStageTransport
from metacom_pm.rl1 import development_preflight as m
from metacom_pm.rl1.schema import digest
import test_rl1_development_dispatch as fixtures
import test_rl1_development_feedback as feedback


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(socket.socket,'connect',lambda *a,**k:(_ for _ in ()).throw(AssertionError('network forbidden')))


def authorize(s,tmp_path):
    record=tmp_path/'authorization.txt';record.write_text('SYNTHETIC AUTHORIZATION')
    s.approval=dict(status='APPROVED',protocol_identity=s.identity,operation='bounded_development_scoring',
        financial_policy_identity=digest(s.policy),researcher_authorization_record=str(record),
        researcher_record_sha256=hashlib.sha256(record.read_bytes()).hexdigest())


def test_native_transport_sends_exact_complete_wire_and_collects_usage(tmp_path,monkeypatch):
    import urllib.request
    adapter=feedback.adapter();item={k:feedback.materials()[0][k] for k in ('reply','evidence')}
    request=adapter.prepare(item,'S');value=feedback.score(item)
    chunks=[dict(model='deepseek-flash',choices=[dict(index=0,delta=dict(content=json.dumps(value)),finish_reason='stop')]),
            dict(model='deepseek-flash',choices=[],usage=dict(prompt_tokens=12,completion_tokens=34))]
    stream=b''.join(('data: '+json.dumps(c)+'\n\n').encode() for c in chunks)+b'data: [DONE]\n\n'
    sent=[]
    class Opener:
        def open(self,req,timeout):sent.append(req);return io.BytesIO(stream)
    monkeypatch.setattr(urllib.request,'build_opener',lambda *a:Opener())
    monkeypatch.setenv('DEEPSEEK_API_KEY','synthetic-not-a-credential')
    transport=DeepSeekStageTransport(tmp_path,timeout_seconds=900,
        credential_fingerprint=hashlib.sha256(b'synthetic-not-a-credential').hexdigest())
    raw=transport.send(request,attempt_id='fixture')
    assert adapter.evaluate(request,item,raw)['technical_valid']
    assert json.loads(sent[0].data)==request['wire_body'] and sent[0].full_url==request['endpoint']
    assert raw['usage']==dict(prompt_tokens=12,completion_tokens=34)
    assert (tmp_path/'fixture.sse').read_bytes()==stream.rstrip(b'\n')+b'\n'
    assert 'synthetic-not-a-credential' not in (tmp_path/'fixture.wire.json').read_text()
    with pytest.raises(FileExistsError):transport.send(request,attempt_id='fixture')
    assert len(sent)==1  # An archived attempt cannot be sent a second time.


def test_preflight_approval_price_account_and_one_time_management(tmp_path,monkeypatch):
    import urllib.request
    s,_=fixtures.setup(tmp_path)
    html=b'<table><tr><td>synthetic</td><td>tariff</td></tr></table>'
    parser=m.FirstTable();parser.feed(html.decode())
    s.policy.update(public_price_table_identity=digest(parser.rows),published_model_names=['fixture-model'])
    authorize(s,tmp_path);sent=[]
    monkeypatch.setattr(m,'visible_paid_writers',lambda:[])
    monkeypatch.setenv('DEEPSEEK_API_KEY','synthetic-not-a-credential')
    class Opener:
        def open(self,req,timeout):
            url=req if isinstance(req,str) else req.full_url;sent.append(url)
            if url==m.PRICING:return io.BytesIO(html)
            if url.endswith('/models'):return io.BytesIO(json.dumps(dict(data=[dict(id='deepseek-flash',name='fixture-model')])).encode())
            if url.endswith('/user/balance'):return io.BytesIO(json.dumps(dict(is_available=True,balance_infos=[dict(currency='USD',total_balance='10')])).encode())
            raise AssertionError(url)
    monkeypatch.setattr(urllib.request,'build_opener',lambda *a:Opener())
    with pytest.raises(ValueError,match='lease'):m.ensure_preflight(s)
    assert not sent
    with s.budget.legacy_lease():
        r=m.ensure_preflight(s);assert m.ensure_preflight(s)==r
    assert r['available_nanodollars']==10**10 and len(sent)==4 and r['management_requests']==2
    (s.root/'management/models.json').write_text('{}')
    with s.budget.legacy_lease():
        with pytest.raises(ValueError,match='receipt changed'):m.ensure_preflight(s)
    assert sum(x.endswith('/models') for x in sent)==1


def test_pending_approval_and_visible_writer_never_access_service(tmp_path,monkeypatch):
    s,_=fixtures.setup(tmp_path)
    with pytest.raises(ValueError,match='not approved'):m.ensure_preflight(s)
    authorize(s,tmp_path)
    monkeypatch.setattr(m,'visible_paid_writers',lambda:[dict(pid=123,comm='synthetic')])
    with s.budget.legacy_lease():
        with pytest.raises(ValueError,match='concurrent'):m.ensure_preflight(s)
    assert not (s.root/'management').exists()


def test_unknown_management_delivery_is_not_queried_again(tmp_path,monkeypatch):
    import urllib.request
    s,_=fixtures.setup(tmp_path);html=b'<table><tr><td>synthetic</td></tr></table>'
    parser=m.FirstTable();parser.feed(html.decode());s.policy['public_price_table_identity']=digest(parser.rows)
    authorize(s,tmp_path);sent=[]
    monkeypatch.setattr(m,'visible_paid_writers',lambda:[]);monkeypatch.setenv('DEEPSEEK_API_KEY','synthetic')
    class Opener:
        def open(self,req,timeout):
            if isinstance(req,str):return io.BytesIO(html)
            sent.append(req.full_url);raise TimeoutError('synthetic management timeout')
    monkeypatch.setattr(urllib.request,'build_opener',lambda *a:Opener())
    with s.budget.legacy_lease():
        with pytest.raises(TimeoutError):m.ensure_preflight(s)
        with pytest.raises(ValueError,match='no automatic retry'):m.ensure_preflight(s)
    assert len(sent)==1
