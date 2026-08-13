from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "data/pm_v1_5_contracts/paper1_ms_mp_v1_1_development_gate_v1.json"


def _read() -> dict:
    return json.loads(GATE.read_text(encoding="utf-8"))


def test_gate_is_frozen_before_any_call():
    gate = _read()
    assert gate["status"] == "FROZEN_BEFORE_ANY_GENERATOR_OR_JUDGE_CALL"
    assert gate["scope_limitation"]["full_context_required"] is True


def test_regression_probe_requirement_is_a_hard_precheck():
    probe = _read()["regression_probe_requirement"]
    assert "blind sided" in probe["required_check"]
    assert "never cheated" in probe["required_check"]
    assert "hard pre-check" in probe["required_check"]


def test_ms_and_mp_each_have_three_scored_criteria_plus_integrity_check():
    criteria = _read()["criteria"]
    assert {"ms_quality", "ms_risk", "ms_function", "ms_ignore_integrity"} <= set(criteria)
    assert {"mp_quality", "mp_risk", "mp_function"} <= set(criteria)


def test_uses_the_new_source_aware_risk_instrument():
    instrument = _read()["instrument"]
    assert "v1_5_source_aware_risk_blind_review.py" in instrument["risk"]
    assert "six distinct dimensions" in instrument["risk"]


def test_forbids_reusing_current_user_text_only_measurement():
    forbidden = " ".join(_read()["forbidden"])
    assert "full context is mandatory" in forbidden


def test_next_step_after_both_pass_is_selector_not_me():
    next_step = _read()["next_if_both_pass"]
    assert "selector" in next_step.lower()
    assert "do not rescue me first" in next_step.lower()
