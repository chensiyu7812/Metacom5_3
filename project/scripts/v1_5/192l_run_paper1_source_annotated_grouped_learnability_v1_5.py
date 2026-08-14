#!/usr/bin/env python3
"""Run one frozen low-capacity grouped-OOF learnability qualification."""

from __future__ import annotations

from collections import Counter
import json
import math
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
from scipy.sparse import csr_matrix, hstack  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import balanced_accuracy_score, brier_score_loss, recall_score  # noqa: E402
from sklearn.model_selection import GroupKFold  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_source_annotated_grouped_learnability_phase_v1.json"
LABELS = ROOT / "outputs/pm_v1_5_paper1_source_annotated_labels_private_20260810/source_annotated_labels.jsonl"
RANK1 = ROOT / "outputs/pm_v1_5_paper1_p1b_actual_rank1/actual_rank1_unlabeled.jsonl"
SURFACE = ROOT / "outputs/pm_v1_5_paper1_p1_public_surface"
CARDS = ROOT / "data/strategy/strategy_cards_v1_5_minimal.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_source_annotated_grouped_learnability_20260810"
PRIVATE = ROOT / "outputs/pm_v1_5_paper1_source_annotated_grouped_learnability_private_20260810"
SEED = 20260810


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def visible_text(state: dict[str, Any]) -> str:
    dialogue = state.get("visible_dialogue") or state.get("visible_current_session_dialogue") or []
    return " ".join(f"{turn['speaker'].upper()} {turn['content']}" for turn in dialogue[-8:])


def build_rows() -> list[dict[str, Any]]:
    labels = rows(LABELS)
    rank = {(row["state_id"], row["component"]): row for row in rows(RANK1)}
    states = {row["state_id"]: row for path in (SURFACE / "esconv_states_unlabeled.jsonl", SURFACE / "evoemo_states_unlabeled.jsonl") for row in rows(path)}
    candidates = {row["candidate_id"]: row for row in rows(SURFACE / "evoemo_candidates_unlabeled.jsonl")}
    cards = {row["strategy_id"]: row for row in rows(CARDS)}
    result = []
    for label in labels:
        component = label["component"]
        state = states[label["state_id"]]
        # Official ESConv test remains outside this development qualification.
        if component == "RS" and state["split"] == "test":
            continue
        selected = rank[(label["state_id"], component)]
        if component == "RS":
            card = cards[selected["actual_rank1_id"]]
            candidate_text = card["guidance_text"]
            categorical = [
                "MOVE_" + selected["retrieval_observations"]["move_id"],
                "MODE_" + selected["retrieval_observations"]["selection_mode"],
                *[
                    "FLAG_" + key
                    for key, value in selected["retrieval_observations"].get("observable_flags", {}).items()
                    if value
                ],
            ]
            age = 0.0
        else:
            candidate = candidates[selected["actual_rank1_id"]]
            candidate_text = " ".join(
                str(value)
                for value in (candidate.get("literal_text"), candidate.get("action_span"), candidate.get("result_span"))
                if value
            )
            categorical = ["MEMORY_" + component, "SUBTYPE_" + candidate["subtype"]]
            age = float(state["source_session_index"] - candidate["available_after_session_index"])
        current = visible_text(state)
        result.append(
            {
                "state_id": label["state_id"],
                "component": component,
                "group": label["split_group_key"],
                "outer_partition": label["outer_partition"],
                "y": int(label["label_value"]),
                "text": " ".join([*categorical, "CURRENT", current, "CANDIDATE", candidate_text]),
                "numeric": [
                    float(selected["selection_score"]),
                    float(selected["top1_top2_margin"]),
                    math.log1p(float(selected["strict_past_pool_count"])),
                    math.log1p(float(state["raw_current_turn_index"])),
                    math.log1p(float(len(current.split()))),
                    math.log1p(float(len(candidate_text.split()))),
                    math.log1p(age),
                ],
            }
        )
    return result


def prior_correct(probability: np.ndarray, prevalence: float) -> np.ndarray:
    clipped = np.clip(probability, 1e-6, 1 - 1e-6)
    odds = clipped / (1 - clipped)
    corrected = odds * prevalence / max(1 - prevalence, 1e-9)
    return corrected / (1 + corrected)


def folds_for(component_rows: list[dict[str, Any]], component: str):
    if component == "RS":
        groups = np.array([row["group"] for row in component_rows])
        yield from GroupKFold(n_splits=5).split(np.arange(len(component_rows)), groups=groups)
    else:
        partitions = np.array([int(row["outer_partition"]) for row in component_rows])
        indices = np.arange(len(component_rows))
        for fold in range(1, 7):
            yield indices[partitions != fold], indices[partitions == fold]


def qualify(component_rows: list[dict[str, Any]], component: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    y = np.array([row["y"] for row in component_rows], dtype=int)
    raw_oof = np.full(len(y), np.nan)
    corrected_oof = np.full(len(y), np.nan)
    fold_ids = np.zeros(len(y), dtype=int)
    for fold_id, (train_idx, test_idx) in enumerate(folds_for(component_rows, component), 1):
        y_train = y[train_idx]
        if len(np.unique(y_train)) != 2 or len(test_idx) == 0:
            raise RuntimeError(f"{component} fold {fold_id} lacks train classes or test rows")
        vectorizer = TfidfVectorizer(
            lowercase=True,
            analyzer="word",
            ngram_range=(1, 2),
            min_df=3,
            max_features=3000,
            sublinear_tf=True,
        )
        train_text = vectorizer.fit_transform([component_rows[i]["text"] for i in train_idx])
        test_text = vectorizer.transform([component_rows[i]["text"] for i in test_idx])
        scaler = StandardScaler()
        train_num = scaler.fit_transform(np.array([component_rows[i]["numeric"] for i in train_idx]))
        test_num = scaler.transform(np.array([component_rows[i]["numeric"] for i in test_idx]))
        x_train = hstack([train_text, csr_matrix(train_num)], format="csr")
        x_test = hstack([test_text, csr_matrix(test_num)], format="csr")
        model = LogisticRegression(
            penalty="l2",
            C=0.25,
            class_weight="balanced",
            solver="liblinear",
            max_iter=1000,
            random_state=SEED,
        )
        model.fit(x_train, y_train)
        raw = model.predict_proba(x_test)[:, 1]
        raw_oof[test_idx] = raw
        corrected_oof[test_idx] = prior_correct(raw, float(y_train.mean()))
        fold_ids[test_idx] = fold_id
    if np.isnan(raw_oof).any() or (fold_ids == 0).any():
        raise RuntimeError(f"{component} OOF coverage incomplete")
    prediction = (raw_oof >= 0.5).astype(int)
    recall = recall_score(y, prediction, pos_label=1, zero_division=0)
    specificity = recall_score(y, prediction, pos_label=0, zero_division=0)
    balanced = balanced_accuracy_score(y, prediction)
    brier = brier_score_loss(y, corrected_oof)
    prevalence_brier = brier_score_loss(y, np.full(len(y), y.mean()))
    on_fraction = float(prediction.mean())
    checks = {
        "balanced_accuracy": balanced >= 0.60,
        "recall": recall >= 0.55,
        "specificity": specificity >= 0.55,
        "brier_beats_prevalence": brier < prevalence_brier,
        "predicted_on_fraction": on_fraction >= 0.15,
        "predicted_off_fraction": 1 - on_fraction >= 0.15,
    }
    metrics = {
        "status": "PASS" if all(checks.values()) else "FAIL_FIXED_OFF",
        "checks": checks,
        "n": len(y),
        "positive": int(y.sum()),
        "negative": int((1 - y).sum()),
        "groups": len({row["group"] for row in component_rows}),
        "balanced_accuracy": float(balanced),
        "recall": float(recall),
        "specificity": float(specificity),
        "brier": float(brier),
        "prevalence_brier": float(prevalence_brier),
        "predicted_on_fraction": on_fraction,
        "predicted_off_fraction": 1 - on_fraction,
        "threshold": 0.5,
    }
    oof = [
        {
            "state_id": row["state_id"],
            "component": component,
            "group": row["group"],
            "fold": int(fold_ids[index]),
            "label": int(y[index]),
            "raw_balanced_probability": float(raw_oof[index]),
            "prior_corrected_probability": float(corrected_oof[index]),
            "decision": int(prediction[index]),
        }
        for index, row in enumerate(component_rows)
    ]
    return metrics, oof


def main() -> None:
    if OUT.exists() or PRIVATE.exists():
        raise RuntimeError("learnability output exists; refusing overwrite")
    authority = read(AUTHORITY)
    current = authority["current_phase"]
    if current["id"] != "SOURCE_ANNOTATED_GROUPED_LEARNABILITY_PILOT":
        raise RuntimeError("learnability pilot is not active")
    if current["active_phase_manifest"]["sha256"] != sha256_file(PHASE):
        raise RuntimeError("learnability phase hash mismatch")
    phase = read(PHASE)
    for binding in [*phase["input_bindings"], *phase["implementation_bindings"]]:
        if sha256_file(ROOT / binding["path"]) != binding["sha256"]:
            raise RuntimeError(f"learnability binding drifted: {binding['path']}")
    joined = build_rows()
    metrics: dict[str, Any] = {"MP": {"status": "FAIL_FIXED_OFF", "reason": "no stable author gold"}}
    all_oof = []
    for component in ("RS", "MS", "ME"):
        component_rows = [row for row in joined if row["component"] == component]
        metrics[component], oof = qualify(component_rows, component)
        all_oof.extend(oof)
    passed = [component for component in ("RS", "MS", "ME") if metrics[component]["status"] == "PASS"]
    primary = "RS" in passed and any(component in passed for component in ("MS", "ME"))
    PRIVATE.mkdir(parents=True)
    oof_path = PRIVATE / "grouped_oof_predictions.jsonl"
    write_jsonl(oof_path, all_oof)
    OUT.mkdir(parents=True)
    report = {
        "protocol": "pm-v1.5-paper1-source-annotated-grouped-learnability-report-v1",
        "status": "PRIMARY_LEARNABILITY_PASS_FORMAL_FULL_FIT_MAY_BE_DESIGNED" if primary else "PRIMARY_LEARNABILITY_FAIL_NO_RESCUE_LOOP",
        "model": {
            "text": "word TF-IDF 1-2 grams, min_df=3, max_features=3000, sublinear_tf",
            "numeric": "7 runtime-only standardized scalars",
            "classifier": "L2 logistic regression C=0.25 class_weight=balanced liblinear",
            "decision_threshold": 0.5,
            "probability_reporting": "analytic training-prior correction; decisions use frozen balanced probability",
        },
        "development_scope": {"RS": "ESConv train+validation grouped 5-fold OOF; official test excluded", "MS_ME": "six connected-owner outer folds"},
        "head_metrics": metrics,
        "passed_heads": passed,
        "paper1_primary_predicate": "RS_pass AND count_pass(MP,MS,ME)>=1",
        "paper1_primary_pass": primary,
        "oof_predictions": {"path": str(oof_path.relative_to(ROOT)), "sha256": sha256_file(oof_path), "rows": len(all_oof)},
        "full_fit_checkpoint_created": False,
        "threshold_tuned": False,
        "api_calls": 0,
        "responses_or_external_outcomes": 0,
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
