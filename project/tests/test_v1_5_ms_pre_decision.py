from __future__ import annotations

import pytest

from metacom_pm.v1_5_component_general_v3 import V3Candidate, build_component_general_plan_v3
from metacom_pm.v1_5_ms_pre_decision import assert_source_absent_from_compiled_text, ms_candidate_or_none
from metacom_pm.v1_5_response_program_v4 import response_generation_messages_v4

# The exact evo::p6 MS source that leaked into the MS+RS reply in
# paper1_rs_ms_panel_v2_blind_review_v2_closeout_v1.json -- a topically
# mismatched, sensitive fact that has nothing to do with the work-opportunity
# conversation it was tested against.
P6_MS_SOURCE = (
    "I have never been so blind sided. Maybe I should reconsider! I have had a guy "
    "after me for at least the last year but I never cheated! I really wanted to though."
)
P6_CURRENT_CONTEXT = (
    "seeker: I am worried about being perfect on my job. I don't want to lose my job.\n"
    "supporter: How long have you been at your job?\n"
    "seeker: Wow, I hope I can take advantage of that. I will have to check into that. "
    "Who should I approach at work?"
)
CURRENT_GOAL = "Respond supportively to the latest visible seeker turn."


def test_ignore_pre_decision_returns_none():
    candidate = ms_candidate_or_none(
        pre_decision="IGNORE",
        evidence_id="ms-p6",
        meaning_cue="cue",
        exact_source=P6_MS_SOURCE,
        owner_id="owner-p6",
        allowed_response_change="change",
        forbidden_inference="forbidden",
    )
    assert candidate is None


def test_use_and_ask_pre_decisions_build_a_real_candidate():
    for decision in ("USE", "ASK"):
        candidate = ms_candidate_or_none(
            pre_decision=decision,
            evidence_id="ms-1",
            meaning_cue="cue",
            exact_source="some past fact",
            owner_id="owner-1",
            allowed_response_change="change",
            forbidden_inference="forbidden",
        )
        assert isinstance(candidate, V3Candidate)
        assert candidate.exact_source == "some past fact"


def test_unknown_pre_decision_rejected():
    with pytest.raises(ValueError):
        ms_candidate_or_none(
            pre_decision="MAYBE",  # type: ignore[arg-type]
            evidence_id="ms-1", meaning_cue="cue", exact_source="x",
            owner_id="owner-1", allowed_response_change="change", forbidden_inference="forbidden",
        )


def test_p6_composition_leak_cannot_recur_with_ignore_pre_decision():
    """The exact failure mode from the real closeout: a topically mismatched
    MS source must never reach the compiled prompt, in ANY arm, once
    pre-decided IGNORE -- including the arm where RS also fires, which is
    precisely where the leak happened under the old architecture."""

    ms_candidate = ms_candidate_or_none(
        pre_decision="IGNORE",
        evidence_id="ms-p6",
        meaning_cue="tentative continuity cue",
        exact_source=P6_MS_SOURCE,
        owner_id="owner-p6",
        allowed_response_change="USE only when it adds information not already available",
        forbidden_inference="do not assume the past remains true",
    )
    assert ms_candidate is None

    rs_candidate = V3Candidate(
        component="RS",
        evidence_id="card-1",
        meaning_cue="strategy_family=Providing Suggestions",
        exact_source="Consider asking a trusted colleague or supervisor for guidance.",
        owner_id=None,
        time_status="CURRENT_CARD",
        allowed_response_change="Add or sharpen one bounded strategy move.",
        forbidden_inference="Do not let the card replace current-turn grounding.",
    )

    for action, candidates in (
        ("M0+RS", {"MP": None, "MS": ms_candidate, "ME": None, "RS": rs_candidate}),
        ("M0+R0", {"MP": None, "MS": ms_candidate, "ME": None, "RS": None}),
    ):
        plan = build_component_general_plan_v3(
            requested_action_id=action, current_user_id="owner-p6", candidates=candidates
        )
        messages = response_generation_messages_v4(
            current_context=P6_CURRENT_CONTEXT, current_goal=CURRENT_GOAL, plan=plan
        )
        assert_source_absent_from_compiled_text(exact_source=P6_MS_SOURCE, compiled_messages=messages)
        # also check the two most distinctive phrases individually, in case
        # of any partial-string normalization difference
        full_text = " ".join(m["content"] for m in messages)
        assert "blind sided" not in full_text
        assert "never cheated" not in full_text
