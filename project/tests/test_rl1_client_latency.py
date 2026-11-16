import math
import time

import pytest

from metacom_pm.rl1.client_latency import ReferenceStreamClient, seconds_return, validate_trace
from metacom_pm.rl1.latency_serving import RequestVectors, prepare_online
from metacom_pm.rl1.organized_policy_interface import HeadSession
from metacom_pm.rl1.schema import digest
from test_rl1_organized_policy_interface import setup, item, feature_encoder


def measured(service):
    client = ReferenceStreamClient(service,regime_identity='test-only',technical_timeout_seconds=2.)
    try:
        return client.measure({'case':'fixture'},trace_id='test')
    finally:
        client.close()


def test_client_covers_online_work_and_first_text_is_not_completion():
    def service(payload,emit):
        time.sleep(.015); emit(''); emit('  '); emit('hello ')
        time.sleep(.015); emit('world')
        return dict(text='hello world',finish_reason='natural_stop')
    trace,raw = measured(service)
    assert trace['ttft_seconds'] >= .015
    assert trace['completion_seconds']-trace['ttft_seconds'] >= .015
    assert trace['observed_wait_seconds'] >= trace['completion_seconds']
    assert trace['reply_identity'] == digest(raw['text'])
    validate_trace(trace)


@pytest.mark.parametrize('reason',['technical_timeout','repetition_guard','context_exhausted'])
def test_partial_text_is_never_a_completed_latency(reason):
    def service(_,emit):
        emit('partial'); return dict(text='partial',finish_reason=reason)
    trace,_ = measured(service)
    assert trace['ttft_seconds'] is not None and trace['completion_seconds'] is None
    assert seconds_return(quality_gain=1.,trace=trace,seconds_weight=.1,regime_identity='test-only')['return_value'] is None


def test_exception_retains_wait_and_partial_text():
    def service(_,emit):
        emit('partial'); raise RuntimeError('fixture error')
    trace,_ = measured(service)
    assert trace['status'] == 'service_error' and trace['observed_wait_seconds'] > 0
    assert trace['completion_ns'] is None and trace['error']['type'] == 'RuntimeError'


def test_stream_mismatch_and_empty_natural_reply_are_not_complete():
    for emitted,final in [('first','different'),('','')]:
        def service(_,emit):
            emit(emitted); return dict(text=final,finish_reason='natural_stop')
        trace,_ = measured(service)
        assert trace['completion_ns'] is None


def test_timeout_and_duplicate_trace_cannot_be_reissued():
    def service(_,emit):
        time.sleep(.03); emit('late'); return dict(text='late',finish_reason='natural_stop')
    client = ReferenceStreamClient(service,regime_identity='test',technical_timeout_seconds=.001)
    trace,_ = client.measure({},trace_id='once')
    assert trace['status'] == 'client_timeout' and trace['completion_ns'] is None
    with pytest.raises(ValueError,match='no implicit retry'): client.measure({},trace_id='twice')
    client.close()
    client = ReferenceStreamClient(lambda _,emit:dict(text='',finish_reason='empty_output'),
        regime_identity='test',technical_timeout_seconds=1.)
    client.measure({},trace_id='once')
    with pytest.raises(ValueError,match='no implicit retry'): client.measure({},trace_id='once')
    client.close()


def test_seconds_cost_has_no_default_no_tokens_and_preserves_missing_quality():
    def service(_,emit):
        emit('reply'); return dict(text='reply',finish_reason='natural_stop')
    trace,_ = measured(service)
    assert seconds_return(quality_gain=None,trace=trace,seconds_weight=.1,regime_identity='test-only')['status'] == 'pending_quality'
    assert seconds_return(quality_gain=1.,trace=None,seconds_weight=.1,regime_identity='test-only')['status'] == 'pending_latency'
    row = seconds_return(quality_gain=.2,trace=trace,seconds_weight=.1,regime_identity='test-only')
    assert row['return_value'] == .2-.1*trace['completion_seconds'] and row['token_penalty'] == 0
    with pytest.raises(ValueError,match='another deployment'): seconds_return(quality_gain=1.,trace=trace,seconds_weight=.1,regime_identity='browser')
    with pytest.raises(ValueError): seconds_return(quality_gain=1.,trace=trace,seconds_weight=float('nan'),regime_identity='test-only')
    bad = dict(trace,completion_seconds=0.); bad['identity'] = digest({k:v for k,v in bad.items() if k != 'identity'})
    with pytest.raises(ValueError,match='seconds disagree'): validate_trace(bad)


@pytest.mark.parametrize('seconds_field',['ttft_seconds','completion_seconds','observed_wait_seconds'])
def test_trace_accepts_one_ulp_roundoff_but_rejects_changed_measurement(seconds_field):
    def service(_,emit):
        emit('reply')
        return dict(text='reply',finish_reason='natural_stop')
    trace,_=measured(service)
    assert trace[seconds_field] is not None
    rounded=dict(trace,**{seconds_field:math.nextafter(trace[seconds_field],math.inf)})
    rounded['identity']=digest({k:v for k,v in rounded.items() if k!='identity'})
    validate_trace(rounded)
    forged=dict(trace,**{seconds_field:trace[seconds_field]+1e-6})
    forged['identity']=digest({k:v for k,v in forged.items() if k!='identity'})
    with pytest.raises(ValueError,match='seconds disagree'):
        validate_trace(forged)


def test_off_skips_catalog_rank_and_feature_encoding(monkeypatch):
    catalog,renderer = setup([item('a')])
    def forbidden(*args): raise AssertionError('OFF ranked resources')
    monkeypatch.setattr(catalog,'rank',forbidden)
    request,events = prepare_online(catalog,renderer,actions=[0],sequential_view=None,decide=None,
        executor_identity='test',draw_identity='test')
    assert request['provenance']['selected_keys'] == []
    assert request['messages'] == renderer.messages(catalog,())
    assert all(e['stage'] != 'online_encoding' for e in events)


def test_fixed_and_sequential_paths_deliver_same_resources_with_online_features():
    catalog,renderer = setup([item('a'),item('b',text='different evidence')])
    planner = feature_encoder(window=5000); seen = []
    def forward(blocks):
        seen.extend(blocks); return [[1.,2.] for b in blocks]
    view = RequestVectors(planner,forward)
    def decide(values,mask,planned):
        assert len(values) == planner.feature_dimension and all(type(m) is bool for m in mask)
        return planned
    kw = dict(actions=[3,3,0],executor_identity='test',draw_identity='test')
    seq,events = prepare_online(catalog,renderer,sequential_view=view,decide=decide,**kw)
    fixed,_ = prepare_online(catalog,renderer,sequential_view=None,decide=None,**kw)
    assert seq['messages'] == fixed['messages']
    assert seq['provenance']['selected_keys'] == fixed['provenance']['selected_keys']
    assert len(seen) == 3 and sum(e['stage']=='online_encoding' for e in events) == 3
    fresh = RequestVectors(planner,forward)
    fresh.sequential(HeadSession(catalog,renderer).observe())
    assert len(seen) == 4  # no cached training/cross-request prefix vector


def test_illegal_diagnostic_program_rejected_before_work():
    catalog,renderer = setup([item('a')])
    for actions in ([3],[0,3,0],[5,0]):
        with pytest.raises(ValueError,match='complete fixed'):
            prepare_online(catalog,renderer,actions=actions,sequential_view=None,decide=None,
                executor_identity='test',draw_identity='test')
