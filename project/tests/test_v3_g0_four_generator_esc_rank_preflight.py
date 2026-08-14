from __future__ import annotations

import json
from pathlib import Path


AUTHORITY = Path(__file__).resolve().parents[1] / "data" / "v3_authority"


def test_four_generator_esc_rank_preflight_is_external_descriptive_not_selection() -> None:
    report = json.loads((AUTHORITY / "g0_four_generator_esc_rank_preflight_v1.json").read_text(encoding="utf-8"))
    assert report["api_calls"] == 0
    assert report["estimated_usd"] == 0
    assert report["complete_dialogues"] == 93
    assert report["local_inference_calls"] == 651
    assert report["candidate_dialogue_counts"] == {
        "llama31_8b_incumbent": 24,
        "nemotron3_nano_30b_a3b_default_thinking": 21,
        "qwen37_plus_nonthinking": 24,
        "qwen37_plus_thinking_upper_bound": 24,
    }
    boundary = report["decision_boundary"]
    assert boundary["quality_selection"] == "NOT_AUTHORIZED_BY_THIS_IDENTITY"
    assert boundary["judge_calls"] == "NOT_AUTHORIZED_BY_THIS_IDENTITY"
    assert "descriptive" in boundary["esc_rank_role"].lower()


def test_four_generator_esc_rank_preflight_binds_source_and_runtime() -> None:
    report = json.loads((AUTHORITY / "g0_four_generator_esc_rank_preflight_v1.json").read_text(encoding="utf-8"))
    assert report["source_generation_identity"] == "45d820f440b333552f0a27822d540260efacc13a377672831157762598cf5668"
    assert report["source_ledger_sha256"] == "d7b434876dbd6357f629d67a1bb69937689af634f5af452adb2df85861370ac3"
    measurement = report["measurement"]
    assert measurement["esc_eval_commit"] == "9ad46e7b5e247e824dae4633910eaa82be668beb"
    assert measurement["esc_rank_revision"] == "450bf2eb5376c79e371aaf432925810243de1527"
    assert measurement["internlm2_revision"] == "c2ba64483dc50b3f8eb2d8271c4b9877a79ed2e2"
    assert len(report["score_run_identity"]) == 64
