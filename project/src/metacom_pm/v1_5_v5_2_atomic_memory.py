"""Outcome-blind atomic memory compiler for the V5.2 executor.

V5.1 treated an entire seeker episode as a reusable event whenever broad
keywords appeared anywhere in the chunk.  This module deliberately accepts a
smaller surface: one local first-person action/choice and an observed result
in the same sentence or its immediately following anaphoric sentence.  The
literal source span is retained and rendered by the backend; an LLM never
paraphrases it into a different past event.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal


OutcomePolarity = Literal["positive", "negative"]


def _clean(value: str) -> str:
    return " ".join(str(value or "").split())


_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'])")
_FIRST_PERSON_ACTION_RE = re.compile(
    r"\b(?:I|we)(?:'ve|'d|\s+have|\s+had)?\s+"
    r"(?:tried|used|chose|decided\s+to|asked|called|wrote|walked|went|"
    r"practiced|paused|breathed|talked|scheduled|limited|stopped|started)\b",
    re.IGNORECASE,
)
_RESULT_CLAUSE_RE = re.compile(
    r"\b(?:(?:and|which)\s+)?(?:(?:it|that|this|doing\s+so)\s+)?"
    r"(?:really\s+|actually\s+)?(?:helped(?:\s+me|\s+us)?|worked|eased|"
    r"reduced|improved|made\s+.{0,45}?\s+easier|felt\s+(?:better|calmer|safer)|"
    r"did\s+not\s+help|didn't\s+help|made\s+.{0,45}?\s+worse|backfired)\b",
    re.IGNORECASE,
)
_ANAPHORIC_RESULT_RE = re.compile(
    r"^(?:It|That|This|Doing\s+so)\s+(?:really\s+|actually\s+)?"
    r"(?:helped(?:\s+me|\s+us)?|worked|eased|reduced|improved|"
    r"made\s+.{0,45}?\s+easier|felt\s+(?:better|calmer|safer)|"
    r"did\s+not\s+help|didn't\s+help|made\s+.{0,45}?\s+worse|backfired)\b",
    re.IGNORECASE,
)
_NEGATIVE_RESULT_RE = re.compile(
    r"\b(?:did\s+not\s+help|didn't\s+help|made\s+.{0,45}?\s+worse|backfired)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class AtomicReusableOutcome:
    literal_evidence_span: str
    past_action_span: str
    observed_outcome_span: str
    polarity: OutcomePolarity
    sentence_count: int


@dataclass(frozen=True)
class AtomicSessionObservation:
    literal_past_note: str


def _sentences(text: str) -> list[str]:
    value = _clean(text)
    if not value:
        return []
    return [part.strip() for part in _SENTENCE_BOUNDARY_RE.split(value) if part.strip()]


def _bounded_local_span(value: str) -> bool:
    words = value.split()
    return 5 <= len(words) <= 70 and len(value) <= 360


def compile_atomic_reusable_outcome(text: str) -> AtomicReusableOutcome | None:
    """Return a literal local action-result span or ``None``.

    Broad mechanism-only markers such as ``because`` are intentionally not
    sufficient.  They caused ordinary autobiographical explanations and grief
    narratives to be mislabeled as successful reusable actions in V5.1.
    """

    sentences = _sentences(text)
    for index, sentence in enumerate(sentences):
        action = _FIRST_PERSON_ACTION_RE.search(sentence)
        if action is None:
            continue
        result = _RESULT_CLAUSE_RE.search(sentence, action.end())
        if result is not None:
            literal = sentence
            if not _bounded_local_span(literal):
                continue
            action_span = sentence[action.start() : result.start()].strip(" ,;:-")
            outcome_span = sentence[result.start() :].strip(" ,;:-")
            if not action_span or not outcome_span:
                continue
            return AtomicReusableOutcome(
                literal_evidence_span=literal,
                past_action_span=action_span,
                observed_outcome_span=outcome_span,
                polarity=(
                    "negative" if _NEGATIVE_RESULT_RE.search(outcome_span) else "positive"
                ),
                sentence_count=1,
            )
        if index + 1 >= len(sentences):
            continue
        next_sentence = sentences[index + 1]
        next_result = _ANAPHORIC_RESULT_RE.search(next_sentence)
        if next_result is None:
            continue
        literal = f"{sentence} {next_sentence}"
        if not _bounded_local_span(literal):
            continue
        action_span = sentence[action.start() :].strip(" ,;:-")
        outcome_span = next_sentence.strip(" ,;:-")
        return AtomicReusableOutcome(
            literal_evidence_span=literal,
            past_action_span=action_span,
            observed_outcome_span=outcome_span,
            polarity=(
                "negative" if _NEGATIVE_RESULT_RE.search(outcome_span) else "positive"
            ),
            sentence_count=2,
        )
    return None


_GENERIC_SESSION_NOTE_RE = re.compile(
    r"^(?:the\s+)?seeker\s+(?:(?:talked|spoke)\s+about|discussed)\s+"
    r"(?:the\s+)?(?:topic|situation|issue|things|feelings?)\.?$",
    re.IGNORECASE,
)


def compile_atomic_session_observation(text: str) -> AtomicSessionObservation | None:
    """Accept one bounded, specific past-session note without paraphrasing it."""

    value = _clean(text)
    words = value.split()
    if not (4 <= len(words) <= 80) or len(value) > 420:
        return None
    if _GENERIC_SESSION_NOTE_RE.match(value):
        return None
    return AtomicSessionObservation(literal_past_note=value)
