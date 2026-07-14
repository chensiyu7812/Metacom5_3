#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from metacom_pm.freeze import create_study_freeze
from metacom_pm.io import sha256_file
from metacom_pm.pm_v2_judging import prompt_contract_hash
from metacom_pm.pm_v2_model import PMV2Model

ROOT = Path(__file__).resolve().parents[1]


def require_complete_report(path: Path) -> dict:
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("status") != "COMPLETE":
        raise RuntimeError(
            "PM-v2 cannot be frozen unless training status is COMPLETE; "
            f"got {report.get('status')}"
        )
    checks = report.get("reportability_checks") or {}
    if not checks or not all(bool(value) for value in checks.values()):
        raise RuntimeError(
            "PM-v2 cannot be frozen because internal reportability checks did not all pass: "
            + str(checks)
        )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-config", type=Path, default=ROOT / "configs" / "experiment.yaml")
    parser.add_argument("--pm-v2-config", type=Path, default=ROOT / "configs" / "pm_v2.yaml")
    parser.add_argument("--checkpoint", type=Path, default=ROOT / "outputs" / "pm_v2_model" / "pm_v2.joblib")
    parser.add_argument("--training-report", type=Path, default=ROOT / "outputs" / "pm_v2_model" / "training_report.json")
    parser.add_argument("--states", type=Path, default=ROOT / "data" / "pm_v2" / "pm_v2_states.jsonl")
    parser.add_argument("--data-report", type=Path, default=ROOT / "data" / "pm_v2" / "pm_v2_data_report.json")
    parser.add_argument("--seed-audit", type=Path, required=True)
    parser.add_argument("--labels", type=Path, default=ROOT / "outputs" / "pm_v2_judging" / "action_labels.jsonl")
    parser.add_argument("--judge-summary", type=Path, default=ROOT / "outputs" / "pm_v2_judging" / "summary.json")
    parser.add_argument("--data-label-audit", type=Path, default=ROOT / "outputs" / "pm_v2_judging" / "data_label_audit.json")
    parser.add_argument("--evoemo", type=Path, default=ROOT / "data" / "external" / "evo_emo.json")
    parser.add_argument("--strategy-bank", type=Path, default=ROOT / "data" / "strategy" / "strategy_cards.jsonl")
    parser.add_argument("--fixed-tracks", type=Path, default=ROOT / "outputs" / "evoemo_fixed_tracks" / "fixed_seeker_tracks.jsonl")
    parser.add_argument("--fixed-tracks-attestation", type=Path, default=ROOT / "outputs" / "evoemo_fixed_tracks" / "artifact_attestation.json")
    parser.add_argument("--out", type=Path, default=ROOT / "outputs" / "pm_v2_study_freeze.json")
    args = parser.parse_args()

    report = require_complete_report(args.training_report)
    model = PMV2Model.load(args.checkpoint)
    if report.get("selection_config_hash") != model.selection_config.digest():
        raise RuntimeError("training report selection hash does not match checkpoint")
    judge_summary = json.loads(args.judge_summary.read_text(encoding="utf-8"))
    if judge_summary.get("status") != "COMPLETE":
        raise RuntimeError("judge summary is not COMPLETE")
    if (judge_summary.get("quality_gate") or {}).get("status") != "PASS":
        raise RuntimeError("judge quality gate did not pass")
    label_audit = json.loads(args.data_label_audit.read_text(encoding="utf-8"))
    if label_audit.get("status") != "PASS":
        raise RuntimeError("data/label diversity audit did not pass")
    seed_audit = json.loads(args.seed_audit.read_text(encoding="utf-8"))
    if seed_audit.get("status") != "COMPLETE" or seed_audit.get("test_or_validation_rows_in_output") != 0:
        raise RuntimeError("seed lineage audit is incomplete or contains non-train rows")

    required = [
        args.experiment_config,
        args.pm_v2_config,
        args.checkpoint,
        args.training_report,
        args.states,
        args.data_report,
        args.seed_audit,
        args.labels,
        args.judge_summary,
        args.data_label_audit,
        args.evoemo,
        args.strategy_bank,
        args.fixed_tracks,
        args.fixed_tracks_attestation,
    ]
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(path)
    frozen = create_study_freeze(
        release_root=ROOT,
        config_path=args.experiment_config,
        checkpoint_paths=[args.checkpoint],
        data_paths=[
            args.pm_v2_config,
            args.training_report,
            args.states,
            args.data_report,
            args.seed_audit,
            args.labels,
            args.judge_summary,
            args.data_label_audit,
            args.evoemo,
            args.strategy_bank,
            args.fixed_tracks,
            args.fixed_tracks_attestation,
        ],
        prompt_files=[args.pm_v2_config],
        out_path=args.out,
        notes={
            "pm_version": model.format_version,
            "selection_config_hash": model.selection_config.digest(),
            "feature_config_hash": model.feature_builder.config_hash(),
            "judge_prompt_contract_hash": prompt_contract_hash(),
            "quality_composite_version": model.selection_config.composite_spec.version,
            "internal_reportability_checks": report["reportability_checks"],
            "checkpoint_sha256": sha256_file(args.checkpoint),
            "external_use": "fixed-input EvoEmo only; no calibration on external results",
        },
    )
    print(frozen)


if __name__ == "__main__":
    main()
