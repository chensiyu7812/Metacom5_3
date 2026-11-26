"""GE2 meaningful synthetic CPU boundaries; no raw source, gold, model or GPU."""
from copy import deepcopy
from types import SimpleNamespace
import pytest

from metacom_pm.rl1v3.io import object_sha256
from metacom_pm.rl1v3.journal.ge2_memory import GE2Episode, Limits, RejectedAction
from metacom_pm.rl1v3.journal.ge2_retrieval import SharedRetrieval, RetrievalConfig, union_intervals


class Clock:
    boot_id = 'synthetic-boot'
    now = 1000000000
    def now_ns(self):
        return self.now


class Tokenizer:
    identity = 'synthetic-native-tokenizer'
    def count(self, text):
        return len(text.split())
    def make_packet(self, views=()):
        texts = [v.reading_text for v in views]
        return SimpleNamespace(input_ids=[0] * (5 + sum(self.count(t) for t in texts)),
                               payload_sha256=object_sha256(texts))


def test_effective_job_deadline_limits_visible_remaining_time_and_acquisition():
    clock = Clock()
    e = episode(clock=clock, deadline_ns=clock.now + 350_000_000_000)
    first = e.observe()
    assert first['decision_time']['agent_seconds_remaining'] == 350
    assert first['decision_time']['acquisition_seconds_remaining'] == 50
    clock.now += 51_000_000_000
    assert e.observe()['action_mask'] == ['STOP']
    with pytest.raises(RejectedAction, match='time_reserve'):
        search(e)
    e.step({'action': 'STOP'})


def test_deadline_changes_decision_identity_but_not_same_evidence_payload():
    a = episode(deadline_ns=401_000_000_000)
    b = episode(deadline_ns=501_000_000_000)
    assert a.content_hash() != b.content_hash()
    search(a); search(b)
    assert a.packet().payload_sha256 == b.packet().payload_sha256


def record(rid='r1', rank=0, owner='allowed', texts=None):
    texts = texts or ['Beginning context.', 'Do you plan to paint?', 'I have not started.',
                      'Another background turn.', 'Later separate topic.', 'I finished the reading.']
    return dict(record_id=rid, head='MS', view='raw', owner_id=owner,
        parent_session_id='parent-'+rid, source_rank=rank,
        reported_at=dict(date='2020-01-'+str(rank+1).zfill(2), session_rank=rank),
        reading_text='WRAPPER unseen irrelevant metadata\n'+'\n'.join(texts),
        source_refs=[dict(turn_index=i, speaker='supporter' if i % 2 else 'seeker', exact_quote=t)
                     for i, t in enumerate(texts)])


def episode(records=None, *, clock=None, nonce='first', limits=Limits(), **kw):
    text = 'Tell me what is known about my plan.'
    task = dict(task_id='synthetic', timestamp='2020-02-01', turns=[dict(role='seeker', text=text)],
                query=text, view_protocol='synthetic', channel='synthetic')
    return GE2Episode(task=task, records=[record()] if records is None else records,
        tokenizer=Tokenizer(), legal=lambda r:r['owner_id']=='allowed' and r['source_rank']<10,
        episode_nonce=nonce, clock=clock or Clock(), limits=limits, **kw)


def search(e, query='paint', unread=True, **kw):
    return e.step(dict(action='SEARCH', query=query, unread_only=unread), **kw)


def test_semantic_new_query_permitted_without_asserting_fact():
    e=episode();obs=search(e,'activity status')
    assert e.accesses==1 and not obs['belief']['query_terms_are_evidence']
    assert 'activity status' not in e.packet().__dict__.get('text','')
    assert obs['belief']['status']=='unassessed'


@pytest.mark.parametrize('bad',[record(owner='foreign'),record(rank=10)])
def test_owner_future_pool_rejected(bad):
    with pytest.raises(ValueError,match='illegal source'):episode([bad])


def test_legality_revalidated_after_construction():
    e=episode();e.legal=lambda r:False
    with pytest.raises(RejectedAction,match='source_no_longer_legal'):search(e)
    assert e.accesses==1 and not e.read_intervals


@pytest.mark.parametrize('backend',['time_lexical','bm25'])
def test_parent_pool_top4_roles_and_fixed_context(backend):
    records=[record('r'+str(i),rank=i) for i in range(6)]
    ranker=SharedRetrieval(records,RetrievalConfig(backend=backend))
    units=ranker.search('paint')
    assert len(units)==4 and len({u['record_id'] for u in units})==4
    assert all(u['anchor_turn']==1 and (u['start_turn'],u['end_turn'])==(0,2) for u in units)
    assert all([r['speaker'] for r in u['source_refs']]==['seeker','supporter','seeker'] for u in units)
    assert all('WRAPPER' not in text for text in ranker.documents.values())


def test_unread_exclusion_happens_before_anchor_selection():
    ranker=SharedRetrieval([record()])
    first=ranker.search('paint')[0]
    second=ranker.search('paint',read_intervals={'r1':[[0,2]]})[0]
    assert first['anchor_turn']==1 and second['anchor_turn']!=1
    assert any(r['turn_index']>2 for r in second['source_refs'])
    assert ranker.search('paint',read_intervals={'r1':[[0,5]]})==[]
    assert ranker.search('paint',read_intervals={'r1':[[0,5]]},unread_only=False)


def test_versioned_handle_new_window_and_provenance():
    e=episode();first=search(e)['last_hits'][0]
    second=search(e,'finished')['last_hits'][0]
    assert first.endswith(':v1') and second.endswith(':v2') and first!=second
    assert e.handles[first]['anchor_turn']!=e.handles[second]['anchor_turn']
    f=episode(nonce='another');search(f)
    with pytest.raises(RejectedAction,match='foreign_handle'):
        f.step(dict(action='EXPAND',handle=first,scope='parent'))


def test_neighbor_then_parent_union_and_duplicate_charge():
    e=episode();h=search(e)['last_hits'][0]
    obs=e.step(dict(action='EXPAND',handle=h,scope='neighbor'))
    assert e.read_intervals=={'r1':[[0,3]]}
    h2=obs['last_hits'][0]
    e.step(dict(action='EXPAND',handle=h2,scope='parent'))
    before=e.receipt()
    e.step(dict(action='EXPAND',handle=h2,scope='parent'))
    after=e.receipt()
    assert after['content_payload_sha256']==before['content_payload_sha256']
    assert after['accesses']==before['accesses']+1
    assert after['cumulative_materialized_tokens']>before['cumulative_materialized_tokens']
    assert after['canonical_source_tokens']==before['canonical_source_tokens']
    obs=e.observe();assert len(obs['readings'])==1
    assert obs['readings'][0]['reading_text'].count('I have not started.')==1
    assert all('reading_text' not in item and 'expanded_text' not in item for item in obs['hits'])


def test_chronological_render_and_same_payload_across_policy_nonces():
    rows=[record('late',rank=5),record('early',rank=0)]
    a=episode(rows,nonce='a');b=episode(rows,nonce='b')
    search(a);search(b)
    dates=[r['reported_at']['date'] for r in a.observe()['readings']]
    assert dates==sorted(dates)
    assert a.packet().payload_sha256==b.packet().payload_sha256
    assert a.last_hits!=b.last_hits


def test_direct_interval_render_is_pure_and_legal():
    e=episode();before=e.content_hash()
    a=e.render_intervals({'r1':[[0,2],[1,4]]})
    b=e.render_intervals({'r1':[[0,4]]})
    assert a==b and e.content_hash()==before and e.accesses==0
    with pytest.raises(RejectedAction,match='foreign_interval'):
        e.render_intervals({'missing':[[0,1]]})
    with pytest.raises(RejectedAction,match='coordinate'):
        e.render_intervals({'r1':[[0,99]]})


def test_snapshot_changes_with_elapsed_content_does_not_and_action_stays_legal():
    clock=Clock();e=episode(clock=clock)
    before=e.observe();clock.now+=10_000_000
    after=e.observe()
    assert before['content_sha256']==after['content_sha256']
    assert before['snapshot_sha256']!=after['snapshot_sha256']
    search(e,expected_content_hash=before['content_sha256'])
    with pytest.raises(RejectedAction,match='stale_content'):
        e.step(dict(action='STOP'),expected_content_hash=before['content_sha256'])


def test_full_state_hash_binds_last_hits_and_handle_order():
    e=episode([record('a'),record('b',rank=1)]);search(e)
    before=e.content_hash();e.last_hits.reverse()
    assert before!=e.content_hash()
    before=e.content_hash();e.handles=dict(reversed(list(e.handles.items())))
    assert before!=e.content_hash()


def test_no_text_observation_masks_exact_evidence_but_keeps_handles_budget():
    e=episode();search(e)
    obs=e.observe(no_text=True)
    assert 'I have not started.' not in str(obs) and 'readings' not in obs
    assert obs['last_hits'] and obs['readings_metadata'] and obs['access_budget']['used']==1


def test_time_reserve_mask_and_stop_remains_legal():
    clock=Clock();e=episode(clock=clock);clock.now+=301_000_000_000
    assert e.observe()['action_mask']==['STOP']
    with pytest.raises(RejectedAction,match='time_reserve'):search(e)
    e.step(dict(action='STOP'));assert e.reward is None
    with pytest.raises(RejectedAction,match='after_stop'):e.step(dict(action='STOP'))


def test_capacity_refusal_has_access_cost_no_evidence_commit():
    e=episode(limits=Limits(delivered_tokens=1))
    with pytest.raises(RejectedAction,match='token_budget'):search(e)
    assert e.accesses==1 and e.materialized_tokens>0 and not e.read_intervals
    assert e.observe()['action_mask']==['STOP']
    e.step(dict(action='STOP'))
    assert e.receipt()['formal_reward'] is None


def test_control_budget_and_payload_input_injection_rejected():
    e=episode();before=e.content_hash();e.set_control_usage(calls=1,output_tokens=3)
    assert e.content_hash()!=before
    with pytest.raises(RejectedAction,match='controller_budget'):
        e.set_control_usage(calls=0,output_tokens=0)
    with pytest.raises(RejectedAction,match='action_schema'):
        e.step(dict(action='SEARCH',query='paint',unread_only=True,gold='private'))
    assert e.accesses==0


def test_access_budget_is_attempt_budget_and_empty_search_is_recorded():
    e=episode([record(texts=['one'])],limits=Limits(accesses=2))
    search(e);search(e)
    assert e.trace[-1]['result']=='no_unread_hit' and e.accesses==2
    with pytest.raises(RejectedAction,match='access_budget'):search(e)
    e.step(dict(action='STOP'))


def test_record_reordering_and_bm25_config_are_deterministic():
    rows=[record('a'),record('b',rank=1)]
    a=SharedRetrieval(rows,RetrievalConfig(backend='bm25'))
    b=SharedRetrieval(list(reversed(rows)),RetrievalConfig(backend='bm25'))
    assert a.identity==b.identity and a.search('paint')==b.search('paint')
    with pytest.raises(ValueError,match='fixed retrieval'):RetrievalConfig(bm25_b=.5)
    assert union_intervals([[2,4],[0,2],[6,8],[5,5]])==[[0,8]]


def test_mutated_bound_record_is_integrity_failure_not_new_fact():
    e=episode();e.records['r1']['source_refs'][0]['exact_quote']='Mutated body'
    with pytest.raises(RejectedAction,match='changed_after_binding'):search(e)
    assert not e.read_intervals


def test_same_source_intervals_have_backend_independent_terminal_bytes():
    a=episode(retrieval_config=RetrievalConfig(backend='time_lexical'))
    b=episode(retrieval_config=RetrievalConfig(backend='bm25'))
    av=a.render_intervals({'r1':[[0,5]]});bv=b.render_intervals({'r1':[[0,5]]})
    assert av==bv
    assert a.tokenizer.make_packet(av).payload_sha256==b.tokenizer.make_packet(bv).payload_sha256
