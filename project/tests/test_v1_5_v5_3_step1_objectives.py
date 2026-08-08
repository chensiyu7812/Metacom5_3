from __future__ import annotations

import pytest

from metacom_pm.v1_5_v5_3_step1_objectives import (
    Step1ObjectiveFreeze,
    build_step1_objective_freeze,
)


def test_objectives_keep_quality_risk_function_and_cost_separate() -> None:
    contract = build_step1_objective_freeze()
    assert contract.components == ["MP", "MS", "ME", "RS"]
    assert contract.primary_component_bundle["count"] == 4
    assert contract.independent_measurements["cost_is_learned"] is False
    assert contract.target_derivation["construction_condition_is_gold"] is False
    assert contract.uncertainty_policy["force_uncertain_to_binary"] is False
    assert contract.evidence_levels[
        "narrow_noninferiority_interval_required_to_call_pm_learned"
    ] is False


def test_objective_identity_detects_drift() -> None:
    contract = build_step1_objective_freeze()
    assert Step1ObjectiveFreeze.model_validate_json(contract.model_dump_json()) == contract
    changed = contract.model_dump(mode="json")
    changed["target_derivation"]["construction_condition_is_gold"] = True
    with pytest.raises(ValueError):
        Step1ObjectiveFreeze.model_validate(changed)
