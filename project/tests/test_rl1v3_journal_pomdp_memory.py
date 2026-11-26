"""Synthetic protocol tests; no source text, gold, model or GPU needed."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from metacom_pm.rl1v3.io import object_sha256
from metacom_pm.rl1v3.journal.pomdp_memory import (
    SearchExpandEpisode, Limits, RejectedAction, run_cpu_policy, POLICIES)


class Tokenizer:
    identity = 'synthetic-tokenizer'
    def count(self, text):
        return len(text.split())
    def make_packet(self, views=()):
        texts = [v.reading_text for v in views]
        return SimpleNamespace(input_ids=[0]*(4+sum(self.count(t) for t in texts)),
            payload_sha256=object_sha256(texts))


def record(rid, text, rank=0, owner='allowed'):
    return dict(record_id=rid, head='MS', view='raw', owner_id=owner,
        source_rank=rank, reported_at=dict(date='2020-01-01', session_rank=rank),
        reading_text=text, parent_session_id='session-'+rid,
        source_refs=[dict(turn_index=0, speaker='seeker', exact_quote=text)])


def make(records=None, nonce='episode-one', limits=Limits(), **kw):
    task = dict(task_id='synthetic', timestamp='2020-01-03',
        turns=[dict(role='seeker', text='Find the hobby report')],
        query='Find the hobby report', view_protocol='synthetic')
    return SearchExpandEpisode(task=task, records=records or [record('r1','The hobby was Zephyr knitting'),
        record('r2','Zephyr became a local class')], tokenizer=Tokenizer(),
        legal=lambda r: r['owner_id']=='allowed' and r['source_rank']<2,
        episode_nonce=nonce, limits=limits, **kw)


def test_query_before_read_and_legal_after_read():
    e=make()
    with pytest.raises(RejectedAction, match='unread_query'):
        e.step(dict(action='SEARCH',query='Zephyr'))
    e.step(dict(action='SEARCH',query='hobby'))
    e.step(dict(action='SEARCH',query='Zephyr'))
    assert e.accesses==2


@pytest.mark.parametrize('bad',[record('x','Future',rank=2),record('y','Other',owner='wrong')])
def test_illegal_owner_future_at_construction(bad):
    with pytest.raises(ValueError,match='illegal source'):
        make([bad])


def test_unread_body_invariance_and_handle_provenance():
    e=make(); altered=make([record('r1','Entirely different unseen text'),record('r2','Different')])
    assert e.observe()==altered.observe()
    a=e.step(dict(action='SEARCH',query='hobby'))
    f=make(nonce='another-episode')
    f.step(dict(action='SEARCH',query='hobby'))
    with pytest.raises(RejectedAction,match='foreign_handle'):
        f.step(dict(action='EXPAND',handle=a['last_hits'][0]))


def test_duplicate_full_charge_canonical_content_reuse():
    e=make();a=e.step(dict(action='SEARCH',query='hobby'))
    action=dict(action='EXPAND',handle=a['last_hits'][0])
    e.step(action); first=e.receipt();e.step(action);second=e.receipt()
    assert first['content_payload_sha256']==second['content_payload_sha256']
    assert first['trajectory_sha256']!=second['trajectory_sha256']
    assert second['delivered_tokens']>first['delivered_tokens']
    assert second['accesses']==first['accesses']+1


def test_budget_refusal_only_stop_and_pending_not_zero():
    e=make(limits=Limits(delivered_tokens=1))
    with pytest.raises(RejectedAction,match='token_budget'):
        e.step(dict(action='SEARCH',query='hobby'))
    assert e.observe()['action_mask']==['STOP']
    assert e.charged_tokens==0 and e.failed_attempts[0]['elapsed_seconds']>0
    with pytest.raises(RejectedAction,match='requires_stop'):
        e.step(dict(action='SEARCH',query='hobby'))
    e.step(dict(action='STOP'))
    assert e.reward is None and e.status=='pending_generation_and_evaluation'
    with pytest.raises(RejectedAction,match='after_stop'):
        e.step(dict(action='STOP'))


def test_no_text_cannot_use_observed_entities_or_see_readings():
    e=make();e.step(dict(action='SEARCH',query='hobby'),no_text=True)
    obs=e.observe(no_text=True)
    assert 'Zephyr' not in str(obs) and 'readings' not in obs
    with pytest.raises(RejectedAction,match='unread_query'):
        e.step(dict(action='SEARCH',query='Zephyr'),no_text=True)
    e.step(dict(action='EXPAND',handle=obs['last_hits'][0]),no_text=True)
    assert 'Zephyr' not in str(e.observe(no_text=True))


def test_source_legality_rechecked_at_expand():
    e=make();obs=e.step(dict(action='SEARCH',query='hobby'))
    e.legal=lambda r:False
    with pytest.raises(RejectedAction,match='source_no_longer_legal'):
        e.step(dict(action='EXPAND',handle=obs['last_hits'][0]))


def test_full_action_schema_does_not_accept_private_fields():
    e=make()
    with pytest.raises(RejectedAction,match='action_schema'):
        e.step(dict(action='SEARCH',query='hobby',gold='secret'))


def test_access_budget_and_no_implicit_observation_reads():
    e=make(limits=Limits(accesses=1));before=e.state_hash()
    for _ in range(3):e.observe()
    assert e.state_hash()==before and e.accesses==0
    obs=e.step(dict(action='SEARCH',query='hobby'))
    with pytest.raises(RejectedAction,match='access_budget'):
        e.step(dict(action='EXPAND',handle=obs['last_hits'][0]))


def test_hybrid_existing_interface_validates_score_coverage():
    e=make(semantic_scores=lambda records,query:{r['record_id']:0.5 for r in records},semantic_identity='synthetic-bound')
    assert len(e.step(dict(action='SEARCH',query='hobby'))['last_hits'])==2
    bad=make(semantic_scores=lambda records,query:{'r1':float('nan')},semantic_identity='synthetic-bound')
    with pytest.raises(RejectedAction,match='invalid_hybrid'):
        bad.step(dict(action='SEARCH',query='hobby'))


@pytest.mark.parametrize('policy',POLICIES)
def test_frozen_cpu_baselines_stop_without_reward(policy):
    e=make(nonce=policy);receipt=run_cpu_policy(e,policy)
    assert receipt['reward'] is None and receipt['status']=='pending_generation_and_evaluation'
    assert receipt['accesses']<=4
    if policy=='OneShot':assert receipt['initial_program']


def test_controller_projection_and_strict_parser():
    from metacom_pm.rl1v3.journal.pomdp_memory_prepare import tool_messages,parse_tool_action
    e=make();obs=e.step(dict(action='SEARCH',query='hobby'))
    assert len(tool_messages(obs))==2
    bad=deepcopy(obs);bad['hits'][0]['gold']='secret'
    with pytest.raises(ValueError,match='private hit'):tool_messages(bad)
    assert parse_tool_action('{"action":"STOP"}')=={'action':'STOP'}
    with pytest.raises(ValueError):parse_tool_action('```json\n{"action":"STOP"}\n```')
    with pytest.raises(ValueError):parse_tool_action('{"action":"STOP","thought":"hidden"}')


def test_capitalization_proxy_cannot_strip_possessive_to_unobserved_word():
    e=make([record('r1',"The hobby is Zephyr's class"),record('r2',"A different topic")])
    result=run_cpu_policy(e,'SequentialRule')
    assert result['status']=='pending_generation_and_evaluation'
    searches=[r['action']['query'] for r in result['trace'] if r['action']['action']=='SEARCH']
    assert 'Zephyr' not in searches[1]


def test_oneshot_same_action_domain_precommitted_query_and_handle_rules():
    from metacom_pm.rl1v3.journal.pomdp_memory_proposal import validate_oneshot_plan
    plan='[{"action":"SEARCH","query":"hobby"},{"action":"EXPAND","from_search":0,"hit_rank":1},{"action":"STOP"}]'
    assert len(validate_oneshot_plan(plan,'Find the hobby report'))==3
    with pytest.raises(ValueError,match='initial-only'):
        validate_oneshot_plan('[{"action":"SEARCH","query":"Zephyr"}]','hobby')
    with pytest.raises(ValueError,match='unobserved'):
        validate_oneshot_plan('[{"action":"EXPAND","from_search":0,"hit_rank":0}]','hobby')
    with pytest.raises(ValueError,match='after STOP'):
        validate_oneshot_plan('[{"action":"STOP"},{"action":"SEARCH","query":"hobby"}]','hobby')
