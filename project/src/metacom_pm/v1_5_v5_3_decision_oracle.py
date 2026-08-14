"""Predeclared component-call and 16-action oracle-set definitions for V5.3."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping

from .contracts import ALL_ACTION_IDS, parse_action_id


QUALITY_EQUIVALENCE_MARGIN = 0.10


class ComponentCallLabel(str, Enum):
    ON_ONLY = "ON_ONLY"
    OFF_ONLY = "OFF_ONLY"
    EITHER = "EITHER"
    UNRESOLVED = "UNRESOLVED"


class ComponentRiskLabel(str, Enum):
    SAFE = "SAFE"
    UNSAFE = "UNSAFE"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True)
class ComponentCallResolution:
    label: ComponentCallLabel
    reason: str
    quality_uplift: float | None
    quality_equivalence_margin: float = QUALITY_EQUIVALENCE_MARGIN


def resolve_component_call(
    *, quality_uplift: float | None, execution_valid: bool,
    resource_attributable_material_risk: bool | None = None,
    measurement_resolved: bool = True,
    unresolved_reason: str | None = None,
    margin: float = QUALITY_EQUIVALENCE_MARGIN,
) -> ComponentCallResolution:
    """Resolve a diagnostic call label without manufacturing negative gold."""

    if margin <= 0:
        raise ValueError("quality equivalence margin must be positive")
    if not measurement_resolved or quality_uplift is None:
        return ComponentCallResolution(
            ComponentCallLabel.UNRESOLVED,
            unresolved_reason or "quality measurement is unresolved",
            quality_uplift,
            margin,
        )
    if not execution_valid:
        return ComponentCallResolution(
            ComponentCallLabel.UNRESOLVED,
            unresolved_reason or "requested resource was not validly executed",
            quality_uplift,
            margin,
        )
    if quality_uplift > margin:
        label = ComponentCallLabel.ON_ONLY
        reason = "quality uplift exceeds the positive indifference boundary"
    elif quality_uplift < -margin:
        label = ComponentCallLabel.OFF_ONLY
        reason = "quality uplift is below the negative indifference boundary"
    else:
        label = ComponentCallLabel.EITHER
        reason = "ON and OFF are quality-equivalent within the frozen margin"
    return ComponentCallResolution(label, reason, quality_uplift, margin)


def resolve_component_risk(
    resource_attributable_material_risk: bool | None,
) -> ComponentRiskLabel:
    if resource_attributable_material_risk is None:
        return ComponentRiskLabel.UNRESOLVED
    return (
        ComponentRiskLabel.UNSAFE
        if resource_attributable_material_risk
        else ComponentRiskLabel.SAFE
    )


def component_decision_compatible(label: ComponentCallLabel, decision_on: bool) -> bool | None:
    if label is ComponentCallLabel.UNRESOLVED:
        return None
    if label is ComponentCallLabel.EITHER:
        return True
    return decision_on is (label is ComponentCallLabel.ON_ONLY)


def component_call_metrics(
    rows: Iterable[tuple[ComponentCallLabel, bool]],
) -> dict[str, float | int | dict[str, int] | None]:
    materialized = list(rows)
    counts = Counter(label.value for label, _ in materialized)
    resolved = [(label, decision) for label, decision in materialized if label is not ComponentCallLabel.UNRESOLVED]
    compatible = [component_decision_compatible(label, decision) for label, decision in resolved]
    on_only = [(label, decision) for label, decision in resolved if label is ComponentCallLabel.ON_ONLY]
    off_only = [(label, decision) for label, decision in resolved if label is ComponentCallLabel.OFF_ONLY]
    either = [(label, decision) for label, decision in resolved if label is ComponentCallLabel.EITHER]
    return {
        "groups": len(materialized),
        "label_counts": dict(counts),
        "resolved_groups": len(resolved),
        "resolved_coverage": len(resolved) / len(materialized) if materialized else None,
        "compatibility_accuracy": sum(bool(value) for value in compatible) / len(compatible) if compatible else None,
        "beneficial_false_off_rate": sum(not decision for _, decision in on_only) / len(on_only) if on_only else None,
        "harmful_false_on_rate": sum(decision for _, decision in off_only) / len(off_only) if off_only else None,
        "equivalent_groups": len(either),
    }


@dataclass(frozen=True)
class ActionOutcome:
    action_id: str
    quality: float | None
    deterministic_incremental_input_tokens: int | None
    structurally_valid: bool
    material_or_critical_risk: bool | None
    measurement_resolved: bool = True

    def __post_init__(self) -> None:
        parse_action_id(self.action_id)
        if self.deterministic_incremental_input_tokens is not None and self.deterministic_incremental_input_tokens < 0:
            raise ValueError("deterministic cost cannot be negative")


@dataclass(frozen=True)
class JointActionOracle:
    resolved: bool
    oracle_actions: tuple[str, ...]
    best_safe_quality: float | None
    minimum_frontier_cost: int | None
    reason: str
    quality_equivalence_margin: float = QUALITY_EQUIVALENCE_MARGIN


def build_joint_action_oracle(
    outcomes: Iterable[ActionOutcome],
    *, margin: float = QUALITY_EQUIVALENCE_MARGIN,
) -> JointActionOracle:
    rows = list(outcomes)
    if [row.action_id for row in rows] != list(ALL_ACTION_IDS):
        raise ValueError("joint oracle requires all 16 actions in canonical order")
    if margin <= 0:
        raise ValueError("quality equivalence margin must be positive")
    unresolved_valid = [
        row.action_id
        for row in rows
        if row.structurally_valid
        and (
            not row.measurement_resolved
            or row.quality is None
            or row.material_or_critical_risk is None
            or row.deterministic_incremental_input_tokens is None
        )
    ]
    if unresolved_valid:
        return JointActionOracle(
            False, (), None, None,
            "valid actions have unresolved quality/risk/cost: " + ",".join(unresolved_valid),
            margin,
        )
    safe = [
        row for row in rows
        if row.structurally_valid and row.material_or_critical_risk is False
    ]
    if not safe:
        return JointActionOracle(False, (), None, None, "no resolved safe valid action", margin)
    best_quality = max(float(row.quality) for row in safe if row.quality is not None)
    quality_frontier = [
        row for row in safe if float(row.quality) >= best_quality - margin
    ]
    minimum_cost = min(
        int(row.deterministic_incremental_input_tokens)
        for row in quality_frontier
        if row.deterministic_incremental_input_tokens is not None
    )
    oracle_actions = tuple(
        row.action_id for row in quality_frontier
        if row.deterministic_incremental_input_tokens == minimum_cost
    )
    return JointActionOracle(
        True, oracle_actions, best_quality, minimum_cost,
        "safe actions within the Q margin, minimized by deterministic injected-token cost",
        margin,
    )


def score_joint_action(
    *, selected_action_id: str, outcomes: Iterable[ActionOutcome],
    oracle: JointActionOracle,
) -> Mapping[str, object]:
    parse_action_id(selected_action_id)
    by_action = {row.action_id: row for row in outcomes}
    selected = by_action[selected_action_id]
    if not oracle.resolved:
        return {
            "oracle_resolved": False,
            "oracle_set_inclusion": None,
            "quality_regret": None,
            "excess_deterministic_cost_on_quality_frontier": None,
            "selected_invalid_or_risky": (
                not selected.structurally_valid or selected.material_or_critical_risk is True
            ),
        }
    safe_selected = selected.structurally_valid and selected.material_or_critical_risk is False
    quality_regret = (
        oracle.best_safe_quality - float(selected.quality)
        if safe_selected and selected.quality is not None and oracle.best_safe_quality is not None
        else None
    )
    on_quality_frontier = (
        safe_selected and quality_regret is not None
        and quality_regret <= oracle.quality_equivalence_margin
    )
    excess_cost = (
        int(selected.deterministic_incremental_input_tokens) - int(oracle.minimum_frontier_cost)
        if on_quality_frontier
        and selected.deterministic_incremental_input_tokens is not None
        and oracle.minimum_frontier_cost is not None
        else None
    )
    return {
        "oracle_resolved": True,
        "oracle_set_inclusion": selected_action_id in oracle.oracle_actions,
        "quality_regret": quality_regret,
        "excess_deterministic_cost_on_quality_frontier": excess_cost,
        "selected_invalid_or_risky": not safe_selected,
    }
