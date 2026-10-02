#!/usr/bin/env python3
"""Freeze RS aggregate interpretation and prepare the 64-item blind review.

This script is deliberately offline.  It never consumes human judgments,
never calls the Generator, and never creates treatment-uptake assignments.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import canonical_json, sha256_file, sha256_text  # noqa: E402
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config  # noqa: E402
from metacom_pm.paper1.rs_atomic_move.resource_qualification import (  # noqa: E402
    AGGREGATE_RULE_PROTOCOL,
    BLIND_REVIEW_PROTOCOL,
    BlindSemanticsReviewItem,
    CompletedSemanticsHumanReview,
    StructuralAdjudication,
    build_blind_review_materials,
)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _schema_hash(model: type) -> str:
    return sha256_text(canonical_json(model.model_json_schema()))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-packet",
        type=Path,
        default=PROJECT
        / "data/paper1_authority/paper1_rs_resource_semantics_qualification_packet_20260820_v1.json",
    )
    parser.add_argument(
        "--blind-review",
        type=Path,
        default=PROJECT
        / "data/paper1_authority/paper1_rs_resource_semantics_blind_review_20260820_v1.jsonl",
    )
    parser.add_argument(
        "--blind-key",
        type=Path,
        default=PROJECT
        / "data/paper1_authority/paper1_rs_resource_semantics_blind_key_20260820_v1.json",
    )
    parser.add_argument(
        "--aggregate-rule",
        type=Path,
        default=PROJECT
        / "data/paper1_authority/paper1_rs_resource_semantics_aggregate_rule_20260820_v1.json",
    )
    parser.add_argument(
        "--readiness",
        type=Path,
        default=PROJECT
        / "data/paper1_authority/paper1_rs_resource_qualification_readiness_20260820_v1.json",
    )
    args = parser.parse_args()

    config = load_public_only_config(PROJECT / "configs/paper1_public_only.yaml")
    assert_pre_outcome_locked(config)
    packet = json.loads(args.source_packet.read_text(encoding="utf-8"))
    source_identity = packet["source_identity"]
    bound_files = {
        "canonical_catalog_sha256": PROJECT
        / "data/paper1_public_rs/esconv_rs_exact_canonical_treatments_v1.jsonl",
        "canonical_top8_sha256": PROJECT
        / "data/paper1_public_rs/esconv_rs_canonical_bge_top8_v1.jsonl",
        "canonical_top8_report_sha256": PROJECT
        / "data/paper1_public_rs/esconv_rs_canonical_bge_top8_report_v1.json",
    }
    for name, path in bound_files.items():
        if sha256_file(path) != source_identity[name]:
            raise RuntimeError(f"source identity drift: {name}")

    blind_seed = "paper1-rs-semantics-blind-order-20260820-v1"
    blind_rows, key = build_blind_review_materials(packet, blind_seed=blind_seed)
    blind_dicts = [row.model_dump(mode="json") for row in blind_rows]
    _write_jsonl(args.blind_review, blind_dicts)

    source_packet_sha256 = sha256_file(args.source_packet)
    key.update(
        {
            "status": "SEALED_JOIN_KEY_NOT_FOR_REVIEWER",
            "source_packet_sha256": source_packet_sha256,
            "blind_review_protocol": BLIND_REVIEW_PROTOCOL,
        }
    )
    _write_json(args.blind_key, key)

    rule = {
        "protocol": AGGREGATE_RULE_PROTOCOL,
        "status": "FROZEN_BEFORE_HUMAN_RESULTS",
        "source_packet_sha256": source_packet_sha256,
        "sample_identity": {
            "N": 64,
            "rank_counts": {"1": 16, "2": 16, "4": 16, "8": 16},
            "family_count": 8,
            "items_per_family": 8,
            "pool": "ESConv validation; isolated from future ESC-Eval role cards",
        },
        "estimands_and_reporting": {
            "primary": "descriptive label prevalence for each frozen rubric dimension",
            "strata": ["overall", "retrieval_rank_1_2_4_8", "atomic_move_family"],
            "report": [
                "raw numerator and denominator for every label",
                "proportion for every label",
                "Wilson 95 percent interval for each binary one-vs-rest label proportion",
                "missing and uncertain counts without recoding uncertain as failure",
            ],
            "binary_PASS_line": None,
            "empirical_threshold_to_invent_after_results": False,
            "small_strata_interpretation": "descriptive only; no family/rank significance claim",
        },
        "interpretation_rule": {
            "permitted": [
                "aggregate evidence about exact-treatment resource semantics",
                "aggregate retriever failure-mode localization by frozen rank and family strata",
                "transparent recommendation for general catalog/retriever repair subject to researcher review",
            ],
            "forbidden": [
                "claiming response quality, PM effect, or ESC-Eval capability",
                "choosing k or token budget",
                "deleting, reranking, or downweighting a candidate because a human or LLM judged state appropriateness",
                "creating any runtime human-or-LLM utility filter",
                "using visible redundancy or near-duplicate judgment as a semantic-threshold deletion rule",
                "turning aggregate results into a post-hoc PASS threshold",
            ],
            "qualification_conclusion_form": (
                "Report the observed descriptive profile and named failure modes; researcher decides whether "
                "a general pre-outcome resource/retriever repair is warranted. No binary automatic gate."
            ),
        },
        "candidate_level_structural_hard_exclusions": {
            "allowed_only_after_separate_deterministic_confirmation": [
                "identity/hash mismatch",
                "leave-dialogue-out/provenance failure",
                "non-atomic treatment",
                "explicit visible boundary conflict for that state-candidate pair",
                "mechanically non-executable treatment",
                "source-specific or outcome leakage",
            ],
            "never_hard_exclusion": [
                "human or LLM state-appropriateness opinion",
                "topic fit opinion",
                "visible redundancy",
                "near-duplicate semantic similarity",
                "predicted helpfulness, utility, response quality, or likely uptake",
            ],
            "human_label_role": (
                "A human structural finding triggers an auditable deterministic adjudication; the human label "
                "alone is not an active runtime exclusion."
            ),
        },
        "review_blinding": {
            "reviewer_sees": ["blind item id", "visible state", "current user text", "exact treatment"],
            "reviewer_does_not_see_until_locked": [
                "rank",
                "cosine similarity",
                "family stratum",
                "provenance IDs",
                "PM identity",
                "future ESC arm",
                "Generator response/outcome",
                "evaluator score",
            ],
            "LLM_may_replace_human": False,
        },
        "review_form_rubric": {
            "atomicity": packet["rubric"]["atomicity"],
            "state_appropriateness": packet["rubric"]["state_appropriateness"],
            "boundary_compatibility": packet["rubric"]["boundary_compatibility"],
            "executability": packet["rubric"]["executability"],
            "leakage": packet["rubric"]["leakage"],
            "redundancy_near_duplicate": packet["rubric"]["redundancy_near_duplicate"],
            "per_item_final_QUALIFIED_NOT_QUALIFIED_label_used": False,
            "completion_instruction": (
                "For every blind_item_id, return exactly one CompletedSemanticsHumanReview row. "
                "Judge the six fixed dimensions and provide a rationale; do not score likely response "
                "quality, helpfulness, utility, or whether the PM should turn RS on."
            ),
        },
        "uptake_assignment_gate": {
            "human_review_must_cover_exact_64_item_set": True,
            "human_results_must_be_locked_before_key_join": True,
            "pool_filter": "separately confirmed structural validity only",
            "state_appropriateness_filter": False,
            "utility_filter": False,
            "current_status": "BLOCKED_PENDING_REAL_HUMAN_REVIEW",
        },
        "schema_sha256": {
            "BlindSemanticsReviewItem": _schema_hash(BlindSemanticsReviewItem),
            "CompletedSemanticsHumanReview": _schema_hash(CompletedSemanticsHumanReview),
            "StructuralAdjudication": _schema_hash(StructuralAdjudication),
        },
        "outcome_calls": 0,
    }
    _write_json(args.aggregate_rule, rule)

    # Bind hashes only after all three primary artifacts exist.
    readiness = {
        "protocol": "pm-paper1-rs-resource-qualification-readiness-v1",
        "status": "AUDIT_REQUIRED",
        "source_packet_sha256": source_packet_sha256,
        "aggregate_rule_sha256": sha256_file(args.aggregate_rule),
        "blind_review_sha256": sha256_file(args.blind_review),
        "blind_key_sha256": sha256_file(args.blind_key),
        "human_judgments_completed": packet["human_judgments_completed"],
        "LLM_judgments_completed": packet["LLM_judgments_completed"],
        "uptake_assignments_created": 0,
        "generator_calls": 0,
        "generator_api_cost_usd": 0.0,
        "blocking_reason": "real human semantics review has not been completed",
        "frozen_generator_identity_for_future_uptake": {
            "provider": "NVIDIA hosted NIM API",
            "base_url": "https://integrate.api.nvidia.com",
            "model": "meta/llama-3.1-8b-instruct",
            "api_key_env": "NVIDIA_API_KEY",
            "generation_identity_sha256": "ca7c97b11330d69a4ad8a33f2aa13b039e3870ec4ba7d2d9e17313db51deb849",
            "temperature": 0.0,
            "max_new_tokens": 256,
            "seed": None,
        },
        "future_live_call_gate": {
            "human_review_complete": False,
            "structural_adjudication_complete": False,
            "small_assignment_identity_frozen": False,
            "dedicated_generator_authorization_and_call_budget_bound": False,
            "attempt_ledger_bound": False,
        },
        "locks": {key: config[key]["status"] for key in config if key.endswith("OUTCOME_LOCK")},
        "outcome_calls": 0,
        "pm_training_runs": 0,
    }
    _write_json(args.readiness, readiness)
    print(
        json.dumps(
            {
                "blind_review": str(args.blind_review),
                "blind_key": str(args.blind_key),
                "aggregate_rule": str(args.aggregate_rule),
                "readiness": str(args.readiness),
                "human_review_blocked": True,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
