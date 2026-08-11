"""Paper 1 P2 atomic bounded-suitability measurement primitives.

This module defines the projection and reliability calculations before any
real public-state judgment is created.  Structural validity is upstream P1B
truth and is never relabeled by a semantic reviewer.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence


SUITABILITY_AXES = (
    "current_target_fit",
    "specific_increment_available",
    "component_minimum_possible_now",
    "current_boundary_permits",
)
AXIS_VALUES = frozenset({"YES", "NO", "UNKNOWN"})
DERIVED_VALUES = frozenset({"SUITABLE", "NOT_SUITABLE", "UNKNOWN"})
ABSENCE_REASON_CODES = frozenset(
    {
        "NONE",
        "NO_TARGET_MATCH",
        "INCREMENT_ALREADY_VISIBLE",
        "ONLY_GENERIC_OR_DECORATIVE",
        "BOUNDARY_CONFLICT",
        "NO_POSITIVE_SPAN_REQUIRED",
    }
)
UNKNOWN_REASON_CODES = frozenset(
    {
        "NONE",
        "TARGET_AMBIGUOUS",
        "REDUNDANCY_AMBIGUOUS",
        "MINIMUM_AMBIGUOUS",
        "BOUNDARY_AMBIGUOUS",
    }
)


def derive_suitability(axes: Mapping[str, str]) -> str:
    """Project four tri-state atoms without holistic reviewer discretion."""

    if set(axes) != set(SUITABILITY_AXES):
        raise ValueError("suitability judgment must contain exactly four frozen axes")
    values = [str(axes[axis]) for axis in SUITABILITY_AXES]
    if any(value not in AXIS_VALUES for value in values):
        raise ValueError("axis values must be YES, NO, or UNKNOWN")
    if "NO" in values:
        return "NOT_SUITABLE"
    if all(value == "YES" for value in values):
        return "SUITABLE"
    return "UNKNOWN"


def validate_atomic_judgment(
    judgment: Mapping[str, Any],
    *,
    allowed_visible_span_ids: Sequence[str],
    allowed_candidate_span_ids: Sequence[str],
) -> list[str]:
    """Validate one reviewer row without deciding whether its semantics are true.

    Reviewers select pre-numbered spans instead of copying prose.  A negative
    judgment may use an explicit absence reason with no span; blank evidence
    without such a reason is invalid.
    """

    errors: list[str] = []
    axes = judgment.get("axes")
    if not isinstance(axes, Mapping) or set(axes) != set(SUITABILITY_AXES):
        return ["axes_schema_invalid"]
    allowed_visible = set(allowed_visible_span_ids)
    allowed_candidate = set(allowed_candidate_span_ids)
    for axis in SUITABILITY_AXES:
        payload = axes[axis]
        if not isinstance(payload, Mapping):
            errors.append(f"{axis}:payload_invalid")
            continue
        decision = str(payload.get("decision") or "")
        if decision not in AXIS_VALUES:
            errors.append(f"{axis}:decision_invalid")
        visible = list(payload.get("visible_span_ids") or [])
        candidate = list(payload.get("candidate_span_ids") or [])
        if any(span not in allowed_visible for span in visible):
            errors.append(f"{axis}:visible_span_invalid")
        if any(span not in allowed_candidate for span in candidate):
            errors.append(f"{axis}:candidate_span_invalid")
        # ``None`` was the original in-memory representation of no reason;
        # the paid strict schema emits the explicit transport value ``NONE``.
        absence_reason = str(payload.get("absence_reason_code") or "NONE")
        unknown_reason = str(payload.get("unknown_reason_code") or "NONE")
        if absence_reason not in ABSENCE_REASON_CODES:
            errors.append(f"{axis}:absence_reason_invalid")
        if unknown_reason not in UNKNOWN_REASON_CODES:
            errors.append(f"{axis}:unknown_reason_invalid")
        if decision in {"YES", "NO"} and not (
            visible or candidate or absence_reason != "NONE"
        ):
            errors.append(f"{axis}:resolved_without_evidence_or_absence_reason")
        if decision == "UNKNOWN" and unknown_reason == "NONE":
            errors.append(f"{axis}:unknown_without_reason")
        if decision != "UNKNOWN" and unknown_reason != "NONE":
            errors.append(f"{axis}:resolved_with_unknown_reason")
    projected = derive_suitability(
        {axis: str(axes[axis].get("decision") or "") for axis in SUITABILITY_AXES}
    ) if not any(error.endswith("decision_invalid") for error in errors) else None
    if projected is not None and judgment.get("derived_suitability") != projected:
        errors.append("derived_suitability_not_mechanical")
    return errors


def raw_agreement(left: Sequence[str], right: Sequence[str]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("agreement vectors must be same non-zero length")
    return sum(a == b for a, b in zip(left, right, strict=True)) / len(left)


def gwet_ac1(left: Sequence[str], right: Sequence[str]) -> float:
    """Nominal multi-category Gwet AC1 for two raters."""

    if len(left) != len(right) or not left:
        raise ValueError("agreement vectors must be same non-zero length")
    categories = sorted(set(left) | set(right))
    if len(categories) == 1:
        return 1.0
    counts = Counter([*left, *right])
    total = 2 * len(left)
    proportions = [counts[category] / total for category in categories]
    chance = sum(p * (1.0 - p) for p in proportions) / (len(categories) - 1)
    observed = raw_agreement(left, right)
    return (observed - chance) / (1.0 - chance) if chance < 1.0 else 1.0


def component_qualification(
    paired_rows: Sequence[Mapping[str, Any]],
    *,
    per_axis_raw_min: float = 0.80,
    per_axis_ac1_min: float = 0.60,
    derived_raw_min: float = 0.80,
    resolved_coverage_min: float = 0.80,
    min_suitable_groups: int = 8,
    min_not_suitable_groups: int = 8,
) -> dict[str, Any]:
    """Compute pre-adjudication measurement gates for one component."""

    if not paired_rows:
        raise ValueError("qualification needs at least one paired judgment")
    axis_metrics: dict[str, dict[str, float]] = {}
    for axis in SUITABILITY_AXES:
        left = [str(row["reviewer_a_axes"][axis]) for row in paired_rows]
        right = [str(row["reviewer_b_axes"][axis]) for row in paired_rows]
        axis_metrics[axis] = {
            "raw_agreement": raw_agreement(left, right),
            "gwet_ac1": gwet_ac1(left, right),
        }
    derived_a = [str(row["reviewer_a_derived"]) for row in paired_rows]
    derived_b = [str(row["reviewer_b_derived"]) for row in paired_rows]
    consensus = [
        left if left == right and left in {"SUITABLE", "NOT_SUITABLE"} else None
        for left, right in zip(derived_a, derived_b, strict=True)
    ]
    suitable_groups = {
        str(row["split_group_key"])
        for row, label in zip(paired_rows, consensus, strict=True)
        if label == "SUITABLE"
    }
    not_suitable_groups = {
        str(row["split_group_key"])
        for row, label in zip(paired_rows, consensus, strict=True)
        if label == "NOT_SUITABLE"
    }
    resolved_coverage = sum(label is not None for label in consensus) / len(consensus)
    checks = {
        "all_axis_raw_agreement": all(
            metric["raw_agreement"] >= per_axis_raw_min
            for metric in axis_metrics.values()
        ),
        "all_axis_gwet_ac1": all(
            metric["gwet_ac1"] >= per_axis_ac1_min
            for metric in axis_metrics.values()
        ),
        "derived_raw_agreement": raw_agreement(derived_a, derived_b)
        >= derived_raw_min,
        "resolved_coverage": resolved_coverage >= resolved_coverage_min,
        "suitable_independent_group_support": len(suitable_groups)
        >= min_suitable_groups,
        "not_suitable_independent_group_support": len(not_suitable_groups)
        >= min_not_suitable_groups,
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "status": "QUALIFIED" if not failed else "FAILED_FIXED_OFF",
        "checks": checks,
        "failed_checks": failed,
        "axis_metrics": axis_metrics,
        "derived_raw_agreement": raw_agreement(derived_a, derived_b),
        "derived_gwet_ac1": gwet_ac1(derived_a, derived_b),
        "resolved_coverage": resolved_coverage,
        "suitable_independent_groups": len(suitable_groups),
        "not_suitable_independent_groups": len(not_suitable_groups),
        "pre_adjudication_only": True,
    }
