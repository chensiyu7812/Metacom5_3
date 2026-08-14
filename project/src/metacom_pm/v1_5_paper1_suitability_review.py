"""Frozen P2B reviewer schema, prompt, and clear-anchor controls."""

from __future__ import annotations

import hashlib
from typing import Any, Literal, Mapping

from pydantic import Field

from .contracts import StrictModel
from .io import canonical_json
from .v1_5_paper1_suitability import SUITABILITY_AXES, derive_suitability


Decision = Literal["YES", "NO", "UNKNOWN"]
AbsenceCode = Literal[
    "NONE",
    "NO_TARGET_MATCH",
    "INCREMENT_ALREADY_VISIBLE",
    "ONLY_GENERIC_OR_DECORATIVE",
    "BOUNDARY_CONFLICT",
    "NO_POSITIVE_SPAN_REQUIRED",
]
UnknownCode = Literal[
    "NONE",
    "TARGET_AMBIGUOUS",
    "REDUNDANCY_AMBIGUOUS",
    "MINIMUM_AMBIGUOUS",
    "BOUNDARY_AMBIGUOUS",
]


class ReviewAxis(StrictModel):
    decision: Decision
    visible_span_ids: list[str]
    candidate_span_ids: list[str]
    absence_reason_code: AbsenceCode
    unknown_reason_code: UnknownCode


class SuitabilityReview(StrictModel):
    review_item_id: str = Field(min_length=1)
    current_target_fit: ReviewAxis
    specific_increment_available: ReviewAxis
    component_minimum_possible_now: ReviewAxis
    current_boundary_permits: ReviewAxis


def prompt_messages(item: Mapping[str, Any], reviewer_id: str) -> list[dict[str, str]]:
    system = f"""You are {reviewer_id}, one of two independent bounded-resource reviewers.

Judge exactly four atoms for the NEXT supporter reply. Do not judge overall helpfulness, response quality, risk, cost, retrieval validity, or whether a future generator will obey. Candidate identity, owner, time, source lineage, compiler validity, and actual Rank-1 selection are already machine-verified.

Apply the supplied component minimum literally. A topic overlap, name, job title, generic 'you mentioned', old event recap, or broadly supportive language is not enough. For RS, only the selected card's exact atomic move counts. A visible stop, refusal, listen-only request, no-history request, or advice boundary overrides apparent usefulness.

For every axis return YES, NO, or UNKNOWN. Select only supplied V... and C... span IDs; never copy prose. Use UNKNOWN only when the frozen surfaces truly cannot decide, and select its matching unknown_reason_code. For a resolved axis use unknown_reason_code=NONE. absence_reason_code=NONE is allowed when selected spans directly support the decision; otherwise use the closest frozen absence code. Do not output a composite label or rationale. Return only the strict schema and preserve review_item_id exactly.

The four axes are independent:
- current_target_fit: exact entity/issue/requested function, not topic similarity.
- specific_increment_available: a candidate-specific fact, relation, or act is not already visible.
- component_minimum_possible_now: a faithful next reply can realize the supplied exact minimum without importing another resource.
- current_boundary_permits: the user's current boundary permits this exact act now.
"""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": canonical_json(dict(item))},
    ]


def normalize_review(parsed: SuitabilityReview) -> dict[str, Any]:
    axes = {
        axis: getattr(parsed, axis).model_dump(mode="json")
        for axis in SUITABILITY_AXES
    }
    return {
        "review_item_id": parsed.review_item_id,
        "axes": axes,
        "derived_suitability": derive_suitability(
            {axis: axes[axis]["decision"] for axis in SUITABILITY_AXES}
        ),
    }


def _id(component: str, ordinal: int, surface: str) -> str:
    digest = hashlib.sha256(
        f"p2b-control-v1:{component}:{ordinal}:{surface}".encode()
    ).hexdigest()[:20]
    return f"control_{digest}"


_MINIMA = {
    "MP": {
        "minimum": "The stored profile fact changes at least one response constraint, logistical detail, framing choice, or materially relevant premise.",
        "does_not_count": ["merely naming the fact", "stereotyping", "a fact already visible"],
    },
    "MS": {
        "minimum": "A verified strictly-prior session observation adds cross-session continuity or context that changes understanding of the current issue.",
        "does_not_count": ["generic continuity", "same-topic repetition", "asserting a past state is current"],
    },
    "ME": {
        "minimum": "A verified past action-result relation is tentative user-owned evidence or an optional transferable possibility while preserving past tense and uncertainty.",
        "does_not_count": ["old-event recap", "guaranteed recurrence", "an action-result unrelated to the current goal"],
    },
    "RS": {
        "minimum": "Only the selected card's one atomic support move counts, and its use boundary must be satisfied.",
        "does_not_count": ["generic support", "a different strategy act", "an already-completed act"],
    },
}


def _surface(
    component: str,
    ordinal: int,
    visible: list[tuple[str, str]],
    candidate: list[str],
    gold: tuple[str, str, str, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    marker = "|".join([component, *candidate, *(text for _, text in visible)])
    item_id = _id(component, ordinal, marker)
    item = {
        "protocol": "pm-v1.5-paper1-p2b-reviewer-control-v1",
        "review_item_id": item_id,
        "component": component,
        "visible_spans": [
            {"span_id": f"V{i:03d}", "speaker": speaker, "content": text}
            for i, (speaker, text) in enumerate(visible, 1)
        ],
        "candidate_spans": [
            {"span_id": f"C{i:03d}", "kind": "control_candidate", "content": text}
            for i, text in enumerate(candidate, 1)
        ],
        "component_minimum": _MINIMA[component],
        "response_contract": {
            "axis_values": ["YES", "NO", "UNKNOWN"],
            "derived_suitability": "machine_projection_only",
            "evidence_submission": "pre_numbered_span_ids_only",
        },
    }
    axes = dict(zip(SUITABILITY_AXES, gold, strict=True))
    key = {
        "review_item_id": item_id,
        "component": component,
        "gold_axes": axes,
        "gold_derived": derive_suitability(axes),
        "critical_boundary_control": gold[-1] == "NO",
    }
    return item, key


def build_reviewer_controls() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return 24 deliberately clear anchors and their physically private key."""

    specs: dict[str, list[tuple[list[tuple[str, str]], list[str], tuple[str, str, str, str]]]] = {
        "MP": [
            ([("seeker", "I need one realistic way to fit meals around my changing shifts; my schedule is the whole problem.")], ["work schedule: rotating night shifts"], ("YES", "YES", "YES", "YES")),
            ([("seeker", "Please help me plan how to attend the venue; accessibility and moving between rooms are my main concerns.")], ["mobility constraint: uses a wheelchair"], ("YES", "YES", "YES", "YES")),
            ([("seeker", "I am anxious about tomorrow's mathematics exam and want help calming down.")], ["pet: has two cats"], ("NO", "YES", "NO", "YES")),
            ([("seeker", "I work rotating night shifts, so ordinary breakfast-time advice will not fit. Can we adapt the plan?")], ["work schedule: rotating night shifts"], ("YES", "NO", "NO", "YES")),
            ([("seeker", "I only want some company while I grieve my aunt; logistics and work are not part of this.")], ["job: accountant"], ("YES", "YES", "NO", "YES")),
            ([("seeker", "Do not use my saved profile or history. Just respond to what I say here: I need written steps because spoken ones are hard to retain.")], ["communication preference: written step-by-step instructions"], ("YES", "YES", "YES", "NO")),
        ],
        "MS": [
            ([("seeker", "The conflict with my supervisor happened again today; I want help understanding why these meetings derail.")], ["In the prior session, the user said the supervisor repeatedly interrupted them during team meetings."], ("YES", "YES", "YES", "YES")),
            ([("seeker", "The morning anxiety is back and I am trying to see whether there is a pattern across days.")], ["In the prior session, the user reported that the anxiety was strongest immediately after waking."], ("YES", "YES", "YES", "YES")),
            ([("seeker", "I want to talk about conflict with my new manager at work.")], ["In the prior session, the user described an argument with their roommate about cleaning."], ("NO", "YES", "NO", "YES")),
            ([("seeker", "Like I said last time, my supervisor interrupts me in team meetings; that exact pattern happened again.")], ["In the prior session, the user said the supervisor repeatedly interrupted them during team meetings."], ("YES", "NO", "NO", "YES")),
            ([("seeker", "We only exchanged greetings last time. Today I need help with a specific rent dispute.")], ["In the prior session, the user said hello and asked whether the supporter was available."], ("NO", "NO", "NO", "YES")),
            ([("seeker", "Please do not bring up earlier sessions. I want to discuss today's recurring morning anxiety only from what I say now.")], ["In the prior session, the user reported that the anxiety was strongest immediately after waking."], ("YES", "YES", "YES", "NO")),
        ],
        "ME": [
            ([("seeker", "My thoughts are racing again tonight. Could we consider something that has actually helped me before?")], ["Past action: wrote the worries in a notebook before bed.", "Observed result: the user reported that their thoughts slowed enough to sleep."], ("YES", "YES", "YES", "YES")),
            ([("seeker", "I have another tense meeting tomorrow and want one optional approach grounded in my own past experience.")], ["Past action: asked the chair for a written agenda before a meeting.", "Observed result: the user reported feeling more prepared and speaking once."], ("YES", "YES", "YES", "YES")),
            ([("seeker", "I am grieving a friendship ending and only want help naming that feeling.")], ["Past action: requested a written agenda before a work meeting.", "Observed result: the user reported feeling more prepared."], ("NO", "YES", "NO", "YES")),
            ([("seeker", "Writing my worries in a notebook slowed my thoughts enough to sleep last time. I want a different possibility now.")], ["Past action: wrote the worries in a notebook before bed.", "Observed result: the user reported that their thoughts slowed enough to sleep."], ("YES", "NO", "NO", "YES")),
            ([("seeker", "A colleague betrayed my confidence. I want emotional support, not workplace procedure.")], ["Past action: called HR about missing paperwork.", "Observed result: HR sent the paperwork the next day."], ("YES", "YES", "NO", "YES")),
            ([("seeker", "Do not use earlier experiences or suggest actions. Just listen while I describe tonight's racing thoughts.")], ["Past action: wrote the worries in a notebook before bed.", "Observed result: the user reported that their thoughts slowed enough to sleep."], ("YES", "YES", "YES", "NO")),
        ],
        "RS": [
            ([("seeker", "I feel ashamed and exhausted after being blamed for something I did not do.")], ["AM05 grounded validation: acknowledge one visible feeling, difficulty, loss, or tension without intensifying or inventing it."], ("YES", "YES", "YES", "YES")),
            ([("seeker", "I need help deciding what to do, but I have not said whether the deadline is tonight or next month.")], ["AM02 focused clarification: ask exactly one missing feeling, fact, timing detail, or goal that would materially improve understanding."], ("YES", "YES", "YES", "YES")),
            ([("supporter", "What part of the situation feels hardest right now?"), ("seeker", "It is the fear that I will disappoint my sister; that is the part I want to discuss.")], ["AM01 open invitation: use one non-presupposing invitation when the concern is not yet clear."], ("NO", "NO", "NO", "YES")),
            ([("seeker", "I do not want advice or action steps. I only want you to hear how overwhelmed I feel.")], ["AM10 optional micro-step: when advice is explicitly welcomed and the goal is clear, offer exactly one low-risk, low-burden, easily declined step."], ("NO", "YES", "NO", "NO")),
            ([("seeker", "I am worn out and want to stop here for today. Thanks for listening.")], ["AM14 supportive transition: when the user signals fatigue, completion, focus change, or closure, provide one bounded transition or close."], ("YES", "YES", "YES", "YES")),
            ([("seeker", "I feel crushed by the rejection."), ("supporter", "It makes sense that the rejection feels crushing after how much this mattered to you."), ("seeker", "Yes, that captures it exactly.")], ["AM05 grounded validation: acknowledge one visible feeling, difficulty, loss, or tension without intensifying or inventing it."], ("YES", "NO", "NO", "YES")),
        ],
    }
    items: list[dict[str, Any]] = []
    key: list[dict[str, Any]] = []
    for component in ("MP", "MS", "ME", "RS"):
        for ordinal, (visible, candidate, gold) in enumerate(specs[component], 1):
            item, truth = _surface(component, ordinal, visible, candidate, gold)
            items.append(item)
            key.append(truth)
    return items, key

