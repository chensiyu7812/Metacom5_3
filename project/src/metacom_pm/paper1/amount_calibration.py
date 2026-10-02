"""Outcome-independent sampling and fold-specific amount recommendations.

No model calls or formal outcome unlocks. Recommendations use one task and
one head at a time; official scorer guards and final promotion stay explicit.
"""
from __future__ import annotations

import hashlib
import math
import random
import statistics
from collections import defaultdict


def _key(seed: int, *parts: object) -> str:
    return hashlib.sha256(repr((seed, *parts)).encode()).hexdigest()


def sample_static_targets(frame: list[dict], *, seed: int = 0) -> list[dict]:
    """One uniform component, then one uniform target per task/owner/fold.

    Hash ordering implements the fixed randomization; every target has known
    nonzero inclusion probability. Components remain in their original fold.
    """
    strata = defaultdict(lambda: defaultdict(list))
    seen, component_folds = set(), {}
    for row in frame:
        if row["task_type"] not in {"qa", "summary"}:
            continue
        tid, component, fold = row["target_id"], row["group_component_id"], row["outer_fold"]
        if tid in seen:
            raise ValueError("duplicate sampling target")
        seen.add(tid)
        if component in component_folds and component_folds[component] != fold:
            raise ValueError("component crosses outer folds")
        component_folds[component] = fold
        strata[(row["task_type"], row["owner_id"], fold)][component].append(row)
    selected = []
    for stratum, groups in sorted(strata.items()):
        component = min(groups, key=lambda c: (_key(seed, "component", stratum, c), c))
        row = min(groups[component], key=lambda r: (_key(seed, "target", stratum, r["target_id"]), r["target_id"]))
        inverse_pi = len(groups) * len(groups[component])
        selected.append({k: row[k] for k in ["target_id", "task_type", "owner_id", "outer_fold", "group_component_id"]} | {
            "sampling_seed": seed, "stratum_components": len(groups),
            "stratum_targets": sum(map(len, groups.values())),
            "selected_component_targets": len(groups[component]),
            "inclusion_probability": 1 / inverse_pi, "analysis_weight": inverse_pi})
    return selected


def recommend_amount(rows: list[dict], *, task: str, head: str, held_out_fold: int,
                     grid: tuple[int, ...] = (0, 1, 2, 3, 4), seed: int = 0,
                     bootstrap_replicates: int = 2000) -> dict:
    """Paired complete-grid, IPW ratio means with owner-cluster bootstrap SE.

    Held-out rows are excluded before any score is read. A missing score or
    incomplete generation excludes that target from *every* k in this
    comparison, with the loss of coverage disclosed. No uncertainty is filled
    with zero. The result is a primary-metric recommendation, not a freeze.
    """
    if task not in {"qa", "summary"} or head not in {"MP", "ME", "MS"}:
        raise ValueError("amount recommendation requires one static task/head")
    if len(set(grid)) != len(grid) or not grid or bootstrap_replicates < 2:
        raise ValueError("invalid grid or bootstrap count")
    by_target = defaultdict(dict)
    components = {}
    for row in rows:
        if row["task"] != task or row["head"] != head or row["outer_fold"] == held_out_fold:
            continue
        k = row["k"]
        if k not in grid:
            continue
        target = row["target_id"]
        if k in by_target[target]:
            raise ValueError("duplicate target/head/k score")
        component = row["group_component_id"]
        if component in components and components[component] != row["outer_fold"]:
            raise ValueError("component crosses outer folds")
        components[component] = row["outer_fold"]
        by_target[target][k] = row
    complete, excluded = [], []
    for target, values in sorted(by_target.items()):
        if set(values) != set(grid) or any(r.get("quality") is None or r.get("natural_end") is not True for r in values.values()):
            excluded.append(target)
            continue
        first = values[grid[0]]
        for r in values.values():
            if any(r[field] != first[field] for field in ["owner_id", "outer_fold", "group_component_id", "analysis_weight"]):
                raise ValueError("paired target metadata drift")
            if not math.isfinite(r["quality"]) or not 0 <= r["quality"] <= 1:
                raise ValueError("official normalized quality must be in [0,1]")
            if not math.isfinite(r["input_tokens"]) or r["input_tokens"] < 0:
                raise ValueError("invalid token count")
            if not math.isfinite(r["analysis_weight"]) or r["analysis_weight"] <= 0:
                raise ValueError("invalid inclusion weight")
        complete.append(values)
    owners = sorted({v[grid[0]]["owner_id"] for v in complete})
    if len(owners) < 2:
        raise ValueError("at least two complete owner clusters are required")
    owner_rows = {o: [v for v in complete if v[grid[0]]["owner_id"] == o] for o in owners}

    def weighted(items, k, field):
        return sum(v[k][field] * v[k]["analysis_weight"] for v in items) / sum(v[k]["analysis_weight"] for v in items)

    means = {k: weighted(complete, k, "quality") for k in grid}
    tokens = {k: weighted(complete, k, "input_tokens") for k in grid}
    rng = random.Random(seed)
    draws = {k: [] for k in grid}
    for _ in range(bootstrap_replicates):
        sampled = [v for owner in rng.choices(owners, k=len(owners)) for v in owner_rows[owner]]
        for k in grid:
            draws[k].append(weighted(sampled, k, "quality"))
    se = {k: statistics.stdev(draws[k]) for k in grid}
    best = min(grid, key=lambda k: (-means[k], grid.index(k)))
    admissible = [k for k in grid if means[k] >= means[best] - se[best]]
    chosen = min(admissible, key=lambda k: (tokens[k], k, grid.index(k)))
    return {"task": task, "head": head, "held_out_fold": held_out_fold,
            "paired_complete_targets": len(complete), "excluded_incomplete_targets": excluded,
            "owner_clusters": len(owners), "bootstrap_replicates": bootstrap_replicates,
            "sampling_seed": seed, "means": means, "standard_errors": se,
            "mean_input_tokens": tokens, "best_mean_k": best,
            "one_se_admissible_k": admissible, "primary_metric_recommended_k": chosen,
            "expand_once_to_6_8": best == 4 and 3 not in admissible and max(grid) == 4,
            "final_k_frozen": False, "official_guard_review_required": True,
            "claim": "sample-based recommendation with owner-cluster uncertainty; no guaranteed power"}
