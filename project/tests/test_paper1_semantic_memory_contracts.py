from pydantic import ValidationError
import pytest

from metacom_pm.paper1.semantic_memory.contracts import (
    ExtractorSessionOutput,
    MEHistoricalOutcomeType,
    MPProfileFieldType,
    MSContinuityType,
    MemoryClass,
    MemorySubtype,
    ProposedMEMemoryUnit,
    ProposedMPMemoryUnit,
    ProposedMSMemoryUnit,
    SupportingSpan,
    VerifierDecision,
    VerifierRejectionReason,
)
from metacom_pm.paper1.semantic_memory.grounding import proposal_contract_violations


def _span() -> SupportingSpan:
    return SupportingSpan(
        span_id="s1", turn_id="esc1:turn:1", exact_text="I moved"
    )


def _mp(*, proposal_id: str = "p1") -> ProposedMPMemoryUnit:
    return ProposedMPMemoryUnit(
        proposal_id=proposal_id,
        profile_field_type=MPProfileFieldType.LOCATION,
        factual_claim="The seeker lives in Kyoto.",
        supporting_spans=(_span(),),
        entities=("Kyoto",),
        linked_prior_relations=(),
    )


def test_me_schema_requires_separate_nonempty_action_and_outcome_spans() -> None:
    with pytest.raises(ValidationError, match="at least 1 item"):
        ProposedMEMemoryUnit(
            proposal_id="p1",
            historical_outcome_type=MEHistoricalOutcomeType.NEUTRAL,
            action="The seeker moved.",
            observed_outcome="The seeker observed no change.",
            supporting_spans=(_span(),),
            entities=(),
            linked_prior_relations=(),
            action_span_ids=(),
            observed_outcome_span_ids=(),
        )


def test_verifier_can_only_decide_and_cannot_rewrite() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        VerifierDecision.model_validate(
            {
                "proposal_id": "p1",
                "accepted": False,
                "reason": "future_plan",
                "factual_rationale": "The action is future tense.",
                "replacement_memory": "rewritten",
            }
        )


def test_verifier_reason_must_match_acceptance() -> None:
    with pytest.raises(ValidationError, match="accepted must match"):
        VerifierDecision(
            proposal_id="p1",
            accepted=True,
            reason=VerifierRejectionReason.FUTURE_PLAN,
            factual_rationale="Mismatch.",
        )


def test_extractor_rejects_duplicate_ids_across_three_arrays() -> None:
    mp = _mp()
    ms = ProposedMSMemoryUnit(
        proposal_id="p1",
        continuity_type=MSContinuityType.EVENT,
        factual_claim="The seeker moved that day.",
        event_status="completed",
        supporting_spans=(_span(),),
        entities=(),
        linked_prior_relations=(),
    )
    with pytest.raises(ValidationError, match="proposal_id values must be unique"):
        ExtractorSessionOutput(
            owner_id="u1",
            session_id="esc1",
            mp_facts=(mp,),
            ms_memories=(ms,),
        )


def test_provider_schema_is_partitioned_and_has_no_global_class_or_subtype() -> None:
    schema = ExtractorSessionOutput.model_json_schema()
    assert set(schema["properties"]) == {
        "schema_version",
        "owner_id",
        "session_id",
        "mp_facts",
        "ms_memories",
        "me_experiences",
    }
    rendered = str(schema)
    assert "memory_class" not in rendered
    assert "memory_subtype" not in rendered
    assert "timestamp_status" not in rendered


def test_profile_field_enum_is_closed_and_derives_internal_subtype() -> None:
    assert _mp().memory_class is MemoryClass.MP
    assert _mp().memory_subtype is MemorySubtype.MP_LOCATION
    with pytest.raises(ValidationError, match="Input should be"):
        ProposedMPMemoryUnit(
            proposal_id="p1",
            profile_field_type="invented_profile_type",
            factual_claim="The seeker moved.",
            supporting_spans=(_span(),),
            entities=(),
            linked_prior_relations=(),
        )


def test_future_plan_is_not_a_valid_ms_output_status() -> None:
    with pytest.raises(ValidationError, match="Input should be"):
        ProposedMSMemoryUnit(
            proposal_id="p1",
            continuity_type=MSContinuityType.STATE,
            factual_claim="The seeker plans to move.",
            event_status="planned",
            supporting_spans=(_span(),),
            entities=(),
            linked_prior_relations=(),
        )


def test_event_or_change_must_be_completed_at_source_session_end() -> None:
    proposal = ProposedMSMemoryUnit(
        proposal_id="p1",
        continuity_type=MSContinuityType.EVENT,
        factual_claim="The seeker is moving.",
        event_status="ongoing",
        supporting_spans=(_span(),),
        entities=(),
        linked_prior_relations=(),
    )
    assert proposal_contract_violations(proposal) == (
        "schema_ms_event_or_change_not_completed",
    )
