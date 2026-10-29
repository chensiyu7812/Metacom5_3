from dataclasses import asdict, replace
import json
import pytest

from metacom_pm.rl1.schema import PrefixSpec, PublicTurn, digest
from metacom_pm.rl1.resource_organization import (
    OrganizedItem, OrganizationCatalog, OrganizedRenderer, OrganizationSession,
)


def prefix():
    return PrefixSpec('owner','now',3,0,'2026-01-03','train',(PublicTurn('seeker','Need support'),))


def item(key,head='MS',text='complete historical text',rank=1):
    field={'MS':'full_source_conversation','MP':'past_report','ME':'past_report','RS':'ai_action'}[head]
    body={'kind':head,field:text}
    if head=='MP':body['profile_slot']='activity'
    return OrganizedItem(key,head,json.dumps(body),text,digest(body),
        None if head=='RS' else 'owner',None if head=='RS' else 1,
        None if head=='RS' else '2026-01-01',('source-'+key,),rank,.9)


def renderer(limit=100000):
    return OrganizedRenderer(count_text=len,count_chat=lambda m:sum(len(x['content']) for x in m),
                             tokenizer_identity='synthetic-character-counter',context_limit=limit)


def catalog(items):
    return OrganizationCatalog(prefix(),items,provenance_identity='fixture')


def test_addressable_rank_three_needs_no_prefix_and_no_2048_cap():
    items=[item('one',text='A'*3000,rank=1),item('two',rank=2),item('three',text='C'*3000,rank=3)]
    c=catalog(items);s=OrganizationSession(c,renderer())
    obs=s.read('three')
    assert obs.resource_tokens>2048 and obs.counts==(0,0,1,0)
    assert obs.acquired[0][1]==items[2].content
    assert s.receipt()['acquired']==['three']
    assert items[0].content not in str(asdict(obs))
    assert s.receipt()['reward'] is None and s.receipt()['formal_policy_compatible'] is False


def test_more_than_four_reads_and_all_candidates_remain_available():
    c=catalog([item(str(i),text='session '+str(i),rank=i+1) for i in range(6)])
    s=OrganizationSession(c,renderer())
    assert len(c.rank('MS'))==6
    for i in range(6):s.read(str(i))
    assert s.observe().counts[2]==6
    assert c.rank('MS',tuple(str(i) for i in range(6)))==[]
    with pytest.raises(ValueError):s.get('MS')
    with pytest.raises(ValueError):s.read('0')


def test_native_context_failure_is_atomic_and_never_clips():
    c=catalog([item('long',text='X'*10000)])
    r=renderer();empty=r.usage(c,())['input_tokens']
    s=OrganizationSession(c,renderer(empty+100))
    with pytest.raises(ValueError,match='native context'):s.read('long')
    assert not s.observe().acquired and s.receipt()['acquired']==[]
    assert c.item('long').content.endswith('X"}')


def test_next_query_changes_only_after_reading_and_no_graph_free_text():
    c=catalog([item('a','RS','kindness'),item('z','RS','cycling'),item('profile','MP','cycling')])
    assert c.rank('RS')[0]['key']=='a'
    s=OrganizationSession(c,renderer())
    assert 'cycling' not in str(asdict(s.observe()))
    s.get('MP')
    result=c.rank('RS',tuple(s.receipt()['acquired']))
    assert result[0]['key']=='z'
    assert result[0]['bge_similarity']==.9 and result[0]['ranking_method']!='BGE'
    assert 'source-profile' not in str(asdict(s.observe()))
    assert not hasattr(s.observe(),'catalog') and not hasattr(s.observe(),'owner_id')
    s.get('RS'); assert s.observe().counts==(1,1,0,0)
    s.stop()
    with pytest.raises(ValueError):s.get('ME')


@pytest.mark.parametrize('change',[dict(owner_id='other'),dict(source_rank=3),dict(reported_at='2026-01-04')])
def test_owner_and_time_remain_hard_boundaries(change):
    with pytest.raises(ValueError):catalog([replace(item('bad'),**change)])


def test_test_prefix_and_duplicate_addresses_rejected():
    with pytest.raises(ValueError):OrganizationCatalog(replace(prefix(),split='test'),[],provenance_identity='x')
    with pytest.raises(ValueError):catalog([item('same'),item('same')])


def test_directory_groups_do_not_invent_updates_results_or_fit_labels():
    c=catalog([item('p','MP'),item('e','ME'),item('s','MS'),item('r','RS')])
    d=c.directory()
    assert d['MP_slots']['activity'][0]['current_status']=='unknown'
    assert d['ME_events'][0]['stage']=='unknown' and d['ME_events'][0]['outcome'] is None
    assert d['MS_sessions'][0]['summary'] is None
    assert d['semantic_updates_or_contradictions']==[]
    assert d['applicability_conditions_created']==0
    assert all(e['semantic_entailment']=='unverified' for e in d['structural_edges'])


def test_canonical_rendering_preserves_native_user_and_complete_history():
    p=replace(prefix(),turns=(PublicTurn('seeker','past question'),PublicTurn('supporter','historical support'),PublicTurn('seeker','latest')),
              cut_after_turn_index=2)
    c=OrganizationCatalog(p,[item('b'),item('a')],provenance_identity='x');r=renderer()
    assert r.messages(c,('a','b'))==r.messages(c,('b','a'))
    assert r.messages(c,())[1]=={'role':'user','content':'latest'}
    assert 'historical support' in r.messages(c,())[0]['content']
    assert '"source-a"' not in r.messages(c,('a',))[0]['content']
    with pytest.raises(ValueError):r.messages(c,('a','a'))
