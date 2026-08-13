from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/pm_v1_5_paper1_rs_ms_panel_v2_20260813"


def _report() -> dict:
    return json.loads((OUT / "report.json").read_text(encoding="utf-8"))


def _cases() -> list[dict]:
    return [
        json.loads(line)
        for line in (OUT / "development_cases_private.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]


def test_clear_use_and_ask_meet_panel_v2_minimums():
    report = _report()
    owners = report["distinct_owners_by_stratum"]
    assert report["strata_counts"]["CLEAR_USE"] >= 4
    assert len(owners["CLEAR_USE"]) >= 4
    assert report["strata_counts"]["ASK"] >= 2
    assert len(owners["ASK"]) >= 2


def test_all_six_required_negative_controls_are_covered():
    report = _report()
    covered = " ".join(report["required_negative_controls_covered"])
    for marker in (
        "current_context_echo",
        "low_information_greeting",
        "topical_mismatch",
        "stale_or_conflicting",
        "rs_structurally_ineligible",
        "wrong_owner",
    ):
        assert marker in covered


def test_rs_coverage_meets_twelve_four_arm_states():
    report = _report()
    assert report["rs_coverage"]["four_arm_complete_states"] >= 12
    assert report["rs_coverage"]["requirement_met"] is True


def test_call_budget_is_within_sixty_four_and_zero_cost():
    report = _report()
    assert report["total_calls"] <= 64
    assert report["estimated_cost_usd"] == 0.0
    assert report["api_calls"] == 0


def test_wrong_owner_gate_actually_blocks():
    check = _report()["wrong_owner_control"]["structural_wrong_owner_check"]
    assert check["gate_holds"] is True
    assert check["ms_resource_fired"] is False


def test_no_state_is_reused_across_strata():
    cases = _cases()
    state_ids = [c["state_id"] for c in cases]
    assert len(state_ids) == len(set(state_ids))
