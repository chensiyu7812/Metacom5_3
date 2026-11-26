import json
import subprocess
import sys

import pytest

from metacom_pm.rl1v3.journal.pomdp_latency import (
    MonotonicClock, FirstOutputObserver, TimingError, duration_ns, remaining_ns, latency_contract)


class Tokenizer:
    all_special_ids=[0,1]
    def decode(self, ids, **kwargs):
        table={0:'',1:'',2:' ',3:'\ufffd',4:'A',5:'.',6:'\u200b'}
        return ''.join(table[x] for x in ids)


def clock():
    values=iter(range(100,10000,10))
    return MonotonicClock(now=lambda:next(values),boot_id='test-only-clock-domain')


def test_first_token_not_first_text_or_client_semantic_success():
    c=clock(); start=c.stamp()
    o=FirstOutputObserver(Tokenizer(),prompt_token_count=2,clock=c,generation_start_stamp=start)
    o.put([[8,9]])
    for token in (0,2,3,6):o.put([token])
    partial=o.measurement()
    assert partial['events']['first_generated_token'] is not None
    assert partial['events']['first_non_special_token'] is not None
    assert partial['events']['first_nonempty_decoded_text'] is None
    o.put([4]);o.put([1]);o.end(); result=o.measurement()
    assert result['first_nonempty_decoded_text_latency_ns'] > result['first_generated_token_latency_ns']
    assert result['client_ttft_ns'] is None and result['semantic_text_validity']=='not_machine_qualified'
    assert result['generated_token_count']==6 and result['callback_work_ns']>0


def test_eos_only_never_imputed_text_latency():
    o=FirstOutputObserver(Tokenizer(),prompt_token_count=1,clock=clock())
    o.put([[9]]);o.put([1]);o.end()
    r=o.measurement()
    assert r['events']['first_generated_token'] is not None
    assert r['events']['first_nonempty_decoded_text'] is None
    assert r['first_nonempty_decoded_text_latency_ns'] is None
    assert r['first_text_status']=='not_observed'


@pytest.mark.parametrize('change', [dict(boot_id='different'),dict(clock='CLOCK_REALTIME'),
                                  dict(monotonic_ns=0),dict(monotonic_ns=True)])
def test_no_cross_boot_utc_negative_or_bool_duration(change):
    c=clock(); a=c.stamp(); b=c.stamp(); b.update(change)
    with pytest.raises(TimingError):duration_ns(a,b)


def test_actual_cross_process_clock_same_linux_boot():
    c=MonotonicClock();a=c.stamp()
    code='import json; from metacom_pm.rl1v3.journal.pomdp_latency import record_stamp; print(json.dumps(record_stamp()))'
    child=json.loads(subprocess.check_output([sys.executable,'-c',code],text=True));b=c.stamp()
    assert child['pid']!=a['pid']
    assert duration_ns(a,child)>=0 and duration_ns(child,b)>=0


def test_deadline_and_no_delivery_estimation():
    c=clock()
    assert remaining_ns(150,c)==50 and remaining_ns(10,c)==0
    with pytest.raises(TimingError):remaining_ns(True,c)
    assert latency_contract()['client_ttft_ns'] is None


@pytest.mark.parametrize('bad', [[[8]], [[8,9],[8,9]], [True,9]])
def test_prompt_callback_shape_rejected(bad):
    o=FirstOutputObserver(Tokenizer(),prompt_token_count=2,clock=clock())
    with pytest.raises(TimingError):o.put(bad)


def test_events_stop_at_stream_end():
    o=FirstOutputObserver(Tokenizer(),prompt_token_count=1,clock=clock())
    o.put([9]);o.put([4]);o.end()
    with pytest.raises(TimingError):o.put([4])
    with pytest.raises(TimingError):o.end()
