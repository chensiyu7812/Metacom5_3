from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = PROJECT_ROOT / "data" / "v3_authority"


def test_uncapped_canary_mechanically_passed_without_selecting_a_generator() -> None:
    report = json.loads((AUTHORITY / "g0_research_aligned_canary_closeout_v2.json").read_text(encoding="utf-8"))
    assert report["run_identity"] == "9852e4c492a027c145bd1216bd7a5584a348ed9f3323c872797280a02e21ed62"
    assert report["status"] == "CANARY_MECHANICAL_PASS_QUALITY_NOT_YET_JUDGED_NO_GENERATOR_SELECTED"
    assert report["api_scope"] == {
        "supporter_successful_turns": 40,
        "local_role_player_turns": 40,
        "judge_calls": 0,
        "cards": 2,
        "candidate_configurations": 4,
    }
    assert report["generation_contract_observed"]["researcher_output_token_cap"] is None
    assert report["generation_contract_observed"]["provider_output_parameter_omitted_on_all_successes"] is True
    assert report["generation_contract_observed"]["provider_length_finishes"] == 0
    assert report["zero_api_interpretation"]["selection"] == "FORBIDDEN_FROM_TWO_CARD_CANARY"


def test_canary_retains_70b_retries_and_qwen_thinking_cost() -> None:
    report = json.loads((AUTHORITY / "g0_research_aligned_canary_closeout_v2.json").read_text(encoding="utf-8"))
    seventy = report["candidates"]["llama33_70b_capacity_reference"]
    assert seventy["successful_turns"] == 10
    assert seventy["first_attempt_success_rate"] == 0.4
    assert seventy["failure_classes"] == {"http_5xx": 1, "network_timeout": 5}
    assert seventy["terminal_trajectories"] == 0
    nonthinking = report["candidates"]["qwen37_plus_nonthinking"]
    thinking = report["candidates"]["qwen37_plus_thinking_upper_bound"]
    assert thinking["completion_tokens"]["reasoning_total_if_provider_reported"] == 8302
    assert thinking["completion_tokens"]["visible_total_inferred_as_completion_minus_reasoning"] == 663
    assert nonthinking["completion_tokens"]["visible_total_inferred_as_completion_minus_reasoning"] == 628
    assert thinking["qwen_actual_usd"] > nonthinking["qwen_actual_usd"]
    assert report["qwen_budget"]["actual_usd"] < report["qwen_budget"]["approved_ceiling_usd"]


def test_canary_public_closeout_contains_no_dialogue_text() -> None:
    report = json.loads((AUTHORITY / "g0_research_aligned_canary_closeout_v2.json").read_text(encoding="utf-8"))
    rendered = json.dumps(report, ensure_ascii=False).lower()
    assert "seeker_text" not in rendered
    assert "supporter_text" not in rendered
    assert all(len(value) == 64 for value in report["private_evidence_hashes"].values())
