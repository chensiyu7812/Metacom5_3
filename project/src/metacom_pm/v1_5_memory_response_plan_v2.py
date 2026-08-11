"""Typed generator program for the realization/composition V2 candidate.

Unlike the historical V5.3 prompt, this compiler never says that every
retrieved item is already useful and must be incorporated as a peer fact.
It renders component-specific roles from a precomputed feasible joint plan.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping

from .text import content_words
from .v1_5_memory_realization_v2 import JointCompositionPlan, PlannedResource, compact
from .v1_5_v5_3_typed_response_program import (
    GeneratorResponse,
    m0_fallback_response,
    parse_generator_response_dict,
    speaker_attribution_guard_errors,
)


@dataclass(frozen=True)
class ResponsePlanEvidence:
    component: str
    evidence_id: str
    owner_id: str | None
    exact_content: str
    role: str
    requires_literal_mention: bool


@dataclass(frozen=True)
class MemoryResponsePlan:
    requested_action_id: str
    feasible_action_id: str
    current_goal: str
    primary_response_act: str
    evidence: tuple[ResponsePlanEvidence, ...]
    suppressed: Mapping[str, str]
    assembly_order: tuple[str, ...]


@dataclass(frozen=True)
class MemoryResponseExecutionResult:
    response: GeneratorResponse
    status: str
    requested_action_id: str
    feasible_action_id: str
    realized_action_id: str
    guard_errors: tuple[str, ...]
    calls_made: int = 1


def build_memory_response_plan(
    *,
    composition: JointCompositionPlan,
    current_goal: str,
    current_user_id: str,
    evidence_ids: Mapping[str, str],
) -> MemoryResponsePlan:
    if not compact(current_goal) or not compact(current_user_id):
        raise ValueError("current_goal and current_user_id must be non-empty")
    evidence = []
    for resource in composition.resources:
        evidence_id = compact(evidence_ids.get(resource.component))
        if not evidence_id:
            raise ValueError(f"missing evidence_id for feasible {resource.component}")
        evidence.append(
            ResponsePlanEvidence(
                component=resource.component,
                evidence_id=evidence_id,
                owner_id=None if resource.component == "RS" else current_user_id,
                exact_content=resource.exact_content,
                role=resource.role,
                requires_literal_mention=resource.requires_literal_mention,
            )
        )
    return MemoryResponsePlan(
        requested_action_id=composition.requested_action_id,
        feasible_action_id=composition.feasible_action_id,
        current_goal=compact(current_goal),
        primary_response_act=composition.primary_response_act,
        evidence=tuple(evidence),
        suppressed=dict(composition.suppressed),
        assembly_order=composition.assembly_order,
    )


def memory_response_generation_messages(
    *, current_context: str, plan: MemoryResponsePlan
) -> list[dict[str, str]]:
    """Render one role-aware response request without raw session injection."""

    if not compact(current_context):
        raise ValueError("current_context must be non-empty")
    lines = [
        f"Current response goal: {plan.current_goal}",
        "Write one natural, coherent, supportive reply to the currently visible user message.",
        "You are the assistant, not the user. Personal evidence with an owner describes the "
        "person you are talking to; never narrate it as your own biography.",
        "The response plan below assigns different logical roles. Do not turn the plan into "
        "a list, do not mention internal components, and do not cite a resource merely to "
        "prove that it was provided.",
        f"Primary response act: {plan.primary_response_act}. Keep one primary task and at most "
        "one additional low-burden invitation.",
    ]
    if not plan.evidence:
        lines.append(
            "No prior memory/profile evidence is authorized. Ground the reply only in the "
            "visible current dialogue and never imply recall of an earlier session."
        )
    for item in plan.evidence:
        owner = "current user" if item.owner_id else "no personal owner"
        if item.role == "SILENT_RESPONSE_MODIFIER":
            instruction = (
                "Apply this silently to response format, burden, timing, or practical framing. "
                "Do not read the fact or preference back unless the user independently made it "
                "the topic."
            )
        elif item.role == "TENTATIVE_CONTINUITY_BRIDGE":
            instruction = (
                "Use this exact prior-user statement to make one specific, tentative continuity "
                "bridge. Mark it as past, leave room for change, and connect it to the current "
                "request; never upgrade it to a present fact, personality pattern, or cause."
            )
        elif item.role == "DECLINABLE_PAST_OPTION":
            instruction = (
                "Use the past action/result as one declinable option. Do not turn one outcome "
                "into a rule, causal claim, or guarantee."
            )
        elif item.role == "PRIMARY_SUPPORT_ACT":
            instruction = "Perform this as the one primary atomic support move."
        else:
            raise ValueError(f"unsupported response-plan role: {item.role}")
        lines.append(
            f"Plan item: evidence_id={item.evidence_id}; owner={owner}; role={item.role}; "
            f'exact content="{item.exact_content}"; instruction={instruction}'
        )
    lines.extend(
        [
            "Forbidden: inventing a person, identity, current cause, stable trait, diagnosis, "
            "future outcome, or unmentioned relationship; exposing IDs/fields/scaffolds; "
            "record-log phrasing; overriding a stop/refusal boundary.",
            "used_evidence_ids is telemetry only. It may contain only exact evidence_id values "
            "from Plan item lines that made a material contribution. The visible current "
            "message is not an evidence item. For a no-evidence plan it must be empty.",
            "Return the required structured response fields: reply, used_evidence_ids, "
            "realized_response_act.",
        ]
    )
    return [
        {"role": "system", "content": " ".join(lines)},
        {"role": "user", "content": compact(current_context)},
    ]


_INTERNAL_LABEL_RE = re.compile(r"\b(?:MP|MS|ME|RS|M0|R0)\b")
_INTERNAL_ID_RE = re.compile(r"(?:mss|mem|strat|card|span)_[0-9a-z_-]{6,}", re.IGNORECASE)
_RECORD_LOG_RE = re.compile(
    r"an earlier session recorded|i am keeping (?:that|this) as past context|"
    r"you previously said|on record|the seeker",
    re.IGNORECASE,
)


def memory_response_guard_errors(
    *, response: GeneratorResponse, plan: MemoryResponsePlan
) -> tuple[str, ...]:
    reply = compact(response.reply)
    if not reply:
        return ("EMPTY_RESPONSE",)
    errors: list[str] = []
    if _INTERNAL_LABEL_RE.search(reply) or _INTERNAL_ID_RE.search(reply):
        errors.append("INTERNAL_LABEL_OR_ID_LEAK")
    if _RECORD_LOG_RE.search(reply):
        errors.append("RECORD_LOG_PHRASING_LEAK")
    authorized = {item.evidence_id for item in plan.evidence}
    used = set(response.used_evidence_ids)
    if used - authorized:
        errors.append("TRACE_REFERENCES_UNAUTHORIZED_EVIDENCE_ID")
    required = {
        item.evidence_id
        for item in plan.evidence
        if item.component in {"MS", "ME"} and item.requires_literal_mention
    }
    if required - used:
        errors.append("REQUIRED_MEMORY_EVIDENCE_NOT_USED")
    if len(response.used_evidence_ids) != len(used):
        errors.append("DUPLICATE_EVIDENCE_ID_IN_TRACE")
    reply_words = content_words(reply)
    for item in plan.evidence:
        if item.evidence_id not in used or item.component not in {"MS", "ME"}:
            continue
        evidence_words = content_words(item.exact_content)
        if evidence_words and not (evidence_words & reply_words):
            errors.append("EVIDENCE_CLAIMED_USED_BUT_NO_WORD_TRACE_IN_REPLY")
            break
    errors.extend(speaker_attribution_guard_errors(response=response))
    return tuple(dict.fromkeys(errors))


def execute_memory_response(
    client,
    response_schema,
    messages: list[dict[str, str]],
    plan: MemoryResponsePlan,
) -> MemoryResponseExecutionResult:
    """One immutable generation attempt followed by guard or M0 fallback."""

    result, parsed = client.chat(messages, response_schema=response_schema)
    if parsed is None:
        errors = (f"NO_STRUCTURED_OUTPUT:{type(result).__name__}",)
        fallback = parse_generator_response_dict(
            {
                "reply": m0_fallback_response("concise_reflection"),
                "used_evidence_ids": [],
                "realized_response_act": "m0_fallback",
            }
        )
        return MemoryResponseExecutionResult(
            response=fallback,
            status="fell_back_to_m0",
            requested_action_id=plan.requested_action_id,
            feasible_action_id=plan.feasible_action_id,
            realized_action_id="M0+R0",
            guard_errors=errors,
        )
    response = parse_generator_response_dict(parsed.model_dump(mode="json"))
    if not plan.evidence and response.used_evidence_ids:
        response = GeneratorResponse(
            reply=response.reply,
            used_evidence_ids=(),
            realized_response_act=response.realized_response_act,
            reported_used_evidence_ids=response.used_evidence_ids,
        )
    errors = memory_response_guard_errors(response=response, plan=plan)
    if not errors:
        return MemoryResponseExecutionResult(
            response=response,
            status="clean",
            requested_action_id=plan.requested_action_id,
            feasible_action_id=plan.feasible_action_id,
            realized_action_id=plan.feasible_action_id,
            guard_errors=(),
        )
    fallback = parse_generator_response_dict(
        {
            "reply": m0_fallback_response("concise_reflection"),
            "used_evidence_ids": [],
            "realized_response_act": "m0_fallback",
        }
    )
    return MemoryResponseExecutionResult(
        response=fallback,
        status="fell_back_to_m0",
        requested_action_id=plan.requested_action_id,
        feasible_action_id=plan.feasible_action_id,
        realized_action_id="M0+R0",
        guard_errors=errors,
    )
