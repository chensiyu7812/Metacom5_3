"""Content-disjoint all-action semantic qualification plan for V5.3 Step2.

The older compatibility artifact proved only that one synthetic fixture could
be serialized for each of the 16 actions.  This plan creates four independent
semantic families for every action (64 logical cases), freezes exact messages,
and declares the requested->realized->functional->risk review fields before
any endpoint is called.  These cases are qualification-only and can never
enter Step1 fitting, confirmation, or external evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import Field, model_validator

from .contracts import ALL_ACTION_IDS, StrictModel
from .io import canonical_json, stable_hex
from .v1_5_typed_resource_adapter import TypedResourceCandidate
from .v1_5_v5_3_typed_response_program import (
    RewritePolicy,
    build_typed_response_program,
    evidence_aware_generation_messages,
)
from .v1_5b_policy_runtime import COMPONENTS, action_component_bits


QUALIFICATION_PROTOCOL = "pm-v1.5-v5.3-step2-semantic-qualification-plan-v1"


@dataclass(frozen=True)
class _Family:
    family_id: str
    current_context: str
    current_goal: str
    mp_subtype: str
    mp_value: str
    ms_observation: str
    me_action: str
    me_outcome: str
    rs_move: str
    rs_when: str
    rs_boundary: str


_FAMILIES = (
    _Family(
        family_id="evening_schedule_transition",
        current_context=(
            "User: My schedule shifted again this week. I want one brief response that "
            "fits what is realistically possible tonight, without turning this into a plan."
        ),
        current_goal="Give one realistic, low-burden response for tonight's schedule transition.",
        mp_subtype="MP_PROFILE",
        mp_value="The user has only a short private window late in the evening.",
        ms_observation=(
            "A prior discussion distinguished strain from abrupt schedule changes from "
            "ordinary difficulty falling asleep."
        ),
        me_action="The user muted nonessential notifications for twenty minutes.",
        me_outcome="That brief pause reduced the pressure to solve everything at once.",
        rs_move="Offer exactly one optional, low-burden step for this evening.",
        rs_when="The user explicitly welcomes one realistic response for tonight.",
        rs_boundary="Do not create a schedule, list, deadline, or second action.",
    ),
    _Family(
        family_id="repairing_friendship_message",
        current_context=(
            "User: I am ready to find a careful way to reply to my friend. Please keep it "
            "tentative and give me only one possible starting point."
        ),
        current_goal="Help the user begin one low-conflict reply without assuming the friend's intent.",
        mp_subtype="MP_PREFERENCE",
        mp_value="The user prefers choices framed as optional possibilities rather than directives.",
        ms_observation=(
            "An earlier conversation separated wanting clarification from wanting an apology."
        ),
        me_action="The user named one concern before discussing the rest.",
        me_outcome="Keeping the opening to one concern made the exchange less reactive.",
        rs_move="Offer one tentative, low-conflict conversation opener.",
        rs_when="The user is ready to reply and asks for one possible starting point.",
        rs_boundary="Do not infer motive, demand reconciliation, or add a follow-up task.",
    ),
    _Family(
        family_id="coursework_pressure_sorting",
        current_context=(
            "User: I can talk about the coursework pressure now, but I need help separating "
            "what is practically heavy from what is emotionally uncertain. Keep it concise."
        ),
        current_goal="Clarify the two kinds of coursework pressure without prescribing a full plan.",
        mp_subtype="MP_PROFILE",
        mp_value="The user can work on coursework only during two short weekday blocks.",
        ms_observation=(
            "A prior session distinguished the actual workload from guilt about taking rest."
        ),
        me_action="The user wrote down one concrete demand before considering the whole workload.",
        me_outcome="That made the immediate source of pressure easier to identify.",
        rs_move="Ask exactly one focused question that helps separate practical load from emotion.",
        rs_when="The user explicitly asks for help distinguishing two already named dimensions.",
        rs_boundary="Ask no second question and do not turn the reply into a study plan.",
    ),
    _Family(
        family_id="settling_into_new_neighborhood",
        current_context=(
            "User: This quiet weekend in the new neighborhood feels different again. I am open "
            "to one small, reversible idea, but please leave room for me to say it does not fit."
        ),
        current_goal="Offer one reversible, declinable response to the quiet weekend.",
        mp_subtype="MP_PREFERENCE",
        mp_value="The user prefers a small experiment that can be declined or revised.",
        ms_observation=(
            "An earlier conversation distinguished unfamiliar surroundings from the absence "
            "of familiar local connections."
        ),
        me_action="The user briefly attended a recurring neighborhood activity.",
        me_outcome="Having one familiar point in the week made the following weekend feel less unstructured.",
        rs_move="Offer exactly one reversible environmental or routine adjustment.",
        rs_when="The user explicitly welcomes one small reversible idea.",
        rs_boundary="Do not presume a support network, prescribe repeated attendance, or stack options.",
    ),
)


def semantic_qualification_surface_rows() -> list[dict[str, str]]:
    """Return only semantic content surfaces used to author the qualification.

    Prompt boilerplate and field names are intentionally excluded: the
    disjointness question is whether the cases, goals, or evidence contents
    were copied from formal/external material, not whether two protocols both
    contain words such as ``current_goal``.
    """

    rows: list[dict[str, str]] = []
    fields = (
        "current_context",
        "current_goal",
        "mp_value",
        "ms_observation",
        "me_action",
        "me_outcome",
        "rs_move",
        "rs_when",
        "rs_boundary",
    )
    for family in _FAMILIES:
        for field_name in fields:
            rows.append(
                {
                    "surface_id": f"step2-semantic:{family.family_id}:{field_name}",
                    "category": f"step2_semantic_{field_name}",
                    "text": str(getattr(family, field_name)),
                }
            )
    return rows


class SemanticQualificationCase(StrictModel):
    case_id: str = Field(pattern=r"^v53step2sem_[0-9a-f]{24}$")
    semantic_family: str
    action_id: str
    current_goal: str
    current_context: str
    evidence_ids: list[str]
    messages: list[dict[str, str]]
    messages_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_requested_components: list[str]
    recovery_policy: Literal["deterministic_fallback"] = "deterministic_fallback"
    qualification_only: Literal[True] = True
    excluded_from_fit_confirmation_external: Literal[True] = True

    @model_validator(mode="after")
    def coherent(self):
        if self.action_id not in ALL_ACTION_IDS:
            raise ValueError("unknown legal action")
        expected = [
            component
            for component in COMPONENTS
            if action_component_bits(self.action_id)[component]
        ]
        if self.expected_requested_components != expected:
            raise ValueError("requested components differ from action bits")
        if len(self.evidence_ids) != len(expected):
            raise ValueError("evidence count differs from requested components")
        if self.messages_sha256 != stable_hex(canonical_json(self.messages), n=64):
            raise ValueError("messages_sha256 does not match messages")
        expected_id = "v53step2sem_" + stable_hex(
            self.semantic_family,
            self.action_id,
            self.messages_sha256,
            n=24,
        )
        if self.case_id != expected_id:
            raise ValueError("case_id does not match frozen case inputs")
        return self


class SemanticQualificationPlan(StrictModel):
    protocol: Literal[
        "pm-v1.5-v5.3-step2-semantic-qualification-plan-v1"
    ] = QUALIFICATION_PROTOCOL
    status: Literal["PLAN_FROZEN_API_EXECUTION_AND_REVIEW_PENDING"] = (
        "PLAN_FROZEN_API_EXECUTION_AND_REVIEW_PENDING"
    )
    cases: list[SemanticQualificationCase]
    family_count: int
    action_count: int
    logical_call_count: int
    review_fields: list[str]
    hard_release_invariants: list[str]
    descriptive_readiness_metrics: list[str]
    endpoint_or_model_selected: Literal[False] = False
    generated_response_or_quality_risk_outcome_read: Literal[False] = False
    api_calls: Literal[0] = 0
    plan_identity: str = Field(pattern=r"^v53step2semplan_[0-9a-f]{24}$")

    @model_validator(mode="after")
    def coherent(self):
        if self.family_count != len(_FAMILIES) or self.action_count != 16:
            raise ValueError("qualification must retain four families and all 16 actions")
        if self.logical_call_count != self.family_count * self.action_count:
            raise ValueError("logical call count differs from family/action product")
        keys = [(case.semantic_family, case.action_id) for case in self.cases]
        if len(keys) != len(set(keys)) or len(keys) != self.logical_call_count:
            raise ValueError("qualification cases are incomplete or duplicated")
        payload = self.model_dump(mode="json", exclude={"plan_identity"})
        expected = "v53step2semplan_" + stable_hex(canonical_json(payload), n=24)
        if self.plan_identity != expected:
            raise ValueError("plan_identity does not match semantic qualification plan")
        return self


def _candidates(family: _Family) -> dict[str, TypedResourceCandidate]:
    if family.mp_subtype == "MP_PREFERENCE":
        mp = TypedResourceCandidate(
            component="MP",
            subtype="MP_PREFERENCE",
            resource_id=f"{family.family_id}_mp",
            candidate_version="qualification_v1",
            source_kind="profile",
            owner_id=f"{family.family_id}_user",
            preference=family.mp_value,
        )
    else:
        mp = TypedResourceCandidate(
            component="MP",
            subtype="MP_PROFILE",
            resource_id=f"{family.family_id}_mp",
            candidate_version="qualification_v1",
            source_kind="profile",
            owner_id=f"{family.family_id}_user",
            profile_fact=family.mp_value,
        )
    return {
        "MP": mp,
        "MS": TypedResourceCandidate(
            component="MS",
            subtype="MS_SESSION_OBSERVATION",
            resource_id=f"{family.family_id}_ms",
            candidate_version="qualification_v1",
            source_kind="session",
            owner_id=f"{family.family_id}_user",
            strictly_prior=True,
            age_sessions=3,
            prior_observation=family.ms_observation,
        ),
        "ME": TypedResourceCandidate(
            component="ME",
            subtype="ME_REUSABLE_OUTCOME",
            resource_id=f"{family.family_id}_me",
            candidate_version="qualification_v1",
            source_kind="event",
            owner_id=f"{family.family_id}_user",
            strictly_prior=True,
            age_sessions=4,
            past_action=family.me_action,
            observed_outcome=family.me_outcome,
        ),
        "RS": TypedResourceCandidate(
            component="RS",
            subtype="RS_ATOMIC_MOVE",
            resource_id=f"{family.family_id}_rs",
            candidate_version="qualification_v1",
            source_kind="strategy",
            support_move=family.rs_move,
            when_to_use=family.rs_when,
            when_not_to_use=family.rs_boundary,
        ),
    }


def build_semantic_qualification_plan() -> SemanticQualificationPlan:
    cases: list[SemanticQualificationCase] = []
    for family in _FAMILIES:
        available = _candidates(family)
        for action_id in ALL_ACTION_IDS:
            bits = action_component_bits(action_id)
            selected = {c: available[c] for c in COMPONENTS if bits[c]}
            expected_ids = {c: selected[c].resource_id for c in selected}
            program = build_typed_response_program(
                requested_action_id=action_id,
                current_goal=family.current_goal,
                current_user_id=f"{family.family_id}_user",
                candidates=selected,
                expected_execution_candidate_ids=expected_ids,
            )
            messages = evidence_aware_generation_messages(
                current_context=family.current_context,
                program=program,
            )
            digest = stable_hex(canonical_json(messages), n=64)
            case_id = "v53step2sem_" + stable_hex(
                family.family_id, action_id, digest, n=24
            )
            cases.append(
                SemanticQualificationCase(
                    case_id=case_id,
                    semantic_family=family.family_id,
                    action_id=action_id,
                    current_goal=family.current_goal,
                    current_context=family.current_context,
                    evidence_ids=[item.evidence_id for item in program.evidence],
                    messages=messages,
                    messages_sha256=digest,
                    expected_requested_components=[c for c in COMPONENTS if bits[c]],
                )
            )
    payload = {
        "protocol": QUALIFICATION_PROTOCOL,
        "status": "PLAN_FROZEN_API_EXECUTION_AND_REVIEW_PENDING",
        "cases": cases,
        "family_count": len(_FAMILIES),
        "action_count": len(ALL_ACTION_IDS),
        "logical_call_count": len(cases),
        "review_fields": [
            "structured_output_valid",
            "requested_action_id",
            "realized_action_id",
            "requested_components",
            "generator_received_evidence_ids",
            "normalized_used_evidence_ids",
            "functional_contribution_per_component",
            "grounding_fidelity",
            "speaker_owner_attribution",
            "atomic_move_compliance",
            "material_risk",
            "critical_event_categories",
            "fallback",
            "adoptable_reply",
        ],
        "hard_release_invariants": [
            "all_16_actions_have_at_least_one_structurally_valid_case",
            "assignment_owner_evidence_binding_errors_equal_zero",
            "fabricated_recall_wrong_owner_and_internal_label_events_equal_zero",
            "no_second_free_generation_call",
        ],
        "descriptive_readiness_metrics": [
            "requested_to_realized_rate_by_action_and_component",
            "functional_contribution_rate_by_component",
            "fallback_rate_by_action_load",
            "material_risk_rate_by_action_load",
            "adoptable_reply_rate_with_cluster_interval",
        ],
        "endpoint_or_model_selected": False,
        "generated_response_or_quality_risk_outcome_read": False,
        "api_calls": 0,
    }
    payload["plan_identity"] = "v53step2semplan_" + stable_hex(
        canonical_json(
            {
                key: [item.model_dump(mode="json") for item in value]
                if key == "cases"
                else value
                for key, value in payload.items()
            }
        ),
        n=24,
    )
    return SemanticQualificationPlan.model_validate(payload)


def semantic_qualification_programs() -> dict[str, TypedResponseProgram]:
    """Rebuild the exact typed program bound to every frozen qualification case.

    The serialized plan intentionally stores model-visible messages rather than
    private candidate objects.  A real executor still needs the program to run
    the same owner/evidence/atomic-move guards.  This helper deterministically
    reconstructs those programs and asserts that their messages and case IDs
    remain byte-identical to the frozen plan, preventing a runner from silently
    validating a different program than the one the endpoint received.
    """

    frozen = build_semantic_qualification_plan()
    frozen_by_key = {
        (case.semantic_family, case.action_id): case for case in frozen.cases
    }
    programs: dict[str, TypedResponseProgram] = {}
    for family in _FAMILIES:
        available = _candidates(family)
        for action_id in ALL_ACTION_IDS:
            bits = action_component_bits(action_id)
            selected = {component: available[component] for component in COMPONENTS if bits[component]}
            expected_ids = {component: selected[component].resource_id for component in selected}
            program = build_typed_response_program(
                requested_action_id=action_id,
                current_goal=family.current_goal,
                current_user_id=f"{family.family_id}_user",
                candidates=selected,
                expected_execution_candidate_ids=expected_ids,
            )
            case = frozen_by_key[(family.family_id, action_id)]
            messages = evidence_aware_generation_messages(
                current_context=family.current_context,
                program=program,
            )
            if messages != case.messages:
                raise RuntimeError("qualification program messages drifted from frozen case")
            programs[case.case_id] = program
    if set(programs) != {case.case_id for case in frozen.cases}:
        raise RuntimeError("qualification program coverage differs from frozen cases")
    return programs
