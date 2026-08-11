"""Meaning-absorption prompt, guard, and execution accounting for V3.

The generator receives bounded meanings and logical roles rather than text it
must splice into the reply.  Generator telemetry is retained as telemetry; it
never proves offline source-aware function.  Safe non-use keeps the reply.
Only machine-detectable personal-resource contamination permits one retry with
MP/MS/ME removed while an independently safe RS remains available.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Callable, Mapping, Sequence

from .v1_5_component_general_v3 import (
    ActionAccountingV3,
    ComponentGeneralPlanV3,
    PlannedV3Resource,
)
from .v1_5_v5_3_typed_response_program import (
    GeneratorResponse,
    m0_fallback_response,
    parse_generator_response_dict,
    speaker_attribution_guard_errors,
)
from .v1_5b_policy_runtime import COMPONENTS, compile_component_bits


_SPACE = re.compile(r"\s+")
_INTERNAL_LABEL_RE = re.compile(r"\b(?:MP|MS|ME|RS|M0|R0)\b")
_INTERNAL_ID_RE = re.compile(
    r"(?:profile|memory|session|event|candidate|scaffold|span|card)_[0-9a-z_-]{4,}",
    re.IGNORECASE,
)
_RECORD_LOG_RE = re.compile(
    r"an earlier session recorded|according to (?:your )?(?:profile|memory record)|"
    r"the retrieved (?:memory|candidate)|used_evidence_ids|internal scaffold",
    re.IGNORECASE,
)
_PERSONAL_COMPONENTS = frozenset({"MP", "MS", "ME"})
_TRACE_ONLY_ERRORS = frozenset(
    {
        "TRACE_REFERENCES_UNAUTHORIZED_EVIDENCE_ID",
        "DUPLICATE_EVIDENCE_ID_IN_TRACE",
    }
)
_PLAN_FIELD_MARKER_RE = re.compile(
    r"\b(?:support_phase|immediate_goal|candidate_increment|resource_disposition|"
    r"entity_link_status|allowed_change|forbidden_inference)\s*=",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ResponseExecutionV3:
    response: GeneratorResponse
    status: str
    accounting: ActionAccountingV3
    guard_errors: tuple[str, ...]
    raw_results: tuple[Any, ...]
    calls_made: int
    regeneration_reason: str | None = None


def _compact(value: object) -> str:
    return _SPACE.sub(" ", str(value or "")).strip()


def _resource_instruction(resource: PlannedV3Resource) -> str:
    if resource.component == "MP":
        return (
            "Use this only as a silent constraint on wording, feasibility, burden, timing, "
            "or practical framing. Do not recite the profile fact and do not infer a trait."
        )
    if resource.component == "MS":
        return (
            "Treat this as a strictly past, user-owned continuity cue. If it naturally helps, "
            "use its meaning tentatively and leave room for change; never copy the user's "
            "first-person source or upgrade the past into the present."
        )
    if resource.component == "ME":
        return (
            "Treat this past action-result as a tentative, declinable option. Do not turn one "
            "outcome into a rule, causal claim, recommendation guarantee, or second primary task."
        )
    if resource.component == "RS":
        return "Perform this as the reply's one primary atomic support act."
    raise ValueError(f"unsupported component: {resource.component}")


def response_generation_messages_v3(
    *,
    current_context: str,
    current_goal: str,
    plan: ComponentGeneralPlanV3,
    excluded_components: frozenset[str] = frozenset(),
) -> list[dict[str, str]]:
    """Render one coherent response program without literal-use obligations."""

    if not _compact(current_context) or not _compact(current_goal):
        raise ValueError("current_context and current_goal must be non-empty")
    unknown = set(excluded_components) - set(COMPONENTS)
    if unknown:
        raise ValueError(f"unknown excluded component(s): {sorted(unknown)}")
    resources = tuple(
        resource
        for resource in plan.resources
        if resource.component not in excluded_components
    )
    rs_available = any(resource.component == "RS" for resource in resources)
    primary_act = "RS" if rs_available else "R0"
    lines = [
        f"Current response goal: {_compact(current_goal)}",
        "Write one natural, coherent, supportive reply to the visible current dialogue.",
        f"Use exactly one primary response act ({primary_act}) and at most one low-burden invitation.",
        "Several authorized resources may jointly support that one act. Do not split the reply "
        "into component sections, and do not omit a resource merely because another memory "
        "resource is also present.",
        "Use a resource only through its meaning and permitted response change. Exact source "
        "text is provenance for interpretation, never text that must appear. Literal mention "
        "and lexical overlap are not required.",
        "If a cue cannot improve the current reply naturally, leave it unused and still produce "
        "a safe current-context-grounded reply. Do not insert generic filler to prove non-use.",
    ]
    if not resources:
        lines.append(
            "No personal resource or strategy card is authorized for this attempt; use only "
            "the visible dialogue and a supportive R0 act."
        )
    for resource in resources:
        owner = resource.owner_id or "non-personal strategy resource"
        lines.append(
            "Authorized meaning cue: "
            f"evidence_id={resource.evidence_id}; component={resource.component}; "
            f"owner={owner}; time_status={resource.time_status}; role={resource.role}; "
            f"meaning={resource.meaning_cue}; allowed_change={resource.allowed_response_change}; "
            f"forbidden_inference={resource.forbidden_inference}; "
            f"source_for_audit_only={resource.exact_source}; instruction={_resource_instruction(resource)}"
        )
    for pair in plan.pair_plans:
        left, right = pair.pair.split("-")
        if left in excluded_components or right in excluded_components:
            continue
        lines.append(
            f"Pair synthesis: pair={pair.pair}; relation={pair.relation}; "
            f"instruction={pair.synthesis_directive}. This relation does not authorize dropping a bit."
        )
    lines.extend(
        [
            "Never invent identity, relationship, diagnosis, current cause, stable trait, or "
            "future outcome; never expose evidence IDs, component labels, source records, or scaffolds; "
            "never override a stop/refusal boundary.",
            "used_evidence_ids is telemetry only. Include an authorized evidence_id only if its "
            "meaning materially changed the reply. It is valid to return fewer IDs than were planned.",
            "Return structured fields: reply, used_evidence_ids, realized_response_act.",
        ]
    )
    return [
        {"role": "system", "content": " ".join(lines)},
        {"role": "user", "content": _compact(current_context)},
    ]


def response_guard_errors_v3(
    *, response: GeneratorResponse, plan: ComponentGeneralPlanV3
) -> tuple[str, ...]:
    """Check structural contamination only; never infer semantic function."""

    reply = _compact(response.reply)
    if not reply:
        return ("EMPTY_RESPONSE",)
    errors: list[str] = []
    if _INTERNAL_LABEL_RE.search(reply) or _INTERNAL_ID_RE.search(reply):
        errors.append("INTERNAL_LABEL_OR_ID_LEAK")
    if _RECORD_LOG_RE.search(reply):
        errors.append("INTERNAL_RESOURCE_OR_SCAFFOLD_EXPOSURE")
    if _PLAN_FIELD_MARKER_RE.search(reply):
        errors.append("PLAN_SCAFFOLD_EXPOSURE")
    # Candidate-specific plans are written as instructions, not user-facing
    # prose.  A model can occasionally emit one instruction verbatim while
    # still producing schema-valid JSON.  Detect a substantial exact prefix
    # in either direction without requiring ordinary semantic overlap.
    reply_folded = reply.casefold()
    if len(reply_folded) >= 40 and any(
        (field := _compact(value).casefold())
        and (field.startswith(reply_folded) or reply_folded.startswith(field))
        for resource in plan.resources
        for value in (
            resource.meaning_cue,
            resource.allowed_response_change,
            resource.forbidden_inference,
        )
    ):
        errors.append("PLAN_SCAFFOLD_EXPOSURE")
    authorized = {resource.evidence_id for resource in plan.resources}
    used = tuple(response.used_evidence_ids)
    if set(used) - authorized:
        errors.append("TRACE_REFERENCES_UNAUTHORIZED_EVIDENCE_ID")
    if len(set(used)) != len(used):
        errors.append("DUPLICATE_EVIDENCE_ID_IN_TRACE")
    errors.extend(speaker_attribution_guard_errors(response=response))
    return tuple(dict.fromkeys(errors))


def _parse_response(parsed: Any) -> GeneratorResponse:
    raw: Mapping[str, object]
    if hasattr(parsed, "model_dump"):
        raw = parsed.model_dump(mode="json")
    elif isinstance(parsed, Mapping):
        raw = parsed
    else:
        raise TypeError("structured response must be a mapping or expose model_dump")
    return parse_generator_response_dict(raw)


def _claimed_accounting(
    plan: ComponentGeneralPlanV3, response: GeneratorResponse
) -> ActionAccountingV3:
    evidence_to_component = {
        resource.evidence_id: resource.component
        for resource in plan.resources
    }
    claimed = {component: False for component in COMPONENTS}
    for evidence_id in set(response.used_evidence_ids):
        component = evidence_to_component.get(evidence_id)
        if component is not None:
            claimed[component] = True
    return plan.accounting.with_generator_claimed(claimed)


def _shared_transport_fallback() -> GeneratorResponse:
    return parse_generator_response_dict(
        {
            "reply": m0_fallback_response("concise_reflection"),
            "used_evidence_ids": [],
            "realized_response_act": "transport_fallback",
        }
    )


def _chat_once(client: Any, response_schema: Any, messages: Sequence[Mapping[str, str]]):
    return client.chat(list(messages), response_schema=response_schema)


def execute_response_program_v3(
    *,
    client: Any,
    response_schema: Any,
    current_context: str,
    current_goal: str,
    plan: ComponentGeneralPlanV3,
    raw_persist: Callable[[int, Any], None],
) -> ResponseExecutionV3:
    """Run once, with one personal-resource-free retry only for contamination."""

    raw_results: list[Any] = []
    messages = response_generation_messages_v3(
        current_context=current_context,
        current_goal=current_goal,
        plan=plan,
    )
    raw, parsed = _chat_once(client, response_schema, messages)
    raw_results.append(raw)
    raw_persist(1, raw)
    if parsed is None:
        fallback = _shared_transport_fallback()
        return ResponseExecutionV3(
            response=fallback,
            status="transport_or_schema_fallback",
            accounting=_claimed_accounting(plan, fallback),
            guard_errors=(f"NO_STRUCTURED_OUTPUT:{type(raw).__name__}",),
            raw_results=tuple(raw_results),
            calls_made=1,
        )
    response = _parse_response(parsed)
    errors = response_guard_errors_v3(response=response, plan=plan)
    # Evidence IDs are untrusted generator telemetry.  Bad telemetry must be
    # sanitized, but it is not evidence that the natural-language reply is
    # contaminated and must never destroy an otherwise safe reply.
    hard_contamination = any(error not in _TRACE_ONLY_ERRORS for error in errors)
    if not hard_contamination:
        if any(error in _TRACE_ONLY_ERRORS for error in errors):
            authorized = {resource.evidence_id for resource in plan.resources}
            response = GeneratorResponse(
                reply=response.reply,
                used_evidence_ids=tuple(
                    evidence_id
                    for evidence_id in dict.fromkeys(response.used_evidence_ids)
                    if evidence_id in authorized
                ),
                realized_response_act=response.realized_response_act,
                reported_used_evidence_ids=response.reported_used_evidence_ids,
            )
        accounting = _claimed_accounting(plan, response)
        any_planned_personal = any(
            plan.accounting.jointly_planned[component]
            for component in _PERSONAL_COMPONENTS
        )
        any_claimed_personal = any(
            accounting.generator_claimed[component]
            for component in _PERSONAL_COMPONENTS
        )
        trace_sanitized = any(error in _TRACE_ONLY_ERRORS for error in errors)
        if any_planned_personal and not any_claimed_personal:
            status = (
                "clean_safe_personal_nonuse_trace_sanitized"
                if trace_sanitized
                else "clean_safe_personal_nonuse"
            )
        else:
            status = "clean_trace_sanitized" if trace_sanitized else "clean"
        return ResponseExecutionV3(
            response=response,
            status=status,
            accounting=accounting,
            guard_errors=errors,
            raw_results=tuple(raw_results),
            calls_made=1,
        )

    # Hard contamination recovery removes all personal resources, not RS.  It
    # does not rewrite the original requested/eligible/planned accounting.
    retry_messages = response_generation_messages_v3(
        current_context=current_context,
        current_goal=current_goal,
        plan=plan,
        excluded_components=_PERSONAL_COMPONENTS,
    )
    raw_retry, parsed_retry = _chat_once(client, response_schema, retry_messages)
    raw_results.append(raw_retry)
    raw_persist(2, raw_retry)
    if parsed_retry is not None:
        retry_response = _parse_response(parsed_retry)
        retry_errors = response_guard_errors_v3(response=retry_response, plan=plan)
        retry_used = tuple(
            evidence_id
            for evidence_id in retry_response.used_evidence_ids
            if any(
                resource.evidence_id == evidence_id and resource.component == "RS"
                for resource in plan.resources
            )
        )
        retry_response = GeneratorResponse(
            reply=retry_response.reply,
            used_evidence_ids=retry_used,
            realized_response_act=retry_response.realized_response_act,
            reported_used_evidence_ids=retry_response.reported_used_evidence_ids,
        )
        retry_errors = response_guard_errors_v3(response=retry_response, plan=plan)
        if not retry_errors:
            return ResponseExecutionV3(
                response=retry_response,
                status="clean_after_personal_resource_removal",
                accounting=_claimed_accounting(plan, retry_response),
                guard_errors=errors,
                raw_results=tuple(raw_results),
                calls_made=2,
                regeneration_reason="PERSONAL_RESOURCE_CONTAMINATION",
            )

    fallback = _shared_transport_fallback()
    return ResponseExecutionV3(
        response=fallback,
        status="contamination_retry_failed_shared_fallback",
        accounting=_claimed_accounting(plan, fallback),
        guard_errors=errors,
        raw_results=tuple(raw_results),
        calls_made=2,
        regeneration_reason="PERSONAL_RESOURCE_CONTAMINATION",
    )


def claimed_action_id(execution: ResponseExecutionV3) -> str:
    return compile_component_bits(execution.accounting.generator_claimed)
