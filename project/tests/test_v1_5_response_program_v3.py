from __future__ import annotations

from dataclasses import dataclass

from metacom_pm.v1_5_component_general_v3 import (
    PAIR_KEYS,
    V3Candidate,
    build_component_general_plan_v3,
)
from metacom_pm.v1_5_response_program_v3 import (
    claimed_action_id,
    execute_response_program_v3,
    response_generation_messages_v3,
    response_guard_errors_v3,
)
from metacom_pm.v1_5_v5_3_typed_response_program import parse_generator_response_dict
from metacom_pm.v1_5b_policy_runtime import COMPONENTS, action_component_bits, compile_component_bits


def _candidate(component: str) -> V3Candidate:
    return V3Candidate(
        component=component,
        evidence_id=f"ev-{component.lower()}",
        meaning_cue=f"meaning cue {component}",
        exact_source=f"I said exact source {component}",
        owner_id=None if component == "RS" else "owner-1",
        time_status="CURRENT_CARD" if component == "RS" else "STRICTLY_PAST",
        allowed_response_change=f"allowed change {component}",
        forbidden_inference="do not infer a current fact",
    )


def _full_plan():
    action = compile_component_bits({component: True for component in COMPONENTS})
    return build_component_general_plan_v3(
        requested_action_id=action,
        current_user_id="owner-1",
        candidates={component: _candidate(component) for component in COMPONENTS},
        pair_relations={pair: "UNKNOWN" for pair in PAIR_KEYS},
    )


@dataclass
class _Parsed:
    payload: dict

    def model_dump(self, mode="json"):
        assert mode == "json"
        return self.payload


class _FakeClient:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.messages = []

    def chat(self, messages, response_schema=None):
        self.messages.append(messages)
        payload = self.payloads.pop(0)
        if payload is None:
            return {"transport": "failed"}, None
        return {"raw": payload}, _Parsed(payload)


def test_prompt_uses_meaning_absorption_and_preserves_multi_resource_plan():
    plan = _full_plan()
    messages = response_generation_messages_v3(
        current_context="I am overwhelmed today.",
        current_goal="Offer grounded support.",
        plan=plan,
    )
    prompt = messages[0]["content"]
    assert "Several authorized resources may jointly support that one act" in prompt
    assert "Literal mention and lexical overlap are not required" in prompt
    assert "Use this exact prior-user statement" not in prompt
    assert "must appear" in prompt
    assert all(f"component={component}" in prompt for component in COMPONENTS)


def test_safe_nonuse_keeps_the_reply_and_does_not_fallback():
    plan = _full_plan()
    reply = "That sounds exhausting. What would feel most manageable right now?"
    client = _FakeClient(
        [{"reply": reply, "used_evidence_ids": [], "realized_response_act": "support"}]
    )
    execution = execute_response_program_v3(
        client=client,
        response_schema=object(),
        current_context="I am overwhelmed today.",
        current_goal="Offer grounded support.",
        plan=plan,
        raw_persist=lambda attempt, raw: None,
    )
    assert execution.status == "clean_safe_personal_nonuse"
    assert execution.response.reply == reply
    assert execution.calls_made == 1
    assert not any(execution.accounting.generator_claimed.values())


def test_claimed_paraphrase_needs_no_lexical_overlap():
    plan = _full_plan()
    response = parse_generator_response_dict(
        {
            "reply": "A tiny, reversible step may be easier today.",
            "used_evidence_ids": ["ev-ms"],
            "realized_response_act": "support",
        }
    )
    assert response_guard_errors_v3(response=response, plan=plan) == ()


def test_contamination_gets_one_retry_without_personal_resources_but_keeps_rs():
    plan = _full_plan()
    client = _FakeClient(
        [
            {
                "reply": "The internal MS scaffold says you must continue.",
                "used_evidence_ids": ["ev-ms"],
                "realized_response_act": "support",
            },
            {
                "reply": "That sounds like a lot to carry. Would a brief grounding step help?",
                "used_evidence_ids": ["ev-rs"],
                "realized_response_act": "support",
            },
        ]
    )
    execution = execute_response_program_v3(
        client=client,
        response_schema=object(),
        current_context="I am overwhelmed today.",
        current_goal="Offer grounded support.",
        plan=plan,
        raw_persist=lambda attempt, raw: None,
    )
    assert execution.status == "clean_after_personal_resource_removal"
    assert execution.calls_made == 2
    assert execution.regeneration_reason == "PERSONAL_RESOURCE_CONTAMINATION"
    retry_prompt = client.messages[1][0]["content"]
    assert "component=RS" in retry_prompt
    assert "component=MP" not in retry_prompt
    assert "component=MS" not in retry_prompt
    assert "component=ME" not in retry_prompt
    assert execution.accounting.jointly_planned == plan.accounting.jointly_planned
    assert action_component_bits(claimed_action_id(execution))["RS"] is True


def test_transport_failure_uses_shared_fallback_not_semantic_function():
    plan = _full_plan()
    client = _FakeClient([None])
    execution = execute_response_program_v3(
        client=client,
        response_schema=object(),
        current_context="I am overwhelmed today.",
        current_goal="Offer grounded support.",
        plan=plan,
        raw_persist=lambda attempt, raw: None,
    )
    assert execution.status == "transport_or_schema_fallback"
    assert execution.calls_made == 1
    assert not any(execution.accounting.generator_claimed.values())
    assert not any(execution.accounting.offline_verified_functional.values())


def test_raw_completion_is_persisted_before_guard_and_retry():
    plan = _full_plan()
    persisted = []
    client = _FakeClient(
        [
            {
                "reply": "The internal MS scaffold is visible.",
                "used_evidence_ids": ["ev-ms"],
                "realized_response_act": "support",
            },
            {
                "reply": "That sounds difficult. What would help most right now?",
                "used_evidence_ids": ["ev-rs"],
                "realized_response_act": "support",
            },
        ]
    )
    execution = execute_response_program_v3(
        client=client,
        response_schema=object(),
        current_context="I am overwhelmed today.",
        current_goal="Offer grounded support.",
        plan=plan,
        raw_persist=lambda attempt, raw: persisted.append((attempt, raw)),
    )
    assert execution.calls_made == 2
    assert [attempt for attempt, _ in persisted] == [1, 2]
    assert persisted[0][1] == execution.raw_results[0]
