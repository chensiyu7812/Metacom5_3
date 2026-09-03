import pytest
from pydantic import ValidationError

from metacom_pm.paper1.contracts import (
    CandidateLineage,
    CostRecord,
    EndToEndLatencyRecord,
    EligibilityDecision,
    EligibilityStatus,
    ExperimentArm,
    LatencyMeasurementSurface,
    OfficialOutcomeRecord,
    PolicyDecision,
    PolicyOperatingMode,
    SoftEffectTarget,
    TaskType,
    TreatmentAssignment,
    TreatmentDeliveryStatus,
    TreatmentDeliveryTrace,
    WarmState,
)


def test_soft_effect_preserves_ties_and_uncertainty_without_a_pass_gate():
    target = SoftEffectTarget(
        on_better=2,
        off_better=1,
        equivalent=1,
        uncertain=2,
        invalid=1,
    )
    assert target.measured_pairs == 4
    assert target.nonpositive_pairs == 2
    assert target.positive_effect_fraction == pytest.approx(0.5)
    assert target.excluded_pairs == 3
    assert target.total_pairs == 7
    assert target.uncertain == 2
    assert target.invalid == 1


def test_equivalent_is_nonpositive_not_half_a_positive_effect():
    target = SoftEffectTarget(on_better=1, off_better=0, equivalent=2, uncertain=0)
    assert target.positive_effect_fraction == pytest.approx(1 / 3)


def test_policy_rule_requires_an_explicit_frozen_operating_point():
    at_threshold = PolicyDecision(
        eligible=True,
        predicted_positive_effect_probability=0.5,
        operating_mode=PolicyOperatingMode.CALIBRATED_THRESHOLD,
        threshold=0.5,
        threshold_protocol_id="threshold-freeze-v1",
        assignment=TreatmentAssignment.OFF,
    )
    assert at_threshold.assignment is TreatmentAssignment.OFF
    above = PolicyDecision(
        eligible=True,
        predicted_positive_effect_probability=0.5001,
        operating_mode=PolicyOperatingMode.CALIBRATED_THRESHOLD,
        threshold=0.5,
        threshold_protocol_id="threshold-freeze-v1",
        assignment=TreatmentAssignment.ON,
    )
    assert above.assignment is TreatmentAssignment.ON
    with pytest.raises(ValidationError):
        PolicyDecision(
            eligible=False,
            predicted_positive_effect_probability=1.0,
            operating_mode=PolicyOperatingMode.ELIGIBLE_ALWAYS_ON,
            threshold_protocol_id="threshold-freeze-v1",
            assignment=TreatmentAssignment.ON,
        )


def test_latency_constrained_policy_requires_benefit_and_client_feasibility():
    decision = PolicyDecision(
        eligible=True,
        predicted_positive_effect_probability=0.8,
        operating_mode=PolicyOperatingMode.LATENCY_CONSTRAINED_THRESHOLD,
        threshold=0.5,
        threshold_protocol_id="threshold-v3",
        client_latency_protocol_id="paper1-client-latency-measurement-v2",
        predicted_p95_client_ttft_ms=800,
        predicted_p95_client_completion_ms=1_800,
        catastrophic_completion_ceiling_ms=60_000,
        deployment_scenario_id="interactive-test-v1",
        deployment_ttft_budget_ms=1_000,
        deployment_completion_budget_ms=2_000,
        assignment=TreatmentAssignment.ON,
    )
    assert decision.assignment is TreatmentAssignment.ON
    with pytest.raises(ValidationError, match="assignment violates"):
        PolicyDecision(
            eligible=True,
            predicted_positive_effect_probability=0.8,
            operating_mode=PolicyOperatingMode.LATENCY_CONSTRAINED_THRESHOLD,
            threshold=0.5,
            threshold_protocol_id="threshold-v3",
            client_latency_protocol_id="paper1-client-latency-measurement-v2",
            predicted_p95_client_ttft_ms=1_200,
            predicted_p95_client_completion_ms=1_800,
            catastrophic_completion_ceiling_ms=60_000,
            deployment_scenario_id="interactive-test-v1",
            deployment_ttft_budget_ms=1_000,
            deployment_completion_budget_ms=2_000,
            assignment=TreatmentAssignment.ON,
        )


def test_latency_telemetry_retains_sla_violations_and_aliases_completion():
    breakdown = EndToEndLatencyRecord(
        trace_id="trace-1",
        measurement_surface=LatencyMeasurementSurface.REFERENCE_CLIENT,
        time_block_id="block-1",
        randomized_sequence_position=0,
        client_region="local-a6000",
        warm_state=WarmState.WARM,
        concurrency=1,
        connection_reuse=True,
        policy_decision_ms=10,
        retrieval_embedding_ms=20,
        resource_render_pack_ms=5,
        provider_request_to_first_content_ms=1_900,
        provider_request_to_completion_ms=70_000,
        client_send_to_first_visible_text_ms=2_000,
        client_send_to_final_visible_text_ms=70_035,
        streaming_observed=True,
        timeout_or_fallback=True,
        input_tokens=10,
        output_tokens=3,
        retry_count=1,
        finish_reason="timeout_fallback",
    )
    record = CostRecord(
        generator_input_tokens=10,
        resource_injected_tokens=2,
        output_tokens=3,
        total_tokens=13,
        latency_ms=70_035,
        latency_breakdown=breakdown,
    )
    assert record.latency_breakdown is not None
    assert record.latency_breakdown.timeout_or_fallback is True
    with pytest.raises(ValidationError, match="must alias"):
        CostRecord(**{**record.model_dump(), "latency_ms": 1})
    always_off = PolicyDecision(
        eligible=True,
        predicted_positive_effect_probability=1.0,
        operating_mode=PolicyOperatingMode.ALWAYS_OFF,
        threshold_protocol_id="threshold-freeze-v1",
        assignment=TreatmentAssignment.OFF,
    )
    assert always_off.assignment is TreatmentAssignment.OFF
    with pytest.raises(ValidationError, match="require a frozen threshold"):
        PolicyDecision(
            eligible=True,
            predicted_positive_effect_probability=0.9,
            operating_mode=PolicyOperatingMode.CALIBRATED_THRESHOLD,
            threshold_protocol_id="threshold-freeze-v1",
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


def test_off_treatment_can_record_prompt_contamination_as_technical_failure():
    trace = TreatmentDeliveryTrace(
        assignment=TreatmentAssignment.OFF,
        status=TreatmentDeliveryStatus.TECHNICAL_FAILURE,
        mechanical_violations=("off_prompt_contains_resource",),
    )
    assert trace.mechanically_valid is False


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
