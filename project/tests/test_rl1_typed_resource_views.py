"""Failure cases that could otherwise create false memory evidence."""
from dataclasses import replace
import json

import pytest

from metacom_pm.rl1.schema import PrefixSpec, PublicTurn
from metacom_pm.rl1.resource_organization import OrganizedItem
from metacom_pm.rl1.typed_resource_views import source_view


def fixture():
    prefix = PrefixSpec(owner_id='owner', session_id='now', cutoff_rank=2,
                        cut_after_turn_index=0, timestamp='2025-03-01', split='train',
                        turns=(PublicTurn('seeker', 'What about that plan?'),))
    turns = [dict(role='seeker', text='I might call tomorrow.'),
             dict(role='supporter', text='Only if you want to.'),
             dict(role='seeker', text='I have not decided.'),
             dict(role='supporter', text='We can leave it there.')]
    parent = OrganizedItem('ms', 'MS', json.dumps(dict(kind='MS',
        full_source_conversation='\n'.join(t['role']+': '+t['text'] for t in turns))),
        '', 'src', 'owner', 1, '2025-02-01', ('session',))
    item = OrganizedItem('me', 'ME', json.dumps(dict(kind='ME',
        past_report='completed a call', action_stage='completed', observed_outcome=None,
        evidence=[dict(turn_index=0, speaker='seeker', start_char=0, end_char=22,
                       quote='I might call tomorrow.')])) , '', 'unit', 'owner', 1,
        '2025-02-01', ('unit', 'session'))
    evidence = dict(current_date=prefix.timestamp,
        legal_past_sessions=[dict(id='H001', date='2025-02-01', turns=turns)])
    return prefix, item, parent, evidence


def test_does_not_promote_compiler_completion_or_hide_omissions():
    p, item, parent, ev = fixture()
    view = source_view(p, [item], [item, parent], ev)
    assert 'completed a call' not in json.dumps(view['compact'])
    assert view['compact']['sessions'][0]['omitted_turns'] == 2
    assert len(view['full']['sessions'][0]['turns']) == 4
    assert view['bindings'][0]['original_compiler_statement'] == 'completed a call'


@pytest.mark.parametrize('change', ['wrong_role', 'wrong_quote', 'future', 'other_owner'])
def test_rejects_false_source_bindings(change):
    p, item, parent, ev = fixture()
    if change in ('wrong_role', 'wrong_quote'):
        body = json.loads(item.content)
        body['evidence'][0]['speaker' if change == 'wrong_role' else 'quote'] = 'supporter' if change == 'wrong_role' else 'I called.'
        item = replace(item, content=json.dumps(body))
    elif change == 'future':
        item = replace(item, source_rank=p.cutoff_rank)
    else:
        item = replace(item, owner_id='someone_else')
    with pytest.raises(ValueError):
        source_view(p, [item], [item, parent], ev)


def test_shared_parent_is_charged_once_without_inferred_event_join():
    p, item, parent, ev = fixture()
    other = replace(item, key='another_me')
    view = source_view(p, [item, other], [item, other, parent], ev)
    assert len(view['compact']['sessions']) == len(view['full']['sessions']) == 1
    assert view['shared_source_count'] == 1
    assert view['semantic_relations_created'] == 0


def test_declared_raw_turn_id_is_not_treated_as_blinded_ordinal():
    p, item, parent, ev = fixture()
    body = json.loads(item.content); body['evidence'][0]['turn_index'] = 1
    view = source_view(p, [replace(item, content=json.dumps(body))], [parent], ev)
    assert view['bindings'][0]['evidence_turns'] == [0]
    assert view['bindings'][0]['original_declared_turn_ids'] == [1]


def test_ambiguous_exact_quote_is_not_silently_attached():
    p, item, parent, ev = fixture()
    turns = ev['legal_past_sessions'][0]['turns']
    turns.append(dict(turns[0]))
    parent = replace(parent, content=json.dumps(dict(kind='MS',
        full_source_conversation='\n'.join(t['role']+': '+t['text'] for t in turns))))
    with pytest.raises(ValueError, match='quote/role/offset'):
        source_view(p, [item], [parent], ev)
