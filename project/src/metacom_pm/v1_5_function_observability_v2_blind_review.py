"""Blind Function Observability V2 reviewer contract: independent judge
version of the CLEAR/PLAUSIBLE/NONE/UNCERTAIN taxonomy defined in
paper1_rs_ms_r0_delta_measurement_and_panel_revision_v2.json
#function_observability_v2.layers.observable_contribution.

Unlike the RS/MS quality reviewer (v1_5_rs_ms_quality_risk_blind_review.py),
this reviewer is not blind to the resource: judging function requires
knowing what was authorized (the exact MS source text, or the RS card's
retrieval text) so the reviewer can decide whether the reply's content is
attributable to it. It is blind to which treatment arm/condition produced
the reply and to the generator's own self-citation (used_evidence_ids is
never shown), matching the established finding that self-citation is
uninformative on this generator.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .contracts import StrictModel


FunctionObservabilityLabel = Literal["CLEAR", "PLAUSIBLE", "NONE", "UNCERTAIN"]


class FunctionObservabilityV2BlindReview(StrictModel):
    blind_item_id: str = Field(min_length=1)
    label: FunctionObservabilityLabel
    response_evidence_quote: str = Field(
        description="Exact span from the reply the label rests on, or empty string if NONE."
    )
    rationale: str = Field(min_length=1, max_length=600)


def function_prompt_messages(
    *,
    blind_item_id: str,
    current_context: str,
    authorized_resource_label: str,
    authorized_resource_text: str,
    reply: str,
) -> list[dict[str, str]]:
    system = """You are an independent reviewer judging whether a candidate reply to a support \
conversation shows an observable, concrete contribution from one authorized piece of \
background information -- not whether the reply cites it, not how warm or long the reply is.

You will see the visible current conversation, the exact authorized background information \
(a stored fact or a strategy card), and one candidate reply. You do NOT know which treatment \
condition produced this reply or whether the generator itself claimed to use the background \
information -- judge only the reply text against the two other inputs.

Label CLEAR when a concrete, specific difference in the reply is directly supported by the \
authorized background information and is not merely generic warmth, length, advice, or a \
restatement of the current conversation. Label PLAUSIBLE when a source-consistent bounded \
difference is visible but unique attribution to the authorized information (rather than chance \
or generic support-language) is not strong enough for CLEAR. Label NONE when no observable \
contribution from the authorized information appears in the reply -- including when the reply \
is generic, or only reflects information already visible in the current conversation. Label \
UNCERTAIN when reasonable reviewers could genuinely disagree about attribution -- this is \
missing/ambiguous evidence, not an automatic NONE.

Do not penalize a reply for being risky, unsafe, or low quality -- a separate review covers \
that. Do not reward length or generic supportiveness alone.

Return blind_item_id (echo exactly), label, response_evidence_quote (the exact reply span the \
label rests on, or an empty string if NONE), and a rationale."""
    user = f"""blind_item_id: {blind_item_id}

VISIBLE CURRENT CONVERSATION:
{current_context}

AUTHORIZED BACKGROUND INFORMATION ({authorized_resource_label}):
{authorized_resource_text}

CANDIDATE REPLY:
{reply}"""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
