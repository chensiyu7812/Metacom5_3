#!/usr/bin/env python3
"""Run the frozen zero-outcome bounded semantic observability test."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import numpy as np  # noqa: E402
from metacom_pm.io import sha256_file, stable_hex, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_v5_3_semantic_ms_retrieval import BgeM3Encoder, DEFAULT_BGE_M3_SNAPSHOT  # noqa: E402

PROTOCOL = "pm-v1.5-v5.4-bounded-semantic-observability-v1"
RUNTIME = ROOT / "outputs/pm_v1_5_v5_4_v4_state_local_actual_rank1_20260810/runtime_state_candidate_surface_no_ids_no_assignment.jsonl"
ASSIGN = ROOT / "outputs/pm_v1_5_v5_4_state_local_authoring_v4_20260810/construction_assignment_private_do_not_join.jsonl"
FIDELITY = ROOT / "outputs/pm_v1_5_v5_4_v4_fidelity_v2_20260810/fidelity_v2_final_resolved_report.json"
CONTRACT = ROOT / "data/pm_v1_5_contracts/v5_4_bounded_semantic_observability_v1.json"
OUT = ROOT / "outputs/pm_v1_5_v5_4_bounded_semantic_observability_20260810"
COMPONENTS = ("MP", "MS", "ME", "RS")
RIDGE = 10.0
PCS = 3


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def metrics(y: np.ndarray, pred: np.ndarray) -> dict:
    tp = int(np.sum((y == 1) & (pred == 1)))
    tn = int(np.sum((y == -1) & (pred == -1)))
    fp = int(np.sum((y == -1) & (pred == 1)))
    fn = int(np.sum((y == 1) & (pred == -1)))
    sensitivity = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    def f1(pos: int, false_pos: int, false_neg: int) -> float:
        return 2 * pos / (2 * pos + false_pos + false_neg) if 2 * pos + false_pos + false_neg else 0.0
    return {
        "n": int(len(y)), "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "balanced_accuracy": (sensitivity + specificity) / 2,
        "macro_f1": (f1(tp, fp, fn) + f1(tn, fn, fp)) / 2,
        "prediction_counts": {"INCREMENTAL": int(np.sum(pred == 1)), "LOW_OPPORTUNITY": int(np.sum(pred == -1))},
    }


def standardize(train: np.ndarray, test: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    mean = train.mean(axis=0)
    scale = train.std(axis=0)
    scale[scale < 1e-8] = 1.0
    return (train - mean) / scale, (test - mean) / scale


def ridge_predict(train_x: np.ndarray, train_y: np.ndarray, test_x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    train_z, test_z = standardize(train_x, test_x)
    train_design = np.column_stack([np.ones(len(train_z)), train_z])
    test_design = np.column_stack([np.ones(len(test_z)), test_z])
    penalty = np.eye(train_design.shape[1]) * RIDGE
    penalty[0, 0] = 0.0
    weights = np.linalg.solve(train_design.T @ train_design + penalty, train_design.T @ train_y)
    scores = test_design @ weights
    pred = np.where(scores >= 0.0, 1, -1)
    return scores, pred


def semantic_fold_features(train_raw: np.ndarray, test_raw: np.ndarray, train_cos: np.ndarray, test_cos: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    center = train_raw.mean(axis=0)
    train_centered = train_raw - center
    _u, _s, vt = np.linalg.svd(train_centered, full_matrices=False)
    basis = vt[:PCS].T
    train_pc = train_centered @ basis
    test_pc = (test_raw - center) @ basis
    return np.column_stack([train_pc, train_cos]), np.column_stack([test_pc, test_cos])


def nuisance(text: str, *, author: str, variant: str) -> list[float]:
    return [
        float(len(text.split())), float(len(text)), float(text.count("?")),
        float(len(re.findall(r"[,.!?;:]", text))),
        float(author == "openai_gpt_5_mini"), float(variant == "B"),
    ]


def normalize_current_text(text: str) -> str:
    return " ".join(text.casefold().split())


def main() -> None:
    contract = json.loads(CONTRACT.read_text())
    fidelity = json.loads(FIDELITY.read_text())
    if fidelity["status"] != "V4_FIDELITY_V2_FINAL_PASS_BOUNDED_OBSERVABILITY_AUTHORIZED":
        raise RuntimeError("fidelity did not authorize observability")
    if not contract["authorization"]["embedding_and_zero_api_observability_test"]:
        raise RuntimeError("observability test not authorized")
    runtime_rows = rows(RUNTIME)
    assignments = {row["pair_id"]: row for row in rows(ASSIGN)}
    authoring_rows = rows(ROOT / "outputs/pm_v1_5_v5_4_state_local_authoring_v4_20260810/authoring_v4_packet_private_outcome_blind.jsonl")
    author_by_pair = {row["pair_id"]: row["assigned_author_endpoint"] for row in authoring_rows}
    if len(runtime_rows) != 96 or len(assignments) != 48:
        raise RuntimeError("observability identities incomplete")
    ordered = sorted(runtime_rows, key=lambda row: row["state_id"])
    texts = []
    for row in ordered:
        if not row["candidate_present"] or not row["actual_rank1_candidate_text"]:
            raise RuntimeError("candidate absent after passed state-local gate")
        texts.extend([row["current_user_text"], row["actual_rank1_candidate_text"]])
    encoder = BgeM3Encoder(DEFAULT_BGE_M3_SNAPSHOT)
    vectors = encoder.encode(texts)
    current = vectors[0::2]
    candidate = vectors[1::2]
    raw = np.concatenate([current, candidate, current - candidate, current * candidate], axis=1)
    cosine = np.sum(current * candidate, axis=1, keepdims=True)

    labels = []
    authors = []
    variants = []
    families = []
    components = []
    nuisance_x = []
    for row in ordered:
        variant = row["variant_id"].rsplit("_", 1)[-1].upper()
        key = assignments[row["pair_id"]]
        assignment = key[f"variant_{variant}_assignment"]
        label = 1 if assignment == "INCREMENTAL" else -1
        author = author_by_pair[row["pair_id"]]
        labels.append(label); authors.append(author); variants.append(variant)
        families.append(row["semantic_family_id"]); components.append(row["component"])
        nuisance_x.append(nuisance(row["current_user_text"], author=author, variant=variant))
    y = np.asarray(labels, dtype=float)
    nuisance_array = np.asarray(nuisance_x, dtype=float)

    fold_by_family = {}
    for component in COMPONENTS:
        component_families = sorted({family for family, comp in zip(families, components) if comp == component}, key=lambda family: stable_hex(PROTOCOL, component, family, n=24))
        if len(component_families) != 12:
            raise RuntimeError(f"{component} family count")
        for index, family in enumerate(component_families):
            fold_by_family[family] = index % 6
    folds = np.asarray([fold_by_family[family] for family in families])
    components_array = np.asarray(components)
    current_text_families: dict[str, set[str]] = {}
    for row in ordered:
        normalized = normalize_current_text(row["current_user_text"])
        current_text_families.setdefault(normalized, set()).add(row["semantic_family_id"])
    cross_family_exact_duplicates = {
        normalized: sorted(family_ids)
        for normalized, family_ids in current_text_families.items()
        if len(family_ids) > 1
    }

    semantic_scores = np.zeros(len(ordered)); semantic_pred = np.zeros(len(ordered), dtype=int)
    nuisance_scores = np.zeros(len(ordered)); nuisance_pred = np.zeros(len(ordered), dtype=int)
    for component in COMPONENTS:
        component_mask = components_array == component
        for fold in range(6):
            test = component_mask & (folds == fold)
            train = component_mask & (folds != fold)
            train_sem, test_sem = semantic_fold_features(raw[train], raw[test], cosine[train], cosine[test])
            semantic_scores[test], semantic_pred[test] = ridge_predict(train_sem, y[train], test_sem)
            nuisance_scores[test], nuisance_pred[test] = ridge_predict(nuisance_array[train], y[train], nuisance_array[test])

    semantic_overall = metrics(y, semantic_pred)
    nuisance_overall = metrics(y, nuisance_pred)
    by_component = {
        component: metrics(y[components_array == component], semantic_pred[components_array == component])
        for component in COMPONENTS
    }
    checks = {
        "96_rows": len(ordered) == 96,
        "balanced_labels_each_component": all(Counter(y[components_array == component]) == Counter({1.0: 12, -1.0: 12}) for component in COMPONENTS),
        "two_families_per_component_per_fold": all(sum(1 for family, fold_value in fold_by_family.items() if fold_value == fold and any(f == family and c == component for f, c in zip(families, components))) == 2 for component in COMPONENTS for fold in range(6)),
        "semantic_overall_balanced_accuracy": semantic_overall["balanced_accuracy"] >= 0.75,
        "semantic_overall_macro_f1": semantic_overall["macro_f1"] >= 0.75,
        "semantic_each_component_balanced_accuracy": all(by_component[component]["balanced_accuracy"] >= 0.65 for component in COMPONENTS),
        "nuisance_only_balanced_accuracy": nuisance_overall["balanced_accuracy"] <= 0.60,
        "normalized_exact_current_user_text_cross_family_duplicate_zero": not cross_family_exact_duplicates,
        "nonconstant_predictions_each_component": all(len(set(semantic_pred[components_array == component])) == 2 for component in COMPONENTS),
        "runtime_candidate_ids_absent": all(not row["candidate_id_present_in_pm_feature_surface"] for row in ordered),
        "response_effect_or_oracle_outcome_absent": True,
    }
    passed = all(checks.values())
    predictions = []
    for index, row in enumerate(ordered):
        predictions.append({
            "protocol": PROTOCOL, "state_id": row["state_id"], "pair_id": row["pair_id"],
            "semantic_family_id": row["semantic_family_id"], "component": row["component"],
            "fold": int(folds[index]), "true_construction_assignment_evaluator_only": "INCREMENTAL" if y[index] == 1 else "LOW_OPPORTUNITY",
            "semantic_score": float(semantic_scores[index]), "semantic_prediction": "INCREMENTAL" if semantic_pred[index] == 1 else "LOW_OPPORTUNITY",
            "nuisance_score": float(nuisance_scores[index]), "nuisance_prediction": "INCREMENTAL" if nuisance_pred[index] == 1 else "LOW_OPPORTUNITY",
            "response_effect_or_oracle_outcome_read": False,
        })
    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "oof_predictions_private_evaluator_assignment_only.jsonl", predictions)
    report = {
        "protocol": PROTOCOL,
        "status": "BOUNDED_OBSERVABILITY_PASS_EFFECT_FEASIBILITY_MAY_BE_PLANNED" if passed else "BOUNDED_OBSERVABILITY_FAIL_NO_EFFECT_CALLS",
        "checks": checks,
        "semantic_overall": semantic_overall,
        "semantic_by_component": by_component,
        "nuisance_only_overall": nuisance_overall,
        "normalized_exact_current_user_text_cross_family_duplicates": cross_family_exact_duplicates,
        "folds": 6, "semantic_parameters_per_head": 5, "ridge_lambda": RIDGE,
        "response_effect_calls_authorized": False,
        "pm_training_authorized": False,
        "response_effect_or_oracle_outcome_read": False,
        "api_calls": 0,
        "source_hashes": {
            "runtime": sha256_file(RUNTIME), "assignments": sha256_file(ASSIGN),
            "fidelity": sha256_file(FIDELITY), "contract": sha256_file(CONTRACT),
        },
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
