"""Outcome-blind component-general V3 planning primitives.

This module preserves the complete four-bit requested action.  It may project a
requested bit OFF only when the corresponding candidate is absent, structurally
invalid, or blocked by an explicit hard safety/boundary veto.  Pair relations
guide synthesis and later interaction analysis; they never pre-emptively erase
an otherwise legal factorial treatment.

No response outcome, future turn, summary, event graph, QA evidence, reviewer
label, or generator telemetry is read here.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, Mapping

from .v1_5b_policy_runtime import (
    COMPONENTS,
    Component,
    action_component_bits,
    compile_component_bits,
)


PairRelation = Literal[
    "COMPLEMENTARY",
    "REDUNDANT",
    "CONFLICT",
    "UNKNOWN",
]
ResourceRole = Literal[
    "SILENT_PROFILE_MODIFIER",
    "TENTATIVE_CONTINUITY_CUE",
    "DECLINABLE_PAST_OPTION",
    "PRIMARY_ATOMIC_SUPPORT_ACT",
]
StructuralFailure = Literal[
    "CANDIDATE_ABSENT",
    "OWNER_INVALID",
    "TIME_INVALID",
    "VERSION_INVALID",
    "COMPILER_INVALID",
    "HARD_SAFETY_OR_BOUNDARY_VETO",
]


PAIR_KEYS: tuple[str, ...] = (
    "MP-MS",
    "MP-ME",
    "MP-RS",
    "MS-ME",
    "MS-RS",
    "ME-RS",
)
_PAIR_COMPONENTS = {
    pair: tuple(pair.split("-"))
    for pair in PAIR_KEYS
}
_ROLE: Mapping[str, ResourceRole] = {
    "MP": "SILENT_PROFILE_MODIFIER",
    "MS": "TENTATIVE_CONTINUITY_CUE",
    "ME": "DECLINABLE_PAST_OPTION",
    "RS": "PRIMARY_ATOMIC_SUPPORT_ACT",
}
_RELATION_DIRECTIVE: Mapping[PairRelation, str] = {
    "COMPLEMENTARY": "combine both cues around the same primary response act",
    "REDUNDANT": "merge overlapping meaning without repeating it; retain both planned bits for measurement",
    "CONFLICT": "do not assert either cue as settled; acknowledge uncertainty or present a bounded choice while retaining both planned bits",
    "UNKNOWN": "keep both cues tentative and independently bounded; retain both planned bits for measurement",
}


@dataclass(frozen=True)
class V3Candidate:
    component: Component
    evidence_id: str
    meaning_cue: str
    exact_source: str
    owner_id: str | None
    time_status: str
    allowed_response_change: str
    forbidden_inference: str
    burden_units: int = 1
    structurally_eligible: bool = True
    structural_failure: StructuralFailure | None = None

    def __post_init__(self) -> None:
        if self.component not in COMPONENTS:
            raise ValueError(f"unknown component: {self.component}")
        if not self.evidence_id.strip() or not self.meaning_cue.strip():
            raise ValueError("evidence_id and meaning_cue must be non-empty")
        if self.burden_units < 0:
            raise ValueError("burden_units must be nonnegative")
        if self.structurally_eligible and self.structural_failure is not None:
            raise ValueError("eligible candidate cannot have a structural failure")
        if not self.structurally_eligible and self.structural_failure is None:
            raise ValueError("ineligible candidate requires an allowed structural failure")
        if self.component in {"MP", "MS", "ME"} and not self.owner_id:
            raise ValueError("personal candidates require owner_id")


@dataclass(frozen=True)
class PlannedV3Resource:
    component: Component
    role: ResourceRole
    evidence_id: str
    owner_id: str | None
    time_status: str
    meaning_cue: str
    exact_source: str
    allowed_response_change: str
    forbidden_inference: str
    burden_units: int
    literal_mention_required: bool = False
    lexical_overlap_required: bool = False


@dataclass(frozen=True)
class PairPlan:
    pair: str
    relation: PairRelation
    synthesis_directive: str
    suppresses_component: bool = False


@dataclass(frozen=True)
class ActionAccountingV3:
    requested_action_id: str
    structurally_eligible_action_id: str
    jointly_planned_action_id: str
    requested: Mapping[Component, bool]
    structurally_eligible: Mapping[Component, bool]
    jointly_planned: Mapping[Component, bool]
    generator_claimed: Mapping[Component, bool]
    offline_verified_functional: Mapping[Component, bool]

    def with_generator_claimed(
        self, claimed: Mapping[str, bool]
    ) -> "ActionAccountingV3":
        bits = _complete_subset(claimed, self.jointly_planned, "generator claim")
        return replace(self, generator_claimed=bits)

    def with_offline_verified_functional(
        self, verified: Mapping[str, bool]
    ) -> "ActionAccountingV3":
        # Offline source-aware verification does not need to agree with the
        # generator's self-report, but it cannot add an unplanned component.
        bits = _complete_subset(verified, self.jointly_planned, "offline verification")
        return replace(self, offline_verified_functional=bits)


@dataclass(frozen=True)
class ComponentGeneralPlanV3:
    requested_action_id: str
    structurally_eligible_action_id: str
    jointly_planned_action_id: str
    primary_response_act: Literal["RS", "R0"]
    resources: tuple[PlannedV3Resource, ...]
    pair_plans: tuple[PairPlan, ...]
    projection_reasons: Mapping[Component, str]
    accounting: ActionAccountingV3
    low_burden_invitation_max: int = 1


def _false_bits() -> dict[Component, bool]:
    return {component: False for component in COMPONENTS}


def _complete_subset(
    partial: Mapping[str, bool],
    ceiling: Mapping[Component, bool],
    layer: str,
) -> dict[Component, bool]:
    unknown = set(partial) - set(COMPONENTS)
    if unknown:
        raise ValueError(f"unknown {layer} component(s): {sorted(unknown)}")
    bits = {
        component: bool(partial.get(component, False))
        for component in COMPONENTS
    }
    added = [component for component in COMPONENTS if bits[component] and not ceiling[component]]
    if added:
        raise ValueError(f"{layer} cannot add unplanned component(s): {added}")
    return bits


def normalize_pair_relations(
    relations: Mapping[str, PairRelation] | None,
) -> dict[str, PairRelation]:
    supplied = dict(relations or {})
    unknown = set(supplied) - set(PAIR_KEYS)
    if unknown:
        raise ValueError(f"unknown component pair(s): {sorted(unknown)}")
    return {
        pair: supplied.get(pair, "UNKNOWN")
        for pair in PAIR_KEYS
    }


def build_component_general_plan_v3(
    *,
    requested_action_id: str,
    current_user_id: str,
    candidates: Mapping[str, V3Candidate | None],
    pair_relations: Mapping[str, PairRelation] | None = None,
) -> ComponentGeneralPlanV3:
    """Build a full factorial plan without outcome-based bit suppression."""

    if not current_user_id.strip():
        raise ValueError("current_user_id must be non-empty")
    requested = action_component_bits(requested_action_id)
    unknown_candidates = set(candidates) - set(COMPONENTS)
    if unknown_candidates:
        raise ValueError(f"unknown candidate component(s): {sorted(unknown_candidates)}")

    eligible = dict(requested)
    projection_reasons: dict[Component, str] = {}
    accepted: dict[Component, V3Candidate] = {}
    for component in COMPONENTS:
        if not requested[component]:
            eligible[component] = False
            continue
        candidate = candidates.get(component)
        if candidate is None:
            eligible[component] = False
            projection_reasons[component] = "CANDIDATE_ABSENT"
            continue
        if candidate.component != component:
            raise ValueError(f"candidate key/component mismatch for {component}")
        if component in {"MP", "MS", "ME"} and candidate.owner_id != current_user_id:
            eligible[component] = False
            projection_reasons[component] = "OWNER_INVALID"
            continue
        if not candidate.structurally_eligible:
            eligible[component] = False
            projection_reasons[component] = str(candidate.structural_failure)
            continue
        accepted[component] = candidate

    # No separate outcome-blind capacity projector is allowed to remove a bit.
    # Jointly planned therefore equals structurally eligible by construction.
    jointly_planned = dict(eligible)
    relations = normalize_pair_relations(pair_relations)
    pair_plans = []
    for pair in PAIR_KEYS:
        left, right = _PAIR_COMPONENTS[pair]
        if jointly_planned[left] and jointly_planned[right]:
            relation = relations[pair]
            pair_plans.append(
                PairPlan(
                    pair=pair,
                    relation=relation,
                    synthesis_directive=_RELATION_DIRECTIVE[relation],
                )
            )

    resources = tuple(
        PlannedV3Resource(
            component=component,
            role=_ROLE[component],
            evidence_id=accepted[component].evidence_id,
            owner_id=accepted[component].owner_id,
            time_status=accepted[component].time_status,
            meaning_cue=accepted[component].meaning_cue,
            exact_source=accepted[component].exact_source,
            allowed_response_change=accepted[component].allowed_response_change,
            forbidden_inference=accepted[component].forbidden_inference,
            burden_units=accepted[component].burden_units,
        )
        for component in COMPONENTS
        if jointly_planned[component]
    )
    eligible_action = compile_component_bits(eligible)
    planned_action = compile_component_bits(jointly_planned)
    accounting = ActionAccountingV3(
        requested_action_id=requested_action_id,
        structurally_eligible_action_id=eligible_action,
        jointly_planned_action_id=planned_action,
        requested=dict(requested),
        structurally_eligible=dict(eligible),
        jointly_planned=dict(jointly_planned),
        generator_claimed=_false_bits(),
        offline_verified_functional=_false_bits(),
    )
    return ComponentGeneralPlanV3(
        requested_action_id=requested_action_id,
        structurally_eligible_action_id=eligible_action,
        jointly_planned_action_id=planned_action,
        primary_response_act="RS" if jointly_planned["RS"] else "R0",
        resources=resources,
        pair_plans=tuple(pair_plans),
        projection_reasons=projection_reasons,
        accounting=accounting,
    )


def all_sixteen_action_ids() -> tuple[str, ...]:
    """Return all canonical four-bit actions in stable binary order."""

    actions = []
    for mask in range(16):
        bits = {
            component: bool(mask & (1 << index))
            for index, component in enumerate(COMPONENTS)
        }
        actions.append(compile_component_bits(bits))
    if len(set(actions)) != 16:
        raise AssertionError("canonical action compiler did not produce 16 unique actions")
    return tuple(actions)
