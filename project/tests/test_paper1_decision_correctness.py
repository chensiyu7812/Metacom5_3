import pytest
from pydantic import ValidationError

from metacom_pm.paper1.contracts import PairedOutcome, TreatmentAssignment
from metacom_pm.paper1.evaluation.decision_correctness import (
    DecisionCorrectnessRow,
    evaluate_decision_correctness,
)


def _row(
    target_id: str,
    outcome: PairedOutcome,
    probability: float,
    assignment: TreatmentAssignment,
    *,
    latency_feasible: bool = True,
    sla_met: bool | None = True,
) -> DecisionCorrectnessRow:
    return DecisionCorrectnessRow(
        target_id=target_id,
        cluster_id=target_id,
        effect_outcome=outcome,
        predicted_positive_effect_probability=probability,
        effect_threshold=0.5,
        predicted_assignment=assignment,
        oracle_action_latency_feasible=latency_feasible,
        observed_client_latency_constraint_met=sla_met,
        r0_m0_sufficient=outcome in {
            PairedOutcome.OFF_BETTER,
            PairedOutcome.EQUIVALENT,
        },
    )


def test_effect_and_action_correctness_are_reported_separately():
    report = evaluate_decision_correctness(
        (
            _row("benefit-fast", PairedOutcome.ON_BETTER, 0.9, TreatmentAssignment.ON),
            _row(
                "benefit-slow",
                PairedOutcome.ON_BETTER,
                0.8,
                TreatmentAssignment.OFF,
                latency_feasible=False,
            ),
            _row("equivalent", PairedOutcome.EQUIVALENT, 0.2, TreatmentAssignment.OFF),
            _row("off-better", PairedOutcome.OFF_BETTER, 0.7, TreatmentAssignment.ON),
            _row("uncertain", PairedOutcome.UNCERTAIN, 0.5, TreatmentAssignment.OFF),
        )
    )
    assert report.measured_rows == 4
    assert report.excluded_uncertain_or_invalid_rows == 1
    assert report.effect_on_benefit_recall == 1.0
    assert report.effect_off_nonbenefit_specificity == 0.5
    assert report.action_on_precision == 0.5
    assert report.action_on_recall == 1.0
    assert report.beneficial_but_latency_infeasible_rate == 0.5
    assert report.avoided_unnecessary_intervention_rate == 0.5


def test_equivalent_is_r0_m0_sufficient_and_never_coerced_positive():
    with pytest.raises(ValidationError, match=r"R0\+M0"):
        DecisionCorrectnessRow(
            target_id="bad",
            cluster_id="bad",
            effect_outcome=PairedOutcome.EQUIVALENT,
            predicted_positive_effect_probability=0.1,
            effect_threshold=0.5,
            predicted_assignment=TreatmentAssignment.OFF,
            oracle_action_latency_feasible=True,
            r0_m0_sufficient=False,
        )


def test_empty_measured_set_and_duplicate_targets_fail_closed():
    uncertain = _row(
        "u", PairedOutcome.UNCERTAIN, 0.5, TreatmentAssignment.OFF, sla_met=None
    )
    with pytest.raises(ValueError, match="at least one measured"):
        evaluate_decision_correctness((uncertain,))
    measured = _row("x", PairedOutcome.ON_BETTER, 0.9, TreatmentAssignment.ON)
    with pytest.raises(ValueError, match="unique"):
        evaluate_decision_correctness((measured, measured))
