from __future__ import annotations

from metacom_pm.v1_5_memory_realization_v2 import (
    build_joint_composition_plan,
    current_seeker_query,
    is_low_information_turn,
    parse_raw_ms_session,
    select_ms_exact_span,
)


def test_phatic_filter_rejects_thanks_but_keeps_concrete_fact():
    assert is_low_information_turn("Thanks, I really appreciate it")
    assert is_low_information_turn("okay")
    assert not is_low_information_turn("I lost my job yesterday")
    assert not is_low_information_turn("I slept for only one hour")


def test_span_selector_uses_exact_informative_turn_not_higher_scored_thanks():
    raw = "\n".join(
        [
            "SEEKER: Thanks, I really appreciate it",
            "SEEKER: I slept for only one hour after working all day",
            "SEEKER: okay",
        ]
    )
    scores = {"I slept for only one hour after working all day": 0.31}
    selected = select_ms_exact_span(raw, scores)
    assert selected is not None
    assert selected.exact_span == "I slept for only one hour after working all day"
    assert selected.raw_turn_count == 3
    assert selected.informative_turn_count == 1


def test_current_query_excludes_supporter_text():
    query = current_seeker_query(
        [
            {"speaker": "seeker", "content": "I feel stuck"},
            {"speaker": "supporter", "content": "Have you tried exercise?"},
            {"speaker": "seeker", "content": "Exercise did not help"},
        ]
    )
    assert query == "I feel stuck\nExercise did not help"


def test_joint_plan_keeps_sixteen_action_interface_but_suppresses_missing_ms():
    plan = build_joint_composition_plan(
        requested_action_id="MS+RS",
        realized_content={"MS": None, "RS": "validate the feeling"},
    )
    assert plan.requested_action_id == "MS+RS"
    assert plan.feasible_action_id == "M0+RS"
    assert plan.suppressed["MS"] == "NO_SAFE_REALIZED_RESOURCE"
    assert plan.primary_response_act == "RS"


def test_mp_is_silent_and_rs_is_primary():
    plan = build_joint_composition_plan(
        requested_action_id="MP+RS",
        realized_content={"MP": "one suggestion at a time", "RS": "ask one open question"},
    )
    resources = {resource.component: resource for resource in plan.resources}
    assert resources["MP"].requires_literal_mention is False
    assert resources["RS"].role == "PRIMARY_SUPPORT_ACT"
    assert plan.feasible_action_id == "MP+RS"


def test_unknown_ms_me_pair_does_not_force_both_into_reply():
    plan = build_joint_composition_plan(
        requested_action_id="MSE+R0",
        realized_content={"MS": "past observation", "ME": "past action and result"},
        component_scores={"MS": 0.7, "ME": 0.6},
        joint_memory_relation="UNKNOWN",
    )
    assert plan.feasible_action_id == "MS+R0"
    assert plan.suppressed["ME"] == "JOINT_MEMORY_UNKNOWN_LOWER_PRIORITY"


def test_complementary_ms_me_pair_can_share_one_plan():
    plan = build_joint_composition_plan(
        requested_action_id="MSE+R0",
        realized_content={"MS": "past observation", "ME": "past action and result"},
        joint_memory_relation="COMPLEMENTARY",
    )
    assert plan.feasible_action_id == "MSE+R0"
    assert not plan.suppressed


def test_raw_parser_preserves_turn_payloads():
    assert parse_raw_ms_session("SEEKER: first\nSEEKER: second") == ("first", "second")
