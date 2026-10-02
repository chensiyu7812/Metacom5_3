"""Outcome-blind RS renderer and explicit-boundary audit helpers.

Nothing in this module chooses the final M2 renderer or boundary horizon.  It
exposes two renderer candidates and three mechanically reproducible boundary
horizons so their zero-outcome consequences can be reviewed before freeze.
The exemplar diagnostics are raw text-shape proxies, never a utility/risk
score and never an eligibility gate.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from .strategy_bank import StrategySourceCard, _tokens


class RenderVariant(StrEnum):
    GUIDANCE_ONLY = "guidance_only"
    GUIDANCE_PLUS_EXEMPLAR = "guidance_plus_exemplar"


class ExplicitBoundary(StrEnum):
    LISTEN_ONLY = "listen_only"
    NO_ADVICE = "no_advice"
    NO_PROBING = "no_probing"


_LISTEN_ONLY_RE = re.compile(
    r"\bi\s+(?:(?:just|only)\s+)?(?:need|want)\s+(?:you|someone)\s+to\s+"
    r"(?:just\s+)?listen\b|"
    r"(?:^|[.!?]\s*)please\s+(?:just\s+)?listen\b",
    re.IGNORECASE,
)
_NO_ADVICE_RE = re.compile(
    r"\bi\s+(?:do not|don't)\s+want\s+(?:any\s+|more\s+|your\s+)?advice\b|"
    r"(?:^|[.!?]\s*)(?:please\s+)?(?:do not|don't)\s+give\s+me\s+"
    r"(?:any\s+|more\s+|your\s+)?advice\b|"
    r"(?:^|[.!?]\s*)no\s+(?:more\s+)?advice(?:,?\s+please)?(?:[.!?]|$)",
    re.IGNORECASE,
)
_NO_PROBING_RE = re.compile(
    r"(?:^|[.!?]\s*)"
    r"(?:please\s+)?(?:do not|don't)\s+ask(?:\s+me)?"
    r"(?:\s+(?:any|more))?\s+questions?\b|"
    r"\bi\s+(?:do not|don't)\s+want\s+you\s+to\s+ask(?:\s+me)?\b|"
    r"(?:^|[.!?]\s*)no\s+(?:more\s+)?questions(?:,?\s+please)?(?:[.!?]|$)",
    re.IGNORECASE,
)
_ADVICE_PERMISSION_RE = re.compile(
    r"(?:^|[.!?]\s*)(?:actually,?\s+)?any\s+advice(?:,?\s+please)?(?:[.!?]|$)|"
    r"\b(?:what should i do|what can i do|do you have any advice|"
    r"can you give me (?:any\s+)?advice|i(?:'d| would) like (?:some\s+)?advice|"
    r"you can give me advice|advice is (?:okay|ok)|could you suggest)\b",
    re.IGNORECASE,
)
_QUESTION_PERMISSION_RE = re.compile(
    r"\b(?:you can ask|feel free to ask|questions? (?:are|is) (?:okay|ok))\b",
    re.IGNORECASE,
)

_FIRST_PERSON_RE = re.compile(r"\b(?:i|i'm|i've|me|my|mine|we|we're|we've|us|our|ours)\b", re.IGNORECASE)
_KINSHIP_RE = re.compile(
    r"\b(?:mother|father|mom|dad|parent|parents|sister|brother|husband|wife|"
    r"partner|boyfriend|girlfriend|son|daughter|child|children|kid|kids)\b",
    re.IGNORECASE,
)
_TIME_OR_NUMBER_RE = re.compile(
    r"\b(?:\d+|monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
    r"january|february|march|april|may|june|july|august|september|october|"
    r"november|december|yesterday|tomorrow|last week|last month|last year)\b",
    re.IGNORECASE,
)
_CAPITALIZED_TOKEN_RE = re.compile(r"\b(?!I\b)[A-Z][a-z]{2,}\b")
_CAPITALIZED_COMMON = frozenset(
    {"The", "This", "That", "It", "You", "Your", "We", "Our", "They", "There"}
)


@dataclass(frozen=True)
class ExemplarContentProxies:
    first_person_reference: bool
    kinship_reference: bool
    time_or_number_reference: bool
    capitalized_token_reference: bool
    source_context_lexical_overlap: float | None


def render_strategy_card(card: StrategySourceCard, variant: RenderVariant) -> str:
    """Render a review candidate; this is not the frozen production renderer."""

    prefix = (
        "[Strategy-RAG resource]\n"
        f"Strategy move: {card.strategy_label}\n"
        f"Guidance: {card.guidance_text}\n"
    )
    grounding = (
        "Ground the response only in the current visible dialogue. Do not infer "
        "facts about the current user from this resource.\n"
    )
    if variant is RenderVariant.GUIDANCE_ONLY:
        return prefix + grounding + "[/Strategy-RAG resource]"
    if variant is RenderVariant.GUIDANCE_PLUS_EXEMPLAR:
        return (
            prefix
            + "Source example from another dialogue (style only; not evidence):\n"
            + card.example_response
            + "\nDo not copy or carry over any person, relationship, place, event, "
            "or fact from the source example.\n"
            + grounding
            + "[/Strategy-RAG resource]"
        )
    raise ValueError(f"unsupported render variant: {variant!r}")


def exemplar_content_proxies(card: StrategySourceCard) -> ExemplarContentProxies:
    response = card.example_response
    response_tokens = _tokens(response)
    context_tokens = _tokens(card.retrieval_text)
    overlap = None
    if response_tokens and context_tokens:
        overlap = len(response_tokens & context_tokens) / len(response_tokens | context_tokens)
    capitalized_reference = False
    for match in _CAPITALIZED_TOKEN_RE.finditer(response):
        prefix = response[: match.start()].rstrip()
        if not prefix or prefix.endswith((".", "!", "?")):
            continue
        if match.group(0) in _CAPITALIZED_COMMON:
            continue
        capitalized_reference = True
        break
    return ExemplarContentProxies(
        first_person_reference=bool(_FIRST_PERSON_RE.search(response)),
        kinship_reference=bool(_KINSHIP_RE.search(response)),
        time_or_number_reference=bool(_TIME_OR_NUMBER_RE.search(response)),
        capitalized_token_reference=capitalized_reference,
        source_context_lexical_overlap=overlap,
    )


def explicit_boundaries(text: str) -> frozenset[ExplicitBoundary]:
    result: set[ExplicitBoundary] = set()
    if _LISTEN_ONLY_RE.search(text):
        result.add(ExplicitBoundary.LISTEN_ONLY)
    if _NO_ADVICE_RE.search(text):
        result.add(ExplicitBoundary.NO_ADVICE)
    if _NO_PROBING_RE.search(text):
        result.add(ExplicitBoundary.NO_PROBING)
    return frozenset(result)


def _seeker_texts(visible_dialogue_text: str) -> tuple[str, ...]:
    return tuple(
        line.partition(": ")[2]
        for line in visible_dialogue_text.splitlines()
        if line.casefold().startswith("seeker: ")
    )


def prefix_any_boundaries(visible_dialogue_text: str) -> frozenset[ExplicitBoundary]:
    result: set[ExplicitBoundary] = set()
    for text in _seeker_texts(visible_dialogue_text):
        result.update(explicit_boundaries(text))
    return frozenset(result)


def narrow_stateful_boundaries(visible_dialogue_text: str) -> frozenset[ExplicitBoundary]:
    """Persist explicit boundaries until an equally explicit narrow permission.

    This is an audit alternative, not the selected runtime rule. Advice
    requests revoke LISTEN_ONLY/NO_ADVICE; explicit question permission revokes
    LISTEN_ONLY/NO_PROBING. No semantic inference is made.
    """

    active: set[ExplicitBoundary] = set()
    for text in _seeker_texts(visible_dialogue_text):
        if _ADVICE_PERMISSION_RE.search(text):
            active.discard(ExplicitBoundary.LISTEN_ONLY)
            active.discard(ExplicitBoundary.NO_ADVICE)
        if _QUESTION_PERMISSION_RE.search(text):
            active.discard(ExplicitBoundary.LISTEN_ONLY)
            active.discard(ExplicitBoundary.NO_PROBING)
        active.update(explicit_boundaries(text))
    return frozenset(active)


def strategy_is_boundary_compatible(
    strategy_label: str, boundaries: frozenset[ExplicitBoundary]
) -> bool:
    """Candidate-level compatibility; never converts a boundary to whole-head OFF."""

    label = " ".join(strategy_label.casefold().split())
    if label == "providing suggestions" and boundaries & {
        ExplicitBoundary.LISTEN_ONLY,
        ExplicitBoundary.NO_ADVICE,
    }:
        return False
    if label == "question" and boundaries & {
        ExplicitBoundary.LISTEN_ONLY,
        ExplicitBoundary.NO_PROBING,
    }:
        return False
    return True
