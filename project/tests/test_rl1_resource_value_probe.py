import json
from dataclasses import replace
import pytest

from metacom_pm.rl1.resource_organization import OrganizedItem
from metacom_pm.rl1.resource_value_probe import match_session, turn_layout


def fixture():
    turns=[dict(id='H001:T000',role='supporter',text='I had a difficult day.\nseeker: quoted text, not a new turn'),
           dict(id='H001:T001',role='seeker',text='I hope to talk with them; I have not done it yet.')]
    ev=dict(current_date='2025-02-01',legal_past_sessions=[dict(id='H001',date='2025-01-01',turns=turns)])
    raw='\n'.join(t['role']+': '+t['text'] for t in turns)
    item=OrganizedItem(key='x',head='MS',content=json.dumps(dict(kind='MS',full_source_conversation=raw)),
        search_text=raw,source_identity='original',reported_at='2025-01-01',source_ids=('session',))
    return item,ev


def test_complete_view_preserves_embedded_newline_roles_and_modal_claim():
    item,ev=fixture();changed,receipt=turn_layout(item,ev);body=json.loads(changed.content)
    assert [x[2] for x in body['turns']]==[t['text'] for t in ev['legal_past_sessions'][0]['turns']]
    assert body['turns'][0][1]=='supporter' and len(body['turns'])==2
    assert changed.key==item.key and changed.source_ids==item.source_ids
    assert changed.source_identity!=item.source_identity and receipt['reward'] is None


def test_partial_or_foreign_transcript_cannot_be_relabelled_as_full_source():
    item,ev=fixture();body=json.loads(item.content);body['full_source_conversation']=body['full_source_conversation'][:30]
    with pytest.raises(ValueError,match='complete legal session'):match_session(replace(item,content=json.dumps(body)),ev)
    with pytest.raises(ValueError,match='complete legal session'):match_session(replace(item,reported_at='2025-01-02'),ev)


def test_duplicate_and_future_sources_rejected():
    item,ev=fixture();ev['legal_past_sessions']*=2
    with pytest.raises(ValueError,match='uniquely'):match_session(item,ev)
    ev['legal_past_sessions']=ev['legal_past_sessions'][:1];ev['current_date']='2024-12-01'
    with pytest.raises(ValueError,match='future'):match_session(item,ev)
