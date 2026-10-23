#!/usr/bin/env python3
"""Audit pinned official scorer sources without invoking any scorer."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[2]
ESC_COMMIT = "9ad46e7b5e247e824dae4633910eaa82be668beb"
MEM_COMMIT = "692624208acc077b8867698c1d6fcd998dee641a"
EXPECTED_HASHES = {
    "esc_eval": {
        "score.py": "1d775462adc7687d84ceb19d3648c3c917abf7ceed8b052b1fed8e4740f12724",
        "evaluate.py": "e66bda0e1093c2bec7c46daa6a64584cc6153e1f1bfde94b3fa2fd3c8f5629f8",
    },
    "es_memeval": {
        "src/lib/qa/qa_experiment.py": "0607d0316d508db0002fb63e18ab86f3dbd2119ec6d90978d7170ed3db99b1db",
        "src/lib/qa/qa_bert_score.py": "f30dd6579ef19b3e762add92df388d354160d2cc7d442a9823b4e04b8779e0e9",
        "src/lib/sum/sum_experiment.py": "93f8267f6aff734fd5f42a7fdd1844b2754e8f314d50d938663f4e1dc0ff6d0f",
        "src/lib/dg/dg_experiment.py": "aad049c2408042947a63ff75c6aebbb43c489340ad5809347ecac102e60c61bc",
        "src/exe/test_org_result.py": "eae09382ad99ede41855670400413fa331f0b2037a4d8a1e70f40be700aaf5f4",
        "src/exe/common_configurations.py": "13e3da404c834970a26849cd15634f8ed426f4b44fb4155aa90a7317648c02c6",
    },
}


def _git_head(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _verify_repo(repo: Path, expected_commit: str, expected_hashes: dict[str, str]) -> list[dict[str, str]]:
    if _git_head(repo) != expected_commit:
        raise RuntimeError(f"pinned repository commit mismatch: {repo}")
    records: list[dict[str, str]] = []
    for relative_path, expected_hash in expected_hashes.items():
        digest = hashlib.sha256((repo / relative_path).read_bytes()).hexdigest()
        if digest != expected_hash:
            raise RuntimeError(f"source hash mismatch: {relative_path}")
        records.append({"repo_relative_path": relative_path, "sha256": digest})
    return records


def build(esc_eval: Path, es_memeval: Path) -> dict[str, object]:
    esc_sources = _verify_repo(esc_eval, ESC_COMMIT, EXPECTED_HASHES["esc_eval"])
    mem_sources = _verify_repo(es_memeval, MEM_COMMIT, EXPECTED_HASHES["es_memeval"])
    return {
        "protocol": "paper1-official-scorer-surface-audit-v1",
        "status": "ZERO_OUTCOME_SOURCE_AUDIT_COMPLETE_CODING_AND_SCORER_FREEZE_PENDING",
        "outcome_calls": 0,
        "training_calls": 0,
        "official_sources": {
            "ESC-Eval": {"commit": ESC_COMMIT, "files": esc_sources},
            "ES-MemEval": {"commit": MEM_COMMIT, "files": mem_sources},
        },
        "effect_surfaces": {
            "esc_response": {
                "formal_capability_metrics": [
                    "Fluency", "Expression", "Empathy", "Information",
                    "Skillful", "Humanoid", "Overall",
                ],
                "official_raw_key_mapping": {
                    "fluency": "Fluency", "diversity": "Expression",
                    "empathic": "Empathy", "suggestion": "Information",
                    "tech": "Skillful", "human": "Humanoid", "overall": "Overall",
                },
                "scale": "integer_0_to_4",
                "training_effect_surface": "blind_pairwise_on_off_weak_supervision_only",
                "training_effect_scorer_status": "PENDING_EXACT_MODEL_PROMPT_PARSER_FREEZE",
                "official_seven_dimensions_are_not_the_rs_training_label": True,
                "runtime_overlay": {
                    "internlm2_revision": "c2ba64483dc50b3f8eb2d8271c4b9877a79ed2e2",
                    "esc_rank_revision": "450bf2eb5376c79e371aaf432925810243de1527",
                    "esc_role_revision": "2e2a4733d2e71da242f348aad165fe171acd5df7",
                    "parser": "strict_single_integer_0_to_4_project_overlay",
                },
            },
            "qa": {
                "official_metrics": ["F1", "BERTScore", "LLM_as_Judge"],
                "f1_definition": "set_overlap_of_normalized_tokens",
                "bert_model": "bert-base-uncased",
                "retrieval_diagnostics_excluded_from_effect_label": ["Recall_at_k", "nDCG_at_k"],
                "judge_model_in_official_code": "gpt-4o",
                "judge_model_revision_status": "PENDING_IMMUTABLE_IDENTITY",
            },
            "summary": {
                "official_metrics": [
                    "ROUGE_1", "ROUGE_2", "ROUGE_L", "Event_Precision",
                    "Event_Recall", "Event_F1", "LLM_Score",
                ],
                "event_f1_definition": "2*num_events_recalled/(num_events_reference+num_events_generated)",
                "reference_event_count_mismatch": "uncertain",
                "judge_model_in_official_code": "gpt-4o",
                "judge_model_revision_status": "PENDING_IMMUTABLE_IDENTITY",
            },
            "dialogue_generation": {
                "trajectory": "10_interaction_rounds_20_generated_role_utterances_plus_fixed_supporter_greeting",
                "observation_relevance_scale": "integer_1_to_3_shifted_to_weight_0_to_2",
                "observation_aggregation_turns": [1, 2, 3, 4, 5],
                "official_metrics": [
                    "Observation_Recall", "Weighted_Score", "LT_Memory",
                    "Personalization", "Emotional_Support",
                ],
                "overall_scale": "integer_1_to_5",
                "turn_judge_model_in_official_code": "mistralai/Mistral-Small-3.1-24B-Instruct-2503",
                "turn_judge_revision_status": "PENDING_LOCALLY_BOUND_WEIGHTS_REVISION",
                "overall_judge_model_in_official_code": "gpt-4o",
                "overall_judge_model_revision_status": "PENDING_IMMUTABLE_IDENTITY",
            },
        },
        "coding_contract": {
            "status": "PROJECT_PARETO_OVERLAY_DRAFT_AWAITING_EXPLICIT_PRE_OUTCOME_FREEZE",
            "implementation": "src/metacom_pm/paper1/evaluation/effect_coding.py",
            "proposed_multi_metric_rule": "on_or_off_only_when_every_non_tied_official_metric_has_one_direction; mixed_directions_uncertain; all_exactly_equal_equivalent",
            "official_rule_disclosure": "official_sources_produce_metric_vectors_but_do_not_define_this_paired_direction_overlay",
            "raw_outcomes": ["on_better", "off_better", "equivalent", "uncertain", "invalid"],
            "equivalent_target": 0,
            "uncertain_enters_likelihood": False,
            "invalid_enters_likelihood": False,
            "cost_in_label": False,
            "empirical_margin_or_pass_gate": False,
        },
        "unresolved_before_formal_effect_calls": [
            "explicitly_freeze_or_replace_project_multi_metric_pareto_coding_rule",
            "freeze_exact_rs_blind_pairwise_model_prompt_parser",
            "freeze_immutable_gpt4o_judge_identity_or_document_provider_snapshot_limitation",
            "bind_exact_mistral24b_turn_judge_weights_revision",
            "freeze_repeated_effect_seed_schedule",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--esc-eval", type=Path, required=True)
    parser.add_argument("--es-memeval", type=Path, required=True)
    parser.add_argument(
        "--out",
        type=Path,
        default=PROJECT / "data/paper1_authority/paper1_official_scorer_surface_audit_v1.json",
    )
    args = parser.parse_args()
    manifest = build(args.esc_eval.resolve(), args.es_memeval.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": manifest["status"], "outcome_calls": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
