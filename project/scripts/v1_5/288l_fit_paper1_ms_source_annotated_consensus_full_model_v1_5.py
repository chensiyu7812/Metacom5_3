#!/usr/bin/env python3
"""Fit the frozen full-data MS suitability checkpoint for the new source-annotated
consensus construct, after the LOGO OOF (287l) authorized it."""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys
from typing import Any

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from metacom_pm.io import read_json, read_jsonl, sha256_file, write_json  # noqa: E402


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
BUNDLE = ROOT / "data/pm_v1_5_contracts/paper1_active_execution_bundle_v1.json"
CONSENSUS = ROOT / "outputs/pm_v1_5_paper1_ms_formal_201_labeling_audit_20260812/consensus_labels_private.jsonl"
PRIVATE_KEY = ROOT / "outputs/pm_v1_5_paper1_ms_supervision_repair_packet_private_20260812/ms_reannotation_private_key.jsonl"
TEACHER_FEATURES = ROOT / "outputs/pm_v1_5_paper1_v3_ms_single_teacher_label_freeze_20260811/ms_teacher_labels.jsonl"
OOF = ROOT / "outputs/pm_v1_5_paper1_ms_source_annotated_consensus_logo_oof_20260812/report.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_ms_source_annotated_consensus_full_fit_20260812"
SEED = 20260812
FEATURES = (
    "selection_score",
    "top1_top2_margin",
    "log1p_candidate_age_sessions",
    "log1p_candidate_word_count",
    "log1p_strict_past_pool_count",
    "low_information_rank1",
    "exact_or_containment_current_echo",
)


def main() -> None:
    if OUT.exists():
        raise RuntimeError("MS source-annotated consensus full-fit output exists; refusing overwrite")
    authority = read_json(AUTHORITY)
    current = authority["current_execution_phase"]
    alias = authority["active_v3_phase"]
    expected_bundle = {"path": str(BUNDLE.relative_to(ROOT)), "sha256": sha256_file(BUNDLE)}
    if current["id"] != "MS_FORMAL_201_LABELING_COMPLETE_127_LABELS_HEAD_TRAINING_DESIGN_NEXT" or current["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("formal-201-labeling-complete phase is not the current execution phase")
    if alias.get("compatibility_alias_of") != "current_execution_phase" or alias["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("authority compatibility alias drifted")

    oof = read_json(OOF)
    if oof["status"] != "MS_SOURCE_ANNOTATED_CONSENSUS_OOF_SIGNAL_PRESENT_FULL_FIT_MAY_BE_DESIGNED":
        raise RuntimeError("OOF did not authorize full-fit design")
    if not all(oof["directional_viability_checks"].values()):
        raise RuntimeError("OOF viability checks are not all true")

    consensus = read_jsonl(CONSENSUS)
    private_key = {row["repair_item_id"]: row for row in read_jsonl(PRIVATE_KEY)}
    teacher_features = {row["case_key"]: row for row in read_jsonl(TEACHER_FEATURES)}

    rows = []
    for row in consensus:
        key_row = private_key[row["repair_item_id"]]
        feat_row = teacher_features[key_row["case_key"]]
        rows.append({
            "y": 1 if row["consensus_binary_label"] == "USE" else 0,
            "x": [
                float(feat_row["selection_score"]),
                float(feat_row["top1_top2_margin"]),
                math.log1p(int(feat_row["candidate_age_sessions"])),
                math.log1p(int(feat_row["candidate_word_count"])),
                math.log1p(int(feat_row["strict_past_pool_count"])),
                int(bool(feat_row["low_information_rank1"])),
                int(bool(feat_row["exact_or_containment_current_echo"])),
            ],
            "group": key_row["split_group_key"],
        })
    if len(rows) != 127 or len({row["group"] for row in rows}) != 17:
        raise RuntimeError("MS source-annotated consensus full-fit denominator drifted")
    x = np.asarray([row["x"] for row in rows], dtype=float)
    y = np.asarray([row["y"] for row in rows], dtype=int)
    if int(y.sum()) != 34:
        raise RuntimeError("MS source-annotated consensus full-fit class distribution drifted")

    estimator = Pipeline([
        ("scale", StandardScaler()),
        ("logistic", LogisticRegression(
            C=0.10,
            penalty="l2",
            class_weight="balanced",
            solver="liblinear",
            max_iter=2000,
            random_state=SEED,
        )),
    ])
    estimator.fit(x, y)
    OUT.mkdir(parents=True)
    model_path = OUT / "ms_source_annotated_suitability_model.joblib"
    joblib.dump(estimator, model_path, compress=3)
    schema_path = OUT / "feature_schema.json"
    write_json(schema_path, {
        "protocol": "pm-v1.5-paper1-ms-source-annotated-suitability-feature-schema-v1",
        "ordered_features": list(FEATURES),
        "transforms": {
            "candidate_age_sessions": "log1p",
            "candidate_word_count": "log1p",
            "strict_past_pool_count": "log1p",
            "booleans": "0_or_1",
            "pipeline": "StandardScaler then L2 logistic",
        },
        "decision_threshold": 0.5,
        "semantic_abstention_runtime_default": "OFF",
        "hard_no_candidate_runtime_default": "OFF",
        "training_target": "binary_collapsed_exact_agreement_consensus (SEMANTIC_ABSTAIN merged into NOT_SUITABLE), not the retired single-LLM-teacher label",
        "forbidden_runtime_inputs": [
            "identity or group keys", "case/state/candidate identifiers as features",
            "raw dialogue text in this checkpoint", "reviewer reason codes",
            "event timeline", "summary", "observation", "influenced_by", "QA answer", "QA evidence",
        ],
    })
    scaler = estimator.named_steps["scale"]
    logistic = estimator.named_steps["logistic"]
    report = {
        "protocol": "pm-v1.5-paper1-ms-source-annotated-consensus-full-fit-report-v1",
        "status": "MS_SOURCE_ANNOTATED_SUITABILITY_CHECKPOINT_FIT_EXECUTOR_QUALIFICATION_REQUIRED",
        "training_target": "dual-qualified-reviewer (GPT-5.6 + Claude Haiku 4.5) binary-collapsed exact-agreement consensus for actual atomic MS Rank-1; not human gold and not response uplift",
        "denominator": {"resolved_rows": len(y), "groups": 17, "on": int(y.sum()), "off": int((1 - y).sum()), "excluded_disagreement_or_transport_failure": 74},
        "frozen_model": {"features": list(FEATURES), "C": 0.10, "class_weight": "balanced", "threshold": 0.5, "seed": SEED},
        "parameters": {
            "scaler_mean": [float(value) for value in scaler.mean_],
            "scaler_scale": [float(value) for value in scaler.scale_],
            "logistic_intercept": float(logistic.intercept_[0]),
            "standardized_coefficients": {feature: float(value) for feature, value in zip(FEATURES, logistic.coef_[0])},
        },
        "upstream_oof": {
            "path": str(OOF.relative_to(ROOT)),
            "sha256": sha256_file(OOF),
            "primary_metrics": oof["primary_metrics"],
            "bootstrap_95_ci": oof["owner_cluster_bootstrap_95_ci"],
        },
        "artifacts": {
            "checkpoint": {"path": str(model_path.relative_to(ROOT)), "sha256": sha256_file(model_path)},
            "feature_schema": {"path": str(schema_path.relative_to(ROOT)), "sha256": sha256_file(schema_path)},
        },
        "claim_boundary": "The MS selector is now trained on a real, dual-qualified-reviewer consensus construct. It is not yet a successful end-to-end PM until V3 meaning-absorption execution, per-head abstention calibration wiring, and same-stack outcomes pass.",
        "api_calls": 0,
        "generator_calls": 0,
        "baseline_calls": 0,
        "external_test_reads": 0,
        "next": "CALIBRATE_OUTER_TRAIN_ABSTENTION_THRESHOLDS_FOR_v1_5_head_semantic_abstention_THEN_QUALIFY_V3_MS_MEANING_ABSORPTION_EXECUTOR",
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
