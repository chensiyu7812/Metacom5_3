"""Protect source binding, missingness and blindness of reference-guided review."""
from copy import deepcopy
import json
import socket

import pytest

from metacom_pm.rl1.feedback_reference_review import compare_reference, prepare_bound_review
from metacom_pm.rl1.schema import digest
import test_rl1_development_feedback as fixtures


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('offline review attempted network')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)


def inputs(unknown=False):
    adapter = fixtures.adapter()
    item = {k:fixtures.materials(1)[0][k] for k in ('reply', 'evidence')}
    request = adapter.prepare(item, 'S')
    raw = fixtures.Transport(unknown=unknown).send(request, attempt_id='synthetic')
    ref = dict(asset_id='SYNTHETIC-LOCAL-ONLY-ANSWER', task_family='singles',
        evidence_identity=digest(item['evidence']), reply_identity=digest(item['reply']),
        q_status='range', q_min=2, q_max=3, q_value=None, m_value=.25,
        raw_label=dict(reason='SYNTHETIC-PRIVATE-HUMAN-REASON'))
    return adapter, item, request, raw, ref


def test_same_utility_does_not_hide_misuse_disagreement_or_invent_midpoint():
    *_, ref = inputs()
    result = compare_reference(dict(q=2, m=0), ref)
    assert result['q_interval'] == [2, 3] and result['U_interval'] == [.25, .5]
    assert result['q_agrees'] is True and result['m_agrees'] is False
    assert result['U_in_interval'] is True and result['utility_hides_component_disagreement'] is True
    assert result['replacement_score'] is None
    for q in (2, 3):
        assert compare_reference(dict(q=q, m=.25), ref)['disposition'] == 'components_match'


def test_known_references_do_not_enter_or_change_existing_audit_request():
    adapter, item, request, raw, ref = inputs()
    before = deepcopy((item,request,raw,ref))
    absent = prepare_bound_review(adapter,item,request,raw,[])
    attached = prepare_bound_review(adapter,item,request,raw,[ref])
    assert attached['request'] == absent['request']
    wire = json.dumps(attached['request']['wire_body'])
    assert ref['asset_id'] not in wire and ref['raw_label']['reason'] not in wire
    assert attached['local_review']['original_references'] == [ref]
    assert not attached['local_review']['qualified_reward']
    assert (item,request,raw,ref) == before


def test_uncertain_primary_stays_missing_but_is_a_valid_existing_audit_input():
    adapter, item, request, raw, ref = inputs(unknown=True)
    result = prepare_bound_review(adapter,item,request,raw,[ref])
    assert result['local_review']['candidate'] is None
    assert result['local_review']['comparisons'][0]['q_agrees'] is None
    assert result['request']['component'] == 'A'


@pytest.mark.parametrize('change', ['evidence', 'reply', 'reference', 'raw_binding', 'partial_raw'])
def test_changed_input_wrong_reference_and_incomplete_raw_fail_closed(change):
    adapter, item, request, raw, ref = inputs()
    if change == 'evidence':
        item['evidence']['current_date'] = '2099-01-01'
    elif change == 'reply':
        item['reply'] += ' Changed.'
    elif change == 'reference':
        ref['evidence_identity'] = 'wrong full evidence'
    elif change == 'raw_binding':
        raw['request_identity'] = 'another primary'
    else:
        raw['choices'][0]['finish_reason'] = 'length'
    with pytest.raises(ValueError):
        prepare_bound_review(adapter,item,request,raw,[ref])


def test_clarification_is_retained_without_becoming_an_additional_numeric_label():
    adapter, item, request, raw, ref = inputs()
    supplement = {k:ref[k] for k in ('evidence_identity', 'reply_identity')}
    supplement.update(asset_id='prior-clarification', task_family='supplements',
                      raw_label=dict(verbatim='SYNTHETIC original clarification'))
    result = prepare_bound_review(adapter,item,request,raw,[ref,supplement])
    assert len(result['local_review']['comparisons']) == 1
    assert len(result['local_review']['original_references']) == 2
    assert result['local_review']['new_human_question'] is None
