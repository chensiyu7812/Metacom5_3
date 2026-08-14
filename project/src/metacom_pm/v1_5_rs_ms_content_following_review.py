"""Independent reviewer contract for whether a routed reply's CONTENT actually
follows the MS/RS guidance it was offered -- as a correction for the
self-citation proxy (`used_evidence_ids` -> `generator_claimed`), which
requires the generator to echo an opaque internal evidence_id string
verbatim in structured output and is a much more brittle mechanic than
actually writing a guidance-consistent reply.

The reviewer sees the baseline reply (same state, same seed, no MS/RS
candidates offered) and the routed reply side by side, plus the guidance
text itself, and judges content-following directly -- blind to whatever the
generator's own used_evidence_ids field reported.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from .contracts import StrictModel


ContentJudgment = Literal[
    "NOT_OFFERED",
    "FOLLOWED",
    "NOT_FOLLOWED_OR_IGNORED",
    "SAFELY_DECLINED",
]


class RSMSContentFollowingReview(StrictModel):
    case_id: str = Field(min_length=1)
    ms_judgment: ContentJudgment
    rs_judgment: ContentJudgment
    rationale: str = Field(min_length=1, max_length=600)


def prompt_messages(
    *,
    case_id: str,
    baseline_reply: str,
    routed_reply: str,
    ms_offered: bool,
    ms_guidance: Optional[dict[str, str]],
    rs_offered: bool,
    rs_guidance: Optional[dict[str, str]],
) -> list[dict[str, str]]:
    system = """You are an independent reviewer judging whether a support-response's \
CONTENT actually follows specific writing guidance it was given -- not whether an \
internal bookkeeping field claims it did.

You will see:
- BASELINE REPLY: generated for the identical conversation state and random seed, \
WITHOUT any of the guidance below.
- ROUTED REPLY: generated for the same state and seed, WITH the guidance below \
available to use if it materially helps.
- Zero or more pieces of GUIDANCE (an "MS" continuity cue and/or an "RS" strategy \
card instruction) that were made available to the generator of the routed reply.

For each piece of guidance that was offered, judge independently from the routed \
reply's actual wording (ignore any internal claim of "used" or "not used" -- you are \
the check on that claim, not a rubber stamp for it):
- FOLLOWED: the routed reply's content meaningfully reflects this specific guidance \
(e.g. an MS cue: the reply references the described past fact/change in an allowed, \
non-literal way; an RS card: the reply's primary act matches the card's named support \
move), and the routed reply is clearly different from the baseline reply in a way \
attributable to this guidance.
- NOT_FOLLOWED_OR_IGNORED: the guidance was offered but the routed reply does not \
reflect it -- it reads generically, like the baseline, or addresses something else.
- SAFELY_DECLINED: the routed reply is clearly, deliberately avoiding the guidance for \
a good reason visible in the text (e.g. the guidance would be intrusive, redundant, or \
does not genuinely fit this turn) -- a legitimate non-use, not a failure to engage.
- NOT_OFFERED: this piece of guidance was not offered for this case (ms_offered or \
rs_offered is false) -- you MUST use this value in that case, do not guess.

Judge ms_judgment and rs_judgment independently of each other. A reply can follow one \
and not the other, or follow both by weaving them into one coherent reply."""

    def _guidance_block(label: str, guidance: Optional[dict[str, str]]) -> str:
        if guidance is None:
            return f"{label} GUIDANCE: not offered for this case."
        lines = "\n".join(f"  {key}: {value}" for key, value in guidance.items())
        return f"{label} GUIDANCE (offered):\n{lines}"

    user = f"""case_id: {case_id}

{_guidance_block("MS", ms_guidance)}

{_guidance_block("RS", rs_guidance)}

BASELINE REPLY:
{baseline_reply}

ROUTED REPLY:
{routed_reply}

ms_offered: {ms_offered}
rs_offered: {rs_offered}

Return case_id (echo exactly), ms_judgment, rs_judgment, and a brief rationale citing \
specific wording from the routed reply."""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
