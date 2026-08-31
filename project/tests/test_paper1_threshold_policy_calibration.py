import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from metacom_pm.paper1.contracts import Head, TaskType
from metacom_pm.paper1.core.threshold import (
    PROBABILITY_THRESHOLD_GRID,
    THRESHOLD_PROTOCOL,
    ThresholdCalibrationRow,
    ThresholdCalibrationScope,
    ThresholdPolicyKind,
    select_threshold_operating_point,
)
from metacom_pm.paper1.core.freeze import (
    ArtifactBinding,
    ThresholdOperatingPointFreeze,
)


ROOT = Path(__file__).resolve().parents[1]


def _row(
    target_id: str,
    *,
    probability: float,
    on_better: int = 0,
    off_better: int = 0,
    equivalent: int = 0,
    on_tokens: float = 20.0,
    off_tokens: float = 10.0,
    on_latency_ms: float | None = 120.0,
    off_latency_ms: float | None = 100.0,
) -> ThresholdCalibrationRow:
    return ThresholdCalibrationRow(
        target_id=target_id,
        cluster_id=target_id,
        head=Head.RS,
        task_type=TaskType.ESC_RESPONSE,
        scope=ThresholdCalibrationScope.RS_GROUPED_OOF,
        predicted_positive_effect_probability=probability,
        on_better=on_better,
        off_better=off_better,
        equivalent=equivalent,
        mean_generator_input_tokens_on=on_tokens,
        mean_generator_input_tokens_off=off_tokens,
        mean_end_to_end_latency_ms_on=on_latency_ms,
        mean_end_to_end_latency_ms_off=off_latency_ms,
    )


def test_protocol_surface_keeps_point_five_and_endpoint_policies():
    assert THRESHOLD_PROTOCOL == "pm-paper1-quality-first-one-se-threshold-v1"
    assert PROBABILITY_THRESHOLD_GRID == tuple(round(step / 20, 2) for step in range(1, 20))
    assert 0.5 in PROBABILITY_THRESHOLD_GRID
    result = select_threshold_operating_point(
        (
            _row("positive", probability=0.8, on_better=3),
            _row("negative", probability=0.2, off_better=3),
        )
    )
    assert {cell.policy_kind for cell in result.cells} == {
        ThresholdPolicyKind.ELIGIBLE_ALWAYS_ON,
        ThresholdPolicyKind.PROBABILITY_THRESHOLD,
        ThresholdPolicyKind.ALWAYS_OFF,
    }
    reference = result.cells[result.fixed_point_five_reference_index]
    assert reference.threshold == 0.5
    assert result.additional_generator_calls == 0
    assert result.confirmatory_outcome_calls == 0


def test_quality_first_then_cost_prefers_off_when_effect_is_equivalent():
    result = select_threshold_operating_point(
        (
            _row("a", probability=0.9, equivalent=3, on_tokens=40, off_tokens=10),
            _row("b", probability=0.1, equivalent=3, on_tokens=40, off_tokens=10),
        )
    )
    selected = result.cells[result.selected_cell_index]
    assert selected.mean_quality == 1.0
    assert selected.policy_kind is ThresholdPolicyKind.ALWAYS_OFF
    assert selected.realized_on_rate == 0.0
    assert selected.mean_generator_input_tokens == 10.0
    assert selected.mean_end_to_end_latency_ms == 100.0


def test_selection_can_move_from_point_five_without_opening_outcomes():
    result = select_threshold_operating_point(
        (
            _row("positive", probability=0.8, on_better=3),
            _row("negative", probability=0.2, off_better=3),
        )
    )
    selected = result.cells[result.selected_cell_index]
    assert selected.policy_kind is ThresholdPolicyKind.PROBABILITY_THRESHOLD
    assert selected.threshold == 0.75
    assert selected.mean_quality == 1.0
    assert selected.realized_on_rate == 0.5


def test_confirmatory_and_outer_target_leakage_fail_closed():
    base = _row("leak", probability=0.5, on_better=1).model_dump()
    base["confirmatory_outcome_read"] = True
    with pytest.raises(ValidationError, match="confirmatory outcomes"):
        ThresholdCalibrationRow(**base)
    with pytest.raises(ValidationError, match="held-out outer-target"):
        ThresholdCalibrationRow(
            target_id="rq2-leak",
            cluster_id="owner-1",
            head=Head.MP,
            task_type=TaskType.QA,
            scope=ThresholdCalibrationScope.RQ2_OUTER_TRAINING_INNER_OOF,
            predicted_positive_effect_probability=0.7,
            on_better=1,
            off_better=0,
            equivalent=0,
            mean_generator_input_tokens_on=20,
            mean_generator_input_tokens_off=10,
            held_out_outer_fold_id="fold-2",
            target_outer_fold_id="fold-2",
        )


def test_one_surface_cannot_mix_tasks_or_isolation_scopes():
    row = _row("rs", probability=0.7, on_better=1)
    mixed = row.model_copy(update={"task_type": TaskType.QA})
    with pytest.raises(ValueError, match="one head/task/isolation scope"):
        select_threshold_operating_point((row, mixed))


def test_task_scope_and_unidentifiable_cells_fail_closed():
    with pytest.raises(ValidationError, match="RS threshold calibration"):
        ThresholdCalibrationRow(
            **{
                **_row("wrong-task", probability=0.7, on_better=1).model_dump(),
                "task_type": TaskType.QA,
            }
        )
    binding = ArtifactBinding(
        repo_relative_path="data/paper1_authority/empty-cell.json",
        sha256="a" * 64,
        role="threshold calibration evidence",
    )
    point = ThresholdOperatingPointFreeze(
        head=Head.MP,
        task_type=TaskType.QA,
        outer_fold_id="fold-0",
        policy_kind=ThresholdPolicyKind.ALWAYS_OFF,
        calibration_artifact=binding,
        calibration_rows=0,
        calibration_clusters=0,
        identified=False,
    )
    assert point.policy_kind is ThresholdPolicyKind.ALWAYS_OFF
    with pytest.raises(ValidationError, match="evidence-free always-off"):
        ThresholdOperatingPointFreeze(
            head=Head.MP,
            task_type=TaskType.QA,
            outer_fold_id="fold-0",
            policy_kind=ThresholdPolicyKind.PROBABILITY_THRESHOLD,
            selected_threshold=0.5,
            calibration_artifact=binding,
            calibration_rows=0,
            calibration_clusters=0,
            identified=False,
        )


def test_authority_keeps_all_locks_closed_and_cost_out_of_learning():
    authority = json.loads(
        (
            ROOT
            / "data/paper1_authority/"
            "paper1_threshold_policy_calibration_amendment_20260831_v1.json"
        ).read_text(encoding="utf-8")
    )
    assert set(authority["locks"].values()) == {"CLOSED"}
    assert authority["preserved_research"]["cost_in_label_or_loss"] is False
    assert authority["isolation"]["additional_generator_calls_for_threshold_surface"] == 0
    assert authority["current_activity"] == {
        "paid_API_calls": 0,
        "formal_outcome_calls": 0,
        "PM_training_runs": 0,
        "formal_GPU_experiments": 0,
    }
