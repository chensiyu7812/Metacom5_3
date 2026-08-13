"""R0-foundation plus component-delta response compiler for Paper 1.

This zero-API compiler fixes the treatment confound found in the first external
RS/MS runs.  R0 is always the response foundation.  RS and personal-memory
resources may add bounded contributions, but may never replace current-turn
grounding, safety handling, or forward motion.

The module intentionally does not call a generator.  A later, content-addressed
execution phase must bind this compiler before any live response generation.
"""

from __future__ import annotations

import re

from .v1_5_component_general_v3 import ComponentGeneralPlanV3, PlannedV3Resource
from .v1_5b_policy_runtime import COMPONENTS


_SPACE = re.compile(r"\s+")


R0_FOUNDATION_LINES: tuple[str, ...] = (
    "Use the visible current dialogue as the response foundation.",
    "First address the user's present message accurately and empathetically.",
    "Respect stop, refusal, safety, and stated-burden boundaries before any optional resource.",
    "Produce a complete natural reply even when every optional resource is omitted.",
    "When appropriate, preserve forward motion with at most one low-burden question, choice, or next step.",
    "Do not invent identity, relationship, diagnosis, current cause, stable trait, or future outcome.",
)


def _compact(value: object) -> str:
    return _SPACE.sub(" ", str(value or "")).strip()


def r0_foundation_contract_v4() -> tuple[str, ...]:
    """Return the invariant base contract shared by every factorial arm."""

    return R0_FOUNDATION_LINES


def _resource_delta(resource: PlannedV3Resource) -> str:
    common = (
        f"evidence_id={resource.evidence_id}; component={resource.component}; "
        f"owner={resource.owner_id or 'non-personal'}; time_status={resource.time_status}; "
        f"meaning={_compact(resource.meaning_cue)}; "
        f"allowed_delta={_compact(resource.allowed_response_change)}; "
        f"forbidden_inference={_compact(resource.forbidden_inference)}; "
        f"source_for_audit_only={_compact(resource.exact_source)}"
    )
    if resource.component == "RS":
        return (
            "Optional RS strategy delta: keep the complete R0 foundation and add or sharpen "
            "one strategy move only when it improves the present reply. A restatement is a "
            "local move, never the whole reply, and may not remove a useful acknowledgement "
            f"or forward move. {common}"
        )
    if resource.component == "MS":
        return (
            "Optional MS continuity delta: decide USE, ASK, or IGNORE. USE only when the "
            "strictly past user-owned fact is specific, relevant, non-conflicting, and adds "
            "information not already available in the current dialogue. ASK when continuity "
            "is materially uncertain and a tentative check is useful. IGNORE otherwise. "
            "USE/ASK may change the reply only through that supported past information; safe "
            f"non-use must not earn memory Function. {common}"
        )
    if resource.component == "MP":
        return (
            "Optional MP profile delta: silently adjust wording, burden, timing, or format only "
            f"when the supported preference constrains this reply; never recite it. {common}"
        )
    if resource.component == "ME":
        return (
            "Optional ME experience delta: offer a supported past action-result only as one "
            f"declinable option; never promote it to a rule or guarantee. {common}"
        )
    raise ValueError(f"unsupported component: {resource.component}")


def response_generation_messages_v4(
    *,
    current_context: str,
    current_goal: str,
    plan: ComponentGeneralPlanV3,
    excluded_components: frozenset[str] = frozenset(),
) -> list[dict[str, str]]:
    """Compile the deconfounded R0 + optional-delta generation treatment."""

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
    lines = [
        f"Current response goal: {_compact(current_goal)}",
        *R0_FOUNDATION_LINES,
        "Optional resources are bounded deltas to R0, not alternative response backbones.",
        "Apply contributions in this order: current-turn and safety foundation; supported "
        "personal-memory delta; strategy delta; one coherent forward move or closure.",
        "Do not add generic warmth, questions, advice, or length merely because a resource is present; "
        "those base response choices are governed by the identical R0 foundation in every arm.",
    ]
    if not resources:
        lines.append("No optional delta is authorized; execute the R0 foundation only.")
    else:
        lines.extend(_resource_delta(resource) for resource in resources)
    for pair in plan.pair_plans:
        left, right = pair.pair.split("-")
        if left in excluded_components or right in excluded_components:
            continue
        lines.append(
            f"Delta interaction: pair={pair.pair}; relation={pair.relation}; "
            f"instruction={pair.synthesis_directive}. Never duplicate content or erase R0."
        )
    lines.extend(
        (
            "Never expose component labels, evidence IDs, source records, or planning scaffolds in the reply.",
            "used_evidence_ids is telemetry only: include an authorized ID only when its specific "
            "information materially changed the reply. Safe non-use returns no ID.",
            "Return structured fields: reply, used_evidence_ids, realized_response_act.",
        )
    )
    return [
        {"role": "system", "content": " ".join(lines)},
        {"role": "user", "content": _compact(current_context)},
    ]

