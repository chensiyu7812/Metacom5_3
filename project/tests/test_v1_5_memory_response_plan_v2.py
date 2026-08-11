from __future__ import annotations

from metacom_pm.v1_5_memory_realization_v2 import build_joint_composition_plan
from metacom_pm.v1_5_memory_response_plan_v2 import (
    build_memory_response_plan,
    execute_memory_response,
    memory_response_guard_errors,
    memory_response_generation_messages,
)
from metacom_pm.v1_5_v5_3_typed_response_program import GeneratorResponse


class _Parsed:
    def __init__(self, value):
        self.value = value

    def model_dump(self, mode="json"):
        return self.value


class _Client:
    def __init__(self, value):
        self.value = value

    def chat(self, messages, *, response_schema):
        return object(), _Parsed(self.value)


def test_ms_plan_injects_only_selected_span_not_raw_session():
    composition = build_joint_composition_plan(
        requested_action_id="MS+R0",
        realized_content={"MS": "I slept for only one hour after working all day"},
    )
    plan = build_memory_response_plan(
        composition=composition,
        current_goal="Respond to the current sleep concern",
        current_user_id="evo::p1",
        evidence_ids={"MS": "mss_span_1"},
    )
    messages = memory_response_generation_messages(
        current_context="I still cannot sleep even when I am exhausted", plan=plan
    )
    system = messages[0]["content"]
    assert "I slept for only one hour after working all day" in system
    assert "TENTATIVE_CONTINUITY_BRIDGE" in system
    assert "use all" not in system.lower()
    assert "every evidence" not in system.lower()
    assert "past" in system and "present fact" in system


def test_m0_plan_forbids_implied_recall():
    composition = build_joint_composition_plan(
        requested_action_id="M0+R0", realized_content={}
    )
    plan = build_memory_response_plan(
        composition=composition,
        current_goal="Respond supportively",
        current_user_id="evo::p1",
        evidence_ids={},
    )
    system = memory_response_generation_messages(
        current_context="I am worried", plan=plan
    )[0]["content"]
    assert "No prior memory/profile evidence is authorized" in system
    assert "never imply recall" in system


def test_mp_is_rendered_as_silent_modifier_not_citation():
    composition = build_joint_composition_plan(
        requested_action_id="MP+R0",
        realized_content={"MP": "Offer one suggestion at a time"},
    )
    plan = build_memory_response_plan(
        composition=composition,
        current_goal="Respond supportively",
        current_user_id="u1",
        evidence_ids={"MP": "mp1"},
    )
    system = memory_response_generation_messages(
        current_context="What should I do?", plan=plan
    )[0]["content"]
    assert "Apply this silently" in system
    assert "Do not read the fact or preference back" in system


def test_suppressed_resource_never_enters_plan():
    composition = build_joint_composition_plan(
        requested_action_id="MS+R0", realized_content={"MS": None}
    )
    plan = build_memory_response_plan(
        composition=composition,
        current_goal="Respond supportively",
        current_user_id="u1",
        evidence_ids={},
    )
    assert not plan.evidence
    assert plan.feasible_action_id == "M0+R0"
    assert plan.suppressed["MS"] == "NO_SAFE_REALIZED_RESOURCE"


def test_guard_requires_ms_trace_and_word_connection():
    composition = build_joint_composition_plan(
        requested_action_id="MS+R0",
        realized_content={"MS": "I slept for only one hour after working all day"},
    )
    plan = build_memory_response_plan(
        composition=composition,
        current_goal="Respond to the sleep concern",
        current_user_id="u1",
        evidence_ids={"MS": "evidence1"},
    )
    missing = GeneratorResponse("That sounds hard.", (), "support")
    assert "REQUIRED_MEMORY_EVIDENCE_NOT_USED" in memory_response_guard_errors(
        response=missing, plan=plan
    )
    clean = GeneratorResponse(
        "You mentioned that even after working all day you slept only one hour; is that still happening?",
        ("evidence1",),
        "tentative continuity",
    )
    assert not memory_response_guard_errors(response=clean, plan=plan)


def test_executor_falls_back_after_ms_nonuse():
    composition = build_joint_composition_plan(
        requested_action_id="MS+R0", realized_content={"MS": "I lost my job"}
    )
    plan = build_memory_response_plan(
        composition=composition,
        current_goal="Respond supportively",
        current_user_id="u1",
        evidence_ids={"MS": "evidence1"},
    )
    result = execute_memory_response(
        _Client({"reply": "I hear you.", "used_evidence_ids": [], "realized_response_act": "support"}),
        object,
        [],
        plan,
    )
    assert result.status == "fell_back_to_m0"
    assert result.realized_action_id == "M0+R0"
