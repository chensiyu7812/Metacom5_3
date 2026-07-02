#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from metacom_pm.config import confirmatory_model_independence, load_config
from metacom_pm.freeze import create_study_freeze
from metacom_pm.io import read_json


ROOT = Path(__file__).resolve().parents[1]


parser = argparse.ArgumentParser(
    description="Freeze EvoEmo balanced paired evidence audit evaluator code/config."
)
parser.add_argument("--config", type=Path, default=ROOT / "configs/experiment.yaml")
parser.add_argument(
    "--response-attestation",
    type=Path,
    default=ROOT / "outputs/evoemo_response_v4/artifact_attestation.json",
)
parser.add_argument(
    "--sample-plan",
    type=Path,
    default=ROOT / "outputs/evoemo_balanced_paired_audit_plan/audit_sample_plan.json",
)
parser.add_argument("--turns", type=Path, default=ROOT / "outputs/evoemo_selective/turns.jsonl")
parser.add_argument("--evoemo", type=Path, default=ROOT / "data/external/evo_emo.json")
parser.add_argument(
    "--checkpoint",
    type=Path,
    default=ROOT / "outputs/final_model_m2b_stable/pm_final.joblib",
)
parser.add_argument("--selection", type=Path, default=ROOT / "outputs/selection_stable.json")
parser.add_argument(
    "--out",
    type=Path,
    default=ROOT / "outputs/evoemo_balanced_paired_audit_eval_freeze.json",
)
args = parser.parse_args()

response_attestation = read_json(args.response_attestation)
if response_attestation.get("stage") != "evoemo_response_v4_full":
    raise RuntimeError(
        "response attestation is not the V4 full-run artifact: "
        f"{response_attestation.get('stage')}"
    )
response_attestation_sha256 = response_attestation.get("attestation_sha256")
if not response_attestation_sha256:
    raise RuntimeError("response attestation lacks attestation_sha256")

sample_plan = read_json(args.sample_plan)
if sample_plan.get("status") != "PLANNED_NO_API":
    raise RuntimeError(f"sample plan is not PLANNED_NO_API: {args.sample_plan}")
if sample_plan.get("protocol") != "evoemo_balanced_paired_evidence_audit_plan_v1":
    raise RuntimeError(
        "sample plan is not the balanced paired audit plan: "
        f"{sample_plan.get('protocol')}"
    )

plan_dir = args.sample_plan.parent
audit_items = plan_dir / "audit_items.jsonl"
audit_plan_md = plan_dir / "audit_sample_plan.md"
for path in (audit_items, audit_plan_md):
    if not path.is_file():
        raise FileNotFoundError(path)

model_independence = confirmatory_model_independence(load_config(args.config))
if not model_independence.get("ok"):
    raise RuntimeError(
        "Confirmatory model-family independence check failed:\n- "
        + "\n- ".join(model_independence.get("errors") or ["unknown error"])
    )

print(
    create_study_freeze(
        release_root=ROOT,
        config_path=args.config,
        checkpoint_paths=[args.checkpoint],
        data_paths=[
            args.evoemo,
            args.turns,
            args.response_attestation,
            args.sample_plan,
            audit_items,
            audit_plan_md,
            args.selection,
            args.checkpoint.with_suffix(args.checkpoint.suffix + ".attestation.json"),
            args.selection.with_suffix(args.selection.suffix + ".attestation.json"),
            ROOT / "outputs/evoemo_response_v4/response_summary.json",
            ROOT / "outputs/evoemo_response_v4/response_scores.jsonl",
            ROOT / "outputs/evoemo_response_v4/response_resource_summary.json",
            ROOT / "outputs/evoemo_response_v4/response_statistical_summary.json",
        ],
        prompt_files=[
            ROOT / "src/metacom_pm/evo_sampled_audit.py",
            ROOT / "scripts/17e_eval_evoemo_sampled_audit.py",
            ROOT / "scripts/17g_plan_evoemo_balanced_paired_audit.py",
        ],
        out_path=args.out,
        notes={
            "freeze_scope": "evoemo_balanced_paired_evidence_audit_evaluation",
            "response_attestation_sha256": response_attestation_sha256,
            "audit_policy": (
                "This freeze binds a balanced paired 50-unit audit plan. "
                "Each selected unit is audited for PM, strong_rule, "
                "best_fixed, and session_rag_rs. It does not authorize "
                "changing the sample after seeing audit outcomes."
            ),
            "primary_metric_policy": (
                "Primary evidence risk is any severity >= 2 among selected "
                "evidence misuse, unnecessary exposure, stale/conflict, and "
                "unsupported personal claim. Strategy omission/overuse are "
                "reported separately as secondary risks."
            ),
            "api_budget_policy": (
                "API runs must be preceded by a matching no-API dry-run and "
                "must pass --accept-cost-estimate-sha256 for the active mode."
            ),
            "pilot_gate_policy": (
                "Full paired audit requires a PASS pilot summary with matching "
                "model, model family, response attestation, evaluation freeze, "
                "and raw row retry threshold."
            ),
            "debug_exception": (
                "Unfrozen runs or --allow-unfrozen-debug outputs are non-reportable."
            ),
            "model_family_independence": model_independence,
        },
    )
)
