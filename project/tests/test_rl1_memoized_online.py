from dataclasses import asdict

import pytest

from metacom_pm.rl1.memoized_online import RequestRenderer, MemoizedHeadSession
from metacom_pm.rl1.organized_policy_interface import HeadSession
from metacom_pm.rl1.schema import digest
from test_rl1_organized_policy_interface import setup, item


@pytest.mark.parametrize('hidden',[False,True])
def test_memoization_preserves_every_observation_trace_and_terminal(hidden):
    c,r = setup([item('m','MP','cycling'),item('r','RS','cycling'),item('s','MS','need help')])
    memo = RequestRenderer(r)
    left,right = HeadSession(c,r,without_text=hidden),MemoizedHeadSession(c,memo,without_text=hidden)
    for action in [2,1,3,0]:
        assert asdict(left.observe()) == asdict(right.observe())
        assert left.step(action) == right.step(action,expected_observation=digest(asdict(right.observe())))
    assert left.terminal(executor_identity='g',draw_identity='d') == right.terminal(executor_identity='g',draw_identity='d')
    assert memo.stats['usage_calls'] > memo.stats['usage_misses']
    with pytest.raises(ValueError,match='masked'): right.step(0)


def test_same_length_text_is_not_same_cache_key_and_mutation_cannot_poison_cache():
    c,r = setup([item('a','MS','abc'),item('b','MS','xyz')])
    memo = RequestRenderer(r)
    memo.usage(c,['a']); memo.usage(c,['b'])
    assert memo.stats['chat_misses']==2
    row = memo.usage(c,['a']); row['input_tokens'] = -1
    assert memo.usage(c,['a']) == r.usage(c,['a'])
    with pytest.raises(ValueError,match='duplicate'): memo.usage(c,['a','a'])


def test_native_mask_and_fresh_request_cache_are_preserved():
    c,r = setup([item('a',text='x'*10000)],limit=2000)
    memo = RequestRenderer(r)
    s=MemoizedHeadSession(c,memo)
    assert not s.observe().action_mask[3]
    with pytest.raises(ValueError,match='masked'): s.step(3)
    other = RequestRenderer(r)
    assert not other._usage_cache and not other._chat_cache
    assert s.observe()==HeadSession(c,r).observe()
