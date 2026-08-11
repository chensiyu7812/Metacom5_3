#!/usr/bin/env python3
"""Outcome-open V5.3 head-failure diagnosis; never a formal requalification."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

import numpy as np
from scipy.stats import pearsonr, spearmanr
from sklearn.decomposition import PCA
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_squared_error
from sklearn.preprocessing import StandardScaler


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, write_json  # noqa: E402
from metacom_pm.v1_5_v5_3_public_learnability_analysis import COMPONENTS  # noqa: E402
from metacom_pm.v1_5_v5_3_semantic_ms_retrieval import (  # noqa: E402
    BgeM3Encoder,
    DEFAULT_BGE_M3_SNAPSHOT,
)


RESULT_DIR = ROOT / "outputs/pm_v1_5_v5_3_public_formal_qf_20260809/shards"
MANIFEST_PATH = ROOT / "outputs/pm_v1_5_v5_3_public_formal_effect_manifest_20260809/effect_group_manifest_private.jsonl"
FORMAL_REPORT = ROOT / "outputs/pm_v1_5_v5_3_public_formal_oof_20260809/formal_oof_report.json"
OUT = ROOT / "outputs/pm_v1_5_v5_3_formal_head_failure_diagnosis_20260809"
DIMENSIONS = (
    "goal_advance",
    "emotional_support",
    "specific_useful_contribution",
    "clarity_and_naturalness",
)


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _target(row: dict) -> float:
    return float(row["quality_effect"]["aggregate"]["mean_positive_support_contribution"])


def _safe_correlation(function, left: np.ndarray, right: np.ndarray) -> float:
    value = function(left, right).statistic
    return float(value) if np.isfinite(value) else 0.0


def _label_diagnostics(rows: list[dict], manifests: list[dict]) -> dict:
    y = np.asarray([_target(row) for row in rows], dtype=float)
    replicate_values = np.asarray(
        [
            [
                float(np.mean([replicate[key] for key in DIMENSIONS]))
                for replicate in row["quality_effect"]["replicates"]
            ]
            for row in rows
        ],
        dtype=float,
    )
    pairwise = []
    for left, right in ((0, 1), (0, 2), (1, 2)):
        pairwise.append(
            {
                "replicates": [left, right],
                "pearson": _safe_correlation(pearsonr, replicate_values[:, left], replicate_values[:, right]),
                "spearman": _safe_correlation(spearmanr, replicate_values[:, left], replicate_values[:, right]),
            }
        )
    two_to_third = []
    for held_out in range(3):
        retained = [index for index in range(3) if index != held_out]
        mean_retained = np.mean(replicate_values[:, retained], axis=1)
        two_to_third.append(
            {
                "held_out_replicate": held_out,
                "pearson": _safe_correlation(pearsonr, mean_retained, replicate_values[:, held_out]),
                "spearman": _safe_correlation(spearmanr, mean_retained, replicate_values[:, held_out]),
            }
        )
    between_variance = float(np.var(y, ddof=1))
    within_variance = float(np.mean(np.var(replicate_values, axis=1, ddof=1)))
    estimated_signal = max(0.0, between_variance - within_variance / 3.0)
    signs = Counter("positive" if value > 0 else "negative" if value < 0 else "tie" for value in y)
    functional = Counter(
        str(record["use_status"])
        for row in rows
        for record in row["functional"]["replicates"]
    )
    statuses = Counter(
        f"{arm}:{replicate[arm]['status']}"
        for row in rows
        for replicate in row["generated"]
        for arm in ("ON", "OFF")
    )
    fold_means = defaultdict(list)
    cluster_means = defaultdict(list)
    for value, manifest in zip(y, manifests):
        fold_means[int(manifest["outer_fold"])].append(float(value))
        cluster_means[str(manifest.get("user_id") or manifest.get("dialogue_id"))].append(float(value))
    return {
        "target_mean": float(np.mean(y)),
        "target_sd": float(np.std(y, ddof=1)),
        "target_sign_counts": dict(signs),
        "mean_within_group_replicate_sd": float(np.mean(np.std(replicate_values, axis=1, ddof=1))),
        "pairwise_replicate_correlations": pairwise,
        "two_seed_mean_to_third_seed_correlations": two_to_third,
        "estimated_replicate_aggregated_signal_fraction": estimated_signal / between_variance if between_variance else None,
        "functional_use_counts": dict(functional),
        "executor_status_counts": dict(statuses),
        "fold_target_means": {str(key): float(np.mean(value)) for key, value in sorted(fold_means.items())},
        "cluster_target_mean_range": [
            float(min(np.mean(value) for value in cluster_means.values())),
            float(max(np.mean(value) for value in cluster_means.values())),
        ],
    }


def _semantic_surface(component: str, states: np.ndarray, candidates: np.ndarray) -> np.ndarray:
    if component == "MP":
        return states
    if component in {"MS", "ME"}:
        return candidates
    if component == "RS":
        return np.column_stack((states, candidates, states * candidates, np.abs(states - candidates)))
    raise ValueError(component)


def _semantic_capacity_sweep(
    *, component: str, rows: list[dict], manifests: list[dict],
    state_vectors: np.ndarray, candidate_vectors: np.ndarray,
) -> dict:
    """Post-hoc capacity diagnostic on the already-open formal panel."""

    y = np.asarray([_target(row) for row in rows], dtype=float)
    folds = np.asarray([int(row["outer_fold"]) for row in manifests], dtype=int)
    semantic = _semantic_surface(component, state_vectors, candidate_vectors)
    baseline = np.zeros(len(y), dtype=float)
    predictions = {dimension: np.zeros(len(y), dtype=float) for dimension in (3, 5, 10, 20)}
    for fold in range(1, 7):
        train = np.flatnonzero(folds != fold)
        test = np.flatnonzero(folds == fold)
        baseline[test] = float(np.mean(y[train]))
        scaler = StandardScaler().fit(semantic[train])
        scaled_train = scaler.transform(semantic[train])
        scaled_test = scaler.transform(semantic[test])
        for dimension, oof in predictions.items():
            reducer = PCA(n_components=dimension).fit(scaled_train)
            model = Ridge(alpha=10.0).fit(reducer.transform(scaled_train), y[train])
            oof[test] = model.predict(reducer.transform(scaled_test))
    baseline_mse = float(mean_squared_error(y, baseline))
    return {
        str(dimension): {
            "relative_mse": float(mean_squared_error(y, prediction) / baseline_mse),
            "oof_spearman": _safe_correlation(spearmanr, y, prediction),
        }
        for dimension, prediction in predictions.items()
    }


def main() -> None:
    formal = json.loads(FORMAL_REPORT.read_text())
    if formal["status"] != "PARTIAL_OR_NO_FORMAL_HEAD_PASS_FAIL_CLOSED":
        raise RuntimeError("this postmortem is only valid after a failed frozen formal analysis")
    all_results = []
    for fold in range(1, 7):
        all_results.extend(_jsonl(RESULT_DIR / f"fold_{fold}_results.jsonl"))
    manifest_by_group = {row["effect_group_id"]: row for row in _jsonl(MANIFEST_PATH)}
    manifests = [manifest_by_group[row["effect_group_id"]] for row in all_results]
    texts = [text for row in manifests for text in (row["current_user_text"], row["candidate_text"])]
    vectors = BgeM3Encoder(DEFAULT_BGE_M3_SNAPSHOT).encode(texts)
    states = vectors[0::2]
    candidates = vectors[1::2]

    components = {}
    for component in COMPONENTS:
        indices = [index for index, row in enumerate(all_results) if row["component"] == component]
        rows = [all_results[index] for index in indices]
        component_manifests = [manifests[index] for index in indices]
        components[component] = {
            "formal_result": formal["analysis"][component],
            "label_and_execution_diagnostics": _label_diagnostics(rows, component_manifests),
            "posthoc_semantic_capacity_sweep_not_formal": _semantic_capacity_sweep(
                component=component,
                rows=rows,
                manifests=component_manifests,
                state_vectors=states[indices],
                candidate_vectors=candidates[indices],
            ),
        }
    report = {
        "protocol": "pm-v1.5-v5.3-formal-head-failure-diagnosis-v1",
        "status": "OUTCOME_OPEN_POSTHOC_DIAGNOSIS_NOT_REQUALIFICATION",
        "formal_conclusion_unchanged": "ALL_FOUR_V5_3_HEADS_FAILED_AND_FAIL_CLOSED",
        "components": components,
        "interpretation_rules": [
            "No result in this artifact may requalify a V5.3 head.",
            "The PCA sweep is outcome-open model development and requires a new named protocol plus fresh evidence before any confirmation claim.",
            "A useful capacity result does not fix weak positive/negative contrast or replicate noise.",
        ],
        "source_hashes": {
            "formal_report": sha256_file(FORMAL_REPORT),
            "manifest": sha256_file(MANIFEST_PATH),
            **{
                f"fold_{fold}": sha256_file(RESULT_DIR / f"fold_{fold}_results.jsonl")
                for fold in range(1, 7)
            },
        },
        "api_calls": 0,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    write_json(OUT / "report.json", report)
    print(
        {
            component: {
                "formal_pass": row["formal_result"]["formal_head_pass"],
                "semantic_sweep": row["posthoc_semantic_capacity_sweep_not_formal"],
            }
            for component, row in components.items()
        }
    )


if __name__ == "__main__":
    main()
