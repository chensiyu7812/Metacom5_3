"""B26: structural outer-fold packing decision surface.

Zero-outcome, diagnostic only. Enumerates ``pack_components_into_outer_
folds`` (already implemented and tested in ``exact_evidence_folds.py``, B14/
B15) over a grid of ``n_outer_folds`` (``K``) and ``seed`` values, purely to
disclose *what the structural packing options look like* -- not to choose
one.

Uses only the already-built 477 ``PREPACK_EXACT_EVIDENCE_COMPONENT``
components (``build_group_components``): this module never reads any
outcome/gold/answer/observation field, never constructs a different
grouping, and never treats a ``group_component_id`` as an outer
``fold_id``.

This module deliberately does NOT:

- select a "best" K or seed from the surface, or output any recommended
  winner;
- declare a PASS/FAIL verdict on any (K, seed) point;
- write a "frozen" outer-fold assignment manifest (``pack_components_into_
  outer_folds``'s own status stays ``OUTER_FOLD_PACKING_PENDING_M2_FREEZE``
  -- this module reports what the *surface* looks like across many
  candidate (K, seed) pairs, it does not itself freeze one);
- promote the shared-session sensitivity connected components
  (``build_shared_session_sensitivity_components``) to primary grouping --
  they remain sensitivity-only (AGENTS.md rule 6) and are not touched here
  at all.

Every surface point independently re-verifies, rather than only trusting
``pack_components_into_outer_folds``'s internal invariants: every target is
assigned to exactly one outer fold (no missing, no duplicate), and every
component's full target set lands inside a single fold (atomicity) --
defense in depth, matching this project's established pattern of verifying
structural invariants explicitly rather than assuming them.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any

from metacom_pm.paper1.splits.exact_evidence_folds import (
    GroupComponent,
    pack_components_into_outer_folds,
)

DEFAULT_K_VALUES: tuple[int, ...] = tuple(range(2, 11))  # K = 2..10 inclusive
DEFAULT_SEED_VALUES: tuple[int, ...] = tuple(range(32))  # seed index = 0..31 inclusive

NO_WINNER_NOTE = (
    "This is a structural decision *surface*, not a decision. No (K, seed) "
    "point is selected, ranked, or recommended here; n_outer_folds and the "
    "outer-fold seed remain explicit M2-freeze researcher decisions."
)


@dataclass(frozen=True)
class FoldDiagnostics:
    """Per-outer-fold aggregate for one (K, seed) packing."""

    outer_fold: int
    target_count: int
    qa_target_count: int
    summary_target_count: int
    dialogue_generation_target_count: int
    component_count: int
    owner_count: int
    owner_ids: tuple[str, ...]

    def to_manifest_row(self) -> dict[str, Any]:
        return {
            "outer_fold": self.outer_fold,
            "target_count": self.target_count,
            "qa_target_count": self.qa_target_count,
            "summary_target_count": self.summary_target_count,
            "dialogue_generation_target_count": self.dialogue_generation_target_count,
            "component_count": self.component_count,
            "owner_count": self.owner_count,
            "owner_ids": list(self.owner_ids),
        }


@dataclass(frozen=True)
class PackingSurfacePoint:
    """One (n_outer_folds, seed) point on the structural packing surface."""

    n_outer_folds: int
    seed: int
    folds: tuple[FoldDiagnostics, ...]
    total_components: int
    total_targets_expected: int
    total_targets_assigned: int
    all_targets_assigned_exactly_once: bool
    all_components_atomic: bool
    no_missing_or_duplicate_targets: bool
    target_count_min: int
    target_count_max: int
    target_count_mean: float
    target_count_variance: float | None
    target_count_imbalance_ratio: float | None
    owner_count_min: int
    owner_count_max: int

    def to_manifest_row(self) -> dict[str, Any]:
        return {
            "protocol": "pm-paper1-outer-fold-packing-surface-point-v1",
            "n_outer_folds": self.n_outer_folds,
            "seed": self.seed,
            "total_components": self.total_components,
            "total_targets_expected": self.total_targets_expected,
            "total_targets_assigned": self.total_targets_assigned,
            "all_targets_assigned_exactly_once": self.all_targets_assigned_exactly_once,
            "all_components_atomic": self.all_components_atomic,
            "no_missing_or_duplicate_targets": self.no_missing_or_duplicate_targets,
            "target_count_min": self.target_count_min,
            "target_count_max": self.target_count_max,
            "target_count_mean": self.target_count_mean,
            "target_count_variance": self.target_count_variance,
            "target_count_imbalance_ratio_max_over_mean": self.target_count_imbalance_ratio,
            "owner_count_min": self.owner_count_min,
            "owner_count_max": self.owner_count_max,
            "folds": [f.to_manifest_row() for f in self.folds],
        }


def _pvariance(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    return statistics.pvariance(values)


def _diagnose_packing(
    components: tuple[GroupComponent, ...],
    assignment: dict[str, int],
    n_outer_folds: int,
    seed: int,
) -> PackingSurfacePoint:
    by_component_id = {c.component_id: c for c in components}

    fold_target_ids: list[set[str]] = [set() for _ in range(n_outer_folds)]
    fold_task_counts: list[dict[str, int]] = [dict() for _ in range(n_outer_folds)]
    fold_owner_ids: list[set[str]] = [set() for _ in range(n_outer_folds)]
    fold_component_counts = [0] * n_outer_folds

    for component_id, fold_index in assignment.items():
        component = by_component_id[component_id]
        fold_component_counts[fold_index] += 1
        fold_target_ids[fold_index].update(component.target_ids)
        fold_owner_ids[fold_index] |= component.owner_ids
        for task_name, count in component.task_type_counts:
            fold_task_counts[fold_index][task_name] = (
                fold_task_counts[fold_index].get(task_name, 0) + count
            )

    # B26.3/B27.1: independently re-verify, not just trust the packer's own
    # internal invariants -- every target assigned to exactly one fold.
    # "Exactly once" is two separate conditions: no duplicate (the naive
    # len(all_assigned) == len(set(all_assigned)) check) AND no missing
    # (the assigned count must also equal the expected total -- a target
    # silently dropped from every fold's target set would still pass the
    # duplicate-only check, since len(assigned) == len(set(assigned)) holds
    # trivially whenever every element is merely unique, missing or not).
    all_assigned: list[str] = [tid for fold_set in fold_target_ids for tid in fold_set]
    total_targets_expected = sum(c.target_count for c in components)
    no_duplicates = len(all_assigned) == len(set(all_assigned))
    no_missing = len(all_assigned) == total_targets_expected
    no_missing_or_duplicate = no_duplicates and no_missing

    # Atomicity: every component's full target set must land inside exactly
    # one fold's target set (never split across two folds).
    all_atomic = True
    for component in components:
        component_target_set = set(component.target_ids)
        fold_index = assignment[component.component_id]
        if not component_target_set.issubset(fold_target_ids[fold_index]):
            all_atomic = False
            break

    folds = tuple(
        FoldDiagnostics(
            outer_fold=i,
            target_count=len(fold_target_ids[i]),
            qa_target_count=fold_task_counts[i].get("qa", 0),
            summary_target_count=fold_task_counts[i].get("summary", 0),
            dialogue_generation_target_count=fold_task_counts[i].get("dialogue_generation", 0),
            component_count=fold_component_counts[i],
            owner_count=len(fold_owner_ids[i]),
            owner_ids=tuple(sorted(fold_owner_ids[i])),
        )
        for i in range(n_outer_folds)
    )

    target_counts = [float(f.target_count) for f in folds]
    owner_counts = [f.owner_count for f in folds]
    target_count_mean = statistics.fmean(target_counts) if target_counts else 0.0
    target_count_max = max(target_counts) if target_counts else 0.0

    return PackingSurfacePoint(
        n_outer_folds=n_outer_folds,
        seed=seed,
        folds=folds,
        total_components=len(components),
        total_targets_expected=total_targets_expected,
        total_targets_assigned=len(all_assigned),
        # B27.1: reuse the same, already-correct no_missing_or_duplicate
        # computation -- these two fields assert the identical claim and
        # must never be allowed to diverge into two different checks again.
        all_targets_assigned_exactly_once=no_missing_or_duplicate,
        all_components_atomic=all_atomic,
        no_missing_or_duplicate_targets=no_missing_or_duplicate,
        target_count_min=int(min(target_counts)) if target_counts else 0,
        target_count_max=int(target_count_max) if target_counts else 0,
        target_count_mean=target_count_mean,
        target_count_variance=_pvariance(target_counts),
        target_count_imbalance_ratio=(
            (target_count_max / target_count_mean) if target_count_mean else None
        ),
        owner_count_min=min(owner_counts) if owner_counts else 0,
        owner_count_max=max(owner_counts) if owner_counts else 0,
    )


def enumerate_packing_surface(
    components: tuple[GroupComponent, ...],
    *,
    k_values: tuple[int, ...] = DEFAULT_K_VALUES,
    seed_values: tuple[int, ...] = DEFAULT_SEED_VALUES,
) -> tuple[PackingSurfacePoint, ...]:
    """One ``PackingSurfacePoint`` per (K, seed) pair, K in ``k_values`` capped
    at the component count (``pack_components_into_outer_folds`` rejects
    ``n_outer_folds > len(components)``; with 477 components this never
    triggers for K<=10, but the cap keeps this function correct at any
    component count)."""

    points: list[PackingSurfacePoint] = []
    max_k = min(max(k_values), len(components)) if components else 0
    for k in k_values:
        if k > max_k:
            continue
        for seed in seed_values:
            assignment = pack_components_into_outer_folds(components, n_outer_folds=k, seed=seed)
            points.append(_diagnose_packing(components, assignment, k, seed))
    return tuple(points)


def summarize_packing_surface(
    points: tuple[PackingSurfacePoint, ...],
    *,
    k_values: tuple[int, ...],
    seed_values: tuple[int, ...],
    total_components: int,
) -> dict[str, Any]:
    all_valid = all(
        p.all_targets_assigned_exactly_once and p.all_components_atomic and p.no_missing_or_duplicate_targets
        for p in points
    )
    imbalance_ratios = [p.target_count_imbalance_ratio for p in points if p.target_count_imbalance_ratio is not None]

    return {
        "protocol": "pm-paper1-outer-fold-packing-surface-summary-v1",
        "status": "OUTER_FOLD_PACKING_DECISION_SURFACE_AUDIT_NOT_A_FREEZE",
        "outcome_calls": 0,
        "no_winner_note": NO_WINNER_NOTE,
        "primary_component_status": "PREPACK_EXACT_EVIDENCE_COMPONENT",
        "outer_fold_packing_status": "OUTER_FOLD_PACKING_PENDING_M2_FREEZE",
        "component_id_is_not_fold_id_note": (
            "group_component_id is never treated as an outer fold_id "
            "anywhere in this module or its outputs; folds here are 0-"
            "indexed integers assigned only by pack_components_into_"
            "outer_folds for the purpose of this diagnostic surface."
        ),
        "shared_session_sensitivity_note": (
            "Shared-session connected components "
            "(build_shared_session_sensitivity_components) are not read, "
            "computed, or referenced anywhere in this module -- they "
            "remain sensitivity-only (AGENTS.md rule 6) and are never "
            "promoted to primary grouping by this surface audit."
        ),
        "k_values": list(k_values),
        "seed_values": list(seed_values),
        "total_components": total_components,
        "surface_points_total": len(points),
        "surface_points_expected": sum(1 for k in k_values if k <= total_components) * len(seed_values),
        "all_points_pass_structural_integrity_checks": all_valid,
        "structural_integrity_note": (
            "'Pass' here means only the three mechanical invariants "
            "checked per point (exactly-once target assignment, component "
            "atomicity, no missing/duplicate target) -- never a PASS/FAIL "
            "verdict on which K or seed to use."
        ),
        "target_count_imbalance_ratio_max_over_mean_across_surface": {
            "min": min(imbalance_ratios) if imbalance_ratios else None,
            "max": max(imbalance_ratios) if imbalance_ratios else None,
            "mean": statistics.fmean(imbalance_ratios) if imbalance_ratios else None,
        },
    }
