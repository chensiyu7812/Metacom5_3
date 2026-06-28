from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence
import math
import numpy as np


@dataclass(frozen=True)
class BootstrapCI:
    estimate: float
    lower: float
    upper: float
    confidence: float
    n_units: int
    n_resamples: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "estimate": self.estimate,
            "lower": self.lower,
            "upper": self.upper,
            "confidence": self.confidence,
            "n_units": self.n_units,
            "n_resamples": self.n_resamples,
        }


def _finite(values: Iterable[float]) -> np.ndarray:
    arr = np.asarray(list(values), dtype=float)
    arr = arr[np.isfinite(arr)]
    if not len(arr):
        raise ValueError("no finite values")
    return arr


def paired_bootstrap_ci(
    differences: Sequence[float],
    *,
    confidence: float = 0.95,
    n_resamples: int = 10000,
    seed: int = 1729,
) -> BootstrapCI:
    values = _finite(differences)
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(values), size=(n_resamples, len(values)))
    means = values[indices].mean(axis=1)
    alpha = (1.0 - confidence) / 2.0
    lo, hi = np.quantile(means, [alpha, 1.0 - alpha])
    return BootstrapCI(
        estimate=float(values.mean()),
        lower=float(lo),
        upper=float(hi),
        confidence=confidence,
        n_units=int(len(values)),
        n_resamples=n_resamples,
    )


def cluster_bootstrap_ci(
    rows: Sequence[Mapping[str, Any]],
    *,
    cluster_key: str,
    value_key: str,
    confidence: float = 0.95,
    n_resamples: int = 10000,
    seed: int = 1729,
) -> BootstrapCI:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        value = row.get(value_key)
        if value is None:
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(numeric):
            grouped[str(row[cluster_key])].append(numeric)
    if not grouped:
        raise ValueError("no valid clusters")
    keys = sorted(grouped)
    cluster_means = np.asarray([np.mean(grouped[key]) for key in keys], dtype=float)
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(keys), size=(n_resamples, len(keys)))
    means = cluster_means[indices].mean(axis=1)
    alpha = (1.0 - confidence) / 2.0
    lo, hi = np.quantile(means, [alpha, 1.0 - alpha])
    return BootstrapCI(
        estimate=float(cluster_means.mean()),
        lower=float(lo),
        upper=float(hi),
        confidence=confidence,
        n_units=len(keys),
        n_resamples=n_resamples,
    )


def hierarchical_bootstrap_ci(
    rows: Sequence[Mapping[str, Any]],
    *,
    user_key: str,
    scenario_key: str,
    value_key: str,
    confidence: float = 0.95,
    n_resamples: int = 10000,
    seed: int = 1729,
) -> BootstrapCI:
    users: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        try:
            value = float(row[value_key])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(value):
            users[str(row[user_key])][str(row[scenario_key])].append(value)
    if not users:
        raise ValueError("no valid hierarchical rows")
    user_ids = sorted(users)
    rng = np.random.default_rng(seed)
    boot = np.empty(n_resamples, dtype=float)
    for b in range(n_resamples):
        sampled_users = rng.choice(user_ids, size=len(user_ids), replace=True)
        user_values: list[float] = []
        for user_id in sampled_users:
            scenario_map = users[user_id]
            scenario_ids = sorted(scenario_map)
            sampled_scenarios = rng.choice(
                scenario_ids, size=len(scenario_ids), replace=True
            )
            scenario_values: list[float] = []
            for scenario_id in sampled_scenarios:
                vals = scenario_map[scenario_id]
                sampled_vals = rng.choice(vals, size=len(vals), replace=True)
                scenario_values.append(float(np.mean(sampled_vals)))
            user_values.append(float(np.mean(scenario_values)))
        boot[b] = float(np.mean(user_values))
    observed = [
        float(np.mean([np.mean(values) for values in scenario_map.values()]))
        for scenario_map in users.values()
    ]
    alpha = (1.0 - confidence) / 2.0
    lo, hi = np.quantile(boot, [alpha, 1.0 - alpha])
    return BootstrapCI(
        estimate=float(np.mean(observed)),
        lower=float(lo),
        upper=float(hi),
        confidence=confidence,
        n_units=len(user_ids),
        n_resamples=n_resamples,
    )


def win_tie_loss(preferences: Iterable[str]) -> dict[str, Any]:
    c = Counter(str(x) for x in preferences)
    n = c["A"] + c["B"] + c["tie"]
    if n == 0:
        return {"n": 0, "wins": 0, "ties": 0, "losses": 0, "preference_score": None}
    return {
        "n": n,
        "wins": c["A"],
        "ties": c["tie"],
        "losses": c["B"],
        "preference_score": (c["A"] + 0.5 * c["tie"]) / n,
    }


def paired_preference_ci(
    preferences: Sequence[str],
    *,
    confidence: float = 0.95,
    n_resamples: int = 10000,
    seed: int = 1729,
) -> BootstrapCI:
    mapping = {"A": 1.0, "tie": 0.5, "B": 0.0}
    unknown = sorted(set(preferences) - set(mapping))
    if unknown:
        raise ValueError(f"invalid preferences: {unknown}")
    values = [mapping[x] - 0.5 for x in preferences]
    return paired_bootstrap_ci(
        values,
        confidence=confidence,
        n_resamples=n_resamples,
        seed=seed,
    )


def success_modes(
    *,
    response_difference_ci: Mapping[str, float],
    cost_difference_ci: Mapping[str, float],
    misuse_difference_ci: Mapping[str, float],
    response_noninferiority_margin: float,
    misuse_noninferiority_margin: float,
) -> dict[str, bool]:
    """Evaluate pre-registered superiority/non-inferiority modes.

    All differences are PM minus baseline. Higher response is better; lower cost
    and lower misuse are better.
    """
    quality_superiority = float(response_difference_ci["lower"]) > 0.0
    quality_noninferiority = (
        float(response_difference_ci["lower"]) > -response_noninferiority_margin
    )
    cost_superiority = float(cost_difference_ci["upper"]) < 0.0
    misuse_noninferiority = (
        float(misuse_difference_ci["upper"]) < misuse_noninferiority_margin
    )
    mode_a = quality_superiority and misuse_noninferiority
    mode_b = quality_noninferiority and cost_superiority and misuse_noninferiority
    return {
        "quality_superiority": quality_superiority,
        "quality_noninferiority": quality_noninferiority,
        "cost_superiority": cost_superiority,
        "misuse_noninferiority": misuse_noninferiority,
        "success_mode_a": mode_a,
        "success_mode_b": mode_b,
        "primary_claim_supported": mode_a or mode_b,
    }


def paired_cluster_permutation_test(
    rows: Sequence[Mapping[str, Any]],
    *,
    cluster_key: str,
    condition_key: str,
    value_key: str,
    treatment: str = "pm",
    baseline: str = "baseline",
    n_permutations: int = 10000,
    seed: int = 1729,
) -> dict[str, Any]:
    """Paired sign-flip/permutation test over clustered condition differences.

    Rows are first averaged within (cluster, condition).  The returned p-value
    tests whether the treatment-baseline mean difference is distinguishable from
    zero using random sign flips at the cluster level.  This is intentionally
    simple and conservative for small EvoEmo user/scenario samples.
    """
    by_cluster: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        try:
            value = float(row[value_key])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(value):
            by_cluster[str(row[cluster_key])][str(row[condition_key])].append(value)
    diffs: list[float] = []
    for conds in by_cluster.values():
        if treatment in conds and baseline in conds:
            diffs.append(float(np.mean(conds[treatment]) - np.mean(conds[baseline])))
    if not diffs:
        raise ValueError("no paired clusters")
    arr = np.asarray(diffs, dtype=float)
    observed = float(arr.mean())
    rng = np.random.default_rng(seed)
    null = np.empty(n_permutations, dtype=float)
    for i in range(n_permutations):
        signs = rng.choice(np.array([-1.0, 1.0]), size=len(arr), replace=True)
        null[i] = float(np.mean(arr * signs))
    p = float((np.sum(np.abs(null) >= abs(observed)) + 1.0) / (n_permutations + 1.0))
    return {
        "estimate": observed,
        "p_value_two_sided": p,
        "n_clusters": int(len(arr)),
        "n_permutations": int(n_permutations),
        "treatment": treatment,
        "baseline": baseline,
    }


def one_sample_cluster_signflip_test(
    rows: Sequence[Mapping[str, Any]],
    *,
    cluster_key: str,
    value_key: str,
    null_value: float = 0.5,
    n_permutations: int = 10000,
    seed: int = 1729,
) -> dict[str, Any]:
    """One-sample cluster sign-flip test against a fixed null value.

    Intended for EvoEmo selective-condition pm_score (1=PM wins, 0.5=tie,
    0=baseline wins), where we test whether the mean is distinguishable from
    null_value=0.5 using cluster-level sign flips.  Rows are averaged within
    each cluster before the permutation test to avoid inflating sample size.
    """
    by_cluster: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        try:
            value = float(row[value_key])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(value):
            by_cluster[str(row[cluster_key])].append(value)
    diffs: list[float] = []
    for vals in by_cluster.values():
        diffs.append(float(np.mean(vals)) - null_value)
    if not diffs:
        raise ValueError("no clusters")
    arr = np.asarray(diffs, dtype=float)
    observed = float(arr.mean())
    rng = np.random.default_rng(seed)
    null_dist = np.empty(n_permutations, dtype=float)
    for i in range(n_permutations):
        signs = rng.choice(np.array([-1.0, 1.0]), size=len(arr), replace=True)
        null_dist[i] = float(np.mean(arr * signs))
    p = float((np.sum(np.abs(null_dist) >= abs(observed)) + 1.0) / (n_permutations + 1.0))
    return {
        "estimate": observed + null_value,
        "mean_minus_null": observed,
        "null_value": null_value,
        "p_value_two_sided": p,
        "n_clusters": int(len(arr)),
        "n_permutations": int(n_permutations),
    }
