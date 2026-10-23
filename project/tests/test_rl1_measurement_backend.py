"""Qualified episode -> content queue -> finite attempts -> BC, offline only."""
from copy import deepcopy
import json

import pytest

from metacom_pm.rl1 import diagnostic_engine as engine
from metacom_pm.rl1.calibration_workflow import qualify
from metacom_pm.rl1.measurement_backend import QualifiedFeedbackBackend
from metacom_pm.rl1.measurement_identity import binding
from metacom_pm.rl1.natural_batch import FeedbackQueue
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.supervised_learning import ENGINEERING
from test_rl1_calibration_workflow import fixture


def setup(tmp_path, outcomes=('format_failure','valid'), *, repeat=False, max_attempts=4, enqueue=True):
    bundle=fixture();f=bundle['freeze'];qual=qualify(**bundle)
    class Adapter:
        identity=f['runtime_identity'];code_identity=f['bindings']['code']
        protocol_identity=f['scorer_protocol_identity']
        def prepare(self,evidence,reply):
            return dict(messages=[dict(role='system',content='MOCK complete rubric and schema'),
                dict(role='user',content=json.dumps(dict(evidence=evidence,reply=reply)))],schema={'MOCK':True})
        def evaluate(self,raw,payload):
            outcome=raw['mock_outcome']
            return dict(outcome=outcome,q=3 if outcome=='valid' else None,m=0 if outcome=='valid' else None)
    class Transport:
        engineering_only=True
        calls=[]
        def send(self,request,*,attempt_id):
            self.calls.append(attempt_id)
            kind=outcomes[len(self.calls)-1]
            if kind=='timeout':raise TimeoutError('MOCK unknown delivery')
            return dict(request_identity=request['identity'],runtime_identity=f['runtime_identity'],
                mock_outcome=kind,cost=None if kind=='unknown_usage' else 1000)
    budget=engine.DiagnosticBudget(tmp_path/'ledger.jsonl',trial='MOCK',study='MOCK_BACKEND',
        stage_cap=100000,trial_cap=100000,shared_cap=100000,baseline=0,opening=0)
    queue=FeedbackQueue(tmp_path/'queue.sqlite');adapter=Adapter();transport=Transport()
    b=binding('G1',digest('MOCK reply'),digest('MOCK evidence'),f,qual)
    if repeat:b.update(measurement_purpose='independent_repeat',measurement_draw_identity='repeat-1')
    if enqueue:queue.measure(b,'MOCK evidence','MOCK reply')
    kwargs=dict(bundle=bundle,adapter=adapter,transport=transport,cost=lambda raw:raw['cost'],
        budget=budget,root=tmp_path/'worker',scope=ENGINEERING,max_attempts=max_attempts,
        recovery_cap=2,reserve_nanodollars=2000)
    return queue,b,kwargs


def test_first_format_failure_stays_pending_then_one_score_reused_across_G(tmp_path):
    q,b,kw=setup(tmp_path);w=QualifiedFeedbackBackend(q,**kw)
    assert w.step()['status']=='PENDING_TECHNICAL_RECOVERY'
    assert q.measure(b,'MOCK evidence','MOCK reply') is None
    assert q.counts()==[dict(kind='measurement',state='STARTED',count=1)]
    restored=QualifiedFeedbackBackend(FeedbackQueue(q.path),**kw)
    assert restored.step()['measurement_status']=='measured_candidate'
    first=q.measure(b,'MOCK evidence','MOCK reply')
    second=q.measure(dict(b,generation_request_id='G2'),'MOCK evidence','MOCK reply')
    assert first['q']==second['q']==3 and first['content_receipt_identity']==second['content_receipt_identity']
    assert len(first['attempts'])==2 and len(kw['transport'].calls)==2
    assert restored.step()['status']=='IDLE'
    events=kw['budget'].events()
    assert sum(e['event']=='RESERVED' for e in events)==sum(e['event']=='SETTLED' for e in events)==2
    outcomes=[json.loads(p.read_text())['outcome'] for p in (tmp_path/'worker').glob('*/*.result.json')]
    assert sorted(outcomes)==['format_failure','valid']


@pytest.mark.parametrize('outcomes,repeat,attempts,status',[
    (('schema_failure','schema_failure'),False,2,'technical_failure'),
    (('format_failure',),True,1,'technical_failure'),
    (('semantic_unknown',),False,1,'semantic_uncertainty')])
def test_final_failure_and_unknown_are_never_zero_or_extra_retries(tmp_path,outcomes,repeat,attempts,status):
    q,b,kw=setup(tmp_path,outcomes,repeat=repeat);w=QualifiedFeedbackBackend(q,**kw)
    for _ in range(attempts):w.step()
    result=q.measure(b,'MOCK evidence','MOCK reply')
    assert result['measurement_status']==status and result['q'] is result['m'] is None
    assert w.step()['status']=='IDLE' and len(kw['transport'].calls)==attempts


@pytest.mark.parametrize('outcome',['timeout','unknown_usage'])
def test_unknown_delivery_or_money_keeps_full_liability_and_never_resends(tmp_path,outcome):
    q,b,kw=setup(tmp_path,(outcome,));w=QualifiedFeedbackBackend(q,**kw)
    if outcome=='timeout':
        with pytest.raises(TimeoutError):w.step()
    else:assert w.step()['status']=='RECONCILIATION_REQUIRED'
    assert QualifiedFeedbackBackend(q,**kw).step()['status']=='RECONCILIATION_REQUIRED'
    assert q.measure(b,'MOCK evidence','MOCK reply') is None
    total,_,reserved,settled=kw['budget']._totals(kw['budget'].events())
    assert total==2000 and len(reserved)==1 and not settled and len(kw['transport'].calls)==1


def test_crash_before_queue_publication_adopts_sealed_result_without_new_call(tmp_path,monkeypatch):
    q,b,kw=setup(tmp_path,('valid',));w=QualifiedFeedbackBackend(q,**kw)
    with monkeypatch.context() as patch:
        patch.setattr(q,'settle',lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
        with pytest.raises(KeyboardInterrupt):w.step()
    assert QualifiedFeedbackBackend(q,**kw).step()['measurement_status']=='measured_candidate'
    assert len(kw['transport'].calls)==1


def test_changed_request_or_global_attempt_cap_never_dispatches(tmp_path):
    q,b,kw=setup(tmp_path,max_attempts=1);w=QualifiedFeedbackBackend(q,**kw)
    w.step();assert w.step()['status']=='STAGE_BLOCKED'
    assert len(kw['transport'].calls)==1
    kw['adapter'].prepare=lambda *_:dict(messages='MOCK changed prompt',schema={})
    with pytest.raises(ValueError,match='actual scoring request changed'):w.step()
    assert q.measure(b,'MOCK evidence','MOCK reply') is None


def test_three_matching_failures_stop_configuration_without_settling_pending_slot(tmp_path):
    q,b,kw=setup(tmp_path,('format_failure',)*3,max_attempts=6)
    other=dict(b,generation_request_id='G2',response_identity=digest('different MOCK reply'))
    q.measure(other,'MOCK evidence','different MOCK reply')
    w=QualifiedFeedbackBackend(q,**kw)
    assert w.step()['status']=='PENDING_TECHNICAL_RECOVERY'
    assert w.step()['measurement_status']=='technical_failure'
    assert w.step()['status']=='PENDING_TECHNICAL_RECOVERY'
    result=w.step()
    assert result['status']=='STAGE_BLOCKED' and 'three matching' in result['reason']
    assert len(kw['transport'].calls)==3
    assert q.measure(other,'MOCK evidence','different MOCK reply') is None


@pytest.mark.parametrize('change',['request','runtime','overrun'])
def test_wrong_identity_or_financial_overrun_stops_without_score(tmp_path,change):
    q,b,kw=setup(tmp_path,('valid',));send=kw['transport'].send
    def changed(*args,**kwargs):
        result=send(*args,**kwargs)
        result.update({'request':{'request_identity':'WRONG'},'runtime':{'runtime_identity':'WRONG'},
                       'overrun':{'cost':3000}}[change])
        return result
    kw['transport'].send=changed;w=QualifiedFeedbackBackend(q,**kw)
    assert w.step()['status']=='RECONCILIATION_REQUIRED'
    assert w.step()['status']=='RECONCILIATION_REQUIRED'
    assert q.measure(b,'MOCK evidence','MOCK reply') is None and len(kw['transport'].calls)==1


def test_budget_change_requires_new_stage_identity(tmp_path):
    q,b,kw=setup(tmp_path);w=QualifiedFeedbackBackend(q,**kw)
    kw['budget'].stage_cap+=1
    with pytest.raises(ValueError,match='financial policy changed'):w.step()
    with pytest.raises(ValueError,match='stage identity changed'):QualifiedFeedbackBackend(q,**kw)
    assert not kw['transport'].calls


def test_pool_uses_same_backend_for_complete_supervision_and_validates_G_source(tmp_path):
    from metacom_pm.rl1.research_backend import ResearchBackend
    from metacom_pm.rl1.learning_preparation import PolicyInputView
    from test_rl1_learning_handoff import inputs
    from rl1_batch_fixtures import make_encoder
    cs,old,_=inputs();q,_,kw=setup(tmp_path,('valid','valid'),enqueue=False)
    backend=ResearchBackend(q,qualification_bundle=old['qualification_bundle'],
        measurement_worker=QualifiedFeedbackBackend(q,**kw))
    evidence={c.prefix_identity:'MOCK legal full source' for c in cs}
    args=dict(episodes=old['episodes'],evidence=evidence)
    assert backend.pool_receipts(cs,**args)=={}
    while (item:=q.claim_next(kind='generation')) is not None:
        p=item['payload'];counts=tuple(p['provenance']['canonical_counts'])
        q.settle(item['id'],dict(request_id=p['request_id'],runtime_identity=p['executor_identity'],
            source_provenance_identity=digest(p['provenance']),finish_reason='natural_stop',
            text='MOCK reply '+str(counts)))
    assert backend.pool_receipts(cs,**args)=={}
    assert backend.service_once()['measurement']['status']=='LOGICAL_SETTLED'
    assert len(backend.pool_receipts(cs,**args))==1
    assert backend.service_once()['measurement']['status']=='LOGICAL_SETTLED'
    encoder,_=make_encoder()
    prepared=backend.prepare_supervision(cs,menu=old['menu'],view=PolicyInputView(encoder),
        method='BC-init',**args)
    assert prepared['status']=='READY' and prepared['method']=='BC-init'
    # Equal quality means original resource cost chooses OFF, not an invented difference.
    assert prepared['rows'][0]['target']==0
    original=q.generate
    q.generate=lambda request:dict(original(request),source_provenance_identity='WRONG')
    with pytest.raises(ValueError,match='frozen generation'):backend.pool_receipts(cs,**args)
