"""Grouped pilot analysis and one-time formal head-design freeze."""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.stats import spearmanr
from sklearn.decomposition import PCA
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_squared_error
from sklearn.model_selection import GroupKFold, LeaveOneGroupOut
from sklearn.preprocessing import StandardScaler


COMPONENTS = ("MP", "MS", "ME", "RS")
DIMENSIONS = (
    "goal_advance", "emotional_support",
    "specific_useful_contribution", "clarity_and_naturalness",
)
ME_RANDOM_PROJECTION_SEED = 1295201654


def _target(row: Mapping[str, Any]) -> float:
    return float(row["quality_effect"]["aggregate"]["mean_positive_support_contribution"])


def _extra(component: str, manifest_rows: Sequence[Mapping[str, Any]]) -> np.ndarray:
    if component == "MP":
        return np.asarray(
            [
                [
                    row["model_features"]["rank1_relative_age"],
                    float(row["model_features"]["current_redundant"]),
                    row["model_features"]["candidate_state_bge_m3_cosine"],
                ]
                for row in manifest_rows
            ],
            dtype=float,
        )
    if component == "ME":
        return np.asarray(
            [
                [
                    float(row["model_features"]["past_action_result"]),
                    row["model_features"]["rank1_relative_age"],
                    float(row["model_features"]["current_redundant"]),
                ]
                for row in manifest_rows
            ],
            dtype=float,
        )
    return np.zeros((len(manifest_rows), 0), dtype=float)


def grouped_oof_head_analysis(
    *, component: str, result_rows: Sequence[Mapping[str, Any]],
    manifest_by_group: Mapping[str, Mapping[str, Any]],
    state_vectors: np.ndarray, candidate_vectors: np.ndarray,
) -> dict[str, Any]:
    rows = [row for row in result_rows if row["component"] == component]
    manifests = [manifest_by_group[str(row["effect_group_id"])] for row in rows]
    y = np.asarray([_target(row) for row in rows], dtype=float)
    groups = np.asarray(
        [str(row.get("user_id") or row.get("dialogue_id")) for row in manifests]
    )
    if component == "MP":
        semantic = state_vectors
        transform = "OUTER_TRAIN_PCA_3_CURRENT_STATE_BGE"
        dimensions = 3
    elif component == "MS":
        semantic = candidate_vectors
        transform = "OUTER_TRAIN_PCA_5_CANDIDATE_BGE"
        dimensions = 5
    elif component == "ME":
        semantic = candidate_vectors
        transform = "GLOBAL_FIXED_RANDOM_PROJECTION_3_CANDIDATE_BGE"
        dimensions = 3
    else:
        semantic = state_vectors * candidate_vectors
        transform = "OUTER_TRAIN_PCA_5_STATE_X_CANDIDATE_BGE"
        dimensions = 5
    extras = _extra(component, manifests)
    oof = np.zeros(len(y), dtype=float)
    baseline = np.zeros(len(y), dtype=float)
    splitter = GroupKFold(6) if component == "RS" else LeaveOneGroupOut()
    random_projection = None
    if component == "ME":
        rng = np.random.default_rng(ME_RANDOM_PROJECTION_SEED)
        random_projection = rng.normal(
            0.0, 1.0 / np.sqrt(dimensions), (semantic.shape[1], dimensions)
        )
    for train, test in splitter.split(semantic, y, groups):
        if component in {"MS", "RS"}:
            semantic_scaler = StandardScaler().fit(semantic[train])
            scaled_train_semantic = semantic_scaler.transform(semantic[train])
            scaled_test_semantic = semantic_scaler.transform(semantic[test])
            reducer = PCA(n_components=dimensions).fit(scaled_train_semantic)
            train_x = reducer.transform(scaled_train_semantic)
            test_x = reducer.transform(scaled_test_semantic)
            model = Ridge(alpha=10.0).fit(train_x, y[train])
            oof[test] = model.predict(test_x)
            baseline[test] = float(np.mean(y[train]))
            continue
        if random_projection is None:
            reducer = PCA(n_components=dimensions).fit(semantic[train])
            train_semantic = reducer.transform(semantic[train])
            test_semantic = reducer.transform(semantic[test])
        else:
            train_semantic = semantic[train] @ random_projection
            test_semantic = semantic[test] @ random_projection
        train_x = np.column_stack((train_semantic, extras[train]))
        test_x = np.column_stack((test_semantic, extras[test]))
        scaler = StandardScaler().fit(train_x)
        model = Ridge(alpha=10.0).fit(scaler.transform(train_x), y[train])
        oof[test] = model.predict(scaler.transform(test_x))
        baseline[test] = float(np.mean(y[train]))
    mse = float(mean_squared_error(y, oof))
    baseline_mse = float(mean_squared_error(y, baseline))
    rho = float(spearmanr(y, oof).statistic)

    replicate_sds = []
    sign_consistent = 0
    functional = Counter()
    for row in rows:
        replicate_values = [
            sum(float(rep[dimension]) for dimension in DIMENSIONS) / len(DIMENSIONS)
            for rep in row["quality_effect"]["replicates"]
        ]
        replicate_sds.append(float(np.std(replicate_values, ddof=1)))
        signs = {int(np.sign(value)) for value in replicate_values if value != 0}
        sign_consistent += int(len(signs) <= 1)
        for record in row["functional"]["replicates"]:
            functional[str(record["use_status"])] += 1
    signs = Counter(
        "positive" if value > 0 else "negative" if value < 0 else "tie"
        for value in y
    )
    return {
        "component": component,
        "groups": len(rows),
        "independent_clusters": len(set(groups)),
        "target_mean": float(np.mean(y)),
        "target_sd": float(np.std(y, ddof=1)),
        "target_sign_counts": dict(signs),
        "mean_within_group_replicate_sd": float(np.mean(replicate_sds)),
        "replicate_sign_consistent_groups": sign_consistent,
        "functional_use_counts": dict(functional),
        "frozen_representation": transform,
        "model_dimensions": dimensions + extras.shape[1],
        "ridge_alpha": 10.0,
        "oof_mse": mse,
        "fold_train_mean_baseline_mse": baseline_mse,
        "relative_mse": mse / baseline_mse,
        "mse_reduction": 1.0 - mse / baseline_mse,
        "oof_spearman": rho,
        "development_engineering_signal": (
            mse <= 0.95 * baseline_mse and rho >= 0.15
        ),
        "binary_balanced_accuracy_not_primary": True,
    }


def formal_oof_head_analysis(
    *, component: str, result_rows: Sequence[Mapping[str, Any]],
    manifest_by_group: Mapping[str, Mapping[str, Any]],
    state_vectors: np.ndarray, candidate_vectors: np.ndarray,
) -> dict[str, Any]:
    """Apply the frozen six-fold formal design without selecting a new model.

    Unlike the small development helper above, this function refuses partial
    panels and consumes the manifest's pre-outcome ``outer_fold`` assignments
    directly.  Its predictions are therefore safe to materialize only after
    all 576 formal groups have completed.
    """

    rows = [row for row in result_rows if row["component"] == component]
    if len(rows) != 144:
        raise ValueError(f"formal {component} analysis requires exactly 144 groups")
    effect_ids = [str(row["effect_group_id"]) for row in rows]
    if len(set(effect_ids)) != 144:
        raise ValueError(f"formal {component} effect_group_id values are not unique")
    if len(state_vectors) != 144 or len(candidate_vectors) != 144:
        raise ValueError("formal semantic vectors must align one-to-one with 144 result rows")
    if any(row.get("quality_effect") is None or row.get("functional") is None for row in rows):
        raise ValueError("formal quality and function measurements must be complete")

    manifests = [manifest_by_group[effect_id] for effect_id in effect_ids]
    folds = np.asarray([int(row["outer_fold"]) for row in manifests], dtype=int)
    if Counter(folds) != Counter({fold: 24 for fold in range(1, 7)}):
        raise ValueError("formal component must contain 24 groups in each frozen outer fold")
    for row, manifest in zip(rows, manifests):
        if int(row["outer_fold"]) != int(manifest["outer_fold"]):
            raise ValueError("result outer_fold differs from frozen manifest")

    y = np.asarray([_target(row) for row in rows], dtype=float)
    clusters = np.asarray(
        [str(row.get("user_id") or row.get("dialogue_id")) for row in manifests]
    )
    if component == "MP":
        semantic = state_vectors
        transform = "OUTER_TRAIN_PCA_3_CURRENT_STATE_BGE"
        dimensions = 3
    elif component == "MS":
        semantic = candidate_vectors
        transform = "OUTER_TRAIN_PCA_5_CANDIDATE_BGE"
        dimensions = 5
    elif component == "ME":
        semantic = candidate_vectors
        transform = "GLOBAL_FIXED_RANDOM_PROJECTION_3_CANDIDATE_BGE"
        dimensions = 3
    elif component == "RS":
        semantic = state_vectors * candidate_vectors
        transform = "OUTER_TRAIN_PCA_5_STATE_X_CANDIDATE_BGE"
        dimensions = 5
    else:
        raise ValueError(f"unsupported component: {component}")

    extras = _extra(component, manifests)
    oof = np.zeros(len(y), dtype=float)
    baseline = np.zeros(len(y), dtype=float)
    random_projection = None
    if component == "ME":
        rng = np.random.default_rng(ME_RANDOM_PROJECTION_SEED)
        random_projection = rng.normal(
            0.0, 1.0 / np.sqrt(dimensions), (semantic.shape[1], dimensions)
        )

    for fold in range(1, 7):
        train = np.flatnonzero(folds != fold)
        test = np.flatnonzero(folds == fold)
        if component in {"MS", "RS"}:
            semantic_scaler = StandardScaler().fit(semantic[train])
            scaled_train = semantic_scaler.transform(semantic[train])
            scaled_test = semantic_scaler.transform(semantic[test])
            reducer = PCA(n_components=dimensions).fit(scaled_train)
            train_x = reducer.transform(scaled_train)
            test_x = reducer.transform(scaled_test)
            model = Ridge(alpha=10.0).fit(train_x, y[train])
            oof[test] = model.predict(test_x)
        else:
            if random_projection is None:
                reducer = PCA(n_components=dimensions).fit(semantic[train])
                train_semantic = reducer.transform(semantic[train])
                test_semantic = reducer.transform(semantic[test])
            else:
                train_semantic = semantic[train] @ random_projection
                test_semantic = semantic[test] @ random_projection
            train_x = np.column_stack((train_semantic, extras[train]))
            test_x = np.column_stack((test_semantic, extras[test]))
            scaler = StandardScaler().fit(train_x)
            model = Ridge(alpha=10.0).fit(scaler.transform(train_x), y[train])
            oof[test] = model.predict(scaler.transform(test_x))
        baseline[test] = float(np.mean(y[train]))

    mse = float(mean_squared_error(y, oof))
    baseline_mse = float(mean_squared_error(y, baseline))
    rho_value = spearmanr(y, oof).statistic
    rho = float(rho_value) if np.isfinite(rho_value) else 0.0
    target_nonconstant = bool(np.ptp(y) > 0)
    prediction_nonconstant = bool(np.ptp(oof) > 0)
    cluster_count = len(set(clusters))
    gate_checks = {
        "mse_at_least_5_percent_below_fold_train_mean": (
            baseline_mse > 0 and mse <= 0.95 * baseline_mse
        ),
        "spearman_at_least_0_15": rho >= 0.15,
        "target_nonconstant": target_nonconstant,
        "prediction_nonconstant": prediction_nonconstant,
        "at_least_12_independent_clusters": cluster_count >= 12,
    }
    predictions = [
        {
            "effect_group_id": effect_id,
            "component": component,
            "outer_fold": int(fold),
            "cluster_id": cluster,
            "observed_uplift": float(observed),
            "oof_predicted_uplift": float(predicted),
            "fold_train_mean_prediction": float(mean_prediction),
        }
        for effect_id, fold, cluster, observed, predicted, mean_prediction in zip(
            effect_ids, folds, clusters, y, oof, baseline
        )
    ]
    return {
        "component": component,
        "groups": len(rows),
        "independent_clusters": cluster_count,
        "fold_counts": dict(sorted(Counter(int(value) for value in folds).items())),
        "frozen_representation": transform,
        "model_dimensions": dimensions + extras.shape[1],
        "ridge_alpha": 10.0,
        "target_mean": float(np.mean(y)),
        "target_sd": float(np.std(y, ddof=1)),
        "oof_mse": mse,
        "fold_train_mean_baseline_mse": baseline_mse,
        "relative_mse": mse / baseline_mse if baseline_mse else None,
        "mse_reduction": 1.0 - mse / baseline_mse if baseline_mse else None,
        "oof_spearman": rho,
        "gate_checks": gate_checks,
        "formal_head_pass": all(gate_checks.values()),
        "failure_action": "FAIL_CLOSED_TO_OFF_OR_PREDECLARED_TRANSPARENT_RULE",
        "predictions": predictions,
        "binary_balanced_accuracy_not_primary": True,
    }


def formal_effect_freeze(pilot_analysis: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    if set(pilot_analysis) != set(COMPONENTS):
        raise ValueError("all four pilot heads are required")
    return {
        "protocol": "pm-v1.5-v5.3-public-formal-effect-freeze-v1",
        "status": "FORMAL_EFFECT_COUNTS_AND_HEADS_FROZEN",
        "development_pilot_groups": 96,
        "formal_groups": {
            "MP": 144, "MS": 144, "ME": 144, "RS": 144,
        },
        "formal_total_groups": 576,
        "paired_generator_seeds_per_group": 3,
        "memory_allocation": (
            "8 outcome-blind factor-balanced actual-Rank1 states per head per "
            "EvoEmo user across all 18 users; all 96 development states excluded"
        ),
        "rs_allocation": (
            "144 distinct quarantined-clean ESConv train dialogue groups; all "
            "development dialogue-state keys excluded"
        ),
        "target": (
            "continuous replicate-aggregated positive-support-contribution uplift; "
            "ties remain zero and negative effects remain negative"
        ),
        "heads": {
            component: {
                "representation": pilot_analysis[component]["frozen_representation"],
                "model_dimensions": pilot_analysis[component]["model_dimensions"],
                "ridge_alpha": 10.0,
                "no_further_representation_selection": True,
            }
            for component in COMPONENTS
        },
        "outer_evaluation": {
            "memory": "six frozen 15-user-train/3-user-test folds from public-backbone contract",
            "RS": "six 120-dialogue-train/24-dialogue-test grouped folds",
            "PCA_fit": "outer-training groups only",
            "scaler_fit": "outer-training groups only",
            "threshold_and_calibration": "inner grouped development only",
        },
        "formal_engineering_gate_each_head": {
            "continuous_mse": "OOF MSE at least 5 percent below fold-training-mean predictor",
            "ranking": "OOF Spearman at least 0.15",
            "support": "nonconstant target and predictions across at least 12 independent clusters",
            "binary_balanced_accuracy": "diagnostic only; not appropriate when true uplift is mostly positive",
        },
        "failure_rule": (
            "a failed formal head is not repaired by adding outcome-selected states or "
            "changing representation; it fails closed to OFF/transparent rule"
        ),
        "risk": (
            "automatic Gemini risk judge failed canary and is excluded from labels and "
            "formal authorization; machine-critical events plus stratified blind human audit"
        ),
        "cost": "never enters component target; used only in final 16-action projection",
        "interaction_followup": "after head qualification, freeze 32-48 common states and run all 16 actions",
        "guarantee_boundary": (
            "this maximizes learnability and freezes a real pass/fail test; it cannot "
            "mathematically guarantee that unseen formal OOF heads pass"
        ),
        "pilot_analysis": dict(pilot_analysis),
        "api_calls_for_freeze": 0,
    }
