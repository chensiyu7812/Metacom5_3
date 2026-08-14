#!/usr/bin/env python3
"""Freeze the 96-group public learnability pilot without API calls."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import stable_hex, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_v5_3_public_learnability_pilot import (  # noqa: E402
    PROTOCOL,
    add_frozen_semantic_similarity,
    audit_pilot,
    estimate_call_budget,
    materialize_memory_pool,
    materialize_rs_pool,
    select_pilot_groups,
    source_hashes,
)
from metacom_pm.v1_5_v5_3_semantic_ms_retrieval import (  # noqa: E402
    BgeM3Encoder,
    CachedTextEncoder,
    DEFAULT_BGE_M3_SNAPSHOT,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-semantic",
        action="store_true",
        help="Diagnostic only: materialize but deliberately fail the semantic-feature gate.",
    )
    args = parser.parse_args()

    paths = {
        "evoemo": ROOT / "data/external/evo_emo.json",
        "esconv": ROOT / "data/external/ESConv.json",
        "esconv_manifest": ROOT / "data/strategy/esconv_split_manifest_v1_5.jsonl",
        "strategy_cards": ROOT / "data/strategy/strategy_cards_v1_5_minimal.jsonl",
        "qrf_judge_source": ROOT / "src/metacom_pm/v1_5_v5_3_qrf_judge.py",
    }
    memory = materialize_memory_pool(paths["evoemo"])
    rs = materialize_rs_pool(
        esconv_path=paths["esconv"],
        manifest_path=paths["esconv_manifest"],
        cards_path=paths["strategy_cards"],
    )
    rows = select_pilot_groups(memory, rs)
    if not args.skip_semantic:
        encoder = CachedTextEncoder(BgeM3Encoder(DEFAULT_BGE_M3_SNAPSHOT))
        add_frozen_semantic_similarity(rows, encoder=encoder)

    audit = audit_pilot(rows)
    budget = estimate_call_budget(rows)
    contract = {
        "protocol": PROTOCOL,
        "status": "PRE_EFFECT_FROZEN" if audit["status"] == "PASS" else "PRE_EFFECT_BLOCKED",
        "source_hashes": source_hashes(paths),
        "pilot_scope": {
            "memory_users": ["p12", "p13", "p18"],
            "groups_per_component": 24,
            "paired_generator_seeds_per_group": 3,
            "selection": "outcome-blind greedy coverage over pre-treatment candidate type, relevance, age, redundancy/readiness, user/session; RS uses distinct ESConv dialogues",
            "actual_rank1_only": True,
        },
        "learnability_protection": {
            "continuous_replicate_aggregated_effect_target": True,
            "tie_is_zero_not_negative": True,
            "positive_support_contribution_separate_from_absolute_risk": True,
            "functional_use_is_diagnostic_not_label_intersection": True,
            "cost_only_after_four_heads": True,
            "candidate_state_semantic_feature": "frozen local BAAI/bge-m3 cosine",
            "head_capacity": "4-7 deployable nonconstant features plus regularization",
            "primary_features": {
                "MP": [
                    "candidate_state_bge_m3_cosine", "topk_top1_lexical_relevance",
                    "rank1_relative_age", "rank1_injected_tokens",
                    "current_redundant", "candidate_subtype",
                ],
                "MS": [
                    "candidate_state_bge_m3_cosine", "topk_top1_lexical_relevance",
                    "rank1_relative_age", "rank1_injected_tokens",
                    "current_redundant", "candidate_subtype",
                ],
                "ME": [
                    "candidate_state_bge_m3_cosine", "topk_top1_lexical_relevance",
                    "rank1_relative_age", "rank1_injected_tokens",
                    "current_redundant", "past_action_result",
                ],
                "RS": [
                    "candidate_state_bge_m3_cosine", "candidate_subtype",
                    "dialogue_phase_bucket", "card_precondition_met",
                    "observable_explicit_advice_welcome",
                    "observable_question_repetition_block",
                ],
            },
            "outcome_adaptive_resampling_forbidden": True,
        },
        "execution_freeze": {
            "generator_endpoint": "generator",
            "generator_family": "llama",
            "training_judge_endpoint": "training_judge",
            "training_judge_family": "google_gemini",
            "judge_replication_batching": "three paired seeds judged together",
            "quality_order_balance": ["ON_as_A", "ON_as_B"],
            "risk": "one blinded six-response absolute-arm event audit per group",
            "function": "one blinded three-ON-response typed-use audit per group",
            "retry_cap": "10 percent of base calls; no silent model substitution",
            "qrf_protocol": "pm-v1.5-v5.3-qrf-judge-v1",
            "qrf_zero_api_fixture_tests": "PASS",
        },
        "call_and_token_budget": {
            **budget,
            "pricing_checked_utc_date": "2026-08-09",
            "generator_price": "NVIDIA hosted prototype endpoint: free API endpoint; rate limited",
            "judge_price_usd_per_1m_input_tokens": 0.10,
            "judge_price_usd_per_1m_output_tokens": 0.40,
            "judge_base_maximum_usd": 0.22848,
            "full_pilot_hard_usd_cap_including_10_percent_retry": 0.26,
            "eight_group_canary_hard_usd_cap": 0.03,
            "pricing_sources": [
                "https://build.nvidia.com/meta/llama-3_1-8b-instruct?nim=hosted&section=deploy",
                "https://ai.google.dev/gemini-api/docs/pricing",
            ],
        },
        "live_execution_allowed": False,
        "live_blockers": [
            "run 2-group-per-head generator/Step2 schema canary before the 96-group batch",
        ],
        "api_calls": 0,
    }
    contract["freeze_identity"] = "v53pilot_" + stable_hex(contract, n=24)

    out = ROOT / "outputs/pm_v1_5_v5_3_public_learnability_pilot_20260809"
    write_jsonl(out / "effect_group_manifest_private.jsonl", rows)
    write_json(out / "audit.json", audit)
    write_json(out / "call_budget.json", budget)
    write_json(out / "contract.json", contract)
    write_json(
        ROOT / "data/pm_v1_5_contracts/v5_3_public_learnability_pilot_v1.json",
        contract,
    )
    print(
        {
            "status": contract["status"],
            "groups": len(rows),
            "audit": audit["status"],
            "api_calls": 0,
            "manifest": str(out / "effect_group_manifest_private.jsonl"),
            "freeze_identity": contract["freeze_identity"],
        }
    )


if __name__ == "__main__":
    main()
