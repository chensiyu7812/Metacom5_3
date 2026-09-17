import pytest

from metacom_pm.paper1.semantic_memory.contracts import (
    CandidateSourceUse,
    ExtractorSessionOutput,
    LinkedPriorMemoryRelation,
    MPProfileFieldType,
    MSContinuityType,
    MemoryClass,
    PriorAcceptedMemory,
    PriorMemoryRelationType,
    ProposedMPMemoryUnit,
    SessionCompileInput,
    SessionTurnInput,
    SupportingSpan,
    VerifierDecision,
    VerifierRejectionReason,
    VerifierSessionOutput,
)
from metacom_pm.paper1.semantic_memory.grounding import (
    validate_proposal_grounding,
    validate_verifier_binding,
)


def _source() -> SessionCompileInput:
    return SessionCompileInput(
        owner_id="u1",
        session_id="esc1",
        timestamp="2024-01-01",
        chronological_rank=0,
        turns=(
            SessionTurnInput(
                turn_id="esc1:turn:1", turn_index=1, role="seeker", content="I moved to Kyoto."
            ),
            SessionTurnInput(
                turn_id="esc1:turn:2", turn_index=2, role="supporter", content="You moved."
            ),
        ),
    )


def _proposal(span: SupportingSpan) -> ProposedMPMemoryUnit:
    return ProposedMPMemoryUnit(
        proposal_id="p1",
        profile_field_type=MPProfileFieldType.LOCATION,
        factual_claim="The seeker moved to Kyoto.",
        supporting_spans=(span,),
        entities=("Kyoto",),
        linked_prior_relations=(),
    )


def test_grounding_requires_exact_seeker_span_and_derives_offsets() -> None:
    valid = validate_proposal_grounding(
        _source(),
        _proposal(
            SupportingSpan(
                span_id="s1", turn_id="esc1:turn:1", exact_text="moved to Kyoto"
            )
        ),
    )
    assert valid.valid
    assert valid.grounded_spans[0].start_char == 2
    assert valid.grounded_spans[0].end_char == 16
    supporter = validate_proposal_grounding(
        _source(),
        _proposal(
            SupportingSpan(
                span_id="s1", turn_id="esc1:turn:2", exact_text="You moved"
            )
        ),
    )
    assert supporter.violations == ("non_seeker_source:s1",)


def test_verifier_must_cover_exact_proposal_id_set() -> None:
    proposal = _proposal(
        SupportingSpan(
            span_id="s1", turn_id="esc1:turn:1", exact_text="I moved"
        )
    )
    extractor = ExtractorSessionOutput(
        owner_id="u1", session_id="esc1", mp_facts=(proposal,)
    )
    verifier = VerifierSessionOutput(
        owner_id="u1",
        session_id="esc1",
        decisions=(
            VerifierDecision(
                proposal_id="replacement",
                accepted=False,
                reason=VerifierRejectionReason.OTHER_FACTUAL_MISMATCH,
                factual_rationale="Wrong ID.",
            ),
        ),
    )
    with pytest.raises(ValueError, match=r"missing=\['p1'\], extra=\['replacement'\]"):
        validate_verifier_binding(_source(), extractor, verifier)


def test_non_coreference_version_relation_must_stay_within_memory_class() -> None:
    source = _source().model_copy(
        update={
            "chronological_rank": 1,
            "strictly_past_memory_table": (
                PriorAcceptedMemory(
                    memory_id="prior-ms",
                    owner_id="u1",
                    source_session_id="esc0",
                    source_session_rank=0,
                    memory_class=MemoryClass.MS,
                    memory_subtype="ms_state",
                    normalized_memory="The seeker was worried.",
                    timestamp_status="ongoing",
                    candidate_source_use=CandidateSourceUse.CANDIDATE_SOURCE,
                    continuity_type=MSContinuityType.STATE,
                ),
            ),
        }
    )
    span = SupportingSpan(
        span_id="s1", turn_id="esc1:turn:1", exact_text="moved to Kyoto"
    )
    proposal = _proposal(span).model_copy(
        update={
            "linked_prior_relations": (
                LinkedPriorMemoryRelation(
                    memory_id="prior-ms",
                    relation=PriorMemoryRelationType.SUPERSEDES,
                ),
            )
        }
    )
    result = validate_proposal_grounding(source, proposal)
    assert result.violations == ("cross_class_version_relation:prior-ms",)

    coreference = proposal.model_copy(
        update={
            "linked_prior_relations": (
                LinkedPriorMemoryRelation(
                    memory_id="prior-ms",
                    relation=PriorMemoryRelationType.COREFERS_WITH,
                ),
            )
        }
    )
    assert validate_proposal_grounding(source, coreference).valid is True
