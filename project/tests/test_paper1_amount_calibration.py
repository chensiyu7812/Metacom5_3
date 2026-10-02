import copy

import pytest

from metacom_pm.paper1.amount_calibration import sample_static_targets, recommend_amount


def test_sampler_is_order_invariant_and_probability_tracks_two_stage_design():
    rows = [{"target_id": f"t{i}", "task_type": "qa", "owner_id": "p1",
             "outer_fold": 0, "group_component_id": "a" if i < 3 else "b"} for i in range(5)]
    selected = sample_static_targets(rows)
    assert selected == sample_static_targets(list(reversed(rows)))
    assert len(selected) == 1
    row = selected[0]
    assert row["analysis_weight"] == 2 * row["selected_component_targets"]
    assert row["inclusion_probability"] * row["analysis_weight"] == 1


def test_sampler_rejects_split_component():
    rows = [{"target_id": f"t{i}", "task_type": "qa", "owner_id": "p1",
             "outer_fold": i, "group_component_id": "same"} for i in range(2)]
    with pytest.raises(ValueError, match="crosses"):
        sample_static_targets(rows)


def fixture_rows():
    return [{"target_id": f"t{i}", "task": "qa", "head": "MP", "k": k,
             "owner_id": f"p{i}", "outer_fold": i, "group_component_id": f"c{i}",
             "analysis_weight": 1, "natural_end": True, "quality": 0.5,
             "input_tokens": 100 + k * 10} for i in range(4) for k in range(5)]


def test_equal_quality_selects_true_off_and_heldout_values_never_affect_choice():
    rows = fixture_rows()
    a = recommend_amount(rows, task="qa", head="MP", held_out_fold=3, bootstrap_replicates=50)
    for r in rows:
        if r["outer_fold"] == 3:
            r["quality"] = float("nan")
    assert a == recommend_amount(rows, task="qa", head="MP", held_out_fold=3, bootstrap_replicates=50)
    assert a["primary_metric_recommended_k"] == 0
    assert a["paired_complete_targets"] == 3


def test_missing_score_excludes_entire_target_and_never_becomes_zero():
    rows = fixture_rows()
    rows[2]["quality"] = None
    result = recommend_amount(rows, task="qa", head="MP", held_out_fold=3, bootstrap_replicates=50)
    assert result["excluded_incomplete_targets"] == ["t0"]
    assert result["paired_complete_targets"] == 2
    assert set(result["means"].values()) == {0.5}


def test_high_endpoint_only_triggers_prespecified_extension_when_three_is_outside():
    rows = fixture_rows()
    for r in rows:
        r["quality"] = 1 if r["k"] == 4 else 0
    result = recommend_amount(rows, task="qa", head="MP", held_out_fold=3, bootstrap_replicates=50)
    assert result["primary_metric_recommended_k"] == 4
    assert result["expand_once_to_6_8"]
    assert result["final_k_frozen"] is False


def test_one_se_prefers_cheaper_near_best_point():
    rows = fixture_rows()
    for r in rows:
        r["quality"] = [0.1, 0.45, 0.46, 0.47, [0.2, 0.5, 0.8, 0.5][r["outer_fold"]]][r["k"]]
    result = recommend_amount(rows, task="qa", head="MP", held_out_fold=3, bootstrap_replicates=300)
    assert result["best_mean_k"] == 4
    assert result["primary_metric_recommended_k"] == 1
    assert not result["expand_once_to_6_8"]


def test_duplicates_are_not_independent_repeats():
    rows = fixture_rows()
    rows.append(copy.deepcopy(rows[0]))
    with pytest.raises(ValueError, match="duplicate"):
        recommend_amount(rows, task="qa", head="MP", held_out_fold=3)
