"""Boundaries of the opt-in preload recovery and complete-score MS replay."""
import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT = Path(__file__).resolve().parents[1]


def load(number, name):
    spec = importlib.util.spec_from_file_location(name, next((PROJECT / 'scripts/rl1').glob(number + '_*.py')))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


RECOVERY = load('172', 'scoped_preload_test')
LOCATOR = load('173', 'complete_ms_test')


def snapshot():
    return dict(rejection_reasons=['utilization_not_zero'], visible_processes=[],
        process_visibility='queries_succeeded_no_processes_listed', sampling_policy='last_xml',
        selected_gpu=dict(free_mib=48551, utilization_percent=2))


def test_scoped_preload_admits_only_the_disclosed_low_idle_snapshot():
    result = snapshot()
    original = copy.deepcopy(result)
    assert RECOVERY.tolerated_preload(result)
    assert result == original
    result['selected_gpu']['utilization_percent'] = 5
    assert RECOVERY.tolerated_preload(result)
    result['selected_gpu']['utilization_percent'] = 6
    assert not RECOVERY.tolerated_preload(result)


@pytest.mark.parametrize('change', [
    {'rejection_reasons': ['utilization_not_zero', 'other_visible_gpu_process']},
    {'rejection_reasons': ['utilization_not_zero', 'GPU query failed']},
    {'rejection_reasons': ['process_visibility_namespace_mismatch']},
    {'visible_processes': [{'pid': 123}]},
    {'process_visibility': 'unknown'},
    {'sampling_policy': 'historical_first_csv'},
    {'selected_gpu': {'free_mib': 44999, 'utilization_percent': 2}},
])
def test_recovery_does_not_relax_other_failures(change):
    result = snapshot()
    result.update(change)
    assert not RECOVERY.tolerated_preload(result)


def catalog(rows):
    return SimpleNamespace(_items={str(i): SimpleNamespace(head='MS', original_rank=rank, bge_similarity=score)
                                  for i, (rank, score) in enumerate(rows)})


@pytest.mark.parametrize('rows', [[], [(1, .7), (None, None)], [(1, .7), (3, .6)],
                                   [(1, .7), (1, .6)], [(1, .6), (2, .7)], [(1, float('nan'))]])
def test_frozen_rank_cannot_silently_exclude_unscored_or_inconsistent_sources(rows):
    with pytest.raises(ValueError):
        LOCATOR.complete_ms_rows(catalog(rows))


def test_equal_score_retains_the_existing_rank_without_retuning():
    rows = LOCATOR.complete_ms_rows(catalog([(2, .7), (1, .7), (3, .5)]))
    assert [r.original_rank for r in rows] == [1, 2, 3]
