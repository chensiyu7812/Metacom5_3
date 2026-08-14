from __future__ import annotations

import json
from pathlib import Path


AUTHORITY = Path(__file__).resolve().parents[1] / "data" / "v3_authority"


def _load(name: str) -> dict:
    return json.loads((AUTHORITY / name).read_text(encoding="utf-8"))


def test_packet_is_complete_two_human_official_dimension_design() -> None:
    packet = _load("g0_esc_eval_human_review_packet_manifest_v1.json")
    assert (packet["dialogues"], packet["reviewers"], packet["assignments"]) == (72, 2, 144)
    assert packet["official_dimension_ratings"] == 72 * 2 * 7 == 1008
    assert len(packet["public_packet_hashes"]) == 6
    assert all(len(value) == 64 for value in packet["public_packet_hashes"].values())


def test_packet_blinding_and_source_identity_are_bound() -> None:
    packet = _load("g0_esc_eval_human_review_packet_manifest_v1.json")
    closeout = _load("g0_four_generator_full_screen_closeout_v1.json")
    preflight = _load("g0_four_generator_full_screen_preflight_v1.json")
    assert packet["source_generation_identity"] == closeout["run_identity"]
    assert packet["joined_supporter_prompt_sha256"] == preflight["prompt"]["joined_prompt_sha256"]
    assert packet["blinding_checks"] == {
        "candidate_provider_model_source_card_absent_from_public_schema": True,
        "single_dialogue_not_candidate_bundle": True,
        "reviewer_orders_independent": True,
        "same_card_candidates_not_adjacent": True,
    }
    assert packet["api_calls"] == 0
    assert packet["status"] == "HISTORICAL_CUSTOM_PROTOCOL_REVIEWS_RECEIVED_DEMOTED_NONPRIMARY"
    assert packet["selection_verdict"] == "NO_ACTIVE_SELECTION_AUTHORITY_UNDER_OFFICIAL_FIRST_CONTRACT"


def test_development_decision_contract_is_outcome_blind_and_official_primary() -> None:
    contract = _load("generator_esc_eval_development_decision_contract_v1.json")
    assert contract["status"] == "FROZEN_BEFORE_ANY_HUMAN_ESC_EVAL_SCORE"
    assert contract["source"]["primary"] == "Overall"
    assert contract["source"]["key_dimensions"] == ["Empathy", "Skill", "Information"]
    assert contract["relative_quality_rule"]["practical_noninferiority_margin_points"] == -0.25
    assert contract["relative_quality_rule"]["strict_advantage_margin_points"] == 0.15
    assert "No dimension average" in contract["relative_quality_rule"]["multiple_dimensions"]


def test_quality_and_integrity_control_cost_tie_break() -> None:
    contract = _load("generator_esc_eval_development_decision_contract_v1.json")
    order = " ".join(contract["selection_order"])
    assert "pairwise development-equivalent" in order
    assert "lowest observed USD" in order
    assert "quality advantage over Qwen non-thinking" in order
    forbidden = " ".join(contract["forbidden"])
    assert "cost or latency compensate" in forbidden
    assert "full ESC-Eval" in forbidden
