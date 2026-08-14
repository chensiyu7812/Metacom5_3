from __future__ import annotations

import json
from pathlib import Path


AUTHORITY = Path(__file__).resolve().parents[1] / "data" / "v3_authority"


def _report() -> dict:
    return json.loads((AUTHORITY / "g0_four_generator_esc_rank_closeout_v1.json").read_text(encoding="utf-8"))


def test_esc_rank_closeout_preserves_format_failure_and_sensitivity_boundary() -> None:
    report = _report()
    assert report["score_run_identity"] == "c22b402c57c6fc14b0a6bd976dc8af012e2e2245862f81616c96223ba04c5a3d"
    assert report["execution"]["final_local_inference_calls"] == 651
    assert report["execution"]["actual_usd"] == 0
    assert report["measurement_result"]["primary_strict_parser"] == {
        "rule": "full-string ^[0-4]$ or INVALID",
        "valid": 0,
        "invalid": 651,
        "interpretation": "PUBLIC_ADAPTER_OUTPUT_PROTOCOL_INCOMPATIBLE_NOT_MODEL_QUALITY_FAILURE",
    }
    assert report["measurement_result"]["anchored_format_sensitivity"]["valid"] == 651
    assert report["measurement_result"]["anchored_format_sensitivity"]["role"] == "DESCRIPTIVE_SENSITIVITY_ONLY"


def test_esc_rank_closeout_does_not_select_from_saturation_or_partial_nemotron() -> None:
    report = _report()
    assert report["instrument_diagnosis"]["generator_selected"] is False
    assert report["decision"]["generator_selected"] is False
    assert report["candidate_profiles"]["nemotron3_nano_30b_a3b_default_thinking"]["reliability_selection_eligible"] is False
    assert report["eligible_same_card_pairwise"]["constant_dimensions_all_three_eligible"] == ["fluency", "diversity", "empathic"]
    assert all(attempt["included_in_formal_summary"] is False for attempt in report["excluded_execution_attempts"])
    assert all(len(value) == 64 for value in report["private_evidence_hashes"].values())
