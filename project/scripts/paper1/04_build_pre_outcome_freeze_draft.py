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
                "data/paper1_authority/esconv_strategy_source_identity_v1.jsonl",
                "ESConv train-only RS source identity",
            ),
            (
                "data/paper1_authority/paper1_official_scorer_surface_audit_v1.json",
                "pinned official scorer source and effect-surface audit",
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
            "integrate_repaired_public_memory_census",
            "freeze_final_candidate_bundle_per_head",
            "freeze_exact_feature_schema_per_head",
            "pack_exact_evidence_components_into_outer_folds",
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
