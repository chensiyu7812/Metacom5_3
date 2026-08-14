from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = PROJECT_ROOT / "data" / "v3_authority"


def _report() -> dict:
    return json.loads((AUTHORITY / "g0_four_generator_full_screen_closeout_v1.json").read_text(encoding="utf-8"))


def test_full_screen_closeout_preserves_itt_and_reliability_failure() -> None:
    report = _report()
    assert report["run_identity"] == "45d820f440b333552f0a27822d540260efacc13a377672831157762598cf5668"
    assert report["scope"]["successful_supporter_turns"] == 469
    assert report["scope"]["expected_supporter_turns"] == 480
    assert report["candidates"]["llama31_8b_incumbent"]["reliability_gate"] == "PASS"
    assert report["candidates"]["qwen37_plus_nonthinking"]["reliability_gate"] == "PASS"
    assert report["candidates"]["qwen37_plus_thinking_upper_bound"]["reliability_gate"] == "PASS"
    nemotron = report["candidates"]["nemotron3_nano_30b_a3b_default_thinking"]
    assert nemotron["successful_turns"] == 109
    assert nemotron["failed_physical_attempts"] == 17
    assert nemotron["terminal_trajectories"] == 3
    assert nemotron["reliability_gate"].startswith("HARD_FAIL")


def test_full_screen_closeout_does_not_select_on_transport_or_hide_cost() -> None:
    report = _report()
    assert report["budget"]["qwen_actual_usd"] == 0.2963172
    assert report["budget"]["within_approved_ceiling"] is True
    assert report["decision"]["quality_judged"] is False
    assert report["decision"]["risk_judged"] is False
    assert report["decision"]["generator_selected"] is False
    rendered = json.dumps(report, ensure_ascii=False).lower()
    assert "seeker_text" not in rendered and "supporter_text" not in rendered
    assert all(len(value) == 64 for value in report["private_evidence_hashes"].values())
