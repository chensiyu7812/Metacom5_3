#!/usr/bin/env python3
"""Run the sole diagnostic-only MP consensus LOGO OOF; never promote labels."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    balanced_accuracy_score, brier_score_loss, log_loss, recall_score,
    roc_auc_score, average_precision_score,
)
from sklearn.model_selection import LeaveOneGroupOut
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402

AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_v3_mp_consensus_diagnostic_logo_oof_phase_v1.json"
LABELS = ROOT / "outputs/pm_v1_5_paper1_v3_g4b3_mp_pre_adjudication_20260811/mp_consensus_labels.jsonl"
PRIVATE = ROOT / "outputs/pm_v1_5_paper1_v3_g4a_packet_v2_private_20260811/private_case_key.jsonl"
G3 = ROOT / "outputs/pm_v1_5_paper1_v3_g3_candidate_surface_audit_20260811/candidate_surface_diagnostics_unlabeled.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_mp_consensus_diagnostic_logo_oof_20260811"
SEED = 20260811
FEATURES = (
    "profile_field", "redundant", "candidate_age_sessions", "scope_match_level",
    "selection_score", "top1_top2_margin", "strict_past_pool_count",
)


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def pipeline(field_only: bool = False) -> Pipeline:
    categorical = [0]
    numeric = [] if field_only else list(range(1, len(FEATURES)))
    transformers: list[tuple[str, Any, list[int]]] = [
        ("field", OneHotEncoder(handle_unknown="ignore"), categorical)
    ]
    if numeric:
        transformers.append(("numeric", Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), numeric))
    return Pipeline([
        ("features", ColumnTransformer(transformers, remainder="drop")),
        ("logistic", LogisticRegression(C=0.10, penalty="l2", class_weight="balanced", solver="liblinear", max_iter=2000, random_state=SEED)),
    ])


def metrics(y: np.ndarray, p: np.ndarray, prior: np.ndarray) -> dict[str, Any]:
    pred = p >= 0.5
    return {
        "roc_auc": float(roc_auc_score(y, p)),
        "average_precision": float(average_precision_score(y, p)),
        "balanced_accuracy_at_0_5": float(balanced_accuracy_score(y, pred)),
        "recall_at_0_5": float(recall_score(y, pred, zero_division=0)),
        "specificity_at_0_5": float(recall_score(y, pred, pos_label=0, zero_division=0)),
        "brier": float(brier_score_loss(y, p)),
        "prevalence_brier": float(brier_score_loss(y, prior)),
        "brier_gain_vs_prevalence": float(brier_score_loss(y, prior) - brier_score_loss(y, p)),
        "log_loss": float(log_loss(y, np.clip(p, 1e-8, 1 - 1e-8))),
        "predicted_on": int(pred.sum()), "predicted_off": int((~pred).sum()),
    }


def main() -> None:
    authority = read(AUTHORITY)
    if authority["active_v3_phase"]["id"] != "MP_CONSENSUS_DIAGNOSTIC_LOGO_OOF":
        raise RuntimeError("diagnostic OOF is not active")
    phase = read(PHASE)
    binding = authority["active_v3_phase"]["active_phase_manifest"]
    if binding["path"] != str(PHASE.relative_to(ROOT)) or binding["sha256"] != sha256_file(PHASE):
        raise RuntimeError("phase binding drifted")
    for item in [*phase["input_bindings"], *phase["implementation_bindings"]]:
        if sha256_file(ROOT / item["path"]) != item["sha256"]:
            raise RuntimeError(f"binding drifted: {item['path']}")

    labels = [row for row in rows(LABELS) if row["primary_binary_label"] is not None]
    private = {row["case_key"]: row for row in rows(PRIVATE) if row["component"] == "MP"}
    g3 = {(row["state_id"], row["actual_rank1_id"]): row for row in rows(G3) if row["component"] == "MP" and row["candidate_present"]}
    data = []
    for label in labels:
        key = private[label["case_key"]]
        feature = g3[(label["state_id"], label["actual_rank1_id"])]
        values = [
            key["proxy_flags"]["profile_field"],
            int(key["proxy_flags"]["exact_profile_value_already_visible"]),
            feature["candidate_age_sessions"], feature["scope_match_level"],
            feature["selection_score"], feature["top1_top2_margin"],
            feature["strict_past_pool_count"],
        ]
        data.append({"case_key": label["case_key"], "state_id": label["state_id"], "group": label["split_group_key"], "y": int(label["primary_binary_label"]), "x": values})
    if len(data) != 136 or len({row["group"] for row in data}) != 17 or Counter(row["y"] for row in data) != Counter({0: 84, 1: 52}):
        raise RuntimeError("frozen diagnostic denominator drifted")
    x = np.asarray([row["x"] for row in data], dtype=object)
    y = np.asarray([row["y"] for row in data], dtype=int)
    groups = np.asarray([row["group"] for row in data], dtype=object)
    primary = np.full(len(y), np.nan)
    field_only = np.full(len(y), np.nan)
    prior = np.full(len(y), np.nan)
    fold_rows = []
    for fold, (train, test) in enumerate(LeaveOneGroupOut().split(x, y, groups), 1):
        if len(np.unique(y[train])) != 2 or len(set(groups[test])) != 1:
            raise RuntimeError("invalid LOGO fold")
        m = pipeline(False).fit(x[train], y[train])
        f = pipeline(True).fit(x[train], y[train])
        primary[test] = m.predict_proba(x[test])[:, 1]
        field_only[test] = f.predict_proba(x[test])[:, 1]
        prior[test] = float(y[train].mean())
        fold_rows.append({"fold": fold, "held_out_group": str(groups[test][0]), "n": len(test), "on": int(y[test].sum()), "off": int(len(test) - y[test].sum())})
    if any(np.isnan(array).any() for array in (primary, field_only, prior)):
        raise RuntimeError("OOF predictions incomplete")
    pooled = metrics(y, primary, prior)
    field_metrics = metrics(y, field_only, prior)
    rng = np.random.default_rng(SEED)
    group_ids = sorted(set(groups.tolist()))
    group_index = {g: np.flatnonzero(groups == g) for g in group_ids}
    boot = {"auc": [], "balanced_accuracy": [], "brier_gain": []}
    for _ in range(5000):
        sampled = rng.choice(group_ids, size=len(group_ids), replace=True)
        idx = np.concatenate([group_index[g] for g in sampled])
        if len(np.unique(y[idx])) != 2:
            continue
        boot["auc"].append(roc_auc_score(y[idx], primary[idx]))
        boot["balanced_accuracy"].append(balanced_accuracy_score(y[idx], primary[idx] >= 0.5))
        boot["brier_gain"].append(brier_score_loss(y[idx], prior[idx]) - brier_score_loss(y[idx], primary[idx]))
    ci = {key: {"low": float(np.quantile(values, 0.025)), "high": float(np.quantile(values, 0.975))} for key, values in boot.items()}
    predictions = []
    for i, row in enumerate(data):
        predictions.append({
            "protocol": "pm-v1.5-paper1-v3-mp-consensus-diagnostic-logo-oof-prediction-v1",
            "case_key": row["case_key"], "state_id": row["state_id"], "split_group_key": row["group"], "label": row["y"],
            "primary_probability": float(primary[i]), "field_only_probability": float(field_only[i]), "train_fold_prevalence": float(prior[i]),
        })
    OUT.mkdir(parents=True, exist_ok=False)
    pred_path = OUT / "oof_predictions.jsonl"
    write_jsonl(pred_path, predictions)
    report = {
        "protocol": "pm-v1.5-paper1-v3-mp-consensus-diagnostic-logo-oof-report-v1",
        "status": "MP_CONSENSUS_DIAGNOSTIC_OOF_COMPLETE_NO_FORMAL_PROMOTION",
        "scope": "high-confidence exact-consensus MP subpopulation only",
        "denominator": {"rows": 136, "groups": 17, "on": 52, "off": 84, "folds": 17},
        "model": {"features": list(FEATURES), "C": 0.10, "class_weight": "balanced", "threshold": 0.5, "split": "LeaveOneGroupOut", "seed": SEED},
        "primary_metrics": pooled, "field_only_metrics": field_metrics, "owner_cluster_bootstrap_95_ci": ci,
        "directional_checks": {
            "auc_above_chance_point": pooled["roc_auc"] > 0.5,
            "balanced_accuracy_above_chance_point": pooled["balanced_accuracy_at_0_5"] > 0.5,
            "brier_better_than_train_prevalence": pooled["brier_gain_vs_prevalence"] > 0,
            "primary_auc_at_least_field_only": pooled["roc_auc"] >= field_metrics["roc_auc"],
            "nondegenerate_predictions": pooled["predicted_on"] > 0 and pooled["predicted_off"] > 0,
        },
        "folds": fold_rows,
        "predictions": {"path": str(pred_path.relative_to(ROOT)), "sha256": sha256_file(pred_path)},
        "formal_label_route_remains_fail": True, "threshold_or_feature_selection_after_result": False,
        "api_calls": 0, "generator_calls": 0, "baseline_calls": 0, "external_calls": 0,
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
