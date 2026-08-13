"""Blind pairwise MS+R0-vs-MS+RS interaction reviewer contract.

Replaces the single-point "judge MS+RS alone, then diff two independent
Function labels after the fact" approach with a direct blind pairwise
comparison, position-randomized A/B like RSMSQualityBlindReview -- this
lets one reviewer directly compare the two replies' observable use of the
same authorized MS source in one call, instead of inferring a change from
two separately-judged single-point labels.

The verdict describes how reply B's observable contribution from the
authorized source compares to reply A's. The caller must decode the verdict
against which physical arm (MS+R0 or MS+RS) was placed at A vs B: when
MS+RS is at position B, the verdict describes RS's effect on MS directly
(STRENGTHENED/WEAKENED/PRESERVED as stated); when MS+RS is at position A,
STRENGTHENED and WEAKENED must be swapped to get RS's effect on MS, because
the verdict is stated as "B relative to A," not "MS+RS relative to MS+R0."
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .contracts import StrictModel


InteractionVerdict = Literal[
    "PRESERVED", "STRENGTHENED", "WEAKENED", "NONE_IN_EITHER", "UNCERTAIN"
]


class MSRSInteractionBlindReview(StrictModel):
    pair_id: str = Field(min_length=1)
    verdict: InteractionVerdict
    a_evidence_quote: str = Field(description="Exact span from reply A, or empty string if none.")
    b_evidence_quote: str = Field(description="Exact span from reply B, or empty string if none.")
    rationale: str = Field(min_length=1, max_length=600)


def interaction_prompt_messages(
    *,
    pair_id: str,
    current_context: str,
    authorized_resource_text: str,
    reply_a: str,
    reply_b: str,
) -> list[dict[str, str]]:
    system = """You are an independent reviewer comparing two candidate replies to a support \
conversation for how each uses ONE piece of authorized background information -- not which \
reply is better overall, longer, or warmer (a separate review covers that).

You will see the visible current conversation, the exact authorized background information \
(a strictly past, user-owned fact), and two candidate replies, A and B, generated independently \
for the same conversation state. You do NOT know which treatment condition produced either \
reply -- judge only what each reply's text shows.

First decide, for EACH reply independently, whether it shows an observable, concrete \
contribution from the authorized background information (a specific detail the reply could not \
have produced from the visible conversation alone) -- ignore generic warmth, length, or advice \
that is not attributable to that specific background information.

Then return exactly one verdict describing how B compares to A:
- STRENGTHENED: B shows a clearer or more concrete use of the background information than A.
- WEAKENED: B shows a less clear or weaker use of the background information than A.
- PRESERVED: both A and B show an observable use of the background information, at roughly the \
same strength.
- NONE_IN_EITHER: neither A nor B shows any observable use of the background information.
- UNCERTAIN: reasonable reviewers could genuinely disagree about the comparison.

Return pair_id (echo exactly), verdict, a_evidence_quote (exact span from A, or empty string), \
b_evidence_quote (exact span from B, or empty string), and a rationale."""
    user = f"""pair_id: {pair_id}

VISIBLE CURRENT CONVERSATION:
{current_context}

AUTHORIZED BACKGROUND INFORMATION (strictly past, user-owned):
{authorized_resource_text}

REPLY A:
{reply_a}

REPLY B:
{reply_b}"""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def decode_interaction_verdict(verdict: str, *, ms_rs_position: Literal["A", "B"]) -> str:
    """Return the verdict in terms of RS's effect on MS (STRENGTHENED means RS
    strengthened MS's observable contribution), regardless of which physical
    position MS+RS was randomized into.
    """

    if verdict not in ("PRESERVED", "STRENGTHENED", "WEAKENED", "NONE_IN_EITHER", "UNCERTAIN"):
        raise ValueError(f"unknown verdict: {verdict!r}")
    if ms_rs_position == "B":
        return verdict
    if ms_rs_position == "A":
        swap = {"STRENGTHENED": "WEAKENED", "WEAKENED": "STRENGTHENED"}
        return swap.get(verdict, verdict)
    raise ValueError(f"ms_rs_position must be 'A' or 'B', got {ms_rs_position!r}")
