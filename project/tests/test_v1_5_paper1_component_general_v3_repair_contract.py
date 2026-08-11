from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/v1_5/201l_validate_paper1_component_general_v3_repair_contract_v1_5.py"


def _module():
    spec = importlib.util.spec_from_file_location("v3_repair_contract_validator", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_component_general_v3_repair_contract_passes_all_checks():
    report = _module().validate()
    assert report["status"] == "V3_REPAIR_CONTRACT_PASS_G2_PHASE_MAY_BE_DESIGNED"
    assert report["failed_checks"] == []
    assert all(report["checks"].values())
    assert report["api_calls"] == 0
    assert report["labels_created"] == 0
    assert report["pm_fit"] is False
    assert report["v3_implementation_authorized"] is False


def test_full_sixteen_action_design_has_no_global_one_memory_cap():
    contract = _module()._read(_module().CONTRACT)
    budget = contract["v3_executor"]["response_budget"]
    policy = contract["v3_executor"]["pre_outcome_joint_policy"]

    assert budget["primary_acts"] == 1
    assert budget["explicit_memory_contributions_max"] == 2
    assert budget["global_one_memory_cap"] is False
    assert policy[
        "preserve_all_requested_bits_when_structurally_eligible_and_no_hard_safety_veto"
    ] is True
    assert policy[
        "unknown_redundant_or_conflicting_relation_automatically_suppresses_a_bit"
    ] is False


def test_suitability_decisions_are_per_component_and_nonexclusive():
    contract = _module()._read(_module().CONTRACT)
    suitability = contract["suitability_gold"]

    assert "state by component" in suitability["decision_grain"]
    assert suitability["components_may_all_be_suitable_in_the_same_state"] is True
    assert suitability["one_of_k_softmax_or_winner_take_all_forbidden"] is True
