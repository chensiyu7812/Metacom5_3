import pytest

from metacom_pm.rl1v3.journal.c1_dimensions import (
    compare, conjunction, paired_delta, quote_offsets, support_bounds,
)


def test_unknown_is_not_zero_and_failure_dominates():
    assert conjunction([[1, 1], [0, 1]]) == [0, 1]
    assert conjunction([[0, 0], [0, 1]]) == [0, 0]
    assert support_bounds(['pass', 'uncertain']) == [0, 1]
    assert support_bounds(['fail', 'uncertain']) == [0, 0]


def test_bad_or_empty_evidence_domain_is_rejected():
    for values in ([], [[1, 0]], [[0, 2]]):
        with pytest.raises(ValueError):
            conjunction(values)
    with pytest.raises(ValueError):
        support_bounds(['unknown_new_label'])


def test_shared_unknown_endpoint_cancels_exactly():
    row = dict(request_id='same', fact=[0, 1])
    assert paired_delta(row, row, 'fact') == [0, 0]
    assert paired_delta(row, dict(request_id='different', fact=[0, 1]), 'fact') == [-1, 1]
    with pytest.raises(ValueError):
        paired_delta(row, dict(request_id='same', fact=[1, 1]), 'fact')


def test_evidence_offsets_are_checked_without_rewriting():
    assert quote_offsets('a sample response', ['sample']) == [dict(start=2, end=8, quote='sample')]
    with pytest.raises(ValueError):
        quote_offsets('a sample response', ['Sample'])


def test_pairing_rejects_different_task_order():
    a = dict(task='anon1', request_id='a', fact=[1, 1], support=[1, 1], joint=[1, 1])
    b = dict(task='anon2', request_id='b', fact=[0, 0], support=[1, 1], joint=[0, 0])
    with pytest.raises(ValueError):
        compare([a], [b])


def test_dimensional_tradeoff_is_not_collapsed_to_support_gain():
    ms = dict(task='anon', request_id='a', fact=[1, 1], support=[0, 1], joint=[0, 1])
    c1 = dict(task='anon', request_id='b', fact=[0, 0], support=[1, 1], joint=[0, 0])
    result = compare([c1], [ms])
    assert result['fact']['confirmed_loss'] == ['anon']
    assert result['support']['paired_delta'] == [0, 1]
    assert result['joint']['paired_delta'] == [-1, 0]
