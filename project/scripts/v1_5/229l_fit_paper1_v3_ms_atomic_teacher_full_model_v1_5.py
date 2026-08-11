#!/usr/bin/env python3
"""Fit the frozen full-data atomic-MS suitability checkpoint after successful OOF."""

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
from metacom_pm.io import sha256_file, write_json  # noqa: E402


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_v3_ms_atomic_teacher_full_fit_phase_v1.json"
LABELS = ROOT / "outputs/pm_v1_5_paper1_v3_ms_single_teacher_label_freeze_20260811/ms_teacher_labels.jsonl"
OOF = ROOT / "outputs/pm_v1_5_paper1_v3_ms_atomic_teacher_logo_oof_20260811/report.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_ms_atomic_teacher_full_fit_20260811"
SEED = 20260811
FEATURES = (
    "selection_score",
    "top1_top2_margin",
    "log1p_candidate_age_sessions",
    "log1p_candidate_word_count",
    "log1p_strict_past_pool_count",
    "low_information_rank1",
    "exact_or_containment_current_echo",
)


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def vector(row: dict[str, Any]) -> list[float]:
    return [
        float(row["selection_score"]),
        float(row["top1_top2_margin"]),
        math.log1p(int(row["candidate_age_sessions"])),
        math.log1p(int(row["candidate_word_count"])),
        math.log1p(int(row["strict_past_pool_count"])),
        int(bool(row["low_information_rank1"])),
        int(bool(row["exact_or_containment_current_echo"])),
    ]


def main() -> None:
    if OUT.exists():
        raise RuntimeError("MS full-fit output exists; refusing overwrite")
    authority = read(AUTHORITY)
    active = authority["active_v3_phase"]
    if active["id"] != "MS_ATOMIC_TEACHER_FULL_FIT":
        raise RuntimeError("MS atomic full fit is not active")
    binding = active["active_phase_manifest"]
    if binding["path"] != str(PHASE.relative_to(ROOT)) or binding["sha256"] != sha256_file(PHASE):
        raise RuntimeError("MS full-fit phase binding drifted")
    phase = read(PHASE)
    for item in [*phase["input_bindings"], *phase["implementation_bindings"]]:
        if sha256_file(ROOT / item["path"]) != item["sha256"]:
            raise RuntimeError(f"bound artifact drifted: {item['path']}")
    oof = read(OOF)
    if oof["status"] != "MS_ATOMIC_TEACHER_OOF_SIGNAL_PRESENT_FULL_FIT_MAY_BE_DESIGNED":
        raise RuntimeError("OOF did not authorize full-fit design")
    if not all(oof["directional_viability_checks"].values()):
        raise RuntimeError("OOF viability checks are not all true")

    labels = [row for row in rows(LABELS) if row["binary_suitability_label"] is not None]
    if len(labels) != 201 or len({row["split_group_key"] for row in labels}) != 17:
        raise RuntimeError("MS full-fit denominator drifted")
    x = np.asarray([vector(row) for row in labels], dtype=float)
    y = np.asarray([int(row["binary_suitability_label"]) for row in labels], dtype=int)
    if int(y.sum()) != 73:
        raise RuntimeError("MS full-fit class distribution drifted")

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
    model_path = OUT / "ms_atomic_suitability_model.joblib"
    joblib.dump(estimator, model_path, compress=3)
    schema_path = OUT / "feature_schema.json"
    write_json(schema_path, {
        "protocol": "pm-v1.5-paper1-v3-ms-atomic-suitability-feature-schema-v1",
        "ordered_features": list(FEATURES),
        "transforms": {
            "candidate_age_sessions": "log1p",
            "candidate_word_count": "log1p",
            "strict_past_pool_count": "log1p",
            "booleans": "0_or_1",
            "pipeline": "StandardScaler then L2 logistic"
        },
        "decision_threshold": 0.5,
        "semantic_abstention_runtime_default": "OFF",
        "hard_no_candidate_runtime_default": "OFF",
        "forbidden_runtime_inputs": [
            "identity or group keys", "case/state/candidate identifiers as features",
            "raw dialogue text in this checkpoint", "teacher reason codes",
            "event timeline", "summary", "observation", "influenced_by", "QA answer", "QA evidence"
        ]
    })
    scaler = estimator.named_steps["scale"]
    logistic = estimator.named_steps["logistic"]
    report = {
        "protocol": "pm-v1.5-paper1-v3-ms-atomic-teacher-full-fit-report-v1",
        "status": "MS_ATOMIC_SUITABILITY_CHECKPOINT_FIT_EXECUTOR_QUALIFICATION_REQUIRED",
        "training_target": "qualified single-LLM-teacher prospective suitability for actual atomic MS Rank-1; not human gold and not response uplift",
        "denominator": {"resolved_rows": len(y), "groups": 17, "on": int(y.sum()), "off": int((1 - y).sum()), "abstentions_excluded": 3},
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
        "claim_boundary": "The MS selector is now trained. It is not yet a successful end-to-end PM until V3 meaning-absorption execution and same-stack outcomes pass.",
        "api_calls": 0,
        "generator_calls": 0,
        "baseline_calls": 0,
        "external_test_reads": 0,
        "next": "QUALIFY_V3_MS_MEANING_ABSORPTION_EXECUTOR_ON_FROZEN_ELIGIBLE_AND_INELIGIBLE_CASES",
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
