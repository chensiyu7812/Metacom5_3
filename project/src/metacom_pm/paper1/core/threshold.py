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


THRESHOLD_PROTOCOL = "pm-paper1-quality-first-one-se-threshold-v1"
PROBABILITY_THRESHOLD_GRID = tuple(round(step / 20, 2) for step in range(1, 20))


class ThresholdCalibrationScope(StrEnum):
    RS_GROUPED_OOF = "rs_grouped_oof_effect_data"
    RQ2_OUTER_TRAINING_INNER_OOF = "rq2_outer_training_inner_oof"


class ThresholdPolicyKind(StrEnum):
    ELIGIBLE_ALWAYS_ON = "eligible_always_on"
    PROBABILITY_THRESHOLD = "probability_threshold"
    ALWAYS_OFF = "always_off"


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
    mean_end_to_end_latency_ms_on: float | None = Field(default=None, ge=0.0)
    mean_end_to_end_latency_ms_off: float | None = Field(default=None, ge=0.0)
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
        if (self.mean_end_to_end_latency_ms_on is None) != (
            self.mean_end_to_end_latency_ms_off is None
        ):
            raise ValueError("latency diagnostics require both ON and OFF measurements")
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
    mean_end_to_end_latency_ms: float | None = Field(default=None, ge=0.0)
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
) -> ThresholdSurfaceCell:
    cluster_quality_numerators: dict[str, int] = defaultdict(int)
    cluster_quality_denominators: dict[str, int] = defaultdict(int)
    selected_tokens: list[float] = []
    selected_latencies: list[float] = []
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
        if row.mean_end_to_end_latency_ms_on is not None:
            assert row.mean_end_to_end_latency_ms_off is not None
            selected_latencies.append(
                row.mean_end_to_end_latency_ms_on
                if choose_on
                else row.mean_end_to_end_latency_ms_off
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
    return ThresholdSurfaceCell(
        policy_kind=policy_kind,
        threshold=threshold,
        mean_quality=fmean(cluster_means),
        quality_standard_error=standard_error,
        mean_generator_input_tokens=fmean(selected_tokens),
        mean_end_to_end_latency_ms=(
            fmean(selected_latencies) if len(selected_latencies) == len(rows) else None
        ),
        mean_api_cost_usd=(
            fmean(selected_api_costs) if len(selected_api_costs) == len(rows) else None
        ),
        realized_on_rate=on_count / len(rows),
        measured_pairs=measured_pairs,
        clusters=len(cluster_means),
    )


def select_threshold_operating_point(
    rows: tuple[ThresholdCalibrationRow, ...],
) -> ThresholdSelectionResult:
    """Select quality-first one-SE, then minimum-token operating point.

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
        _surface_cell(rows, policy_kind=policy_kind, threshold=threshold)
        for policy_kind, threshold in _candidate_rules()
    )
    best_index = max(range(len(cells)), key=lambda index: (cells[index].mean_quality, -index))
    best = cells[best_index]
    floor = max(0.0, best.mean_quality - best.quality_standard_error)
    admissible = tuple(
        index for index, cell in enumerate(cells) if cell.mean_quality >= floor - 1e-12
    )

    def selection_key(index: int) -> tuple[float, float, float, int]:
        cell = cells[index]
        threshold_for_tie = cell.threshold if cell.threshold is not None else (
            1.0 if cell.policy_kind is ThresholdPolicyKind.ALWAYS_OFF else 0.0
        )
        return (
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
        cells=cells,
        best_quality_cell_index=best_index,
        one_se_floor=floor,
        admissible_cell_indices=admissible,
        selected_cell_index=selected_index,
        fixed_point_five_reference_index=reference_index,
    )
