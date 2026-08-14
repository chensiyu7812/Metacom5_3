from __future__ import annotations

from metacom_pm.v1_5_component_general_v3 import (
    V3Candidate,
    build_component_general_plan_v3,
)
from metacom_pm.v1_5_response_program_v4 import (
    r0_foundation_contract_v4,
    response_generation_messages_v4,
)


def _candidate(component: str) -> V3Candidate:
    return V3Candidate(
        component=component,
        evidence_id=f"evidence-{component.lower()}",
        meaning_cue=f"bounded meaning for {component}",
        exact_source=f"source for {component}",
        owner_id=None if component == "RS" else "owner-1",
        time_status="CURRENT_CARD" if component == "RS" else "STRICTLY_PAST",
        allowed_response_change=f"bounded change for {component}",
        forbidden_inference="do not infer a present fact",
    )


def _plan(action: str):
    mem, strategy = action.split("+")
    candidates = {
        "MP": _candidate("MP") if "MP" in mem else None,
        "MS": _candidate("MS") if "MS" in mem else None,
        "ME": None,
        "RS": _candidate("RS") if strategy == "RS" else None,
    }
    return build_component_general_plan_v3(
        requested_action_id=action,
        current_user_id="owner-1",
        candidates=candidates,
    )


def _prompt(action: str) -> str:
    return response_generation_messages_v4(
        current_context="I feel stuck today.",
        current_goal="Offer grounded support.",
        plan=_plan(action),
    )[0]["content"]


def test_every_factorial_arm_keeps_the_exact_r0_foundation():
    for action in ("M0+R0", "M0+RS", "MS+R0", "MS+RS"):
        prompt = _prompt(action)
        assert all(line in prompt for line in r0_foundation_contract_v4())


def test_rs_is_a_delta_and_restatement_cannot_replace_the_reply():
    prompt = _prompt("M0+RS")
    assert "add or sharpen one strategy move" in prompt
    assert "A restatement is a local move, never the whole reply" in prompt
    assert "one primary atomic support act" not in prompt
    assert "Use exactly one primary response act" not in prompt


def test_ms_has_use_ask_ignore_and_nonuse_is_not_function():
    prompt = _prompt("MS+R0")
    assert "decide USE, ASK, or IGNORE" in prompt
    assert "safe non-use must not earn memory Function" in prompt
    assert "adds information not already available in the current dialogue" in prompt


def test_joint_arm_has_explicit_composition_order_without_erasing_r0():
    prompt = _prompt("MS+RS")
    assert "current-turn and safety foundation; supported personal-memory delta; strategy delta" in prompt
    assert "Never duplicate content or erase R0" in prompt
    assert "Do not add generic warmth, questions, advice, or length merely because a resource is present" in prompt


def test_mp_has_constrain_ignore_and_declared_without_change_is_ignore():
    prompt = _prompt("MP+R0")
    assert "decide CONSTRAIN or IGNORE" in prompt
    assert "never only a mental note" in prompt
    assert "Declaring CONSTRAIN without a concrete change is the same as IGNORE" in prompt
    assert "never state, recite, or imply the literal profile value itself" in prompt


def test_mp_and_ms_are_both_deltas_and_can_coexist_with_rs():
    prompt = _prompt("MPMS+RS")
    assert "Optional MP profile delta" in prompt
    assert "Optional MS continuity delta" in prompt
    assert "Optional RS strategy delta" in prompt
    assert all(line in prompt for line in r0_foundation_contract_v4())


def test_excluding_ms_keeps_rs_and_the_same_r0_foundation():
    plan = _plan("MS+RS")
    prompt = response_generation_messages_v4(
        current_context="I feel stuck today.",
        current_goal="Offer grounded support.",
        plan=plan,
        excluded_components=frozenset({"MS"}),
    )[0]["content"]
    assert "Optional MS continuity delta" not in prompt
    assert "Optional RS strategy delta" in prompt
    assert all(line in prompt for line in r0_foundation_contract_v4())

