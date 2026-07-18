from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence

import numpy as np

from .contracts import MemorySource, StrategyMode, parse_action_id
from .pm_v2_contracts import PMV2State
from .pm_v2_data import EvaluatorContextIndex


SHORTCUT_AUDIT_PROTOCOL = "pm-v1.5-step0-shortcut-audit-v1"


def _balanced_accuracy(target: np.ndarray, prediction: np.ndarray) -> float:
    values = sorted(set(bool(value) for value in target))
    if values != [False, True]:
        raise ValueError("shortcut target must contain both classes")
    recalls = []
    for value in values:
        mask = target == value
        recalls.append(float(np.mean(prediction[mask] == target[mask])))
    return float(np.mean(recalls))


def _best_threshold(feature: np.ndarray, target: np.ndarray) -> dict[str, Any]:
    values = np.unique(feature.astype(float))
    if not len(values):
        raise ValueError("shortcut feature is empty")
    thresholds = np.concatenate(
        (
            [values[0] - 1e-9],
            (values[:-1] + values[1:]) / 2.0,
            [values[-1] + 1e-9],
        )
    )
    candidates = []
    for threshold in thresholds:
        for direction in ("ge", "le"):
            prediction = (
                feature >= threshold if direction == "ge" else feature <= threshold
            )
            candidates.append(
                {
                    "balanced_accuracy": _balanced_accuracy(target, prediction),
                    "threshold": float(threshold),
                    "direction": direction,
                }
            )
    return max(
        candidates,
        key=lambda row: (
            row["balanced_accuracy"],
            -abs(row["threshold"]),
            row["direction"],
        ),
    )


def _nearest_neighbor_identifiability(
    matrix: np.ndarray, labels: Sequence[str]
) -> dict[str, Any]:
    labels = [str(value) for value in labels]
    if len(matrix) != len(labels) or len(matrix) < 2:
        raise ValueError("identifiability matrix/labels are incomplete")
    scale = np.std(matrix, axis=0)
    normalized = (matrix - np.mean(matrix, axis=0)) / np.where(
        scale > 1e-12, scale, 1.0
    )
    distances = np.sum(
        (normalized[:, None, :] - normalized[None, :, :]) ** 2,
        axis=2,
    )
    np.fill_diagonal(distances, np.inf)
    nearest = np.argmin(distances, axis=1)
    accuracy = float(
        np.mean([labels[index] == labels[int(nearest[index])] for index in range(len(labels))])
    )
    majority = max(Counter(labels).values()) / len(labels)
    return {
        "protocol": "leave-one-state-out-nearest-neighbor-diagnostic-v1",
        "accuracy": accuracy,
        "majority_baseline": float(majority),
        "class_count": len(set(labels)),
    }


def audit_step0_shortcuts(
    *,
    states: Sequence[PMV2State],
    evaluator_contexts: EvaluatorContextIndex,
    maximum_single_threshold_balanced_accuracy: float,
    centroid_noise_std: float,
    shuffle_seed: int,
) -> dict[str, Any]:
    """Audit all states without reading any response/judge outcome."""

    if not states or len({state.state_id for state in states}) != len(states):
        raise ValueError("shortcut audit requires unique non-empty states")
    if not 0.5 <= float(maximum_single_threshold_balanced_accuracy) <= 1.0:
        raise ValueError("shortcut threshold must be in [0.5, 1.0]")
    if float(centroid_noise_std) <= 0.0:
        raise ValueError("centroid noise std must be positive")
    contexts = evaluator_contexts.require_states(states, exact=False)
    ordered = sorted(states, key=lambda value: value.state_id)
    rng = np.random.default_rng(int(shuffle_seed))
    source_order = list(MemorySource)
    feature_names = [f"{source.value}_similarity" for source in source_order] + [
        "strategy_max_family_similarity",
        "strategy_advice_requested",
        "strategy_advice_rejected",
        "strategy_question_present",
    ]
    matrix_rows = []
    targets: dict[str, list[bool]] = {
        **{source.value: [] for source in source_order},
        "RS": [],
    }
    regime_labels: list[str] = []
    user_labels: list[str] = []
    split_labels: list[str] = []
    for state in ordered:
        if state.step0_observation is None:
            raise RuntimeError("shortcut audit requires formal Step-0 on every state")
        context = contexts[state.state_id]
        needed = set(str(value) for value in context.get("needed_memory_sources") or [])
        regime = str(context.get("regime") or "")
        strategy = state.step0_observation.strategy
        matrix_rows.append(
            [
                *[
                    float(
                        state.step0_observation.memory_sources[
                            source
                        ].query_to_source_similarity
                    )
                    for source in source_order
                ],
                max(strategy.family_similarities.values(), default=0.0),
                float(strategy.advice_requested),
                float(strategy.advice_rejected),
                float(strategy.question_present),
            ]
        )
        for source in source_order:
            targets[source.value].append(source.value in needed)
        targets["RS"].append(regime == "strategy_helpful")
        regime_labels.append(regime)
        user_labels.append(state.user_id)
        split_labels.append(state.split.value)
    matrix = np.asarray(matrix_rows, dtype=float)
    target_arrays = {
        key: np.asarray(values, dtype=bool) for key, values in targets.items()
    }
    feature_columns = {
        name: matrix[:, index] for index, name in enumerate(feature_names)
    }
    target_feature_sets = {
        "MP": ["MP_similarity"],
        "MS": ["MS_similarity"],
        "ME": ["ME_similarity"],
        "RS": feature_names[3:],
    }
    threshold_rows: dict[str, dict[str, Any]] = {}
    for target_name, names in target_feature_sets.items():
        rows = {
            name: _best_threshold(feature_columns[name], target_arrays[target_name])
            for name in names
        }
        selected_name, selected = max(
            rows.items(), key=lambda item: item[1]["balanced_accuracy"]
        )
        shuffled = target_arrays[target_name].copy()
        rng.shuffle(shuffled)
        shuffled_score = max(
            _best_threshold(feature_columns[name], shuffled)["balanced_accuracy"]
            for name in names
        )
        noisy_score = max(
            _best_threshold(
                np.clip(
                    feature_columns[name]
                    + rng.normal(0.0, float(centroid_noise_std), len(ordered)),
                    -1.0,
                    1.0,
                ),
                target_arrays[target_name],
            )["balanced_accuracy"]
            for name in names
        )
        threshold_rows[target_name] = {
            "selected_feature": selected_name,
            "selected": selected,
            "all_features": rows,
            "shuffled_label_best_balanced_accuracy": float(shuffled_score),
            "centroid_noise_best_balanced_accuracy": float(noisy_score),
            "no_step0_balanced_accuracy": 0.5,
            "positive_rate": float(np.mean(target_arrays[target_name])),
        }

    permuted_source = {}
    for index, source in enumerate(source_order):
        permuted = source_order[(index + 1) % len(source_order)]
        permuted_source[source.value] = {
            "replacement_feature": f"{permuted.value}_similarity",
            "balanced_accuracy": _best_threshold(
                feature_columns[f"{permuted.value}_similarity"],
                target_arrays[source.value],
            )["balanced_accuracy"],
        }
    maximum_observed = max(
        row["selected"]["balanced_accuracy"] for row in threshold_rows.values()
    )
    checks = {
        "all_468_states_present": len(ordered) == 468,
        "formal_step0_complete": all(
            state.step0_observation is not None for state in ordered
        ),
        "single_threshold_not_near_oracle": maximum_observed
        < float(maximum_single_threshold_balanced_accuracy),
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "protocol": SHORTCUT_AUDIT_PROTOCOL,
        "outcome_labels_read": False,
        "n_states": len(ordered),
        "feature_names": feature_names,
        "maximum_single_threshold_balanced_accuracy": float(
            maximum_single_threshold_balanced_accuracy
        ),
        "maximum_observed_single_threshold_balanced_accuracy": float(
            maximum_observed
        ),
        "targets": threshold_rows,
        "permuted_source": permuted_source,
        "identifiability_diagnostics": {
            "user": _nearest_neighbor_identifiability(matrix, user_labels),
            "regime": _nearest_neighbor_identifiability(matrix, regime_labels),
            "split_environment": _nearest_neighbor_identifiability(
                matrix, split_labels
            ),
        },
        "action_factor_coverage": {
            "factors": ["MP", "MS", "ME", "RS"],
            "main_effect_levels": {name: [0, 1] for name in ("MP", "MS", "ME", "RS")},
            "pairwise_interactions": [
                "MP*MS",
                "MP*ME",
                "MP*RS",
                "MS*ME",
                "MS*RS",
                "ME*RS",
            ],
            "observed_action_factor_combinations": sorted(
                {
                    tuple(
                        [
                            int(MemorySource.MP in parse_action_id(action)[0]),
                            int(MemorySource.MS in parse_action_id(action)[0]),
                            int(MemorySource.ME in parse_action_id(action)[0]),
                            int(parse_action_id(action)[1] is StrategyMode.RS),
                        ]
                    )
                    for state in ordered
                    for action in state.allowed_actions
                }
            ),
        },
        "checks": checks,
    }
