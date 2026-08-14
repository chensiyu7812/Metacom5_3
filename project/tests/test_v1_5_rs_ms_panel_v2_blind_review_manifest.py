from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/pm_v1_5_paper1_rs_ms_panel_v2_blind_review_manifest_20260813"


def _report() -> dict:
    return json.loads((OUT / "report.json").read_text(encoding="utf-8"))


def test_manifest_is_zero_api_and_reuses_existing_replies():
    report = _report()
    assert report["api_calls"] == 0
    assert "no new generation" in report["source"]


def test_call_counts_match_the_requested_scope():
    counts = _report()["call_counts"]
    assert counts["rs_quality"] == 12
    assert counts["ms_quality"] == 13
    assert counts["risk_absolute"] == 38
    assert counts["rs_strategy_realization"] == 12
    assert counts["ms_function_independent"] == 7
    assert counts["ms_rs_interaction_crowdout"] == 7
    assert counts["total"] == 89


def test_owner_clusters_collapse_the_known_duplicate():
    clusters = _report()["owner_clusters"]
    assert clusters["count"] == 12
    assert "evo::p1" in clusters["members"]


def test_all_self_checks_pass():
    checks = _report()["checks"]
    assert all(checks.values()), checks


def test_condition_labels_are_not_leaked_into_provider_visible_text():
    assert _report()["checks"]["condition_and_arm_labels_absent_from_provider_text"] is True
