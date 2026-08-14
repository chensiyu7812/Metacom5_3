"""Blind pairwise observable-constraint reviewer for MP.

MP is forbidden to recite its profile source, so pointwise source matching is
not a valid Function test.  This reviewer sees a randomized same-state reply
pair and asks whether one reply makes a concrete source-consistent change to
wording, burden, timing, format, or logistics relative to the other.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .contracts import StrictModel


MPFunctionPairVerdict = Literal[
    "A_CLEAR", "A_PLAUSIBLE", "B_CLEAR", "B_PLAUSIBLE",
    "NO_INCREMENTAL_CONSTRAINT", "UNCERTAIN",
]


class MPFunctionPairBlindReview(StrictModel):
    pair_id: str = Field(min_length=1)
    verdict: MPFunctionPairVerdict
    a_evidence_quote: str
    b_evidence_quote: str
    rationale: str = Field(min_length=1, max_length=700)


def mp_function_pair_prompt_messages(
    *, pair_id: str, full_dialogue: str, profile_field: str,
    authorized_profile_source: str, reply_a: str, reply_b: str,
) -> list[dict[str, str]]:
    system = """You are an independent reviewer testing whether one of two replies shows an
observable, concrete constraint from an authorized user profile fact. You do not know which
condition produced A or B. Overall quality, warmth, and length are assessed elsewhere.

The profile fact must NOT be repeated, exposed, or explicitly mentioned. Its permitted function
is only to change a concrete response choice: wording, burden, timing, format, logistics, or the
specific practical option offered. Generic paraphrase, warmth, or a suggestion that is equally
recoverable from the visible conversation is not Function.

Return A_CLEAR or B_CLEAR only when that side shows a concrete source-consistent constraint that
the other side does not and attribution is strong. Return A_PLAUSIBLE or B_PLAUSIBLE for a bounded
but not uniquely attributable difference. Return NO_INCREMENTAL_CONSTRAINT when neither side, or
both sides equally, show the constraint. Return UNCERTAIN only for genuine ambiguity. Quote exact
evidence from both replies (empty string when absent)."""
    user = f"""pair_id: {pair_id}

FULL VISIBLE CURRENT-SESSION CONVERSATION:
{full_dialogue}

AUTHORIZED PROFILE SOURCE (field={profile_field}; do not reward literal exposure):
{authorized_profile_source}

REPLY A:
{reply_a}

REPLY B:
{reply_b}"""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def decode_mp_function_verdict(verdict: str, *, mp_position: Literal["A", "B"]) -> str:
    if verdict == f"{mp_position}_CLEAR":
        return "CLEAR"
    if verdict == f"{mp_position}_PLAUSIBLE":
        return "PLAUSIBLE"
    if verdict == "UNCERTAIN":
        return "UNCERTAIN"
    return "NONE"
