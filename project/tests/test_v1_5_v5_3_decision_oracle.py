from __future__ import annotations

from metacom_pm.contracts import ALL_ACTION_IDS
from metacom_pm.v1_5_v5_3_decision_oracle import (
    ActionOutcome,
    ComponentCallLabel,
    ComponentRiskLabel,
    build_joint_action_oracle,
    component_call_metrics,
    resolve_component_call,
    resolve_component_risk,
    score_joint_action,
)


def test_component_label_does_not_turn_executor_failure_into_off_gold() -> None:
    result = resolve_component_call(
        quality_uplift=-0.8,
        execution_valid=False,
        resource_attributable_material_risk=False,
    )
    assert result.label is ComponentCallLabel.UNRESOLVED


def test_component_label_preserves_on_off_either_and_separate_risk_overlay() -> None:
    assert resolve_component_call(
        quality_uplift=0.11, execution_valid=True,
        resource_attributable_material_risk=False,
    ).label is ComponentCallLabel.ON_ONLY
    assert resolve_component_call(
        quality_uplift=-0.11, execution_valid=True,
        resource_attributable_material_risk=False,
    ).label is ComponentCallLabel.OFF_ONLY
    assert resolve_component_call(
        quality_uplift=0.10, execution_valid=True,
        resource_attributable_material_risk=False,
    ).label is ComponentCallLabel.EITHER
    assert resolve_component_call(
        quality_uplift=0.9, execution_valid=True,
        resource_attributable_material_risk=True,
    ).label is ComponentCallLabel.ON_ONLY
    assert resolve_component_risk(True) is ComponentRiskLabel.UNSAFE
    assert resolve_component_risk(False) is ComponentRiskLabel.SAFE
    assert resolve_component_risk(None) is ComponentRiskLabel.UNRESOLVED


def test_component_call_metrics_use_only_resolved_denominator() -> None:
    report = component_call_metrics([
        (ComponentCallLabel.ON_ONLY, True),
        (ComponentCallLabel.ON_ONLY, False),
        (ComponentCallLabel.OFF_ONLY, True),
        (ComponentCallLabel.EITHER, True),
        (ComponentCallLabel.UNRESOLVED, False),
    ])
    assert report["resolved_groups"] == 4
    assert report["resolved_coverage"] == 0.8
    assert report["compatibility_accuracy"] == 0.5
    assert report["beneficial_false_off_rate"] == 0.5
    assert report["harmful_false_on_rate"] == 1.0


def _outcomes() -> list[ActionOutcome]:
    rows = []
    for index, action in enumerate(ALL_ACTION_IDS):
        rows.append(ActionOutcome(
            action_id=action,
            quality=0.5,
            deterministic_incremental_input_tokens=index * 10,
            structurally_valid=True,
            material_or_critical_risk=False,
        ))
    rows[1] = ActionOutcome(
        action_id=ALL_ACTION_IDS[1], quality=0.58,
        deterministic_incremental_input_tokens=10,
        structurally_valid=True, material_or_critical_risk=False,
    )
    rows[2] = ActionOutcome(
        action_id=ALL_ACTION_IDS[2], quality=0.60,
        deterministic_incremental_input_tokens=20,
        structurally_valid=True, material_or_critical_risk=False,
    )
    return rows


def test_joint_oracle_keeps_q_equivalent_minimum_cost_action_not_unique_best_q() -> None:
    rows = _outcomes()
    oracle = build_joint_action_oracle(rows)
    assert oracle.resolved is True
    assert oracle.best_safe_quality == 0.60
    assert oracle.oracle_actions == (ALL_ACTION_IDS[0],)
    score = score_joint_action(
        selected_action_id=ALL_ACTION_IDS[1], outcomes=rows, oracle=oracle,
    )
    assert score["oracle_set_inclusion"] is False
    assert round(score["quality_regret"], 2) == 0.02
    assert score["excess_deterministic_cost_on_quality_frontier"] == 10


def test_joint_oracle_is_unresolved_if_any_valid_action_lacks_measurement() -> None:
    rows = _outcomes()
    rows[-1] = ActionOutcome(
        action_id=ALL_ACTION_IDS[-1], quality=None,
        deterministic_incremental_input_tokens=100,
        structurally_valid=True, material_or_critical_risk=False,
        measurement_resolved=False,
    )
    assert build_joint_action_oracle(rows).resolved is False
