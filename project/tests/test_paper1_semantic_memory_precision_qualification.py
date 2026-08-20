import pytest

from metacom_pm.paper1.semantic_memory.contracts import MPProfileFieldType, SupportingSpan
from metacom_pm.paper1.semantic_memory.precision_qualification import (
    CurrentValidityEvidence,
    DurabilityEvidence,
    ExperienceLinkage,
    MEPrecisionDecision,
    MEPrecisionReason,
    MPPrecisionDecision,
    MPPrecisionReason,
    PRECISION_EXTRACTOR_SYSTEM_PROMPT,
)


def _span(text="I am 26"):
    return (SupportingSpan(span_id="s1", turn_id="t1", exact_text=text),)


def test_mp_gate_rejects_prior_inference_even_with_durable_prior():
    with pytest.raises(ValueError, match="requires_prior_inference"):
        MPPrecisionDecision(
            proposal_id="p",
            exact_support_span=_span("Jane and I planned a trip"),
            field_type=MPProfileFieldType.STABLE_SOCIAL_ROLE,
            owner_subject_direct=True,
            directly_entailed_by_current_span=True,
            durability_evidence=DurabilityEvidence.DIRECT_ENDURING,
            current_validity_evidence=CurrentValidityEvidence.DIRECT_CURRENT_ROLE,
            episodic_or_transient=False,
            future_plan=False,
            requires_prior_inference=True,
            accepted=True,
            reason=MPPrecisionReason.ACCEPTED,
        )


def test_mp_health_gate_rejects_one_transient_feeling():
    with pytest.raises(ValueError, match="health_durability"):
        MPPrecisionDecision(
            proposal_id="p",
            exact_support_span=_span("I am depressed because of my friends"),
            field_type=MPProfileFieldType.HEALTH_CONDITION,
            owner_subject_direct=True,
            directly_entailed_by_current_span=True,
            durability_evidence=DurabilityEvidence.DIRECT_ENDURING,
            current_validity_evidence=CurrentValidityEvidence.DIRECT_CURRENT,
            episodic_or_transient=False,
            future_plan=False,
            requires_prior_inference=False,
            accepted=True,
            reason=MPPrecisionReason.ACCEPTED,
        )


def test_me_gate_rejects_same_predicate_symptom_as_action_and_outcome():
    with pytest.raises(ValueError, match="same_predicate"):
        MEPrecisionDecision(
            proposal_id="m",
            action_span=_span("I panicked"),
            action_is_owner=True,
            action_is_agentive=True,
            action_is_completed=True,
            outcome_span=_span("I was panicking"),
            outcome_is_user_observed=True,
            action_before_outcome=True,
            same_predicate=True,
            future_or_hypothetical=False,
            purpose_or_prediction_as_outcome=False,
            experience_linkage=ExperienceLinkage.SAME_EXPERIENCE,
            accepted=True,
            reason=MEPrecisionReason.ACCEPTED,
        )


def test_precision_prompt_contains_no_dev_item_blacklist_identifiers():
    for item_specific in ("esc508", "p18_conv_8", "Margaret", "Jessica"):
        assert item_specific not in PRECISION_EXTRACTOR_SYSTEM_PROMPT
