import pytest
from pydantic import ValidationError

from metacom_pm.paper1.semantic_memory.contracts import (
    ExtractorSessionOutput,
    MEHistoricalOutcomeType,
    MPProfileFieldType,
    MSContinuityType,
    ProposedMEMemoryUnit,
    ProposedMPMemoryUnit,
    ProposedMSMemoryUnit,
    SessionCompileInput,
    SessionTurnInput,
    SupportingSpan,
    TemporalStatus,
)
from metacom_pm.paper1.semantic_memory.evidence_v8 import (
    EvidenceTemporalStatus,
    ExperienceLinkageV8,
    PersistenceObservation,
)
from metacom_pm.paper1.semantic_memory.evidence_v9 import (
    METypedEvidenceV9,
    MPTypedEvidenceV9,
    MSTypedEvidenceV9,
    PersistenceBasis,
    PredicateRelation,
    SemanticActionOutcomeOrder,
    SupportRelation,
    V9EvidenceWireSessionOutput,
)
from metacom_pm.paper1.semantic_memory.precision_qualification import (
    CurrentValidityEvidence,
)
from metacom_pm.paper1.semantic_memory.runtime_v9_dev import (
    deterministic_v9_decision,
    strict_v9_output,
    v9_binding_violations,
)


def _source(text: str) -> SessionCompileInput:
    return SessionCompileInput(
        owner_id="u",
        session_id="s",
        timestamp="2024-01-01",
        chronological_rank=0,
        turns=(
            SessionTurnInput(
                turn_id="s:turn:1", turn_index=1, role="seeker", content=text
            ),
        ),
    )


def _mp_case(text: str = "I just celebrated my 18th birthday."):
    source = _source(text)
    span = SupportingSpan(span_id="mp-span", turn_id="s:turn:1", exact_text=text)
    proposal = ProposedMPMemoryUnit(
        proposal_id="mp",
        profile_field_type=MPProfileFieldType.AGE,
        factual_claim="The owner is 18 years old.",
        supporting_spans=(span,),
        entities=(),
        linked_prior_relations=(),
    )
    return source, proposal, span


def _mp_evidence(span: SupportingSpan, **updates) -> MPTypedEvidenceV9:
    values = {
        "proposal_id": "mp",
        "exact_support_spans": (span,),
        "field_type": MPProfileFieldType.AGE,
        "owner_subject_direct": True,
        "support_relation": SupportRelation.CONVENTIONAL_ENTAILMENT,
        "temporal_status": EvidenceTemporalStatus.CURRENT,
        "persistence": PersistenceObservation.DURABLE,
        "persistence_basis": PersistenceBasis.CONVENTIONAL_STABLE_ATTRIBUTE,
        "requires_prior_memory_inference": False,
        "current_validity_evidence": CurrentValidityEvidence.DIRECT_CURRENT,
    }
    values.update(updates)
    return MPTypedEvidenceV9(**values)


def test_v9_provider_schema_forbids_model_verdict_reason_and_confidence():
    source = {
        **_mp_evidence(
            SupportingSpan(span_id="mp-span", turn_id="s:turn:1", exact_text="x")
        ).model_dump(mode="json"),
        "accepted": True,
        "reason": "looks useful",
        "confidence": 0.99,
    }
    with pytest.raises(ValidationError):
        MPTypedEvidenceV9.model_validate(source)


def test_v9_mp_accepts_conventional_entailment_without_prior_memory():
    source, proposal, span = _mp_case()
    decision = deterministic_v9_decision(source, proposal, _mp_evidence(span))
    assert decision.accepted
    assert decision.gate_reasons == ()


def test_v9_mp_rejects_temporary_transition_despite_durable_label():
    source, proposal, span = _mp_case("I am the new kid at work this week.")
    evidence = _mp_evidence(
        span,
        persistence=PersistenceObservation.DURABLE,
        persistence_basis=PersistenceBasis.TEMPORARY_TRANSITION,
    )
    decision = deterministic_v9_decision(source, proposal, evidence)
    assert not decision.accepted
    assert "persistence_basis_not_supportive" in decision.gate_reasons


def test_v9_mp_prior_relation_and_boolean_must_agree():
    source, proposal, span = _mp_case()
    evidence = _mp_evidence(
        span,
        support_relation=SupportRelation.PRIOR_DEPENDENT,
        requires_prior_memory_inference=False,
    )
    decision = deterministic_v9_decision(source, proposal, evidence)
    assert not decision.accepted
    assert "support_relation_prior_flag_disagrees" in decision.internal_contradictions


def _me_case():
    text = "I tried breathing exercises, and they helped me feel calmer."
    source = _source(text)
    broad = SupportingSpan(span_id="both", turn_id="s:turn:1", exact_text=text)
    proposal = ProposedMEMemoryUnit(
        proposal_id="me",
        historical_outcome_type=MEHistoricalOutcomeType.POSITIVE,
        action="The owner tried breathing exercises.",
        observed_outcome="The owner felt calmer.",
        supporting_spans=(broad,),
        action_span_ids=("both",),
        observed_outcome_span_ids=("both",),
        entities=(),
        linked_prior_relations=(),
    )
    action = SupportingSpan(
        span_id="both", turn_id="s:turn:1", exact_text="I tried breathing exercises"
    )
    outcome = SupportingSpan(
        span_id="both", turn_id="s:turn:1", exact_text="they helped me feel calmer"
    )
    evidence = METypedEvidenceV9(
        proposal_id="me",
        action_spans=(action,),
        owner_action=True,
        action_agentive=True,
        action_completed=True,
        outcome_spans=(outcome,),
        outcome_user_observed=True,
        semantic_temporal_relation=SemanticActionOutcomeOrder.ACTION_THEN_OUTCOME,
        predicate_relation=PredicateRelation.DISTINCT,
        future_or_hypothetical=False,
        purpose_or_prediction=False,
        same_experience_linkage=ExperienceLinkageV8.SAME_EXPERIENCE,
    )
    return source, proposal, evidence


def test_v9_me_accepts_minimal_ordered_subspans_from_one_broad_grounded_span():
    source, proposal, evidence = _me_case()
    assert v9_binding_violations(source, proposal, evidence) == ()
    assert deterministic_v9_decision(source, proposal, evidence).accepted


def test_v9_me_rejects_unseparated_shared_full_span_order():
    source, proposal, evidence = _me_case()
    full = proposal.supporting_spans[0]
    evidence = evidence.model_copy(
        update={"action_spans": (full,), "outcome_spans": (full,)}
    )
    decision = deterministic_v9_decision(source, proposal, evidence)
    assert not decision.accepted
    assert "me_action_before_outcome_not_mechanically_proven" in decision.binding_violations


def test_v9_me_rejects_semantic_restatement_even_when_spans_are_ordered():
    source, proposal, evidence = _me_case()
    evidence = evidence.model_copy(
        update={"predicate_relation": PredicateRelation.SAME_OR_RESTATEMENT}
    )
    decision = deterministic_v9_decision(source, proposal, evidence)
    assert not decision.accepted
    assert "predicate_same_or_restatement" in decision.gate_reasons


def test_v9_binding_rejects_text_outside_grounded_proposal_span():
    source, proposal, evidence = _me_case()
    bad = SupportingSpan(
        span_id="both", turn_id="s:turn:1", exact_text="feel calmer"
    )
    # It is in the source turn, but this changed proposal proves the binder
    # checks the grounded proposal span independently.
    proposal = proposal.model_copy(
        update={
            "supporting_spans": (
                SupportingSpan(
                    span_id="both",
                    turn_id="s:turn:1",
                    exact_text="I tried breathing exercises",
                ),
            )
        }
    )
    evidence = evidence.model_copy(update={"outcome_spans": (bad,)})
    assert "evidence_not_subspan_of_grounded_proposal" in v9_binding_violations(
        source, proposal, evidence
    )


def test_v9_ms_keeps_event_state_change_lane_and_rejects_failed_me_dumping():
    text = "Last month I moved apartments and I am still unpacking."
    source = _source(text)
    span = SupportingSpan(span_id="ms-span", turn_id="s:turn:1", exact_text=text)
    proposal = ProposedMSMemoryUnit(
        proposal_id="ms",
        continuity_type=MSContinuityType.CHANGE,
        factual_claim="The owner moved apartments and is still unpacking.",
        event_status=TemporalStatus.ONGOING,
        supporting_spans=(span,),
        entities=(),
        linked_prior_relations=(),
    )
    evidence = MSTypedEvidenceV9(
        proposal_id="ms",
        exact_support_spans=(span,),
        continuity_type=MSContinuityType.CHANGE,
        owner_event_or_state=True,
        support_relation=SupportRelation.DIRECT_EXPLICIT,
        source_temporal_status=EvidenceTemporalStatus.PAST,
        event_or_thread_traceable=True,
        profile_like=False,
        greeting_or_trivia=False,
        malformed_me=True,
    )
    decision = deterministic_v9_decision(source, proposal, evidence)
    assert not decision.accepted
    assert decision.gate_reasons == ("malformed_me",)


def test_v9_wire_parser_is_per_item_fail_closed_and_lane_bound():
    source, proposal, span = _mp_case()
    extractor = ExtractorSessionOutput(owner_id="u", session_id="s", mp_facts=(proposal,))
    valid = _mp_evidence(span).model_dump(mode="json")
    invalid = {**valid, "proposal_id": "unknown"}
    wire = V9EvidenceWireSessionOutput(
        owner_id="u", session_id="s", mp_evidence=(valid, invalid)
    )
    parsed, rejected = strict_v9_output(wire, extractor=extractor)
    assert [row.proposal_id for row in parsed.mp_evidence] == ["mp"]
    assert len(rejected) == 1
    assert rejected[0].violations == ("proposal_id:unknown_or_wrong_class_lane",)
