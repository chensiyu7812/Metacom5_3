"""Timing identities and unknowns must survive reused-endpoint summaries."""
import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('smv_latency', Path(__file__).parents[1]/'scripts/rl1v3/journal_analyze_smv_latency.py')
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)


def endpoint(identity, seconds, completion):
    return dict(request_id=identity, generation_seconds=seconds, completion=completion,
                output_object_sha256='synthetic-'+identity, arm='MS', input_tokens=10, output_tokens=2)


def test_nearest_rank_small_cohorts_have_p95_equal_to_observed_max():
    assert L.nearest_rank(list(range(1, 16)), .95) == 15
    assert L.nearest_rank(list(range(1, 6)), .95) == 5
    assert L.nearest_rank([8, 1, 2, 3, 4], .5) == 3
    assert L.distribution([])['p95_seconds'] is None
    with pytest.raises(ValueError): L.nearest_rank([float('nan')], .95)


def test_shared_unknown_endpoint_cancels_difference_without_becoming_success():
    a = endpoint('same', 2.1, [0, 1]);r = L.paired(a, a)
    assert r['completion_difference'] == [0, 0]
    assert r['outcome_stratum'] == 'uncertain' and r['selected_completion'] == [0, 1]
    assert r['direction'] == 'equal' and r['same_physical_endpoint']


def test_shared_identity_cannot_hide_changed_time_or_evaluation():
    a = endpoint('same', 2, [1, 1])
    for b in (endpoint('same', 3, [1, 1]), endpoint('same', 2, [0, 1])):
        with pytest.raises(ValueError, match='inconsistent'): L.paired(a, b)


def test_fast_failure_and_unknown_do_not_enter_common_success_savings():
    b = endpoint('reference', 5, [1, 1])
    rows = [dict(task='synthetic-fail', **L.paired(endpoint('fail', 1, [0, 0]), b)),
            dict(task='synthetic-unknown', **L.paired(endpoint('unknown', 2, [0, 1]), b)),
            dict(task='synthetic-success', **L.paired(endpoint('success', 4, [1, 1]), b))]
    report = L.summarize_pairs(rows)
    assert report['paired_delta']['sum_seconds'] == -8
    assert report['outcome_strata']['both_definite_success']['all_pairs']['paired_delta']['sum_seconds'] == -1
    assert report['outcome_strata']['uncertain']['all_pairs']['tasks'] == 1
    assert report['outcome_strata']['definite_regression']['all_pairs']['tasks'] == 1


def test_distinct_endpoints_with_equal_observed_seconds_are_not_reuse():
    r = L.paired(endpoint('a', 4, [1, 1]), endpoint('b', 4, [1, 1]))
    assert r['direction'] == 'equal' and not r['same_physical_endpoint']


def test_duplicate_identity_fails_before_silent_join_overwrite():
    with pytest.raises(ValueError, match='duplicate'):
        L.unique_index([dict(id='same'), dict(id='same')], 'id')
