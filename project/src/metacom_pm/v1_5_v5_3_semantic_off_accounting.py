"""Deterministic semantic-coverage and OFF-reason accounting for V5.3.

This module does not infer semantics.  It makes every component decision
auditable after candidate discovery and a separately qualified semantic/value
head have produced their decisions.  In particular, it prevents candidate
absence, semantic abstention, a failed head, and cost projection from being
collapsed into one flattering global OFF rate.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Iterable


COMPONENTS = ("MP", "MS", "ME", "RS")


class SemanticStatus(str, Enum):
    OPEN_ELIGIBLE = "OPEN_ELIGIBLE"
    DO_NOT_OPEN_REDUNDANT = "DO_NOT_OPEN_REDUNDANT"
    DO_NOT_OPEN_NOT_USEFUL = "DO_NOT_OPEN_NOT_USEFUL"
    ABSTAIN_OUT_OF_SUPPORT = "ABSTAIN_OUT_OF_SUPPORT"
    ABSTAIN_LOW_CONFIDENCE = "ABSTAIN_LOW_CONFIDENCE"
    NOT_REACHED = "NOT_REACHED"


class ValueStatus(str, Enum):
    ON = "ON"
    OFF = "OFF"
    EITHER = "EITHER"
    UNRESOLVED = "UNRESOLVED"
    NOT_REACHED = "NOT_REACHED"


class OffReason(str, Enum):
    CANDIDATE_ABSENT = "CANDIDATE_ABSENT"
    STRUCTURAL_INVALID_OWNER_TIME_VERSION = "STRUCTURAL_INVALID_OWNER_TIME_VERSION"
    SAFETY_HARD_OFF = "SAFETY_HARD_OFF"
    SEMANTIC_DO_NOT_OPEN_REDUNDANT = "SEMANTIC_DO_NOT_OPEN_REDUNDANT"
    SEMANTIC_DO_NOT_OPEN_NOT_USEFUL = "SEMANTIC_DO_NOT_OPEN_NOT_USEFUL"
    SEMANTIC_ABSTAIN_OUT_OF_SUPPORT = "SEMANTIC_ABSTAIN_OUT_OF_SUPPORT"
    SEMANTIC_ABSTAIN_LOW_CONFIDENCE = "SEMANTIC_ABSTAIN_LOW_CONFIDENCE"
    HEAD_NOT_QUALIFIED = "HEAD_NOT_QUALIFIED"
    VALUE_PREDICTED_OFF = "VALUE_PREDICTED_OFF"
    VALUE_UNRESOLVED = "VALUE_UNRESOLVED"
    JOINT_PROJECTION_COST_FRONTIER_OFF = "JOINT_PROJECTION_COST_FRONTIER_OFF"
    ON = "ON"


@dataclass(frozen=True)
class ComponentDecisionTrace:
    state_id: str
    component: str
    candidate_present: bool
    structurally_valid: bool
    safety_hard_off: bool
    semantic_status: SemanticStatus
    head_qualified: bool
    value_status: ValueStatus
    projected_on: bool
    requested_on: bool

    def __post_init__(self) -> None:
        if self.component not in COMPONENTS:
            raise ValueError(f"unsupported component: {self.component}")
        if not self.state_id:
            raise ValueError("state_id is required")
        if not self.candidate_present and self.structurally_valid:
            raise ValueError("an absent candidate cannot be structurally valid")
        if self.requested_on and not self.projected_on:
            raise ValueError("requested ON requires projected_on")
        if self.projected_on and (
            not self.candidate_present
            or not self.structurally_valid
            or self.safety_hard_off
            or self.semantic_status is not SemanticStatus.OPEN_ELIGIBLE
            or not self.head_qualified
            or self.value_status not in {ValueStatus.ON, ValueStatus.EITHER}
        ):
            raise ValueError("projected ON violates a preceding gate")

    @property
    def off_reason(self) -> OffReason:
        if not self.candidate_present:
            return OffReason.CANDIDATE_ABSENT
        if not self.structurally_valid:
            return OffReason.STRUCTURAL_INVALID_OWNER_TIME_VERSION
        if self.safety_hard_off:
            return OffReason.SAFETY_HARD_OFF
        semantic_reason = {
            SemanticStatus.DO_NOT_OPEN_REDUNDANT: OffReason.SEMANTIC_DO_NOT_OPEN_REDUNDANT,
            SemanticStatus.DO_NOT_OPEN_NOT_USEFUL: OffReason.SEMANTIC_DO_NOT_OPEN_NOT_USEFUL,
            SemanticStatus.ABSTAIN_OUT_OF_SUPPORT: OffReason.SEMANTIC_ABSTAIN_OUT_OF_SUPPORT,
            SemanticStatus.ABSTAIN_LOW_CONFIDENCE: OffReason.SEMANTIC_ABSTAIN_LOW_CONFIDENCE,
        }.get(self.semantic_status)
        if semantic_reason is not None:
            return semantic_reason
        if self.semantic_status is SemanticStatus.NOT_REACHED:
            raise ValueError("semantic gate was not reached despite a legal candidate")
        if not self.head_qualified:
            return OffReason.HEAD_NOT_QUALIFIED
        if self.value_status is ValueStatus.OFF:
            return OffReason.VALUE_PREDICTED_OFF
        if self.value_status in {ValueStatus.UNRESOLVED, ValueStatus.NOT_REACHED}:
            return OffReason.VALUE_UNRESOLVED
        if not self.projected_on or not self.requested_on:
            return OffReason.JOINT_PROJECTION_COST_FRONTIER_OFF
        return OffReason.ON


def action_id(on_components: Iterable[str]) -> str:
    enabled = set(on_components)
    unknown = enabled - set(COMPONENTS)
    if unknown:
        raise ValueError(f"unsupported components: {sorted(unknown)}")
    memory = {
        frozenset(): "M0",
        frozenset({"MP"}): "MP",
        frozenset({"MS"}): "MS",
        frozenset({"ME"}): "ME",
        frozenset({"MP", "MS"}): "MPMS",
        frozenset({"MP", "ME"}): "MPE",
        frozenset({"MS", "ME"}): "MSE",
        frozenset({"MP", "MS", "ME"}): "MPMSME",
    }[frozenset(enabled & {"MP", "MS", "ME"})]
    response = "RS" if "RS" in enabled else "R0"
    return f"{memory}+{response}"


def summarize_decision_traces(rows: Iterable[ComponentDecisionTrace]) -> dict[str, object]:
    traces = list(rows)
    by_component: dict[str, list[ComponentDecisionTrace]] = defaultdict(list)
    by_state: dict[str, list[ComponentDecisionTrace]] = defaultdict(list)
    for row in traces:
        by_component[row.component].append(row)
        by_state[row.state_id].append(row)

    components: dict[str, object] = {}
    for component in COMPONENTS:
        values = by_component.get(component, [])
        total = len(values)
        legal = [row for row in values if row.candidate_present and row.structurally_valid]
        semantic_resolved = [
            row for row in legal if row.semantic_status in {
                SemanticStatus.OPEN_ELIGIBLE,
                SemanticStatus.DO_NOT_OPEN_REDUNDANT,
                SemanticStatus.DO_NOT_OPEN_NOT_USEFUL,
            }
        ]
        requested = [row for row in values if row.requested_on]
        components[component] = {
            "states": total,
            "candidate_available": len(legal),
            "candidate_availability_rate": len(legal) / total if total else None,
            "structural_off_rate": (total - len(legal)) / total if total else None,
            "semantic_resolution_coverage": (
                len(semantic_resolved) / len(legal) if legal else None
            ),
            "conditional_on_rate": len(requested) / len(legal) if legal else None,
            "policy_on_rate": len(requested) / total if total else None,
            "off_reason_counts": dict(Counter(row.off_reason.value for row in values)),
        }

    actions: Counter[str] = Counter()
    for state_id, values in by_state.items():
        if len(values) != 4 or {row.component for row in values} != set(COMPONENTS):
            raise ValueError(f"state {state_id} must have exactly one trace per component")
        actions[action_id(row.component for row in values if row.requested_on)] += 1
    states = len(by_state)
    return {
        "states": states,
        "components": components,
        "action_counts": dict(actions),
        "always_off_alias_rate": actions.get("M0+R0", 0) / states if states else None,
    }
