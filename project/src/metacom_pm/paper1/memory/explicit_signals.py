"""Deterministic, outcome-blind signals from the current target's own
visible query text -- ``ms_thread_entity_overlap``, ``ms_explicit_return_
marker``, and ``me_current_action_request`` (blueprint sections 5.3/5.4).

These are a different construct from RS's ``rs_explicit_request_flags``
(``rs/preoutcome_audit.py``): RS detects *permission/boundary* language the
seeker states about how the supporter should behave right now (listen-only,
no-advice, no-probing) -- a restriction on a real-time conversational
intervention. Memory has no such intervention-boundary concept; instead:

- ``ms_explicit_return_marker`` detects *continuity* language -- the current
  query referring back to something from before ("again", "last time",
  "before", "still", "like I said") -- a signal that a past MS document may
  be relevant, not a restriction on anything.
- ``me_current_action_request`` detects *forward-looking advice-seeking*
  language ("what should I do", "any advice", "how do I") -- a signal that a
  past ME action+outcome experience may be relevant precedent, not a
  boundary on the current turn.
- ``ms_thread_entity_overlap`` is not a single-text flag at all: it is a
  pairwise count between the target's query text and one MS candidate's
  content, structurally like the existing lexical-Jaccard proxy in
  ``features/zero_outcome_census.py``, not like anything in RS.

All three are only ever computed against ``Target.visible_query_text``
(QA/Summary's real officially-asked question); DG has no such text
pre-generation (B17.4) and reports ``None`` for all three, the same
convention ``zero_outcome_census.py`` already uses for lexical overlap.
"""

from __future__ import annotations

import re

_RETURN_MARKER_RE = re.compile(
    r"\b(?:again|before|still|previously|last time|"
    r"like i (?:said|mentioned|told you)|as i (?:said|mentioned)|"
    r"(?:i )?(?:mentioned|said) (?:this|that|earlier))\b",
    re.IGNORECASE,
)

_ACTION_REQUEST_RE = re.compile(
    r"\b(?:what should i do|what would you do|what do you think i should do|"
    r"any advice|how do i\b|what'?s the best way to|"
    r"how should i (?:handle|deal with|approach)|what are my options)\b",
    re.IGNORECASE,
)

# Entity-like proxy: a capitalized token not in sentence-initial position,
# the same deterministic heuristic RS's leak-proxy audit uses for the
# opposite purpose (flagging over-specific content to reject). Here it is a
# positive overlap feature, not a rejection check.
_CAPITALIZED_TOKEN_RE = re.compile(r"(?<!^)(?<![.!?]\s)\b[A-Z][a-z]{2,}\b")


def has_explicit_return_marker(text: str) -> bool:
    """True if ``text`` deterministically refers back to something earlier."""

    return bool(_RETURN_MARKER_RE.search(text))


def has_current_action_request(text: str) -> bool:
    """True if ``text`` deterministically asks what to do / for advice."""

    return bool(_ACTION_REQUEST_RE.search(text))


def entity_like_tokens(text: str) -> frozenset[str]:
    """Non-sentence-initial capitalized tokens, casefolded."""

    return frozenset(match.group(0).casefold() for match in _CAPITALIZED_TOKEN_RE.finditer(text))


def thread_entity_overlap_count(query_text: str, candidate_text: str) -> int | None:
    """Count of entity-like tokens shared between a query and one candidate.

    ``None`` when either side has no entity-like tokens at all (nothing to
    overlap), mirroring how the existing lexical-overlap proxy reports
    ``None`` rather than a spurious ``0`` for an empty comparison.
    """

    query_entities = entity_like_tokens(query_text)
    candidate_entities = entity_like_tokens(candidate_text)
    if not query_entities or not candidate_entities:
        return None
    return len(query_entities & candidate_entities)
