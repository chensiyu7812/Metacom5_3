from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLOSEOUT = ROOT / "data/pm_v1_5_contracts/paper1_rs_ms_panel_v2_blind_review_v2_closeout_v1.json"


def _fields() -> dict:
    return json.loads(CLOSEOUT.read_text(encoding="utf-8"))["fields_to_fill"]


def test_completed_all_101_calls_under_cost_cap():
    fields = _fields()
    assert fields["completed_calls"] == 101
    assert fields["observed_cost_usd"] < 1.35


def test_rs_passes_this_round():
    verdict = _fields()["verdict"]
    assert verdict["rs_pass_this_round"] is True


def test_ms_fails_this_round_on_risk_not_quality_or_function():
    fields = _fields()
    criteria = fields["criteria"]
    assert criteria["ms_quality"]["pass"] is True
    assert criteria["ms_function"]["pass"] is True
    assert criteria["ms_risk"]["pass"] is False
    assert fields["verdict"]["ms_pass_this_round"] is False


def test_interaction_fails_on_combined_risk_not_content_preservation():
    fields = _fields()
    criteria = fields["criteria"]
    assert criteria["ms_rs_interaction"]["pass"] is True
    assert criteria["ms_rs_combined_risk"]["pass"] is False
    assert "evo::p6" in criteria["ms_rs_combined_risk"]["owners_with_critical"]
    assert fields["verdict"]["interaction_pass_this_round"] is False


def test_overall_label_is_partial_not_met_or_pass():
    label = _fields()["verdict"]["label"]
    assert label == "FIRST_VERSION_DEVELOPMENT_PROMOTION_PARTIAL"
    assert label != "FIRST_VERSION_DEVELOPMENT_PROMOTION_MET"


def test_p6_leak_evidence_is_recorded_verbatim():
    evidence = json.loads(CLOSEOUT.read_text(encoding="utf-8"))["raw_evidence"]["p6_ms_rs_combined_risk"]
    assert "tempted to act on some impulses" in evidence["ms_rs_reply"]
    assert "blindsided" in evidence["ms_rs_reply"]
    assert "infidelity" in evidence["interpretation"].lower()
    assert "cheated" in evidence["ms_source"].lower()


def test_scope_limitation_forbids_external_test_substitution():
    statement = _fields()["scope_limitation_restated"]
    assert "current_user_text" in statement
    assert "never" in statement.lower() or "can never" in statement
