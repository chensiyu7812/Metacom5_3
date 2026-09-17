"""Offline v9 evidence parsing, source binding, and deterministic decisions.

There is intentionally no provider client and no 401-session compiler in this
module.  A later live DEV runner requires a separate researcher authorization.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Type

from pydantic import BaseModel, ValidationError

from .contracts import (
    ExtractorSessionOutput,
    MemoryClass,
    ProposedMEMemoryUnit,
    ProposedMPMemoryUnit,
    ProposedMSMemoryUnit,
    ProposedSemanticMemoryUnit,
    SchemaRejectedItem,
    SessionCompileInput,
    SourceRole,
    SupportingSpan,
)
from .evidence_v9 import (
    DeterministicV9Decision,
    METypedEvidenceV9,
    MPTypedEvidenceV9,
    MSTypedEvidenceV9,
    TypedEvidenceV9,
    V9EvidenceSessionOutput,
    V9EvidenceWireSessionOutput,
    me_gate_reasons_v9,
    me_internal_contradictions_v9,
    mp_gate_reasons_v9,
    mp_internal_contradictions_v9,
    ms_gate_reasons_v9,
    ms_internal_contradictions_v9,
)
from .runtime import _raw_proposal_id, _schema_rejection, _validation_violations


COMPILER_VERSION_V9_DEV = "paper1-qwen-semantic-memory-verifier-v9-dev-offline"
LOCAL_BINDING_VERSION_V9_DEV = "paper1-semantic-memory-v9-minimal-subspan-binding-v1"


def _expected_by_class(extractor: ExtractorSessionOutput) -> dict[MemoryClass, set[str]]:
    return {
        MemoryClass.MP: {item.proposal_id for item in extractor.mp_facts},
        MemoryClass.MS: {item.proposal_id for item in extractor.ms_memories},
        MemoryClass.ME: {item.proposal_id for item in extractor.me_experiences},
    }


def strict_v9_output(
    wire: V9EvidenceWireSessionOutput,
    *,
    extractor: ExtractorSessionOutput,
) -> tuple[V9EvidenceSessionOutput, tuple[SchemaRejectedItem, ...]]:
    """Parse each provider row independently and require one row per proposal."""

    expected_by_class = _expected_by_class(extractor)
    lanes: tuple[
        tuple[str, MemoryClass, tuple[dict[str, Any], ...], Type[BaseModel]], ...
    ] = (
        ("mp_evidence", MemoryClass.MP, wire.mp_evidence, MPTypedEvidenceV9),
        ("ms_evidence", MemoryClass.MS, wire.ms_evidence, MSTypedEvidenceV9),
        ("me_evidence", MemoryClass.ME, wire.me_evidence, METypedEvidenceV9),
    )
    raw_ids = [_raw_proposal_id(raw) for _, _, rows, _ in lanes for raw in rows]
    duplicates = {
        proposal_id
        for proposal_id, count in Counter(raw_ids).items()
        if proposal_id is not None and count > 1
    }
    parsed: dict[str, list[BaseModel]] = {name: [] for name, _, _, _ in lanes}
    rejected: list[SchemaRejectedItem] = []
    covered: set[str] = set()
    item_index = 0
    for lane_name, memory_class, rows, model in lanes:
        for raw in rows:
            proposal_id = _raw_proposal_id(raw)
            if proposal_id is not None:
                covered.add(proposal_id)
            if proposal_id in duplicates:
                violations = ("proposal_id:schema_duplicate",)
            elif proposal_id not in expected_by_class[memory_class]:
                violations = ("proposal_id:unknown_or_wrong_class_lane",)
            else:
                try:
                    parsed[lane_name].append(model.model_validate(raw))
                    item_index += 1
                    continue
                except ValidationError as exc:
                    violations = _validation_violations(exc)
            rejected.append(
                _schema_rejection(
                    phase="verifier", item_index=item_index, raw=raw, violations=violations
                )
            )
            item_index += 1
    expected_all = set().union(*expected_by_class.values())
    for offset, proposal_id in enumerate(sorted(expected_all - covered)):
        rejected.append(
            _schema_rejection(
                phase="verifier",
                item_index=item_index + offset,
                raw={"proposal_id": proposal_id, "missing": True},
                violations=("proposal_id:missing_evidence",),
            )
        )
    return (
        V9EvidenceSessionOutput(
            owner_id=wire.owner_id,
            session_id=wire.session_id,
            mp_evidence=tuple(parsed["mp_evidence"]),
            ms_evidence=tuple(parsed["ms_evidence"]),
            me_evidence=tuple(parsed["me_evidence"]),
        ),
        tuple(rejected),
    )


def _proposal_span_by_id(proposal: ProposedSemanticMemoryUnit) -> dict[str, SupportingSpan]:
    return {span.span_id: span for span in proposal.supporting_spans}


def _bind_minimal_span(
    source: SessionCompileInput,
    proposal: ProposedSemanticMemoryUnit,
    span: SupportingSpan,
) -> list[str]:
    violations: list[str] = []
    turns = {turn.turn_id: turn for turn in source.turns}
    proposal_span = _proposal_span_by_id(proposal).get(span.span_id)
    if proposal_span is None:
        violations.append("unknown_proposal_span_id")
    else:
        if span.turn_id != proposal_span.turn_id:
            violations.append("proposal_span_turn_mismatch")
        if span.exact_text not in proposal_span.exact_text:
            violations.append("evidence_not_subspan_of_grounded_proposal")
    turn = turns.get(span.turn_id)
    if turn is None:
        violations.append("unknown_turn")
    else:
        if turn.role is not SourceRole.SEEKER:
            violations.append("non_seeker_span")
        occurrences = turn.content.count(span.exact_text)
        if occurrences == 0:
            violations.append("span_text_absent")
        elif occurrences > 1:
            violations.append("span_text_non_unique_in_turn")
    return violations


def _position(source: SessionCompileInput, span: SupportingSpan) -> tuple[int, int, int] | None:
    turn = next((item for item in source.turns if item.turn_id == span.turn_id), None)
    if turn is None or turn.content.count(span.exact_text) != 1:
        return None
    start = turn.content.index(span.exact_text)
    return (turn.turn_index, start, start + len(span.exact_text))


def _mechanical_action_before_outcome(
    source: SessionCompileInput,
    action_spans: tuple[SupportingSpan, ...],
    outcome_spans: tuple[SupportingSpan, ...],
) -> bool:
    action_positions = [_position(source, span) for span in action_spans]
    outcome_positions = [_position(source, span) for span in outcome_spans]
    if any(position is None for position in (*action_positions, *outcome_positions)):
        return False
    action_positions = [position for position in action_positions if position is not None]
    outcome_positions = [position for position in outcome_positions if position is not None]
    latest_action = max((turn, end) for turn, _start, end in action_positions)
    earliest_outcome = min((turn, start) for turn, start, _end in outcome_positions)
    return latest_action <= earliest_outcome


def v9_binding_violations(
    source: SessionCompileInput,
    proposal: ProposedSemanticMemoryUnit,
    evidence: TypedEvidenceV9,
) -> tuple[str, ...]:
    violations: list[str] = []
    if evidence.proposal_id != proposal.proposal_id:
        violations.append("proposal_id_mismatch")
    if isinstance(evidence, MPTypedEvidenceV9):
        spans = evidence.exact_support_spans
        if not isinstance(proposal, ProposedMPMemoryUnit):
            violations.append("wrong_proposal_class")
        elif evidence.field_type is not proposal.profile_field_type:
            violations.append("mp_field_type_mismatch")
    elif isinstance(evidence, MSTypedEvidenceV9):
        spans = evidence.exact_support_spans
        if not isinstance(proposal, ProposedMSMemoryUnit):
            violations.append("wrong_proposal_class")
        elif evidence.continuity_type is not proposal.continuity_type:
            violations.append("ms_continuity_type_mismatch")
    else:
        spans = (*evidence.action_spans, *evidence.outcome_spans)
        if not isinstance(proposal, ProposedMEMemoryUnit):
            violations.append("wrong_proposal_class")
        else:
            allowed_action_ids = set(proposal.action_span_ids)
            allowed_outcome_ids = set(proposal.observed_outcome_span_ids)
            if any(span.span_id not in allowed_action_ids for span in evidence.action_spans):
                violations.append("me_action_span_not_bound")
            if any(span.span_id not in allowed_outcome_ids for span in evidence.outcome_spans):
                violations.append("me_outcome_span_not_bound")
            if not _mechanical_action_before_outcome(
                source, evidence.action_spans, evidence.outcome_spans
            ):
                violations.append("me_action_before_outcome_not_mechanically_proven")
    for span in spans:
        violations.extend(_bind_minimal_span(source, proposal, span))
    return tuple(sorted(set(violations)))


def deterministic_v9_decision(
    source: SessionCompileInput,
    proposal: ProposedSemanticMemoryUnit,
    evidence: TypedEvidenceV9,
) -> DeterministicV9Decision:
    if isinstance(evidence, MPTypedEvidenceV9):
        gates = mp_gate_reasons_v9(evidence)
        contradictions = mp_internal_contradictions_v9(evidence)
    elif isinstance(evidence, MSTypedEvidenceV9):
        gates = ms_gate_reasons_v9(evidence)
        contradictions = ms_internal_contradictions_v9(evidence)
    else:
        gates = me_gate_reasons_v9(evidence)
        contradictions = me_internal_contradictions_v9(evidence)
    binding = v9_binding_violations(source, proposal, evidence)
    return DeterministicV9Decision(
        proposal_id=proposal.proposal_id,
        accepted=not (gates or contradictions or binding),
        gate_reasons=gates,
        binding_violations=binding,
        internal_contradictions=contradictions,
    )
