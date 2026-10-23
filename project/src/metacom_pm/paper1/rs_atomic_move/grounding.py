"""Deterministic, fail-closed grounding for RS atomic-move proposals.

Mirrors ``semantic_memory/grounding.py``'s role: a hard, mechanical gate that
runs before (and independent of) the Qwen verifier. The verifier's semantic
judgment is not a substitute for this -- these checks must pass regardless of
what the same model says about itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import ProposedAtomicMoveUnit, SupportingSpan, VerifierRejectionReason
from .renderer import leaked_source_specific_terms

GROUNDING_VERSION = "paper1-rs-atomic-move-grounding-v3"


@dataclass(frozen=True)
class GroundingResult:
    passed: bool
    reasons: tuple[VerifierRejectionReason, ...]
    detail: tuple[str, ...] = ()
    # Populated only when passed=True: the locally-assembled, offset-bearing
    # spans, in the same order as proposal.supporting_spans. Never
    # constructed from anything Qwen claimed about location, because Qwen's
    # ProposedSpanQuote carries no location -- see locate_spans below.
    located_spans: tuple[SupportingSpan, ...] = field(default_factory=tuple)


def locate_spans(
    proposal: ProposedAtomicMoveUnit,
    *,
    target_dialogue_id: str,
    target_turn_index: int,
    target_turn_text: str,
) -> GroundingResult:
    """Locate every ``ProposedSpanQuote`` exclusively inside
    ``target_turn_text`` -- never inside a preceding turn, because no other
    text is ever searched. A quote that does not appear verbatim, or that
    appears more than once (ambiguous -- which occurrence would even be
    meant?), fails closed rather than guessing. This single mechanism is
    what makes a seeker-grounded proposal structurally impossible to pass:
    there is no seeker text in ``target_turn_text`` to find a match in."""

    problems: list[str] = []
    located: list[SupportingSpan] = []
    for quote in proposal.supporting_spans:
        occurrences = target_turn_text.count(quote.exact_text)
        if occurrences == 0:
            problems.append(f"span {quote.span_id}: {quote.exact_text!r} not found in target turn")
            continue
        if occurrences > 1:
            problems.append(
                f"span {quote.span_id}: {quote.exact_text!r} is ambiguous "
                f"({occurrences} occurrences in target turn); use a longer, unique quote"
            )
            continue
        start = target_turn_text.index(quote.exact_text)
        located.append(
            SupportingSpan(
                span_id=quote.span_id,
                source_dialogue_id=target_dialogue_id,
                source_turn_index=target_turn_index,
                exact_text=quote.exact_text,
                start_char=start,
                end_char=start + len(quote.exact_text),
            )
        )
    if problems:
        return GroundingResult(
            passed=False,
            reasons=(VerifierRejectionReason.AMBIGUOUS_SPAN,),
            detail=tuple(problems),
        )
    return GroundingResult(passed=True, reasons=(), located_spans=tuple(located))


def check_action_description_not_leaking(proposal: ProposedAtomicMoveUnit) -> GroundingResult:
    """Fail-closed pre-check reusing the exact same detector
    ``renderer.leaked_source_specific_terms`` uses immediately before
    rendering, so a leaking proposal is rejected here -- before spending a
    verifier call on it -- rather than only being caught at render time.
    ``renderer.py`` re-runs the identical check right before rendering
    regardless, since a renderer must never trust that an earlier gate ran.

    This mechanical scan is a conservative proxy, not complete detection
    (see ``renderer.py``'s docstring for known gaps: spelled-out numbers,
    all-caps short acronyms, and a name that happens to be the very first
    word). The verifier is separately asked (prompts.py, criterion 5) to
    judge the same question semantically; that is a real second layer, not
    a redundant one, precisely because this mechanical layer is known-
    incomplete and the verifier is not an independent model check either
    (see runtime.VERIFIER_METHOD) -- neither layer alone is sufficient."""

    leaked = leaked_source_specific_terms(proposal.action_description)
    if leaked:
        return GroundingResult(
            passed=False,
            reasons=(VerifierRejectionReason.LEAKED_SOURCE_SPECIFIC_CONTENT,),
            detail=(f"action_description contains {leaked!r}",),
        )
    return GroundingResult(passed=True, reasons=())


def run_deterministic_grounding(
    proposal: ProposedAtomicMoveUnit,
    *,
    target_dialogue_id: str,
    target_turn_index: int,
    target_turn_text: str,
) -> GroundingResult:
    """Combined fail-closed gate. Both checks must pass; failures accumulate
    reasons/detail rather than short-circuiting, so a single rejected
    proposal's report is fully diagnosable without a second pass.
    ``located_spans`` is populated only when both checks pass."""

    location_result = locate_spans(
        proposal,
        target_dialogue_id=target_dialogue_id,
        target_turn_index=target_turn_index,
        target_turn_text=target_turn_text,
    )
    leak_result = check_action_description_not_leaking(proposal)
    passed = location_result.passed and leak_result.passed
    reasons = location_result.reasons + leak_result.reasons
    detail = location_result.detail + leak_result.detail
    located_spans = location_result.located_spans if passed else ()
    return GroundingResult(passed=passed, reasons=reasons, detail=detail, located_spans=located_spans)
