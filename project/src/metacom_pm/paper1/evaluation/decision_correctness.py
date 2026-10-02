"""Decision-level evaluation separated from raw response-quality effects."""

from __future__ import annotations

import math
from statistics import fmean

from pydantic import Field, model_validator

from ..contracts import PairedOutcome, StrictContract, TreatmentAssignment


class DecisionCorrectnessRow(StrictContract):
    target_id: str = Field(min_length=1, description="Audit identity only")
    cluster_id: str = Field(min_length=1)
    effect_outcome: PairedOutcome
    predicted_positive_effect_probability: float = Field(ge=0.0, le=1.0)
    effect_threshold: float = Field(ge=0.0, le=1.0)
    predicted_assignment: TreatmentAssignment
    oracle_action_latency_feasible: bool
    observed_client_latency_constraint_met: bool | None = None
    r0_m0_sufficient: bool

    @model_validator(mode="after")
    def validate_semantics(self) -> "DecisionCorrectnessRow":
        if self.effect_outcome in {PairedOutcome.UNCERTAIN, PairedOutcome.INVALID}:
            return self
        expected_sufficient = self.effect_outcome is not PairedOutcome.ON_BETTER
        if self.r0_m0_sufficient != expected_sufficient:
            raise ValueError("R0+M0 sufficiency must match the paired quality-effect outcome")
        return self


class DecisionCorrectnessReport(StrictContract):
    measured_rows: int = Field(ge=1)
    excluded_uncertain_or_invalid_rows: int = Field(ge=0)
    effect_on_benefit_recall: float | None = Field(default=None, ge=0.0, le=1.0)
    effect_off_nonbenefit_specificity: float | None = Field(default=None, ge=0.0, le=1.0)
    effect_balanced_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    brier_score: float = Field(ge=0.0, le=1.0)
    log_loss: float = Field(ge=0.0)
    action_on_precision: float | None = Field(default=None, ge=0.0, le=1.0)
    action_on_recall: float | None = Field(default=None, ge=0.0, le=1.0)
    beneficial_but_latency_infeasible_rate: float | None = Field(
        default=None, ge=0.0, le=1.0
    )
    avoided_unnecessary_intervention_rate: float | None = Field(
        default=None, ge=0.0, le=1.0
    )
    observed_client_latency_constraint_violation_rate: float | None = Field(
        default=None, ge=0.0, le=1.0
    )
    denominators: dict[str, int]


def _safe_rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def evaluate_decision_correctness(
    rows: tuple[DecisionCorrectnessRow, ...],
) -> DecisionCorrectnessReport:
    """Evaluate effect prediction and latency-constrained action separately.

    Equivalent and OFF-better are both nonbeneficial for deployment, while
    uncertain/invalid rows are retained in the exclusion count and never
    coerced into binary ground truth.
    """

    if len({row.target_id for row in rows}) != len(rows):
        raise ValueError("decision correctness target ids must be unique")
    measured = tuple(
        row
        for row in rows
        if row.effect_outcome not in {PairedOutcome.UNCERTAIN, PairedOutcome.INVALID}
    )
    if not measured:
        raise ValueError("decision correctness requires at least one measured effect row")

    benefit = [row for row in measured if row.effect_outcome is PairedOutcome.ON_BETTER]
    nonbenefit = [row for row in measured if row.effect_outcome is not PairedOutcome.ON_BETTER]

    effect_predicted_on = {
        row.target_id: row.predicted_positive_effect_probability > row.effect_threshold
        for row in measured
    }
    effect_recall = _safe_rate(
        sum(effect_predicted_on[row.target_id] for row in benefit), len(benefit)
    )
    effect_specificity = _safe_rate(
        sum(not effect_predicted_on[row.target_id] for row in nonbenefit),
        len(nonbenefit),
    )
    balanced = (
        (effect_recall + effect_specificity) / 2
        if effect_recall is not None and effect_specificity is not None
        else None
    )

    binary_truth = [int(row.effect_outcome is PairedOutcome.ON_BETTER) for row in measured]
    probabilities = [row.predicted_positive_effect_probability for row in measured]
    epsilon = 1e-15
    brier = fmean(
        (probability - truth) ** 2
        for probability, truth in zip(probabilities, binary_truth, strict=True)
    )
    log_loss = -fmean(
        truth * math.log(min(max(probability, epsilon), 1 - epsilon))
        + (1 - truth) * math.log(min(max(1 - probability, epsilon), 1 - epsilon))
        for probability, truth in zip(probabilities, binary_truth, strict=True)
    )

    oracle_action_on = {
        row.target_id: (
            row.effect_outcome is PairedOutcome.ON_BETTER
            and row.oracle_action_latency_feasible
        )
        for row in measured
    }
    predicted_action_on = {
        row.target_id: row.predicted_assignment is TreatmentAssignment.ON
        for row in measured
    }
    predicted_on_count = sum(predicted_action_on.values())
    oracle_on_count = sum(oracle_action_on.values())
    action_true_positive = sum(
        predicted_action_on[row.target_id] and oracle_action_on[row.target_id]
        for row in measured
    )
    action_precision = _safe_rate(action_true_positive, predicted_on_count)
    action_recall = _safe_rate(action_true_positive, oracle_on_count)

    latency_infeasible_benefit = sum(
        not row.oracle_action_latency_feasible for row in benefit
    )
    sufficient = [row for row in measured if row.r0_m0_sufficient]
    avoided = sum(
        row.predicted_assignment is TreatmentAssignment.OFF for row in sufficient
    )
    observed = [
        row for row in rows if row.observed_client_latency_constraint_met is not None
    ]
    violations = sum(
        not row.observed_client_latency_constraint_met for row in observed
    )

    return DecisionCorrectnessReport(
        measured_rows=len(measured),
        excluded_uncertain_or_invalid_rows=len(rows) - len(measured),
        effect_on_benefit_recall=effect_recall,
        effect_off_nonbenefit_specificity=effect_specificity,
        effect_balanced_accuracy=balanced,
        brier_score=brier,
        log_loss=log_loss,
        action_on_precision=action_precision,
        action_on_recall=action_recall,
        beneficial_but_latency_infeasible_rate=_safe_rate(
            latency_infeasible_benefit, len(benefit)
        ),
        avoided_unnecessary_intervention_rate=_safe_rate(avoided, len(sufficient)),
        observed_client_latency_constraint_violation_rate=_safe_rate(
            violations, len(observed)
        ),
        denominators={
            "measured_effect_rows": len(measured),
            "beneficial_rows": len(benefit),
            "nonbeneficial_rows": len(nonbenefit),
            "predicted_action_on_rows": predicted_on_count,
            "oracle_action_on_rows": oracle_on_count,
            "r0_m0_sufficient_rows": len(sufficient),
            "observed_latency_rows": len(observed),
        },
    )


__all__ = [
    "DecisionCorrectnessReport",
    "DecisionCorrectnessRow",
    "evaluate_decision_correctness",
]
