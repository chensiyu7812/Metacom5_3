from __future__ import annotations

import json
from pathlib import Path


AUTHORITY = Path(__file__).resolve().parents[1] / "data" / "v3_authority"


def _preflight() -> dict:
    return json.loads((AUTHORITY / "g0_fair_judge_canary_preflight_v1.json").read_text(encoding="utf-8"))


def test_fair_judge_canary_is_source_stratified_and_call_complete() -> None:
    report = _preflight()
    assert report["api_calls"] == 0
    assert sorted(row["source"] for row in report["cards"]) == ["EPITOME", "ESconv", "ESconv", "ExTES", "MHP", "Psych"]
    assert report["call_accounting"] == {
        "eia_dual_order": 108,
        "repeatability": 18,
        "absolute_guardrail": 18,
        "total": 144,
    }
    assert report["candidates"] == [
        "llama31_8b_incumbent", "qwen37_plus_nonthinking", "qwen37_plus_thinking_upper_bound"
    ]


def test_fair_judge_canary_binds_independent_judge_budget_and_no_selection() -> None:
    report = _preflight()
    assert report["status"].startswith("SUPERSEDED_BEFORE_ANY_CALL")
    assert report["supersession"]["api_calls_made"] == 0
    assert report["supersession"]["usd_spent"] == 0
    assert report["supersession"]["former_identity_authorized"] is False
    assert report["judge"]["family"] == "openai_gpt_5_6_sol"
    assert report["judge"]["model"] == "gpt-5.6-sol"
    assert 2.0 < report["budget"]["point_estimate_usd"] < report["budget"]["suggested_ceiling_usd"]
    assert report["budget"]["suggested_ceiling_usd"] == 3.34
    assert "cannot select" in report["canary_boundary"]
    assert len(report["run_identity"]) == 64
    assert all(len(value) == 64 for value in report["private_manifest_hashes"].values())
