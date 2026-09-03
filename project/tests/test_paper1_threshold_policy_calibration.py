import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from metacom_pm.paper1.contracts import Head, TaskType
from metacom_pm.paper1.core.threshold import (
    ClientLatencyConstraint,
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


def _client_latency(
    *,
    scenario: bool = False,
    ttft_ms: float = 1_000.0,
    completion_ms: float = 2_000.0,
) -> ClientLatencyConstraint:
    return ClientLatencyConstraint(
        deployment_scenario_id="paper1-test-scenario-v1" if scenario else None,
        deployment_ttft_budget_ms=ttft_ms if scenario else None,
        deployment_completion_budget_ms=completion_ms if scenario else None,
        zero_outcome_profiled=scenario,
        researcher_frozen=scenario,
    )


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
    on_ttft_ms: float | None = 60.0,
    off_ttft_ms: float | None = 50.0,
    on_quality: float | None = None,
    off_quality: float | None = None,
) -> ThresholdCalibrationRow:
    if on_quality is None or off_quality is None:
        if on_better > off_better:
            on_quality, off_quality = 1.0, 0.0
        elif off_better > on_better:
            on_quality, off_quality = 0.0, 1.0
        else:
            on_quality = off_quality = 0.5
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
        official_primary_quality_metric="ESC-RANK:Overall/4",
        normalized_official_primary_quality_on=on_quality,
        normalized_official_primary_quality_off=off_quality,
        mean_generator_input_tokens_on=on_tokens,
        mean_generator_input_tokens_off=off_tokens,
        client_send_to_first_visible_text_ms_on=() if on_ttft_ms is None else (on_ttft_ms,),
        client_send_to_first_visible_text_ms_off=() if off_ttft_ms is None else (off_ttft_ms,),
        client_send_to_final_visible_text_ms_on=() if on_latency_ms is None else (on_latency_ms,),
        client_send_to_final_visible_text_ms_off=() if off_latency_ms is None else (off_latency_ms,),
    )


def test_protocol_surface_keeps_point_five_and_endpoint_policies():
    assert THRESHOLD_PROTOCOL == "pm-paper1-client-e2e-quality-latency-frontier-v4"
    assert PROBABILITY_THRESHOLD_GRID == tuple(round(step / 20, 2) for step in range(1, 20))
    assert 0.5 in PROBABILITY_THRESHOLD_GRID
    result = select_threshold_operating_point(
        (
            _row("positive", probability=0.8, on_better=3),
            _row("negative", probability=0.2, off_better=3),
        ),
        client_latency=_client_latency(),
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
        ),
        client_latency=_client_latency(),
    )
    selected = result.cells[result.selected_cell_index]
    assert selected.mean_normalized_official_primary_quality == 0.5
    assert selected.mean_oracle_decision_correctness == 1.0
    assert selected.policy_kind is ThresholdPolicyKind.ALWAYS_OFF
    assert selected.realized_on_rate == 0.0
    assert selected.mean_generator_input_tokens == 10.0
    assert selected.mean_client_completion_ms == 100.0


def test_selection_can_move_from_point_five_without_opening_outcomes():
    result = select_threshold_operating_point(
        (
            _row("positive", probability=0.8, on_better=3),
            _row("negative", probability=0.2, off_better=3),
        ),
        client_latency=_client_latency(),
    )
    selected = result.cells[result.selected_cell_index]
    assert selected.policy_kind is ThresholdPolicyKind.PROBABILITY_THRESHOLD
    assert selected.threshold == 0.75
    assert selected.mean_normalized_official_primary_quality == 1.0
    assert selected.mean_oracle_decision_correctness == 1.0
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
            official_primary_quality_metric="ES-MemEval:LLM_as_Judge/2",
            normalized_official_primary_quality_on=1.0,
            normalized_official_primary_quality_off=0.0,
            mean_generator_input_tokens_on=20,
            mean_generator_input_tokens_off=10,
            held_out_outer_fold_id="fold-2",
            target_outer_fold_id="fold-2",
        )


def test_one_surface_cannot_mix_tasks_or_isolation_scopes():
    row = _row("rs", probability=0.7, on_better=1)
    mixed = row.model_copy(update={"task_type": TaskType.QA})
    with pytest.raises(ValueError, match="one head/task/isolation scope"):
        select_threshold_operating_point((row, mixed), client_latency=_client_latency())


def test_official_quality_and_oracle_decision_surfaces_are_not_conflated():
    result = select_threshold_operating_point(
        (
            _row(
                "small-on-gain",
                probability=0.9,
                on_better=1,
                on_quality=0.51,
                off_quality=0.50,
            ),
            _row(
                "small-on-harm",
                probability=0.8,
                off_better=1,
                on_quality=0.49,
                off_quality=0.50,
            ),
            _row(
                "large-on-gain",
                probability=0.7,
                on_better=1,
                on_quality=1.0,
                off_quality=0.0,
            ),
        ),
        client_latency=_client_latency(),
    )
    selected = result.cells[result.selected_cell_index]
    assert selected.policy_kind is ThresholdPolicyKind.PROBABILITY_THRESHOLD
    assert selected.threshold == 0.65
    assert selected.mean_normalized_official_primary_quality == pytest.approx(2.0 / 3.0)
    assert selected.mean_oracle_decision_correctness == pytest.approx(2.0 / 3.0)

    same_decision_accuracy = next(
        cell
        for cell in result.cells
        if cell.policy_kind is ThresholdPolicyKind.PROBABILITY_THRESHOLD
        and cell.threshold == 0.85
    )
    assert same_decision_accuracy.mean_oracle_decision_correctness == pytest.approx(2.0 / 3.0)
    assert (
        same_decision_accuracy.mean_normalized_official_primary_quality
        < selected.mean_normalized_official_primary_quality
    )


def test_catastrophic_client_completion_ceiling_precedes_quality():
    result = select_threshold_operating_point(
        (
            _row(
                "positive-but-slow",
                probability=0.9,
                on_better=3,
                on_ttft_ms=9_000,
                on_latency_ms=60_001,
            ),
            _row(
                "negative",
                probability=0.1,
                off_better=3,
                off_ttft_ms=100,
                off_latency_ms=200,
            ),
        ),
        client_latency=_client_latency(),
    )
    selected = result.cells[result.selected_cell_index]
    assert selected.catastrophic_ceiling_feasible is True
    assert selected.policy_kind is ThresholdPolicyKind.ALWAYS_OFF


def test_tighter_deployment_scenario_requires_profile_freeze_and_subminute_budget():
    with pytest.raises(ValidationError):
        ClientLatencyConstraint(
            deployment_scenario_id="not-frozen",
            deployment_ttft_budget_ms=500,
            deployment_completion_budget_ms=1_000,
            researcher_frozen=False,
        )
    with pytest.raises(ValidationError):
        ClientLatencyConstraint(
            deployment_scenario_id="one-minute-is-unacceptable",
            deployment_ttft_budget_ms=500,
            deployment_completion_budget_ms=60_000,
            zero_outcome_profiled=True,
            researcher_frozen=True,
        )
    assert ClientLatencyConstraint().has_tighter_deployment_scenario is False


def test_latency_selection_uses_raw_call_samples_not_row_means():
    row = _row("repeated", probability=0.8, on_better=1).model_copy(
        update={
            "client_send_to_first_visible_text_ms_on": (100.0, 100.0, 900.0),
            "client_send_to_first_visible_text_ms_off": (50.0, 50.0, 50.0),
            "client_send_to_final_visible_text_ms_on": (200.0, 200.0, 1_900.0),
            "client_send_to_final_visible_text_ms_off": (100.0, 100.0, 100.0),
        }
    )
    result = select_threshold_operating_point(
        (row,),
        client_latency=_client_latency(
            scenario=True,
            ttft_ms=500,
            completion_ms=1_000,
        ),
    )
    on_cell = result.cells[0]
    assert on_cell.policy_kind is ThresholdPolicyKind.ELIGIBLE_ALWAYS_ON
    assert on_cell.p95_client_ttft_ms == 900
    assert on_cell.p95_client_completion_ms == 1_900
    assert on_cell.catastrophic_ceiling_feasible is True
    assert on_cell.deployment_scenario_feasible is False


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


def test_authority_keeps_locks_closed_and_uses_client_latency_frontier():
    authority = json.loads(
        (
            ROOT
            / "data/paper1_authority/"
            "paper1_client_observed_latency_and_frontier_amendment_20260903_v2.json"
        ).read_text(encoding="utf-8")
    )
    assert set(authority["locks"].values()) == {"CLOSED"}
    assert authority["primary_metrics"]["cost_outcome"] == (
        "p95_client_send_to_final_visible_text_ms"
    )
    assert authority["paper_primary_selection"]["order"][0] == (
        "catastrophic_p95_client_completion_below_60000ms"
    )
    assert authority["deployment_budgets"]["not_a_research_execution_blocker"] is True
    assert authority["current_activity"] == {
        "paid_API_calls": 0,
        "formal_outcome_calls": 0,
        "PM_training_runs": 0,
        "formal_GPU_experiments": 0,
    }
