#!/usr/bin/env python3
"""Build the M2 draft without selecting unresolved research values."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.paper1.core.freeze import (  # noqa: E402
    FreezeStatus,
    GeneratorStackBinding,
    PreOutcomeFreezeManifest,
    bind_artifact,
)


def _head_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def build() -> PreOutcomeFreezeManifest:
    memory_summary_path = (
        PROJECT
        / "data/paper1_public_memory/es_memeval_public_candidate_census_summary_v1.json"
    )
    memory_summary = json.loads(memory_summary_path.read_text(encoding="utf-8"))
    if memory_summary.get("candidate_source") != "accepted_semantic_memory_v6":
        raise RuntimeError(
            "formal pre-outcome draft requires the complete v6 semantic-memory census; "
            "legacy regex/string census is diagnostic only"
        )
    if not isinstance(memory_summary.get("semantic_compiler_source"), dict):
        raise RuntimeError("semantic-memory census is missing compiler artifact identity")
    feature_summary_path = (
        PROJECT
        / "data/paper1_public_memory/es_memeval_public_feature_readiness_audit_v1.json"
    )
    feature_summary = json.loads(feature_summary_path.read_text(encoding="utf-8"))
    feature_source = feature_summary.get("semantic_compiler_source")
    if not isinstance(feature_source, dict):
        raise RuntimeError("semantic feature-readiness report is missing compiler identity")
    if (
        memory_summary["semantic_compiler_source"].get("sha256")
        != feature_source.get("artifact_sha256")
    ):
        raise RuntimeError("semantic census/readiness compiler artifact mismatch")
    generator_sources = tuple(
        bind_artifact(PROJECT, path, role=role)
        for path, role in (
            ("src/metacom_pm/api.py", "NVIDIA NIM API client"),
            ("scripts/v3/46_run_rq0_llama31_8b_esc_eval_exact.py", "historical exact RQ0 runner"),
            ("src/metacom_pm/esc_rank_runtime.py", "ESC-RANK parsing/runtime"),
            ("src/metacom_pm/paper1/contracts.py", "paired outcome and shared contracts"),
            ("src/metacom_pm/paper1/core/freeze.py", "pre-outcome freeze validator"),
            ("src/metacom_pm/paper1/core/treatment.py", "Paper-1 treatment delivery"),
            ("src/metacom_pm/paper1/evaluation/official.py", "official metric surface"),
            (
                "src/metacom_pm/paper1/evaluation/effect_coding.py",
                "zero-outcome task-specific paired-effect coding",
            ),
            ("src/metacom_pm/paper1/evaluation/rq1.py", "RQ1 paired input cells"),
        )
    )
    official = tuple(
        bind_artifact(PROJECT, path, role=role)
        for path, role in (
            (
                "data/paper1_authority/esc_eval_english331_source_overlap_v1.jsonl",
                "ESC-Eval 331-card source slices",
            ),
            (
                "data/v3_authority/es_memeval_public_v1_0_0_1427_row_identity_v1.jsonl",
                "ES-MemEval public 1427 QA identity",
            ),
            (
                "data/paper1_public_rs/esconv_strategy_source_identity_dialogue_only_v2.jsonl",
                "ESConv train-only dialogue-visible RS source identity",
            ),
            (
                "data/paper1_public_rs/esconv_rs_decision_state_identity_v1.jsonl",
                "ESConv outcome-blind RS decision-state identity",
            ),
            (
                "data/paper1_public_rs/esconv_rs_zero_outcome_census_summary_v1.json",
                "ESConv RS Phase-1 zero-outcome census summary",
            ),
            (
                "data/paper1_public_rs/esconv_rs_retriever_comparison_summary_v1.json",
                "RS lexical/BGE-small/BGE-M3 zero-outcome behavior comparison",
            ),
            (
                "data/paper1_evaluator_only_rs/esconv_rs_strategy_family_match_summary_v1.json",
                "evaluator-only ESConv strategy-family retriever diagnostic",
            ),
            (
                "data/paper1_public_rs/esconv_rs_renderer_card_audit_v1.jsonl",
                "text-free per-card RS renderer token and exemplar-shape audit",
            ),
            (
                "data/paper1_public_rs/esconv_rs_renderer_boundary_audit_v1.json",
                "RS renderer-token and explicit-boundary zero-outcome decision surface",
            ),
            (
                "data/paper1_authority/paper1_official_scorer_surface_audit_v1.json",
                "pinned official scorer source and effect-surface audit",
            ),
            (
                "data/paper1_authority/paper1_local_environment_attestation_v1.json",
                "zero-outcome local runtime, tokenizer, and encoder capability attestation",
            ),
            (
                "data/paper1_authority/paper1_official_rag_runtime_attestation_v1.json",
                "ES-MemEval Official RAG BGE-M3 plus FAISS Top-4 engineering attestation",
            ),
            (
                "data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json",
                "gold-free ES-MemEval runtime state and visible history",
            ),
            (
                "data/paper1_public_memory/es_memeval_public_targets_v1.jsonl",
                "opaque public RQ2 target identities",
            ),
            (
                "data/paper1_public_memory/es_memeval_public_candidate_census_v1.jsonl",
                "MP/MS/ME strict-past candidate census",
            ),
            (
                "data/paper1_public_memory/es_memeval_public_candidate_census_summary_v1.json",
                "MP/MS/ME zero-outcome candidate census summary",
            ),
            (
                "data/paper1_public_memory/es_memeval_public_feature_readiness_audit_v1.json",
                "memory outcome-blind feature inventory and implementation gaps",
            ),
            (
                "data/paper1_public_memory/es_memeval_public_group_component_assignments_v1.jsonl",
                "exact-evidence atomic grouping before outer-fold packing",
            ),
            (
                "data/paper1_public_memory/es_memeval_public_outer_fold_packing_surface_summary_v1.json",
                "zero-outcome structural outer-fold packing surface",
            ),
            (
                "data/paper1_public_memory/es_memeval_public_official_visibility_audit_v1.json",
                "pinned official RQ2 task-arm visibility and baseline contract",
            ),
            (
                "data/paper1_public_memory/es_memeval_public_me_candidate_audit_v1.json",
                "legacy same-turn regex ME diagnostic only, not formal candidate source",
            ),
        )
    )
    return PreOutcomeFreezeManifest(
        status=FreezeStatus.DRAFT,
        source_tree_sha=_head_sha(),
        generator=GeneratorStackBinding(
            provider="NVIDIA hosted NIM",
            model="meta/llama-3.1-8b-instruct",
            route="build.nvidia.com/v1/chat/completions",
            source_artifacts=generator_sources,
        ),
        official_evaluation_artifacts=official,
        pending_items=(
            "complete_and_bind_v6_semantic_memory_compiler_artifact",
            "bind_candidate_compiler_identity_into_five_fold_artifacts",
            "freeze_final_candidate_bundle_per_head",
            "freeze_rs_effect_state_overlap_policy",
            "freeze_rs_retriever_after_reviewing_zero_outcome_behavior_surface",
            "freeze_official_rag_local_bge_m3_revision_with_unpinned_upstream_disclosure",
            "bind_task_specific_official_rag_prompt_and_truncation_wrappers",
            "freeze_rs_guidance_only_vs_guidance_plus_exemplar",
            "freeze_rs_boundary_horizon_and_candidate_mapping",
            "verify_nvidia_nim_tokenizer_parity_and_freeze_resource_token_cap",
            "freeze_exact_feature_schema_per_head",
            "materialize_exact_evidence_components_into_five_outer_folds_seed_zero",
            "freeze_inner_fold_count",
            "bind_new_paper1_generation_runners_and_prompt_templates",
            "freeze_decoding_and_max_tokens",
            "freeze_effect_seed_schedule",
            "freeze_project_multi_metric_effect_coding_rule",
            "freeze_exact_rs_pairwise_and_es_memeval_scorer_identities",
            "freeze_matched_random_seed_and_proposals",
            "materialize_api_call_plan",
        ),
        notes={
            "purpose": "configuration/provenance completeness, not an empirical PASS gate",
            "formal_unlock": False,
            "rq0_historical_dependency_disclosure": (
                "data/v3_authority/rq0_llama31_8b_integration_dependency_closure_v1.json"
            ),
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out",
        type=Path,
        default=PROJECT / "data/paper1_authority/paper1_pre_outcome_freeze_draft_v1.json",
    )
    args = parser.parse_args()
    manifest = build()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
