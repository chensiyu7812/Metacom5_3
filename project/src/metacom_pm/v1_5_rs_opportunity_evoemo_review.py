"""Independent reviewer contract for RS opportunity on real EvoEmo turns.

The RS opportunity router's own construct (see v1_5_strategy_rag_v4.eligible_families)
already defines the gate precisely: an opportunity exists unless the turn is
pure phatic, an explicit stop/boundary, an active high-stakes crisis, or not
substantive. This reviewer applies that same gate to real EvoEmo text so an
independent judgment (not the reviewer's own regex features) can check
whether the router's near-universal ON rate on EvoEmo reflects a genuine
construct property of the domain or under-firing exclusion features.
"""

from __future__ import annotations

from typing import Literal, Mapping

from pydantic import Field

from .contracts import StrictModel


ExclusionReason = Literal[
    "NONE",
    "PURE_PHATIC_OR_GRATITUDE_ONLY",
    "ROUTINE_CLOSING_OR_FAREWELL",
    "EXPLICIT_STOP_OR_BOUNDARY",
    "ACTIVE_HIGH_STAKES_CRISIS",
    "NOT_SUBSTANTIVE",
]


class RSOpportunityEvoEmoReview(StrictModel):
    state_id: str = Field(min_length=1)
    opportunity_present: bool
    exclusion_reason: ExclusionReason
    applicable_family: Literal[
        "Question",
        "Restatement or Paraphrasing",
        "Reflection of feelings",
        "Affirmation and Reassurance",
        "Providing Suggestions",
        "NONE",
    ]
    rationale: str = Field(min_length=1, max_length=500)


def prompt_messages(state_id: str, visible_dialogue: list[dict[str, str]]) -> list[dict[str, str]]:
    dialogue_text = "\n".join(
        f"{str(turn['speaker']).upper()}: {str(turn['content']).strip()}"
        for turn in visible_dialogue
        if str(turn.get("content", "")).strip()
    )
    system = """You are an independent reviewer judging whether a support-strategy \
opportunity exists at the end of a visible dialogue.

An opportunity is PRESENT unless the latest seeker turn falls into one of these \
exclusions:
- PURE_PHATIC_OR_GRATITUDE_ONLY: the turn is only a greeting, thanks, or closing \
pleasantry with no other content (e.g. "thanks", "okay thank you so much.") -- \
but a turn that pairs gratitude with a genuine plan, feeling, or new detail is \
NOT pure phatic.
- ROUTINE_CLOSING_OR_FAREWELL: the turn is a generic well-wish or sign-off \
("take care", "have a good night") with nothing else to respond to.
- EXPLICIT_STOP_OR_BOUNDARY: the seeker has explicitly asked to stop, pause, or \
not receive suggestions/advice.
- ACTIVE_HIGH_STAKES_CRISIS: the turn signals an active safety crisis that needs \
an immediate, narrowly-scoped safety response, not a general strategic move.
- NOT_SUBSTANTIVE: the turn is too short/empty to respond to meaningfully (fewer \
than about 4 real words, or just filler).

If none of these apply, opportunity_present is true, and you must name which ONE \
of the five strategy families would genuinely fit: Question (a clarifying or \
open question), Restatement or Paraphrasing (reflecting back the content), \
Reflection of feelings (naming the emotion), Affirmation and Reassurance \
(validating effort or feeling), or Providing Suggestions (only if the seeker is \
explicitly asking what to do). If opportunity_present is false, applicable_family \
must be NONE and exclusion_reason must name the specific exclusion.

Judge only whether a strategic move would be a genuine, non-redundant opportunity \
here -- not whether the dialogue is emotionally rich in general, and not whether \
you personally would enjoy responding."""
    user = f"Visible dialogue (state_id={state_id}):\n{dialogue_text}\n\nJudge the latest turn."
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
