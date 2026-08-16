import pytest
from pydantic import ValidationError

from metacom_pm.paper1.contracts import (
    CandidateLineage,
    EligibilityDecision,
    EligibilityStatus,
    ExperimentArm,
    OfficialOutcomeRecord,
    PolicyDecision,
    SoftEffectTarget,
    TaskType,
    TreatmentAssignment,
    TreatmentDeliveryStatus,
    TreatmentDeliveryTrace,
)


def test_soft_effect_preserves_ties_and_uncertainty_without_a_pass_gate():
    target = SoftEffectTarget(on_wins=2, off_wins=1, ties=1, uncertain=2)
    assert target.measured_pairs == 4
    assert target.positive_effect_fraction == pytest.approx(0.625)
    assert target.uncertain == 2


def test_primary_policy_rule_is_strictly_greater_than_point_five():
    at_threshold = PolicyDecision(
        eligible=True,
        predicted_positive_effect_probability=0.5,
        assignment=TreatmentAssignment.OFF,
    )
    assert at_threshold.assignment is TreatmentAssignment.OFF
    above = PolicyDecision(
        eligible=True,
        predicted_positive_effect_probability=0.5001,
        assignment=TreatmentAssignment.ON,
    )
    assert above.assignment is TreatmentAssignment.ON
    with pytest.raises(ValidationError):
        PolicyDecision(
            eligible=False,
            predicted_positive_effect_probability=1.0,
            assignment=TreatmentAssignment.ON,
        )


def test_semantic_nonuse_does_not_invalidate_correct_delivery():
    trace = TreatmentDeliveryTrace(
        assignment=TreatmentAssignment.ON,
        status=TreatmentDeliveryStatus.DELIVERED,
        expected_resource_sha256="a" * 64,
        delivered_resource_sha256="a" * 64,
        semantic_adoption_diagnostic=False,
    )
    assert trace.mechanically_valid is True


def test_eligibility_is_mechanical_and_strict():
    assert EligibilityDecision(status=EligibilityStatus.ELIGIBLE).hard_reasons == ()
    with pytest.raises(ValidationError):
        EligibilityDecision(status=EligibilityStatus.INELIGIBLE)
    with pytest.raises(ValidationError):
        CandidateLineage(
            source="ESConv",
            owner_id="audit",
            source_record_ids=("1",),
            strict_past=True,
            content_sha256="a" * 64,
            unexpected="forbidden",
        )


def test_official_outcome_contract_rejects_project_composites():
    outcome = OfficialOutcomeRecord(
        benchmark="ESC-Eval",
        task_type=TaskType.ESC_RESPONSE,
        target_id="card-1",
        arm=ExperimentArm.R0,
        metrics={"Overall": 2.0, "Empathy": 3.0},
        official_scorer_id="ESC-RANK@450bf2e",
    )
    assert outcome.metrics["Overall"] == 2.0
    with pytest.raises(ValidationError):
        OfficialOutcomeRecord(
            benchmark="ESC-Eval",
            task_type=TaskType.ESC_RESPONSE,
            target_id="card-1",
            arm=ExperimentArm.R0,
            metrics={"composite": 1.0},
            official_scorer_id="invalid",
        )
