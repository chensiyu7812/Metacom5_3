#!/usr/bin/env python3
"""Finalize the Llama-only RQ0 decision from exact ESC-Eval evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = ROOT / "data" / "v3_authority"


REFERENCE_KEYS = {
    "Fluency": "fluency",
    "Expression": "diversity",
    "Empathy": "empathic",
    "Information": "suggestion",
    "Humanoid": "human",
    "Skill": "tech",
    "Overall": "overall",
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_qualification(
    *,
    contract: dict[str, Any],
    preflight: dict[str, Any],
    generation: dict[str, Any],
    score_preflight: dict[str, Any],
    scores: dict[str, Any],
    reference: dict[str, dict[str, int]],
) -> dict[str, Any]:
    expected_generation = preflight["run_identity"]
    expected_score = score_preflight["score_identity"]
    if generation["run_identity"] != expected_generation:
        raise RuntimeError("generation identity mismatch")
    if scores["source_generation_identity"] != expected_generation:
        raise RuntimeError("score source-generation identity mismatch")
    if scores["score_identity"] != expected_score:
        raise RuntimeError("score identity mismatch")

    operational_pass = (
        generation["status"] == "GENERATION_COMPLETE_READY_FOR_OFFICIAL_SCORING"
        and generation["complete_dialogues"] == 331
        and generation["successful_turns"] == 1655
        and generation["terminal_trajectories"] == 0
    )
    scoring_pass = (
        scores["status"] == "COMPLETE_OFFICIAL_PROFILE_PARSER_AUDIT_PASS"
        and scores["dialogues"] == 331
        and scores["dimension_calls"] == 2317
        and scores["parser_disagreements_where_exact_label_valid"] == 0
    )
    reference_rows = list(reference.values())
    reference_means = {
        name: sum(row[key] for row in reference_rows) / len(reference_rows)
        for name, key in REFERENCE_KEYS.items()
    }
    profile = {
        name: {
            "mean_0_to_4": dimension["official_legacy_mean_itt"],
            "distribution": dimension["official_legacy_distribution"],
            "repository_llama3_example_mean_n3": reference_means[name],
            "delta_vs_repository_example": (
                dimension["official_legacy_mean_itt"] - reference_means[name]
            ),
        }
        for name, dimension in scores["dimensions"].items()
    }
    complete = operational_pass and scoring_pass
    length_finishes = generation["provider_length_finishes"]
    result = {
        "protocol": "metacom-v3-rq0-llama31-8b-esc-eval-exact-qualification-v1",
        "status": (
            "RQ0_COMPLETE_LLAMA31_8B_FROZEN_FOR_PM_EFFECT_GENERATION"
            if complete
            else "RQ0_INCOMPLETE_DO_NOT_USE_GENERATOR"
        ),
        "candidate": contract["candidate"],
        "identities": {
            "generation": expected_generation,
            "score": expected_score,
        },
        "protocol_fidelity": {
            "status": "PASS" if complete else "FAIL",
            "esc_eval_commit": contract["official_interaction"]["source_commit"],
            "official_prompt_and_interaction_code": True,
            "official_role_model_and_generation": True,
            "official_llama_max_new_tokens": 256,
            "official_esc_rank_code_and_adapters": True,
            "disclosed_difference": contract["candidate"]["model_difference_disclosed"],
        },
        "operational_qualification": {
            "status": "PASS" if operational_pass else "FAIL",
            "complete_dialogues": generation["complete_dialogues"],
            "expected_dialogues": generation["cards"],
            "successful_turns": generation["successful_turns"],
            "expected_turns": generation["expected_turns"],
            "physical_failed_attempts_retried": generation["physical_failed_attempts"],
            "terminal_trajectories": generation["terminal_trajectories"],
            "provider_length_finishes": length_finishes,
            "provider_length_finish_rate": length_finishes / generation["expected_turns"],
        },
        "official_esc_rank_profile": profile,
        "scoring_integrity": {
            "status": "PASS" if scoring_pass else "FAIL",
            "dialogues": scores["dialogues"],
            "dimension_calls": scores["dimension_calls"],
            "exact_label_valid_calls": sum(
                row["exact_label_valid"] for row in scores["dimensions"].values()
            ),
            "parser_disagreements": scores["parser_disagreements_where_exact_label_valid"],
        },
        "reference_context": {
            "artifact": "ESC-Eval/score/llama3_en.json",
            "rows": len(reference_rows),
            "role": "WEAK_SANITY_REFERENCE_ONLY_NOT_A_BENCHMARK_POPULATION",
            "interpretation": (
                "The full 331-card Llama 3.1 profile closely reproduces the repository's "
                "three-row Llama 3 example profile; the tiny example cannot define a pass line."
            ),
        },
        "decision": {
            "formal_absolute_esc_eval_pass": "UNDEFINED_BY_OFFICIAL_REPOSITORY",
            "operational_protocol_pass": operational_pass,
            "quality_judgment": (
                "USABLE_OFFICIAL_LLAMA_PROFILE_WITH_HUMANOID_AND_LENGTH_CEILING_CAVEATS"
                if complete else "NOT_QUALIFIED"
            ),
            "selected_generator": (
                "llama31_8b_incumbent_esc_eval_exact" if complete else None
            ),
            "pm_effect_generation_authorized": complete,
            "selection_basis": (
                "Full official-protocol completion and a 331-card ESC-RANK profile consistent "
                "with the repository Llama example; no invented absolute threshold."
            ),
        },
        "claim_boundaries": {
            "esc_quality": "DESCRIPTIVE_OFFICIAL_ESC_RANK_PROFILE",
            "safety_or_clinical_quality": "NOT_ESTABLISHED",
            "human_preference": "NOT_ESTABLISHED_BY_ESC_RANK_ALONE",
            "cross_model_superiority": "NOT_TESTED_IN_THIS_LLAMA_ONLY_RUN",
        },
        "budget": {
            "qwen_calls": 0,
            "observed_api_usd": generation["observed_usd"],
        },
        "official_pass_line": None,
        "evidence_hashes": {
            "generation_ledger_sha256": generation["evidence_hashes"]["private_turn_ledger_sha256"],
            "official_result_sha256": generation["evidence_hashes"]["official_result_sha256"],
            "score_ledger_sha256": scores["score_ledger_sha256"],
        },
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--score-summary", required=True, type=Path)
    parser.add_argument(
        "--out",
        type=Path,
        default=AUTHORITY / "rq0_llama31_8b_esc_eval_exact_qualification_v1.json",
    )
    args = parser.parse_args()
    if args.out.exists():
        raise RuntimeError("qualification exists; refusing overwrite")
    report = build_qualification(
        contract=_load(AUTHORITY / "rq0_llama31_8b_esc_eval_exact_contract_v1.json"),
        preflight=_load(AUTHORITY / "rq0_llama31_8b_esc_eval_exact_preflight_v1.json"),
        generation=_load(AUTHORITY / "rq0_llama31_8b_esc_eval_exact_generation_closeout_v1.json"),
        score_preflight=_load(AUTHORITY / "rq0_llama31_8b_esc_eval_exact_score_preflight_v1.json"),
        scores=_load(args.score_summary),
        reference=_load(args.reference),
    )
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["decision"]["pm_effect_generation_authorized"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
