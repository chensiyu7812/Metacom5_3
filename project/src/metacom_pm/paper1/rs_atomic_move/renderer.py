"""Deterministic RS atomic-move card rendering.

Mirrors ``semantic_memory/renderer.py``: the final card text is a fixed
template applied to already-verified, already-grounded structured fields --
never Qwen's raw prose inserted directly.

This renderer is also the final safety gate, not just a formatter.
``action_description`` is the only Qwen-written text that is ever rendered
into the card the Generator sees (``supporting_spans`` are grounding
evidence only and are never rendered), so this is the one place a
person/kinship/number/date leak from the source dialogue can actually reach
a downstream user. ``grounding.py`` runs this same scan earlier, before the
verifier call, as a fail-closed pre-check (see
``grounding.check_action_description_not_leaking``) so a leaking proposal is
rejected before spending a verifier call on it; this module re-runs it
immediately before rendering and refuses to render (raises) on any leak
regardless, since a renderer must never trust that an earlier gate ran.

The reused detectors are conservative proxies, not a claim of complete
detection -- notably ``_TIME_OR_NUMBER_RE`` matches digit sequences and named
weekdays/months but not spelled-out number words (e.g. "six months" is not
caught, "6 months" is). This gap is inherited from the existing diagnostic
regex and is a known limitation, not a silent assumption.
"""

from __future__ import annotations

import re
from pathlib import Path

from metacom_pm.io import sha256_file, sha256_text

from ..rs.preoutcome_audit import _CAPITALIZED_COMMON, _CAPITALIZED_TOKEN_RE, _KINSHIP_RE, _TIME_OR_NUMBER_RE
from .contracts import ProposedAtomicMoveUnit

RENDERER_VERSION = "paper1-rs-atomic-move-renderer-v1"
RENDERER_SPEC = """paper1 RS atomic-move renderer v1
=> Strategy family [atomic_move_family]: action_description
No model-generated fit/burden/helpfulness/confidence/treatment language is
added. action_description is re-scanned for leaked source-specific content
(capitalized-token/all-caps-acronym/kinship/number-or-date proxies) before
rendering; a hit raises rather than rendering, since it means the extractor
embedded source-specific content outside the checked supporting spans.
"""
RENDERER_SHA256 = sha256_text(RENDERER_SPEC)
RENDERER_CODE_SHA256 = sha256_file(Path(__file__))

# _CAPITALIZED_TOKEN_RE (from rs/preoutcome_audit.py) requires a capital
# followed by lowercase letters, so it never matches an all-caps acronym
# like "HR" or "CEO" -- a real, confirmed gap found in review. This is a
# second, narrow detector for exactly that case; "OK" is excluded as
# ordinary conversational filler, not an organization/entity reference.
_ALL_CAPS_ACRONYM_RE = re.compile(r"\b[A-Z]{2,}\b")
_ALL_CAPS_COMMON = frozenset({"OK"})


class UnscrubbedActionDescriptionError(ValueError):
    """action_description contains a likely-leaked source-specific detail."""


def leaked_source_specific_terms(text: str) -> list[str]:
    hits: list[str] = []
    for match in _CAPITALIZED_TOKEN_RE.finditer(text):
        if match.start() == 0:
            # action_description is written as an ordinary English clause and
            # is expected to start with a capitalized word; only a
            # capitalized token *inside* the text is a plausible proper-noun
            # leak, mirroring how a human reader would notice a name. This is
            # a known, documented gap: a name that happens to be the very
            # first word is not caught by this detector.
            continue
        if match.group(0) not in _CAPITALIZED_COMMON:
            hits.append(match.group(0))
    for match in _ALL_CAPS_ACRONYM_RE.finditer(text):
        if match.group(0) not in _ALL_CAPS_COMMON:
            hits.append(match.group(0))
    hits.extend(match.group(0) for match in _KINSHIP_RE.finditer(text))
    hits.extend(match.group(0) for match in _TIME_OR_NUMBER_RE.finditer(text))
    return hits


def render_atomic_move(proposal: ProposedAtomicMoveUnit) -> str:
    leaked = leaked_source_specific_terms(proposal.action_description)
    if leaked:
        raise UnscrubbedActionDescriptionError(
            f"action_description contains likely-unscrubbed source-specific "
            f"content: {leaked!r}. Reject or re-delexicalize; do not render."
        )
    family_label = proposal.atomic_move_family.value.replace("_", " ").title()
    return f"Strategy family [{family_label}]: {proposal.action_description}"
