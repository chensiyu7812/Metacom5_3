#!/usr/bin/env python3
"""Run the first LOGO OOF for the new source-annotated MS suitability construct.

Target: the 127-item binary-collapsed exact-agreement consensus label
(consensus_labels_private.jsonl), produced by the qualified GPT-5.6 +
Claude Haiku 4.5 reviewer pairing -- a materially stricter, source-attributed
construct than the old "development provenance, not repaired gold"
single-LLM-teacher binary_suitability_label used by the retired
228l/229l pipeline. Reuses that pipeline's exact model/validation
machinery (StandardScaler + L2 logistic, LeaveOneGroupOut by
split_group_key, owner-cluster bootstrap 95% CI) because the 7 candidate-
level structural features (selection_score, margin, age, word count, pool
count, low-information flag, echo flag) are retrieval-mechanical and
construct-independent -- they don't encode the suitability judgment itself,
so reusing them isn't reusing the old (superseded) label.

Zero API calls, zero generator calls -- this is a local fit over
already-collected real data.
"""

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
from metacom_pm.io import read_json, read_jsonl, sha256_file, write_json, write_jsonl  # noqa: E402


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
BUNDLE = ROOT / "data/pm_v1_5_contracts/paper1_active_execution_bundle_v1.json"
CONSENSUS = ROOT / "outputs/pm_v1_5_paper1_ms_formal_201_labeling_audit_20260812/consensus_labels_private.jsonl"
PRIVATE_KEY = ROOT / "outputs/pm_v1_5_paper1_ms_supervision_repair_packet_private_20260812/ms_reannotation_private_key.jsonl"
TEACHER_FEATURES = ROOT / "outputs/pm_v1_5_paper1_v3_ms_single_teacher_label_freeze_20260811/ms_teacher_labels.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_ms_source_annotated_consensus_logo_oof_20260812"
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
RETRIEVAL_ONLY_FEATURES = (0, 1, 2, 3, 4)
VETO_ONLY_FEATURES = (5, 6)


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
        raise RuntimeError("source-annotated MS consensus OOF output exists; refusing overwrite")
    authority = read_json(AUTHORITY)
    current = authority["current_execution_phase"]
    alias = authority["active_v3_phase"]
    expected_bundle = {"path": str(BUNDLE.relative_to(ROOT)), "sha256": sha256_file(BUNDLE)}
    if current["id"] != "MS_FORMAL_201_LABELING_COMPLETE_127_LABELS_HEAD_TRAINING_DESIGN_NEXT" or current["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("formal-201-labeling-complete phase is not the current execution phase")
    if alias.get("compatibility_alias_of") != "current_execution_phase" or alias["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("authority compatibility alias drifted")

    consensus = read_jsonl(CONSENSUS)
    private_key = {row["repair_item_id"]: row for row in read_jsonl(PRIVATE_KEY)}
    teacher_features = {row["case_key"]: row for row in read_jsonl(TEACHER_FEATURES)}

    data = []
    for row in consensus:
        key_row = private_key[row["repair_item_id"]]
        feat_row = teacher_features[key_row["case_key"]]
        data.append({
            "repair_item_id": row["repair_item_id"],
            "case_key": key_row["case_key"],
            "state_id": key_row["state_id"],
            "actual_rank1_id": key_row["actual_rank1_id"],
            "group": key_row["split_group_key"],
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
        })
    if len(data) != 127 or len({row["group"] for row in data}) != 17 or sum(row["y"] for row in data) != 34:
        raise RuntimeError("frozen source-annotated MS consensus OOF denominator drifted")
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
    skipped_single_class_resamples = 0
    for _ in range(5000):
        sampled = rng.choice(group_ids, size=len(group_ids), replace=True)
        index = np.concatenate([group_index[str(group)] for group in sampled])
        if len(np.unique(y[index])) != 2:
            skipped_single_class_resamples += 1
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
            "protocol": "pm-v1.5-paper1-ms-source-annotated-consensus-logo-oof-prediction-v1",
            "repair_item_id": row["repair_item_id"],
            "case_key": row["case_key"],
            "state_id": row["state_id"],
            "actual_rank1_id": row["actual_rank1_id"],
            "split_group_key": row["group"],
            "consensus_label": row["y"],
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
        "protocol": "pm-v1.5-paper1-ms-source-annotated-consensus-logo-oof-report-v1",
        "status": "MS_SOURCE_ANNOTATED_CONSENSUS_OOF_SIGNAL_PRESENT_FULL_FIT_MAY_BE_DESIGNED" if signal_present else "MS_SOURCE_ANNOTATED_CONSENSUS_OOF_SIGNAL_ABSENT_STOP_AND_DIAGNOSE",
        "estimand": "cross-group prediction of the binary-collapsed dual-qualified-reviewer exact-agreement consensus decision for the frozen actual atomic MS Rank-1 candidate",
        "denominator": {"resolved_rows": len(y), "excluded_disagreement_or_transport_failure": 74, "groups": 17, "on": int(y.sum()), "off": int((1 - y).sum()), "folds": 17},
        "model": {
            "features": list(FEATURES),
            "identity_text_and_ids_forbidden": True,
            "classifier": "StandardScaler + L2 logistic C=0.10 class_weight=balanced liblinear",
            "threshold": 0.5,
            "threshold_tuned": False,
            "feature_or_model_search_after_labels": False,
            "split": "LeaveOneGroupOut",
            "seed": SEED,
            "bootstrap_resamples_skipped_single_class": skipped_single_class_resamples,
        },
        "primary_metrics": primary_metrics,
        "retrieval_only_metrics": retrieval_metrics,
        "veto_only_metrics": veto_metrics,
        "owner_cluster_bootstrap_95_ci": ci,
        "directional_viability_checks": directional,
        "interpretation_rule": "These are feasibility checks, not a paper success line. Final adequacy is determined by meaning-absorption executor qualification and same-stack Quality/Risk/Function/Cost comparisons.",
        "comparison_to_old_construct": {
            "old_atomic_teacher_oof": "outputs/pm_v1_5_paper1_v3_ms_atomic_teacher_logo_oof_20260811/report.json",
            "old_balanced_accuracy_at_0_5": 0.7449165239726028,
            "note": "Not directly comparable: old construct used all 201 items with a looser single-LLM-teacher label; this run uses only the 127 items where two independently qualified reviewers reached binary-collapsed exact agreement on the new source-attributed construct. Fewer rows, stricter label, different prevalence (34/127=26.8% vs 73/201=36.3%).",
        },
        "folds": folds,
        "predictions": {"path": str(prediction_path.relative_to(ROOT)), "sha256": sha256_file(prediction_path), "rows": len(predictions)},
        "consensus_not_human_gold": True,
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
