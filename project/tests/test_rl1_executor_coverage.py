from copy import deepcopy

import pytest

from metacom_pm.rl1.executor_coverage import admitted_supplement, merge_accepted
from metacom_pm.rl1.schema import digest


def fixture():
    messages = [{'role': 'user', 'content': 'Hello'}]
    c = dict(index=1, condition='R', split='train', owner='p1', prefix_identity='prefix',
        messages=messages, messages_identity=digest(messages), counts=[0, 1, 1, 0])
    payload = dict(messages=messages, executor_identity='author', seed=17)
    rid = digest(payload)
    req = dict(payload, request_id=rid)
    raw = dict(request_id=rid, runtime_identity='author', text='Hello, what is on your mind?', finish_reason='natural_stop')
    review = dict(request_identity=rid, raw_identity=digest(raw), messages_identity=digest(messages),
        evidence_identity=digest({}), status='accept', rationale='Fixture only.', resource_behavior='appropriate_nonuse',
        checks={'completed': True, 'grounded': True}, unresolved_claims=[])
    job = dict(request_id=rid, index=1, condition='R', split='train', prefix_identity='prefix', seed=17)
    return dict(contract=dict(conditions=[c], seeds=[17, 29]), jobs=[job], requests={rid: req}, raws={rid: raw},
                reviews={rid: review}, evidence=[dict(prefix_identity='prefix', evidence={}, evidence_identity=digest({}))])


def test_individual_acceptance_does_not_require_every_cell_or_positive_use():
    rows = admitted_supplement(**fixture())
    assert len(rows) == 1 and rows[0]['counts'] == [0, 1, 1, 0]
    f = fixture()
    next(iter(f['reviews'].values()))['status'] = 'uncertain'
    assert admitted_supplement(**f) == []


@pytest.mark.parametrize('fault', ['missing_review', 'changed_seed', 'changed_response', 'unresolved', 'failed_check', 'unfinished', 'private_input', 'test_split'])
def test_invalid_supervision_rejected(fault):
    f = fixture()
    rid = f['jobs'][0]['request_id']
    if fault == 'missing_review': f['reviews'].clear()
    if fault == 'changed_seed': f['jobs'][0]['seed'] = 29
    if fault == 'changed_response': f['raws'][rid]['text'] = 'Altered answer'
    if fault == 'unresolved': f['reviews'][rid]['unresolved_claims'] = ['unknown claim']
    if fault == 'failed_check': f['reviews'][rid]['checks']['grounded'] = False
    if fault == 'unfinished':
        f['raws'][rid]['finish_reason'] = 'context_exhausted'
        f['reviews'][rid]['raw_identity'] = digest(f['raws'][rid])
    if fault == 'private_input': f['requests'][rid]['messages'] = [{'role': 'user', 'content': 'private history'}]
    if fault == 'test_split': f['contract']['conditions'][0]['split'] = 'test'
    with pytest.raises(ValueError): admitted_supplement(**f)


def test_exact_duplicates_keep_both_origins_without_double_weight():
    first = admitted_supplement(**fixture())[0]
    duplicate = dict(first, request_id='other-seed')
    dev = dict(first, request_id='dev', owner='p2', split='dev', response='Another answer', response_identity=digest('Another answer'))
    rows, dup = merge_accepted([first], [duplicate, dev])
    assert len(rows) == 2 and rows[0]['duplicate_request_ids'] == ['other-seed']
    assert dup[0]['duplicate_request_id'] == 'other-seed'


@pytest.mark.parametrize('fault', ['cross_split_duplicate', 'owner_leakage', 'same_request_twice'])
def test_union_never_hides_split_or_provenance_errors(fault):
    first = admitted_supplement(**fixture())[0]
    dev = dict(first, request_id='dev', owner='p2', split='dev', response='Another answer', response_identity=digest('Another answer'))
    if fault == 'cross_split_duplicate': dev.update(response=first['response'], response_identity=first['response_identity'])
    if fault == 'owner_leakage': dev['owner'] = first['owner']
    if fault == 'same_request_twice': dev['request_id'] = first['request_id']
    with pytest.raises(ValueError): merge_accepted([first], [dev])
