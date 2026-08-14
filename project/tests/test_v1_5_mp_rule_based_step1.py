from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "data/pm_v1_5_contracts/paper1_mp_rule_based_step1_v1.json"


def _read() -> dict:
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_mp_decision_space_is_constrain_ignore_and_forbids_recitation():
    contract = _read()
    space = contract["mp_decision_space"]
    assert set(space["options"]) == {"CONSTRAIN", "IGNORE"}
    assert any("literal profile value" in item for item in space["forbidden"])
    assert any(
        "no visible reply change" in item for item in space["forbidden"]
    )


def test_repair_targets_the_missing_realization_content_not_step1_alone():
    contract = _read()
    finding = contract["audit_finding"]
    assert "MP_PROFILE_SCOPE_V1" in finding["prior_assumption_corrected"]
    assert "bounded {component} response change" in finding["actual_root_cause"]
    repair = contract["repair_applied"]
    assert repair["new_module"]["path"] == "src/metacom_pm/v1_5_mp_profile_delta_templates_v1.py"
    assert repair["compiler_change"]["path"] == "src/metacom_pm/v1_5_response_program_v4.py"


def test_panel_requires_field_type_diversity_not_only_owner_diversity():
    strata = _read()["panel_v1_requirements"]["minimum_strata"]
    assert "3 distinct MP_PROFILE_SCOPE_V1 field types" in strata["CONSTRAIN_eligible"]
    assert "wrong-owner" in strata["IGNORE_controls"]


def test_measurement_reuses_function_observability_v2_not_a_new_construct():
    reuse = _read()["measurement_reuse"]
    assert reuse["source"] == (
        "data/pm_v1_5_contracts/paper1_rs_ms_r0_delta_measurement_and_panel_revision_v2.json"
    )
    assert any("function_observability_v2.layers" in item for item in reuse["reused_as_is"])


def test_authorization_is_zero_api():
    auth = _read()["authorization"]
    assert auth["api_calls"] == 0
    assert auth["generator_calls"] == 0
    assert auth["external_execution"] is False
