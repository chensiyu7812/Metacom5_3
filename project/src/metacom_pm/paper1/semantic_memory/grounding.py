"""Deterministic structural grounding, separate from semantic verification."""

from __future__ import annotations

from dataclasses import dataclass

from metacom_pm.io import canonical_json, sha256_text

from .contracts import (
    ExtractorSessionOutput,
    GroundedSupportingSpan,
    MEMORY_SUBTYPES_BY_CLASS,
    TEMPORAL_STATUSES_BY_CLASS,
    MemoryClass,
    MSContinuityType,
    PriorMemoryRelationType,
    ProposedSemanticMemoryUnit,
    ProposedMSMemoryUnit,
    SessionCompileInput,
    SourceRole,
    VerifierSessionOutput,
)

GROUNDING_VERSION = "paper1-semantic-memory-structural-grounding-v6"


@dataclass(frozen=True)
class GroundingResult:
    proposal_id: str
    schema_valid: bool
    structural_valid: bool
    valid: bool
    violations: tuple[str, ...]
    grounded_spans: tuple[GroundedSupportingSpan, ...]


def proposal_contract_violations(
    proposal: ProposedSemanticMemoryUnit,
) -> tuple[str, ...]:
    """Validate cross-field constraints per atomic proposal, not per envelope."""

    violations: list[str] = []
    if proposal.memory_subtype not in MEMORY_SUBTYPES_BY_CLASS[proposal.memory_class]:
        violations.append("schema_memory_subtype_class_mismatch")
    if proposal.timestamp_status not in TEMPORAL_STATUSES_BY_CLASS[proposal.memory_class]:
        violations.append("schema_timestamp_status_class_mismatch")
    if (
        isinstance(proposal, ProposedMSMemoryUnit)
        and proposal.continuity_type in {MSContinuityType.EVENT, MSContinuityType.CHANGE}
        and proposal.timestamp_status.value != "completed"
    ):
        violations.append("schema_ms_event_or_change_not_completed")
    span_ids = [span.span_id for span in proposal.supporting_spans]
    known = set(span_ids)
    if len(span_ids) != len(known):
        violations.append("schema_duplicate_supporting_span_ids")
    if len(proposal.entities) != len(set(proposal.entities)):
        violations.append("schema_duplicate_entities")
    if len(proposal.linked_prior_memory_ids) != len(
        set(proposal.linked_prior_memory_ids)
    ):
        violations.append("schema_duplicate_linked_prior_memory_ids")
    if len(proposal.action_span_ids) != len(set(proposal.action_span_ids)):
        violations.append("schema_duplicate_action_span_ids")
    if len(proposal.observed_outcome_span_ids) != len(
        set(proposal.observed_outcome_span_ids)
    ):
        violations.append("schema_duplicate_observed_outcome_span_ids")
    if not set(proposal.action_span_ids).issubset(known):
        violations.append("schema_unknown_action_span_id")
    if not set(proposal.observed_outcome_span_ids).issubset(known):
        violations.append("schema_unknown_observed_outcome_span_id")
    if proposal.memory_class is MemoryClass.ME:
        if not proposal.action_span_ids:
            violations.append("schema_me_missing_action_spans")
        if not proposal.observed_outcome_span_ids:
            violations.append("schema_me_missing_observed_outcome_spans")
    elif proposal.action_span_ids or proposal.observed_outcome_span_ids:
        violations.append("schema_non_me_has_action_outcome_spans")
    return tuple(sorted(set(violations)))


def source_sha256(source: SessionCompileInput) -> str:
    current_only = source.model_dump(mode="json", exclude={"strictly_past_memory_table"})
    return sha256_text(canonical_json(current_only))


def prior_memory_table_sha256(source: SessionCompileInput) -> str:
    table = [memory.model_dump(mode="json") for memory in source.strictly_past_memory_table]
    return sha256_text(canonical_json(table))


def validate_output_binding(
    source: SessionCompileInput,
    extractor: ExtractorSessionOutput,
) -> None:
    if extractor.owner_id != source.owner_id or extractor.session_id != source.session_id:
        raise ValueError("extractor output owner/session binding mismatch")


def validate_verifier_binding(
    source: SessionCompileInput,
    extractor: ExtractorSessionOutput,
    verifier: VerifierSessionOutput,
) -> None:
    if verifier.owner_id != source.owner_id or verifier.session_id != source.session_id:
        raise ValueError("verifier output owner/session binding mismatch")
    expected = {proposal.proposal_id for proposal in extractor.proposals}
    actual = {decision.proposal_id for decision in verifier.decisions}
    if actual != expected:
        raise ValueError(
            "verifier decision coverage mismatch: "
            f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
        )


def validate_proposal_grounding(
    source: SessionCompileInput,
    proposal: ProposedSemanticMemoryUnit,
) -> GroundingResult:
    turns = {turn.turn_id: turn for turn in source.turns}
    prior_by_id = {
        memory.memory_id: memory for memory in source.strictly_past_memory_table
    }
    schema_violations = list(proposal_contract_violations(proposal))
    structural_violations: list[str] = []
    grounded_spans: list[GroundedSupportingSpan] = []
    for span in proposal.supporting_spans:
        turn = turns.get(span.turn_id)
        if turn is None:
            structural_violations.append(f"unknown_turn_id:{span.span_id}")
            continue
        if turn.role is not SourceRole.SEEKER:
            structural_violations.append(f"non_seeker_source:{span.span_id}")
        start_char = turn.content.find(span.exact_text)
        if start_char < 0:
            structural_violations.append(f"span_text_absent:{span.span_id}")
            continue
        if turn.content.find(span.exact_text, start_char + 1) >= 0:
            structural_violations.append(f"span_text_ambiguous:{span.span_id}")
            continue
        grounded_spans.append(
            GroundedSupportingSpan(
                span_id=span.span_id,
                turn_id=span.turn_id,
                exact_text=span.exact_text,
                start_char=start_char,
                end_char=start_char + len(span.exact_text),
            )
        )
    for link in proposal.linked_prior_relations:
        prior = prior_by_id.get(link.memory_id)
        if prior is None:
            structural_violations.append(
                f"unknown_linked_prior_memory:{link.memory_id}"
            )
        elif (
            link.relation is not PriorMemoryRelationType.COREFERS_WITH
            and prior.memory_class is not proposal.memory_class
        ):
            structural_violations.append(
                f"cross_class_version_relation:{link.memory_id}"
            )
    violations = schema_violations + structural_violations
    return GroundingResult(
        proposal_id=proposal.proposal_id,
        schema_valid=not schema_violations,
        structural_valid=not structural_violations,
        valid=not violations,
        violations=tuple(sorted(set(violations))),
        grounded_spans=tuple(grounded_spans),
    )
