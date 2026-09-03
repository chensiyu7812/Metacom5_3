"""Deterministic structural grounding for active MP/ME proposals."""

from __future__ import annotations

from dataclasses import dataclass

from metacom_pm.io import canonical_json, sha256_text

from .contracts import (
    ExtractorSessionOutput,
    GroundedSourceSpan,
    MultiViewSessionInput,
    ProposedAtomicMemoryUnit,
    VerifierSessionOutput,
)


MULTI_VIEW_GROUNDING_VERSION = "paper1-multi-view-structural-grounding-v1"


@dataclass(frozen=True)
class GroundingResult:
    proposal_id: str
    valid: bool
    violations: tuple[str, ...]
    grounded_spans: tuple[GroundedSourceSpan, ...]


def source_sha256(source: MultiViewSessionInput) -> str:
    current = source.model_dump(mode="json", exclude={"prior_current_profile"})
    return sha256_text(canonical_json(current))


def prior_profile_sha256(source: MultiViewSessionInput) -> str:
    table = [row.model_dump(mode="json") for row in source.prior_current_profile]
    return sha256_text(canonical_json(table))


def validate_output_binding(
    source: MultiViewSessionInput,
    output: ExtractorSessionOutput | VerifierSessionOutput,
) -> None:
    if output.owner_id != source.owner_id or output.session_id != source.session_id:
        raise ValueError("active compiler owner/session binding mismatch")


def validate_proposal_grounding(
    source: MultiViewSessionInput,
    proposal: ProposedAtomicMemoryUnit,
) -> GroundingResult:
    turns = {turn.turn_id: turn for turn in source.turns}
    violations: list[str] = []
    grounded: list[GroundedSourceSpan] = []
    span_ids = [span.span_id for span in proposal.supporting_spans]
    if len(span_ids) != len(set(span_ids)):
        violations.append("duplicate_span_id")
    for span in proposal.supporting_spans:
        turn = turns.get(span.turn_id)
        if turn is None:
            violations.append(f"unknown_turn:{span.span_id}")
            continue
        if turn.role != "seeker":
            violations.append(f"supporter_only_source:{span.span_id}")
        start = turn.content.find(span.exact_text)
        if start < 0:
            violations.append(f"span_text_absent:{span.span_id}")
            continue
        if turn.content.find(span.exact_text, start + 1) >= 0:
            violations.append(f"span_text_ambiguous:{span.span_id}")
            continue
        grounded.append(
            GroundedSourceSpan(
                span_id=span.span_id,
                turn_id=span.turn_id,
                turn_index=turn.turn_index,
                exact_text=span.exact_text,
                start_char=start,
                end_char=start + len(span.exact_text),
                exact_text_sha256=sha256_text(span.exact_text),
            )
        )
    return GroundingResult(
        proposal_id=proposal.proposal_id,
        valid=not violations,
        violations=tuple(sorted(set(violations))),
        grounded_spans=tuple(grounded),
    )


__all__ = [
    "GroundingResult",
    "MULTI_VIEW_GROUNDING_VERSION",
    "prior_profile_sha256",
    "source_sha256",
    "validate_output_binding",
    "validate_proposal_grounding",
]
