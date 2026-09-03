"""Outcome-isolated operating-point calibration for Paper-1 PM heads.

The learner remains a benefit-only probability model.  This module selects a
deployment rule from grouped OOF or outer-training/inner-OOF paired effects;
it never reads confirmatory or held-out outer-target outcomes and never puts
cost into the learner label or loss.
"""

from __future__ import annotations

import math
from collections import defaultdict
from enum import StrEnum
from statistics import fmean, stdev

from pydantic import Field, model_validator

from ..contracts import Head, StrictContract, TaskType


THRESHOLD_PROTOCOL = "pm-paper1-client-e2e-quality-latency-frontier-v3"
PROBABILITY_THRESHOLD_GRID = tuple(round(step / 20, 2) for step in range(1, 20))


class ThresholdCalibrationScope(StrEnum):
    RS_GROUPED_OOF = "rs_grouped_oof_effect_data"
    RQ2_OUTER_TRAINING_INNER_OOF = "rq2_outer_training_inner_oof"


class ThresholdPolicyKind(StrEnum):
    ELIGIBLE_ALWAYS_ON = "eligible_always_on"
    PROBABILITY_THRESHOLD = "probability_threshold"
    ALWAYS_OFF = "always_off"


class ClientLatencyConstraint(StrictContract):
    """Primary catastrophic ceiling plus an optional deployment scenario."""

    measurement_protocol_id: str = "paper1-client-latency-measurement-v2"
    catastrophic_completion_ceiling_ms: float = Field(default=60_000.0, gt=0.0)
    percentile: float = 0.95
    deployment_scenario_id: str | None = Field(default=None, min_length=1)
    deployment_ttft_budget_ms: float | None = Field(default=None, gt=0.0)
    deployment_completion_budget_ms: float | None = Field(default=None, gt=0.0)
    zero_outcome_profiled: bool = False
    researcher_frozen: bool = False

    @model_validator(mode="after")
    def enforce_pre_outcome_constraint(self) -> "ClientLatencyConstraint":
        if self.percentile != 0.95:
            raise ValueError("primary client latency reporting is frozen at p95")
        if self.catastrophic_completion_ceiling_ms != 60_000.0:
            raise ValueError("catastrophic client completion ceiling must remain 60000 ms")
        scenario = (
            self.deployment_scenario_id,
            self.deployment_ttft_budget_ms,
            self.deployment_completion_budget_ms,
        )
        if any(value is None for value in scenario) and any(
            value is not None for value in scenario
        ):
            raise ValueError("deployment scenario id and both budgets must be complete")
        if self.deployment_scenario_id is not None:
            assert self.deployment_ttft_budget_ms is not None
            assert self.deployment_completion_budget_ms is not None
            if self.deployment_ttft_budget_ms > self.deployment_completion_budget_ms:
                raise ValueError("deployment TTFT budget cannot exceed completion budget")
            if (
                self.deployment_completion_budget_ms
                >= self.catastrophic_completion_ceiling_ms
            ):
                raise ValueError("deployment completion budget must be below the ceiling")
            if not self.zero_outcome_profiled or not self.researcher_frozen:
                raise ValueError("tighter deployment budgets require profiling and freeze")
        return self

    @property
    def has_tighter_deployment_scenario(self) -> bool:
        return self.deployment_scenario_id is not None


class ThresholdCalibrationRow(StrictContract):
    """One state-level OOF effect record eligible for threshold calibration."""

    target_id: str = Field(min_length=1)
    cluster_id: str = Field(min_length=1)
    head: Head
    task_type: TaskType
    scope: ThresholdCalibrationScope
    predicted_positive_effect_probability: float = Field(ge=0.0, le=1.0)
    on_better: int = Field(ge=0)
    off_better: int = Field(ge=0)
    equivalent: int = Field(ge=0)
    uncertain: int = Field(default=0, ge=0)
    invalid: int = Field(default=0, ge=0)
    mean_generator_input_tokens_on: float = Field(ge=0.0)
    mean_generator_input_tokens_off: float = Field(ge=0.0)
    client_send_to_first_visible_text_ms_on: tuple[float, ...] = ()
    client_send_to_first_visible_text_ms_off: tuple[float, ...] = ()
    client_send_to_final_visible_text_ms_on: tuple[float, ...] = ()
    client_send_to_final_visible_text_ms_off: tuple[float, ...] = ()
    mean_api_cost_usd_on: float | None = Field(default=None, ge=0.0)
    mean_api_cost_usd_off: float | None = Field(default=None, ge=0.0)
    prediction_is_grouped_oof: bool = True
    confirmatory_outcome_read: bool = False
    held_out_outer_fold_id: str | None = None
    target_outer_fold_id: str | None = None

    @property
    def measured_pairs(self) -> int:
        return self.on_better + self.off_better + self.equivalent

    @model_validator(mode="after")
    def enforce_outcome_isolation(self) -> "ThresholdCalibrationRow":
        if not self.prediction_is_grouped_oof:
            raise ValueError("threshold calibration requires grouped OOF predictions")
        if self.confirmatory_outcome_read:
            raise ValueError("confirmatory outcomes are forbidden in threshold calibration")
        latency_lengths = {
            len(self.client_send_to_first_visible_text_ms_on),
            len(self.client_send_to_first_visible_text_ms_off),
            len(self.client_send_to_final_visible_text_ms_on),
            len(self.client_send_to_final_visible_text_ms_off),
        }
        if len(latency_lengths) != 1:
            raise ValueError("paired ON/OFF TTFT and completion samples must have equal counts")
        latency_values = (
            *self.client_send_to_first_visible_text_ms_on,
            *self.client_send_to_first_visible_text_ms_off,
            *self.client_send_to_final_visible_text_ms_on,
            *self.client_send_to_final_visible_text_ms_off,
        )
        if any(not math.isfinite(value) or value < 0 for value in latency_values):
            raise ValueError("latency samples must be finite and non-negative")
        if any(
            ttft > completion
            for ttft, completion in zip(
                self.client_send_to_first_visible_text_ms_on,
                self.client_send_to_final_visible_text_ms_on,
                strict=True,
            )
        ) or any(
            ttft > completion
            for ttft, completion in zip(
                self.client_send_to_first_visible_text_ms_off,
                self.client_send_to_final_visible_text_ms_off,
                strict=True,
            )
        ):
            raise ValueError("TTFT cannot exceed completion latency")
        if (self.mean_api_cost_usd_on is None) != (self.mean_api_cost_usd_off is None):
            raise ValueError("API-cost diagnostics require both ON and OFF measurements")
        if self.scope is ThresholdCalibrationScope.RS_GROUPED_OOF:
            if self.head is not Head.RS or self.task_type is not TaskType.ESC_RESPONSE:
                raise ValueError("RS threshold calibration requires the RS ESC-response cell")
            if self.held_out_outer_fold_id is not None or self.target_outer_fold_id is not None:
                raise ValueError("RS grouped-OOF rows cannot claim RQ2 outer-fold identities")
        else:
            if self.head is Head.RS or self.task_type is TaskType.ESC_RESPONSE:
                raise ValueError("RQ2 threshold calibration requires a memory head and task")
            if self.held_out_outer_fold_id is None or self.target_outer_fold_id is None:
                raise ValueError("RQ2 threshold rows require target and held-out outer folds")
            if self.held_out_outer_fold_id == self.target_outer_fold_id:
                raise ValueError("held-out outer-target outcomes cannot select their own threshold")
        return self


class ThresholdSurfaceCell(StrictContract):
    policy_kind: ThresholdPolicyKind
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    mean_quality: float = Field(ge=0.0, le=1.0)
    quality_standard_error: float = Field(ge=0.0)
    mean_generator_input_tokens: float = Field(ge=0.0)
    median_client_ttft_ms: float = Field(ge=0.0)
    p95_client_ttft_ms: float = Field(ge=0.0)
    mean_client_completion_ms: float = Field(ge=0.0)
    median_client_completion_ms: float = Field(ge=0.0)
    p95_client_completion_ms: float = Field(ge=0.0)
    catastrophic_ceiling_feasible: bool
    deployment_scenario_feasible: bool | None = None
    mean_api_cost_usd: float | None = Field(default=None, ge=0.0)
    realized_on_rate: float = Field(ge=0.0, le=1.0)
    measured_pairs: int = Field(ge=1)
    clusters: int = Field(ge=1)


class ThresholdSelectionResult(StrictContract):
    protocol: str = THRESHOLD_PROTOCOL
    head: Head
    task_type: TaskType
    scope: ThresholdCalibrationScope
    held_out_outer_fold_id: str | None = None
    client_latency_measurement_protocol_id: str = Field(min_length=1)
    deployment_scenario_id: str | None = Field(default=None, min_length=1)
    cells: tuple[ThresholdSurfaceCell, ...]
    best_quality_cell_index: int = Field(ge=0)
    one_se_floor: float = Field(ge=0.0, le=1.0)
    admissible_cell_indices: tuple[int, ...]
    selected_cell_index: int = Field(ge=0)
    fixed_point_five_reference_index: int = Field(ge=0)
    confirmatory_outcome_calls: int = 0
    additional_generator_calls: int = 0

    @model_validator(mode="after")
    def validate_selection_identity(self) -> "ThresholdSelectionResult":
        indices = {
            self.best_quality_cell_index,
            self.selected_cell_index,
            self.fixed_point_five_reference_index,
            *self.admissible_cell_indices,
        }
        if not indices or min(indices) < 0 or max(indices) >= len(self.cells):
            raise ValueError("threshold result contains an out-of-range cell index")
        if self.selected_cell_index not in self.admissible_cell_indices:
            raise ValueError("selected threshold must be in the one-SE admissible set")
        reference = self.cells[self.fixed_point_five_reference_index]
        if (
            reference.policy_kind is not ThresholdPolicyKind.PROBABILITY_THRESHOLD
            or reference.threshold != 0.5
        ):
            raise ValueError("the mandatory fixed-0.5 reference is missing")
        if self.confirmatory_outcome_calls != 0 or self.additional_generator_calls != 0:
            raise ValueError("offline threshold calibration cannot make outcome or Generator calls")
        return self


def _assignment_on(
    row: ThresholdCalibrationRow,
    *,
    policy_kind: ThresholdPolicyKind,
    threshold: float | None,
) -> bool:
    if policy_kind is ThresholdPolicyKind.ALWAYS_OFF:
        return False
    if policy_kind is ThresholdPolicyKind.ELIGIBLE_ALWAYS_ON:
        return True
    assert threshold is not None
    return row.predicted_positive_effect_probability > threshold


def _candidate_rules() -> tuple[tuple[ThresholdPolicyKind, float | None], ...]:
    return (
        (ThresholdPolicyKind.ELIGIBLE_ALWAYS_ON, None),
        *(
            (ThresholdPolicyKind.PROBABILITY_THRESHOLD, threshold)
            for threshold in PROBABILITY_THRESHOLD_GRID
        ),
        (ThresholdPolicyKind.ALWAYS_OFF, None),
    )


def _surface_cell(
    rows: tuple[ThresholdCalibrationRow, ...],
    *,
    policy_kind: ThresholdPolicyKind,
    threshold: float | None,
    client_latency: ClientLatencyConstraint,
) -> ThresholdSurfaceCell:
    cluster_quality_numerators: dict[str, int] = defaultdict(int)
    cluster_quality_denominators: dict[str, int] = defaultdict(int)
    selected_tokens: list[float] = []
    selected_latencies: list[float] = []
    selected_ttfts: list[float] = []
    selected_api_costs: list[float] = []
    on_count = 0
    measured_pairs = 0

    for row in rows:
        choose_on = _assignment_on(row, policy_kind=policy_kind, threshold=threshold)
        on_count += int(choose_on)
        selected_tokens.append(
            row.mean_generator_input_tokens_on
            if choose_on
            else row.mean_generator_input_tokens_off
        )
        selected_latencies.extend(
            row.client_send_to_final_visible_text_ms_on
            if choose_on
            else row.client_send_to_final_visible_text_ms_off
        )
        selected_ttfts.extend(
            row.client_send_to_first_visible_text_ms_on
            if choose_on
            else row.client_send_to_first_visible_text_ms_off
        )
        if row.mean_api_cost_usd_on is not None:
            assert row.mean_api_cost_usd_off is not None
            selected_api_costs.append(
                row.mean_api_cost_usd_on if choose_on else row.mean_api_cost_usd_off
            )
        # Equivalent means the two arms are quality-equivalent.  Both choices
        # receive quality credit; the later cost tie-break prefers OFF.
        quality_successes = (
            row.on_better + row.equivalent
            if choose_on
            else row.off_better + row.equivalent
        )
        cluster_quality_numerators[row.cluster_id] += quality_successes
        cluster_quality_denominators[row.cluster_id] += row.measured_pairs
        measured_pairs += row.measured_pairs

    cluster_means = [
        cluster_quality_numerators[cluster] / denominator
        for cluster, denominator in cluster_quality_denominators.items()
        if denominator > 0
    ]
    if not cluster_means or measured_pairs == 0:
        raise ValueError("threshold calibration requires at least one measured paired effect")
    standard_error = stdev(cluster_means) / math.sqrt(len(cluster_means)) if len(cluster_means) > 1 else 0.0
    if not selected_latencies or not selected_ttfts:
        raise ValueError(
            "latency-constrained selection requires raw TTFT and completion samples for every row"
        )

    def nearest_rank(values: list[float], percentile: float) -> float:
        ordered = sorted(values)
        return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]

    median_ttft = nearest_rank(selected_ttfts, 0.5)
    p95_ttft = nearest_rank(selected_ttfts, client_latency.percentile)
    median_completion = nearest_rank(selected_latencies, 0.5)
    p95_completion = nearest_rank(selected_latencies, client_latency.percentile)
    catastrophic_feasible = (
        p95_completion < client_latency.catastrophic_completion_ceiling_ms
    )
    deployment_feasible = None
    if client_latency.has_tighter_deployment_scenario:
        assert client_latency.deployment_ttft_budget_ms is not None
        assert client_latency.deployment_completion_budget_ms is not None
        deployment_feasible = (
            p95_ttft <= client_latency.deployment_ttft_budget_ms
            and p95_completion <= client_latency.deployment_completion_budget_ms
        )

    return ThresholdSurfaceCell(
        policy_kind=policy_kind,
        threshold=threshold,
        mean_quality=fmean(cluster_means),
        quality_standard_error=standard_error,
        mean_generator_input_tokens=fmean(selected_tokens),
        median_client_ttft_ms=median_ttft,
        p95_client_ttft_ms=p95_ttft,
        mean_client_completion_ms=fmean(selected_latencies),
        median_client_completion_ms=median_completion,
        p95_client_completion_ms=p95_completion,
        catastrophic_ceiling_feasible=catastrophic_feasible,
        deployment_scenario_feasible=deployment_feasible,
        mean_api_cost_usd=(
            fmean(selected_api_costs) if len(selected_api_costs) == len(rows) else None
        ),
        realized_on_rate=on_count / len(rows),
        measured_pairs=measured_pairs,
        clusters=len(cluster_means),
    )


def select_threshold_operating_point(
    rows: tuple[ThresholdCalibrationRow, ...],
    *,
    client_latency: ClientLatencyConstraint,
) -> ThresholdSelectionResult:
    """Select below the catastrophic ceiling, then by quality and client latency.

    Candidate evaluation reuses already-authorized paired effects and OOF
    predictions.  It therefore performs no generation, judging, or benchmark
    outcome access of its own.
    """

    if not rows:
        raise ValueError("threshold calibration rows cannot be empty")
    signature = {
        (
            row.head,
            row.task_type,
            row.scope,
            row.held_out_outer_fold_id,
        )
        for row in rows
    }
    if len(signature) != 1:
        raise ValueError("one threshold surface must bind one head/task/isolation scope")
    cells = tuple(
        _surface_cell(
            rows,
            policy_kind=policy_kind,
            threshold=threshold,
            client_latency=client_latency,
        )
        for policy_kind, threshold in _candidate_rules()
    )
    feasible_indices = tuple(
        index for index, cell in enumerate(cells) if cell.catastrophic_ceiling_feasible
    )
    if not feasible_indices:
        raise ValueError("no threshold policy is below the catastrophic client completion ceiling")
    best_index = max(
        feasible_indices,
        key=lambda index: (cells[index].mean_quality, -index),
    )
    best = cells[best_index]
    floor = max(0.0, best.mean_quality - best.quality_standard_error)
    admissible = tuple(
        index
        for index in feasible_indices
        if cells[index].mean_quality >= floor - 1e-12
    )

    def selection_key(index: int) -> tuple[float, float, float, float, float, float, int]:
        cell = cells[index]
        threshold_for_tie = cell.threshold if cell.threshold is not None else (
            1.0 if cell.policy_kind is ThresholdPolicyKind.ALWAYS_OFF else 0.0
        )
        return (
            cell.p95_client_completion_ms,
            cell.median_client_completion_ms,
            cell.p95_client_ttft_ms,
            cell.mean_generator_input_tokens,
            cell.realized_on_rate,
            -threshold_for_tie,
            index,
        )

    selected_index = min(admissible, key=selection_key)
    reference_index = next(
        index
        for index, cell in enumerate(cells)
        if cell.policy_kind is ThresholdPolicyKind.PROBABILITY_THRESHOLD
        and cell.threshold == 0.5
    )
    head, task_type, scope, held_out_outer_fold_id = next(iter(signature))
    return ThresholdSelectionResult(
        head=head,
        task_type=task_type,
        scope=scope,
        held_out_outer_fold_id=held_out_outer_fold_id,
        client_latency_measurement_protocol_id=client_latency.measurement_protocol_id,
        deployment_scenario_id=client_latency.deployment_scenario_id,
        cells=cells,
        best_quality_cell_index=best_index,
        one_se_floor=floor,
        admissible_cell_indices=admissible,
        selected_cell_index=selected_index,
        fixed_point_five_reference_index=reference_index,
    )
