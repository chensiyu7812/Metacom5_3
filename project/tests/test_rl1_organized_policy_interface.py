from dataclasses import asdict, replace
import json

import pytest

from metacom_pm.rl1.schema import Action, PrefixSpec, PublicTurn, digest
from metacom_pm.rl1.resource_organization import OrganizedItem, OrganizationCatalog, OrganizedRenderer
from metacom_pm.rl1.organized_policy_interface import HeadSession, commit_program, replay_program
from metacom_pm.rl1.organized_features import FullTextFeatures


def item(key, head='MS', text='complete evidence', rank=1):
    field = {'RS':'ai_action', 'MP':'past_report', 'ME':'past_report', 'MS':'full_source_conversation'}[head]
    body = {'kind':head, field:text}
    if head == 'MP': body['profile_slot'] = 'interest'
    return OrganizedItem(key, head, json.dumps(body), text, digest(body),
        None if head == 'RS' else 'private-owner', None if head == 'RS' else 1,
        None if head == 'RS' else '2026-01-01', ('private-source-'+key,), rank, .9)


def setup(items, *, limit=100000):
    prefix = PrefixSpec('private-owner','now',3,0,'2026-01-03','train',(PublicTurn('seeker','need help'),))
    catalog = OrganizationCatalog(prefix,items,provenance_identity='private-catalog-binding')
    renderer = OrganizedRenderer(count_text=len,count_chat=lambda m:sum(len(x['content']) for x in m),
        tokenizer_identity='synthetic-character-count',context_limit=limit)
    return catalog, renderer


def feature_encoder(window=19):
    return FullTextFeatures(encode_tokens=lambda s:list(s.encode()), add_special_tokens=lambda ids:[300]+ids+[301],
        native_window=window,special_tokens=2,tokenizer_identity='synthetic-bytes-not-BGE',encoder_identity='fixture',dimension=2)


def vectors(plan):
    return [[sum(c['input_ids'])/len(c['input_ids']), float(c['end_token'])] for d in plan['documents'] for c in d['chunks']]


def test_six_reads_no_2048_or_four_slot_limit_and_oneshot_same_terminal():
    c,r=setup([item(str(i),text='x'*500,rank=i+1) for i in range(6)])
    sequential=HeadSession(c,r); programmed=HeadSession(c,r)
    actions=(Action.GET_MS,)*6+(Action.STOP,)
    program=commit_program(programmed.observe(),actions,interface_identity=programmed.interface_identity)
    for a in actions:sequential.step(a)
    replay_program(programmed,program)
    assert sequential.observe().counts==(0,0,6,0)
    assert sequential.observe().resource_tokens>2048
    x=sequential.terminal(executor_identity='original-G',draw_identity='same-draw')
    y=programmed.terminal(executor_identity='original-G',draw_identity='same-draw')
    assert x['identity']==y['identity'] and x['messages']==y['messages']
    assert x['reward'] is None and not x['measurement_qualified'] and x['model_calls']==0
    with pytest.raises(ValueError,match='masked'):sequential.step(Action.GET_MS)


def test_read_then_retrieve_uses_acquired_body_but_observation_has_no_unread_body():
    c,r=setup([item('a','RS','kindness'),item('z','RS','cycling'),item('p','MP','cycling')])
    s=HeadSession(c,r)
    initial=json.dumps(asdict(s.observe()))
    for secret in ('cycling','private-owner','private-source','catalog_identity','selected_keys'):
        assert secret not in initial
    s.step(Action.GET_MP);s.step(Action.GET_RS);s.step(Action.STOP)
    assert s.terminal(executor_identity='g',draw_identity='d')['selected_keys']==['z','p']


def test_notext_is_persistent_and_generator_receives_same_complete_resources():
    c,r=setup([item('p','MP','cycling'),item('z','RS','cycling')])
    full,hidden=HeadSession(c,r),HeadSession(c,r,without_text=True)
    for action in (Action.GET_MP,Action.GET_RS):
        fo=full.step(action);ho=hidden.step(action,expected_observation=digest(asdict(hidden.observe())))
        assert fo.action_mask==ho.action_mask and fo.counts==ho.counts
        assert all(x.content is None for x in ho.acquired)
        assert 'cycling' not in json.dumps(asdict(ho))
        e=feature_encoder();p=e.plan(ho)
        assert len(p['documents'])==1
        features=e.assemble(ho,p,vectors=vectors(p),encoder_feature_identity=e.identity)
        assert features['values'][2:10]==(0.,)*8
    full.step(Action.STOP);hidden.step(Action.STOP)
    assert full.terminal(executor_identity='g',draw_identity='d')['identity']==hidden.terminal(executor_identity='g',draw_identity='d')['identity']


def test_native_mask_rejects_whole_top_item_without_skipping_or_partial_read():
    c,r=setup([item('a',text='need help '+'X'*10000),item('z',text='small')])
    limit=r.usage(c,())['input_tokens']+500
    c,r=setup(list(c._items.values()),limit=limit)
    s=HeadSession(c,r);before=s.observe()
    assert before.remaining_items[2]==2 and not before.action_mask[Action.GET_MS]
    with pytest.raises(ValueError,match='masked'):s.step(Action.GET_MS)
    assert s.observe()==before


def test_stale_action_and_program_from_other_prefix_fail_closed():
    c,r=setup([item('p','MP')]);s=HeadSession(c,r);initial=s.observe()
    p=commit_program(initial,(Action.GET_MP,Action.STOP),interface_identity=s.interface_identity)
    s.step(Action.GET_MP)
    with pytest.raises(ValueError,match='stale'):s.step(Action.STOP,expected_observation=digest(asdict(initial)))
    with pytest.raises(ValueError):replay_program(s,p)
    with pytest.raises(ValueError):commit_program(s.observe(),(Action.STOP,),interface_identity=s.interface_identity)


@pytest.mark.parametrize('actions',[(1,), (0,1,0), (False,), (9,0), ()])
def test_program_must_have_valid_actions_and_one_terminal_stop(actions):
    c,r=setup([]);s=HeadSession(c,r)
    with pytest.raises(ValueError):commit_program(s.observe(),actions,interface_identity=s.interface_identity)


def test_all_text_chunks_tail_included_and_missing_vector_never_zero_filled():
    c,r=setup([item('p','MP','start '+'tail-evidence '*80)])
    s=HeadSession(c,r);o=s.step(Action.GET_MP);e=feature_encoder();p=e.plan(o)
    d=p['documents'][1]
    restored=[i for chunk in d['chunks'] for i in chunk['input_ids'][1:-1]]
    assert restored==d['payload_ids'] and len(d['chunks'])>4
    vs=vectors(p);first=e.assemble(o,p,vectors=vs,encoder_feature_identity=e.identity)
    vs[-1][0]+=100
    second=e.assemble(o,p,vectors=vs,encoder_feature_identity=e.identity)
    assert first['values']!=second['values']
    with pytest.raises(ValueError,match='every chunk'):e.assemble(o,p,vectors=vs[:-1],encoder_feature_identity=e.identity)
    with pytest.raises(ValueError,match='identity'):e.assemble(o,p,vectors=vs,encoder_feature_identity='old-four-slot')
    p['documents'][1]['chunks'].pop()
    with pytest.raises(ValueError,match='plan'):e.assemble(o,p,vectors=vs,encoder_feature_identity=e.identity)


def test_all_six_resources_affect_pool_and_old_observation_rejected():
    c,r=setup([item(str(i),text='item '+str(i)) for i in range(6)])
    s=HeadSession(c,r)
    for _ in range(6):o=s.step(Action.GET_MS)
    e=feature_encoder();p=e.plan(o)
    assert len(p['documents'])==7
    vs=vectors(p);x=e.assemble(o,p,vectors=vs,encoder_feature_identity=e.identity)
    assert len(x['values'])==e.feature_dimension
    assert x['encoded_payload_tokens']==sum(len(d['payload_ids']) for d in p['documents'])
    with pytest.raises(TypeError):e.plan(asdict(o))


def test_special_token_builder_cannot_drop_or_reorder_payload():
    c,r=setup([]);o=HeadSession(c,r).observe();e=feature_encoder()
    e.add_special_tokens=lambda ids:[300]+list(reversed(ids))+[301]
    with pytest.raises(ValueError,match='special-token'):e.plan(o)


def test_new_features_drive_shared_five_action_actor_without_optimizer():
    import torch
    from metacom_pm.rl1.observation_features import make_actor_critic
    c,r=setup([item('p','MP')]);o=HeadSession(c,r).observe();e=feature_encoder();p=e.plan(o)
    features=e.assemble(o,p,vectors=vectors(p),encoder_feature_identity=e.identity)
    model=make_actor_critic(e.feature_dimension)
    with torch.no_grad():
        distribution,value=model(torch.tensor([features['values']],dtype=torch.float32),
            torch.tensor([features['action_mask']],dtype=torch.bool))
    assert value.shape==(1,) and torch.isfinite(value).all()
    assert distribution.probs[0,2]>0 and distribution.probs[0,0]>0
    assert distribution.probs[0,[1,3,4]].sum()==0
