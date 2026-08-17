from metacom_pm.paper1.semantic_memory.contracts import (
    MEHistoricalOutcomeType,
    MPProfileFieldType,
    MSContinuityType,
    ProposedMEMemoryUnit,
    ProposedMPMemoryUnit,
    ProposedMSMemoryUnit,
    SupportingSpan,
)
from metacom_pm.paper1.semantic_memory.renderer import render_semantic_memory


def _span(span_id: str = "s1") -> SupportingSpan:
    return SupportingSpan(
        span_id=span_id,
        turn_id="esc1:turn:1",
        exact_text="Exact seeker evidence.",
    )


def test_renderer_has_exact_frozen_mp_output() -> None:
    proposal = ProposedMPMemoryUnit(
        proposal_id="mp1",
        profile_field_type=MPProfileFieldType.LOCATION,
        factual_claim="The seeker lives in Kyoto.",
        supporting_spans=(_span(),),
        entities=("Kyoto",),
        linked_prior_relations=(),
    )
    assert render_semantic_memory(proposal) == (
        "Profile fact [location]: The seeker lives in Kyoto."
    )


def test_renderer_has_exact_frozen_ms_output() -> None:
    proposal = ProposedMSMemoryUnit(
        proposal_id="ms1",
        continuity_type=MSContinuityType.EVENT,
        factual_claim="The seeker argued with Jack that day.",
        event_status="completed",
        supporting_spans=(_span(),),
        entities=("Jack",),
        linked_prior_relations=(),
    )
    assert render_semantic_memory(proposal) == (
        "Continuity fact [event; source_status=completed]: "
        "The seeker argued with Jack that day."
    )


def test_renderer_has_exact_frozen_me_output() -> None:
    proposal = ProposedMEMemoryUnit(
        proposal_id="me1",
        historical_outcome_type=MEHistoricalOutcomeType.NEGATIVE,
        action="The seeker tried journaling.",
        observed_outcome="The seeker did not feel better.",
        supporting_spans=(_span("action"), _span("outcome")),
        entities=(),
        linked_prior_relations=(),
        action_span_ids=("action",),
        observed_outcome_span_ids=("outcome",),
    )
    assert render_semantic_memory(proposal) == (
        "Past action: The seeker tried journaling. "
        "User-observed outcome [negative]: The seeker did not feel better."
    )
