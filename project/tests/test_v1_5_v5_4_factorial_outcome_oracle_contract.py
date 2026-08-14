from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "data/pm_v1_5_contracts/v5_4_factorial_outcome_oracle_learning_v1.json"


def _contract() -> dict:
    return json.loads(CONTRACT.read_text())


def test_semantic_reviewer_projection_is_never_route_gold() -> None:
    contract = _contract()
    assert contract["triggering_evidence"]["atomic_axis_development"]["all_axis_gates_pass"] is False
    assert contract["rank1_and_structural_boundary"]["semantic_reviewer_role"].startswith("explanation")
    superseded = " ".join(contract["authority"]["supersedes"])
    assert "PM gold" in superseded


def test_deployment_itt_is_training_target_and_clean_execution_is_diagnostic() -> None:
    contract = _contract()
    estimands = contract["dual_estimands"]
    assert estimands["deployment_itt"]["role"] == "primary PM training and policy-selection target"
    assert "diagnosis only" in estimands["clean_execution_mechanism"]["role"]
    assert "fallback" in estimands["deployment_itt"]["definition"]


def test_construction_assignment_cannot_leak_into_value_learning() -> None:
    contract = _contract()
    design = contract["outcome_blind_state_contrast_design"]
    assert "never the worth-opening target" in design["construction_assignment_role"]
    assert contract["bounded_semantic_observability_gate"]["anti_shortcut_gate"][
        "construction_tag_or_template_hash_present_in_features"
    ] == 0


def test_architecture_remains_four_bits_and_full_sixteen_action_oracle() -> None:
    contract = _contract()
    joint = contract["sixteen_action_policy"]
    assert "unchanged 16 legal actions" in joint["architecture"]
    assert "not a 16-class classifier" in joint["architecture"]
    assert "all 16 actions" in joint["joint_panel"]


def test_current_authorization_stops_effect_calls_and_training() -> None:
    authorization = _contract()["current_authorization"]
    assert authorization["state_variant_authoring"] is False
    assert authorization["only_authorized_authoring_revision"].startswith("source-prefix-locked")
    assert authorization["representation_observability_test"] is False
    assert authorization["fidelity_and_leakage_audit"] is True
    assert authorization["actual_rank1_recomputation"] is True
    assert authorization["new_response_effect_calls"] is False
    assert authorization["pm_training"] is False
