from __future__ import annotations

import hashlib
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = PROJECT_ROOT / "data" / "v3_authority"


def _json(name: str) -> dict:
    return json.loads((AUTHORITY / name).read_text(encoding="utf-8"))


def test_full_screen_contains_exactly_the_four_approved_configurations() -> None:
    contract = _json("g0_four_generator_full_screen_contract_v1.json")
    candidates = contract["candidates"]
    assert [row["candidate_id"] for row in candidates] == [
        "llama31_8b_incumbent",
        "qwen37_plus_nonthinking",
        "qwen37_plus_thinking_upper_bound",
        "nemotron3_nano_30b_a3b_default_thinking",
    ]
    assert "meta/llama-3.3-70b-instruct" not in {row["model"] for row in candidates}
    assert {row.get("enable_thinking") for row in candidates if row["model"].startswith("qwen")} == {False, True}
    assert contract["shared_generation_contract"]["researcher_output_token_cap"] is None


def test_full_screen_preflight_is_zero_call_text_free_and_complete() -> None:
    report = _json("g0_four_generator_full_screen_preflight_v1.json")
    assert report["status"] == "ZERO_CALL_PREFLIGHT_PASS_EXECUTION_REQUIRES_IDENTITY_SPECIFIC_APPROVAL"
    assert report["api_calls"] == 0
    assert report["contains_role_card_or_dialogue_text"] is False
    assert report["cards"] == report["sample"]["development_cards"] == 24
    assert report["logical_supporter_calls"] == report["local_role_player_calls"] == 480
    assert report["qwen_paid_logical_calls"] == 240
    assert report["judge_calls"] == 0
    assert report["run_identity"] == "45d820f440b333552f0a27822d540260efacc13a377672831157762598cf5668"
    assert report["budget"]["linear_24_card_point_estimate_usd"] == 0.2336304


def test_full_screen_identity_binds_current_runner_engine_and_manifest() -> None:
    report = _json("g0_four_generator_full_screen_preflight_v1.json")
    paths = {
        "16_run_g0_research_aligned_esc.py": PROJECT_ROOT / "scripts" / "v3" / "16_run_g0_research_aligned_esc.py",
        "22_run_g0_four_generator_full_screen.py": PROJECT_ROOT / "scripts" / "v3" / "22_run_g0_four_generator_full_screen.py",
        "api.py": PROJECT_ROOT / "src" / "metacom_pm" / "api.py",
        "g0_research_aligned_screening_manifest_v2.jsonl": AUTHORITY / "g0_research_aligned_screening_manifest_v2.jsonl",
    }
    for name, path in paths.items():
        assert hashlib.sha256(path.read_bytes()).hexdigest() == report["input_hashes"][name]
    assert report["manifest_sha256"] == report["sample"]["manifest_sha256"]
