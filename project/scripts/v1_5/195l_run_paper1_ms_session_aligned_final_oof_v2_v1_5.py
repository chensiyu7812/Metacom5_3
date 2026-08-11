#!/usr/bin/env python3
"""Run the single frozen grouped OOF for session-aligned MS V2."""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import balanced_accuracy_score, brier_score_loss, recall_score, roc_auc_score  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_paper1_session_aligned_ms import token_jaccard  # noqa: E402


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_ms_session_aligned_final_oof_phase_v2.json"
PUBLIC = ROOT / "outputs/pm_v1_5_paper1_ms_session_aligned_public_20260810"
PRIVATE_LABELS = ROOT / "outputs/pm_v1_5_paper1_ms_session_aligned_labels_private_20260810/ms_session_aligned_labels.jsonl"
OLD_REPORT = ROOT / "outputs/pm_v1_5_paper1_source_annotated_grouped_learnability_20260810/report.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_ms_session_aligned_final_oof_20260810"
PRIVATE_OUT = ROOT / "outputs/pm_v1_5_paper1_ms_session_aligned_final_oof_private_20260810"
SEED = 20260810


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def prior_correct(probability: np.ndarray, prevalence: float) -> np.ndarray:
    clipped = np.clip(probability, 1e-6, 1 - 1e-6)
    odds = clipped / (1 - clipped)
    corrected = odds * prevalence / max(1 - prevalence, 1e-9)
    return corrected / (1 + corrected)


def metrics(y: np.ndarray, probability: np.ndarray, corrected: np.ndarray) -> dict[str, float]:
    decision = (probability >= 0.5).astype(int)
    return {
        "balanced_accuracy": float(balanced_accuracy_score(y, decision)),
        "recall": float(recall_score(y, decision, pos_label=1, zero_division=0)),
        "specificity": float(recall_score(y, decision, pos_label=0, zero_division=0)),
        "roc_auc": float(roc_auc_score(y, probability)),
        "brier": float(brier_score_loss(y, corrected)),
        "prevalence_brier": float(brier_score_loss(y, np.full(len(y), y.mean()))),
        "predicted_on_fraction": float(decision.mean()),
        "predicted_off_fraction": float(1 - decision.mean()),
    }


def main() -> None:
    if OUT.exists() or PRIVATE_OUT.exists():
        raise RuntimeError("V2 final OOF output exists; refusing overwrite")
    authority = read(AUTHORITY)
    current = authority["current_phase"]
    if current["id"] != "MS_SESSION_ALIGNED_FINAL_OOF_V2":
        raise RuntimeError("V2 final OOF is not active")
    if current["active_phase_manifest"]["sha256"] != sha256_file(PHASE):
        raise RuntimeError("V2 final OOF phase binding drifted")
    phase = read(PHASE)
    for binding in [*phase["input_bindings"], *phase["implementation_bindings"]]:
        if sha256_file(ROOT / binding["path"]) != binding["sha256"]:
            raise RuntimeError(f"binding drifted: {binding['path']}")

    states = {row["state_id"]: row for row in rows(PUBLIC / "ms_checkpoint_states_unlabeled.jsonl")}
    candidates = {row["candidate_id"]: row for row in rows(PUBLIC / "ms_raw_session_candidates_unlabeled.jsonl")}
    rank1 = {row["state_id"]: row for row in rows(PUBLIC / "ms_actual_rank1_unlabeled.jsonl")}
    labels = rows(PRIVATE_LABELS)
    joined = []
    for label in labels:
        state = states[label["state_id"]]
        selected = rank1[label["state_id"]]
        candidate = candidates[selected["actual_rank1_id"]]
        age = int(state["source_session_index"]) - int(candidate["available_after_session_index"])
        joined.append(
            {
                "state_id": state["state_id"],
                "group": state["split_group_key"],
                "fold": int(state["outer_fold"]),
                "y": int(label["label_value"]),
                "x": [
                    float(selected["selection_score"]),
                    float(selected["top1_top2_margin"]),
                    math.log1p(age),
                    token_jaccard(str(state["visible_text"]), str(candidate["literal_text"])),
                ],
            }
        )
    y = np.array([row["y"] for row in joined], dtype=int)
    x = np.array([row["x"] for row in joined], dtype=float)
    partitions = np.array([row["fold"] for row in joined], dtype=int)
    raw_oof = np.full(len(y), np.nan)
    corrected_oof = np.full(len(y), np.nan)
    fold_ids = np.zeros(len(y), dtype=int)
    fold_metrics = []
    for fold in range(1, 7):
        train = np.flatnonzero(partitions != fold)
        test = np.flatnonzero(partitions == fold)
        if len(test) == 0 or len(np.unique(y[train])) != 2:
            raise RuntimeError(f"invalid outer fold {fold}")
        scaler = StandardScaler().fit(x[train])
        model = LogisticRegression(
            penalty="l2",
            C=0.10,
            class_weight="balanced",
            solver="liblinear",
            max_iter=1000,
            random_state=SEED,
        ).fit(scaler.transform(x[train]), y[train])
        raw = model.predict_proba(scaler.transform(x[test]))[:, 1]
        corrected = prior_correct(raw, float(y[train].mean()))
        raw_oof[test] = raw
        corrected_oof[test] = corrected
        fold_ids[test] = fold
        fold_metrics.append({"fold": fold, "n": len(test), **metrics(y[test], raw, corrected)})
    if np.isnan(raw_oof).any() or np.isnan(corrected_oof).any() or (fold_ids == 0).any():
        raise RuntimeError("OOF coverage incomplete")
    pooled = metrics(y, raw_oof, corrected_oof)
    groups = sorted(set(row["group"] for row in joined))
    group_metrics = []
    for group in groups:
        index = np.array([i for i, row in enumerate(joined) if row["group"] == group])
        group_metrics.append({"group": group, "n": len(index), "positive": int(y[index].sum()), **metrics(y[index], raw_oof[index], corrected_oof[index])})
    macro = {
        key: float(np.mean([row[key] for row in group_metrics]))
        for key in ("balanced_accuracy", "recall", "specificity", "brier", "prevalence_brier", "predicted_on_fraction", "predicted_off_fraction")
    }
    rng = np.random.default_rng(SEED)
    bootstrap_ba = []
    group_indices = {group: np.array([i for i, row in enumerate(joined) if row["group"] == group]) for group in groups}
    for _ in range(5000):
        sampled = rng.choice(groups, size=len(groups), replace=True)
        index = np.concatenate([group_indices[str(group)] for group in sampled])
        bootstrap_ba.append(balanced_accuracy_score(y[index], (raw_oof[index] >= 0.5).astype(int)))
    checks = {
        "balanced_accuracy": pooled["balanced_accuracy"] >= 0.60,
        "recall": pooled["recall"] >= 0.55,
        "specificity": pooled["specificity"] >= 0.55,
        "brier_beats_prevalence": pooled["brier"] < pooled["prevalence_brier"],
        "predicted_on_fraction": pooled["predicted_on_fraction"] >= 0.15,
        "predicted_off_fraction": pooled["predicted_off_fraction"] >= 0.15,
    }
    ms_pass = all(checks.values())
    old = read(OLD_REPORT)
    if old["head_metrics"]["RS"]["status"] != "PASS":
        raise RuntimeError("hash-bound carried RS evidence is not PASS")
    primary = ms_pass
    PRIVATE_OUT.mkdir(parents=True)
    oof_path = PRIVATE_OUT / "ms_grouped_oof_predictions.jsonl"
    write_jsonl(
        oof_path,
        [
            {
                "state_id": row["state_id"],
                "component": "MS",
                "group": row["group"],
                "fold": int(fold_ids[index]),
                "label": int(y[index]),
                "raw_balanced_probability": float(raw_oof[index]),
                "prior_corrected_probability": float(corrected_oof[index]),
                "decision": int(raw_oof[index] >= 0.5),
            }
            for index, row in enumerate(joined)
        ],
    )
    OUT.mkdir(parents=True)
    report = {
        "protocol": "pm-v1.5-paper1-ms-session-aligned-final-oof-report-v2",
        "status": "PRIMARY_LEARNABILITY_PASS_FULL_FIT_MAY_BE_DESIGNED" if primary else "PRIMARY_LEARNABILITY_FAIL_TERMINAL_NO_V3",
        "method_id": phase["method_id"],
        "carried_RS": {
            "status": "PASS",
            "source_report": str(OLD_REPORT.relative_to(ROOT)),
            "source_report_sha256": sha256_file(OLD_REPORT),
            "metrics": old["head_metrics"]["RS"],
        },
        "MS": {
            "status": "PASS" if ms_pass else "FAIL_FIXED_OFF",
            "checks": checks,
            "n": len(y),
            "positive": int(y.sum()),
            "negative": int((1 - y).sum()),
            "connected_owner_groups": len(groups),
            "pooled_oof": pooled,
            "equal_owner_macro": macro,
            "owner_cluster_bootstrap_balanced_accuracy_ci95": [float(np.quantile(bootstrap_ba, 0.025)), float(np.quantile(bootstrap_ba, 0.975))],
            "fold_metrics": fold_metrics,
            "owner_metrics": group_metrics,
            "threshold": 0.5,
        },
        "model": {
            "features": ["BGE-M3 selection score", "top1-top2 margin", "log1p memory age", "token Jaccard"],
            "classifier": "StandardScaler + L2 logistic C=0.10 class_weight=balanced liblinear",
            "threshold_tuned": False,
            "feature_or_model_search_after_V2_labels": False,
        },
        "head_status": {"RS": "PASS", "MS": "PASS" if ms_pass else "FAIL_FIXED_OFF", "MP": "FAIL_FIXED_OFF", "ME": "FAIL_FIXED_OFF"},
        "paper1_primary_predicate": "RS_pass AND MS_pass",
        "paper1_primary_pass": primary,
        "oof_predictions": {"path": str(oof_path.relative_to(ROOT)), "sha256": sha256_file(oof_path), "rows": len(y)},
        "full_fit_checkpoint_created": False,
        "api_calls": 0,
        "response_or_external_outcomes": 0,
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
