#!/usr/bin/env python3
"""Run the sole frozen identity-free LOGO OOF for atomic MS suitability."""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys
from typing import Any

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    log_loss,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_v3_ms_atomic_teacher_logo_oof_phase_v1.json"
LABELS = ROOT / "outputs/pm_v1_5_paper1_v3_ms_single_teacher_label_freeze_20260811/ms_teacher_labels.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_ms_atomic_teacher_logo_oof_20260811"
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
RETRIEVAL_ONLY_FEATURES = (0, 1, 2, 3, 4)
VETO_ONLY_FEATURES = (5, 6)


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def model() -> Pipeline:
    return Pipeline([
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


def metrics(y: np.ndarray, probability: np.ndarray, prior: np.ndarray) -> dict[str, Any]:
    prediction = probability >= 0.5
    return {
        "roc_auc": float(roc_auc_score(y, probability)),
        "average_precision": float(average_precision_score(y, probability)),
        "balanced_accuracy_at_0_5": float(balanced_accuracy_score(y, prediction)),
        "recall_at_0_5": float(recall_score(y, prediction, zero_division=0)),
        "specificity_at_0_5": float(recall_score(y, prediction, pos_label=0, zero_division=0)),
        "brier": float(brier_score_loss(y, probability)),
        "prevalence_brier": float(brier_score_loss(y, prior)),
        "brier_gain_vs_train_prevalence": float(brier_score_loss(y, prior) - brier_score_loss(y, probability)),
        "log_loss": float(log_loss(y, np.clip(probability, 1e-8, 1 - 1e-8))),
        "prevalence_log_loss": float(log_loss(y, np.clip(prior, 1e-8, 1 - 1e-8))),
        "log_loss_gain_vs_train_prevalence": float(log_loss(y, np.clip(prior, 1e-8, 1 - 1e-8)) - log_loss(y, np.clip(probability, 1e-8, 1 - 1e-8))),
        "predicted_on": int(prediction.sum()),
        "predicted_off": int((~prediction).sum()),
        "predicted_on_fraction": float(prediction.mean()),
    }


def run_logo(x: np.ndarray, y: np.ndarray, groups: np.ndarray, columns: tuple[int, ...]) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    probability = np.full(len(y), np.nan)
    prior = np.full(len(y), np.nan)
    folds = []
    for fold, (train, test) in enumerate(LeaveOneGroupOut().split(x, y, groups), 1):
        if len(np.unique(y[train])) != 2 or len(set(groups[test])) != 1:
            raise RuntimeError("invalid LOGO fold")
        estimator = model().fit(x[train][:, columns], y[train])
        probability[test] = estimator.predict_proba(x[test][:, columns])[:, 1]
        prior[test] = float(y[train].mean())
        folds.append({
            "fold": fold,
            "held_out_group": str(groups[test][0]),
            "n": len(test),
            "on": int(y[test].sum()),
            "off": int(len(test) - y[test].sum()),
            "train_prevalence": float(y[train].mean()),
        })
    if np.isnan(probability).any() or np.isnan(prior).any():
        raise RuntimeError("OOF coverage incomplete")
    return probability, prior, folds


def main() -> None:
    if OUT.exists():
        raise RuntimeError("atomic MS OOF output exists; refusing overwrite")
    authority = read(AUTHORITY)
    active = authority["active_v3_phase"]
    if active["id"] != "MS_ATOMIC_TEACHER_LOGO_OOF":
        raise RuntimeError("atomic MS OOF is not active")
    binding = active["active_phase_manifest"]
    if binding["path"] != str(PHASE.relative_to(ROOT)) or binding["sha256"] != sha256_file(PHASE):
        raise RuntimeError("atomic MS OOF phase binding drifted")
    phase = read(PHASE)
    for item in [*phase["input_bindings"], *phase["implementation_bindings"]]:
        if sha256_file(ROOT / item["path"]) != item["sha256"]:
            raise RuntimeError(f"bound artifact drifted: {item['path']}")

    source = [row for row in rows(LABELS) if row["binary_suitability_label"] is not None]
    data = []
    for row in source:
        data.append({
            "case_key": row["case_key"],
            "state_id": row["state_id"],
            "actual_rank1_id": row["actual_rank1_id"],
            "group": row["split_group_key"],
            "y": int(row["binary_suitability_label"]),
            "x": [
                float(row["selection_score"]),
                float(row["top1_top2_margin"]),
                math.log1p(int(row["candidate_age_sessions"])),
                math.log1p(int(row["candidate_word_count"])),
                math.log1p(int(row["strict_past_pool_count"])),
                int(bool(row["low_information_rank1"])),
                int(bool(row["exact_or_containment_current_echo"])),
            ],
        })
    if len(data) != 201 or len({row["group"] for row in data}) != 17 or sum(row["y"] for row in data) != 73:
        raise RuntimeError("frozen atomic MS OOF denominator drifted")
    x = np.asarray([row["x"] for row in data], dtype=float)
    y = np.asarray([row["y"] for row in data], dtype=int)
    groups = np.asarray([row["group"] for row in data], dtype=object)

    primary, prior, folds = run_logo(x, y, groups, tuple(range(len(FEATURES))))
    retrieval, retrieval_prior, _ = run_logo(x, y, groups, RETRIEVAL_ONLY_FEATURES)
    veto, veto_prior, _ = run_logo(x, y, groups, VETO_ONLY_FEATURES)
    if not np.array_equal(prior, retrieval_prior) or not np.array_equal(prior, veto_prior):
        raise RuntimeError("comparator prevalence drift")
    primary_metrics = metrics(y, primary, prior)
    retrieval_metrics = metrics(y, retrieval, prior)
    veto_metrics = metrics(y, veto, prior)

    rng = np.random.default_rng(SEED)
    group_ids = sorted(set(groups.tolist()))
    group_index = {group: np.flatnonzero(groups == group) for group in group_ids}
    boot = {"auc": [], "balanced_accuracy": [], "brier_gain": [], "log_loss_gain": []}
    for _ in range(5000):
        sampled = rng.choice(group_ids, size=len(group_ids), replace=True)
        index = np.concatenate([group_index[str(group)] for group in sampled])
        if len(np.unique(y[index])) != 2:
            continue
        boot["auc"].append(roc_auc_score(y[index], primary[index]))
        boot["balanced_accuracy"].append(balanced_accuracy_score(y[index], primary[index] >= 0.5))
        boot["brier_gain"].append(brier_score_loss(y[index], prior[index]) - brier_score_loss(y[index], primary[index]))
        boot["log_loss_gain"].append(log_loss(y[index], np.clip(prior[index], 1e-8, 1 - 1e-8)) - log_loss(y[index], np.clip(primary[index], 1e-8, 1 - 1e-8)))
    ci = {
        name: {"low": float(np.quantile(values, 0.025)), "high": float(np.quantile(values, 0.975))}
        for name, values in boot.items()
    }

    directional = {
        "roc_auc_above_chance": primary_metrics["roc_auc"] > 0.5,
        "balanced_accuracy_above_chance": primary_metrics["balanced_accuracy_at_0_5"] > 0.5,
        "brier_beats_train_fold_prevalence": primary_metrics["brier_gain_vs_train_prevalence"] > 0,
        "log_loss_beats_train_fold_prevalence": primary_metrics["log_loss_gain_vs_train_prevalence"] > 0,
        "nondegenerate_on_and_off": primary_metrics["predicted_on"] > 0 and primary_metrics["predicted_off"] > 0,
    }
    signal_present = all(directional.values())
    predictions = [
        {
            "protocol": "pm-v1.5-paper1-v3-ms-atomic-teacher-logo-oof-prediction-v1",
            "case_key": row["case_key"],
            "state_id": row["state_id"],
            "actual_rank1_id": row["actual_rank1_id"],
            "split_group_key": row["group"],
            "teacher_label": row["y"],
            "primary_probability": float(primary[index]),
            "retrieval_only_probability": float(retrieval[index]),
            "veto_only_probability": float(veto[index]),
            "train_fold_prevalence": float(prior[index]),
            "decision_at_0_5": int(primary[index] >= 0.5),
        }
        for index, row in enumerate(data)
    ]
    OUT.mkdir(parents=True)
    prediction_path = OUT / "oof_predictions.jsonl"
    write_jsonl(prediction_path, predictions)
    report = {
        "protocol": "pm-v1.5-paper1-v3-ms-atomic-teacher-logo-oof-report-v1",
        "status": "MS_ATOMIC_TEACHER_OOF_SIGNAL_PRESENT_FULL_FIT_MAY_BE_DESIGNED" if signal_present else "MS_ATOMIC_TEACHER_OOF_SIGNAL_ABSENT_STOP_AND_DIAGNOSE",
        "estimand": "cross-group prediction of a qualified teacher's prospective suitability decision for the frozen actual atomic MS Rank-1 candidate",
        "denominator": {"resolved_rows": len(y), "abstentions_excluded": 3, "groups": 17, "on": int(y.sum()), "off": int((1 - y).sum()), "folds": 17},
        "model": {
            "features": list(FEATURES),
            "identity_text_and_ids_forbidden": True,
            "classifier": "StandardScaler + L2 logistic C=0.10 class_weight=balanced liblinear",
            "threshold": 0.5,
            "threshold_tuned": False,
            "feature_or_model_search_after_labels": False,
            "split": "LeaveOneConnectedGroupOut",
            "seed": SEED,
        },
        "primary_metrics": primary_metrics,
        "retrieval_only_metrics": retrieval_metrics,
        "veto_only_metrics": veto_metrics,
        "owner_cluster_bootstrap_95_ci": ci,
        "directional_viability_checks": directional,
        "interpretation_rule": "These are feasibility checks, not a paper success line. Final adequacy is determined by meaning-absorption executor qualification and same-stack Quality/Risk/Function/Cost comparisons.",
        "folds": folds,
        "predictions": {"path": str(prediction_path.relative_to(ROOT)), "sha256": sha256_file(prediction_path), "rows": len(predictions)},
        "teacher_not_human_gold": True,
        "full_fit_checkpoint_created": False,
        "api_calls": 0,
        "generator_calls": 0,
        "baseline_calls": 0,
        "external_test_reads": 0,
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
