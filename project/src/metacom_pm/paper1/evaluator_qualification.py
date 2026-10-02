"""Outcome-blind ESC evaluator-qualification contracts and metrics.

This module is deliberately separate from the formal ESC-Eval runner.  It
accepts only opaque qualification item identifiers, two-human blind ratings,
adjudicated human references, and candidate-evaluator traces.  It never reads
PM arms, Top-k labels, or formal benchmark outcomes.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import defaultdict
from typing import Any, Iterable, Mapping, Sequence


DIMENSIONS = (
    "Fluency",
    "Expression",
    "Empathy",
    "Information",
    "Skillful",
    "Humanoid",
    "Overall",
)
# The pinned ESC-Eval ``prompt_EN`` list is not in ``DIMENSIONS`` order:
# Humanoid precedes Skillful in the official scorer.  Keep the report/schema
# order above for compatibility, but never pair prompts by positional index.
OFFICIAL_RUBRIC_DIMENSION_ORDER = (
    "Fluency",
    "Expression",
    "Empathy",
    "Information",
    "Humanoid",
    "Skillful",
    "Overall",
)
FORBIDDEN_FIELDS = {
    "pm_identity",
    "arm",
    "on_off",
    "k",
    "token_budget",
    "ours",
    "baseline",
    "retrieval_score",
    "head_decision",
    "formal_outcome",
}


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def assert_blind_payload(value: Any) -> None:
    """Reject PM/system-label leakage at any nesting depth."""

    if isinstance(value, Mapping):
        overlap = set(value) & FORBIDDEN_FIELDS
        if overlap:
            raise ValueError(f"blind payload exposes forbidden fields: {sorted(overlap)}")
        for nested in value.values():
            assert_blind_payload(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            assert_blind_payload(nested)


def validate_scores(scores: Mapping[str, Any]) -> dict[str, int]:
    if set(scores) != set(DIMENSIONS):
        missing = sorted(set(DIMENSIONS) - set(scores))
        extra = sorted(set(scores) - set(DIMENSIONS))
        raise ValueError(f"seven-dimension score mismatch; missing={missing}, extra={extra}")
    normalized: dict[str, int] = {}
    for dimension in DIMENSIONS:
        score = scores[dimension]
        if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 4:
            raise ValueError(f"{dimension} must be an integer on the official 0-4 scale")
        normalized[dimension] = score
    return normalized


def validate_single_overall_adjudication(
    row: Mapping[str, Any], *, expected_item_id: str
) -> dict[str, Any]:
    """Validate the pre-candidate targeted adjudication of one major Overall split."""

    if row.get("status") != "ADJUDICATION_COMPLETE":
        raise ValueError("single Overall adjudication status must be ADJUDICATION_COMPLETE")
    if row.get("adjudication_completed") is not True:
        raise ValueError("single Overall adjudication must be complete")
    if row.get("blind_item_id") != expected_item_id:
        raise ValueError("single Overall adjudication item identity mismatch")
    if row.get("dimension") != "Overall":
        raise ValueError("targeted adjudication may resolve only Overall")
    score = row.get("adjudicated_score")
    if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 4:
        raise ValueError("adjudicated Overall score must be an integer on 0-4")
    if row.get("identity_blinded") is not True:
        raise ValueError("adjudication must remain identity blinded")
    if row.get("original_rater_scores_shown_to_adjudicator") is not False:
        raise ValueError("targeted adjudicator must not see original rater scores")
    return {
        "blind_item_id": expected_item_id,
        "dimension": "Overall",
        "adjudicated_score": score,
        "identity_blinded": True,
        "original_rater_scores_shown_to_adjudicator": False,
    }


def quadratic_weighted_kappa(left: Sequence[int], right: Sequence[int]) -> float | None:
    """Quadratic weighted kappa on the frozen 0..4 ordinal scale."""

    if len(left) != len(right) or not left:
        raise ValueError("kappa requires equal non-empty vectors")
    for value in (*left, *right):
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 4:
            raise ValueError("kappa values must be integer ordinals 0..4")
    observed = [[0.0] * 5 for _ in range(5)]
    left_counts = [0.0] * 5
    right_counts = [0.0] * 5
    for a, b in zip(left, right, strict=True):
        observed[a][b] += 1.0
        left_counts[a] += 1.0
        right_counts[b] += 1.0
    n = float(len(left))
    observed_disagreement = 0.0
    expected_disagreement = 0.0
    for i in range(5):
        for j in range(5):
            weight = ((i - j) / 4.0) ** 2
            observed_disagreement += weight * observed[i][j] / n
            expected_disagreement += weight * (left_counts[i] * right_counts[j] / (n * n))
    if expected_disagreement == 0.0:
        return 1.0 if observed_disagreement == 0.0 else None
    return 1.0 - observed_disagreement / expected_disagreement


def _average_ranks(values: Sequence[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda row: (row[1], row[0]))
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(indexed):
        end = cursor + 1
        while end < len(indexed) and indexed[end][1] == indexed[cursor][1]:
            end += 1
        rank = (cursor + 1 + end) / 2.0
        for original_index, _ in indexed[cursor:end]:
            ranks[original_index] = rank
        cursor = end
    return ranks


def spearman_rho(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        raise ValueError("Spearman requires equal vectors with at least two observations")
    a = _average_ranks(left)
    b = _average_ranks(right)
    mean_a = statistics.fmean(a)
    mean_b = statistics.fmean(b)
    numerator = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b, strict=True))
    denominator = math.sqrt(
        sum((x - mean_a) ** 2 for x in a) * sum((y - mean_b) ** 2 for y in b)
    )
    return None if denominator == 0.0 else numerator / denominator


def mean_absolute_deviation(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("MAD requires equal non-empty vectors")
    return statistics.fmean(abs(x - y) for x, y in zip(left, right, strict=True))


def _sign(value: float) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def _score_index(rows: Iterable[Mapping[str, Any]], *, id_field: str) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for row in rows:
        item_id = str(row[id_field])
        if item_id in result:
            raise ValueError(f"duplicate score row for {item_id}")
        result[item_id] = validate_scores(row["scores"])
    return result


def human_reliability(
    human_rows: Sequence[Mapping[str, Any]], item_ids: Sequence[str]
) -> dict[str, Any]:
    by_rater: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in human_rows:
        by_rater[str(row["rater_id"])].append(row)
    if len(by_rater) != 2:
        raise ValueError("exactly two independent human raters are required")
    rater_ids = sorted(by_rater)
    indexes = [_score_index(by_rater[rater], id_field="blind_item_id") for rater in rater_ids]
    expected = set(item_ids)
    if any(set(index) != expected for index in indexes):
        raise ValueError("both human raters must cover every frozen qualification item exactly once")
    per_dimension = {}
    for dimension in DIMENSIONS:
        left = [indexes[0][item][dimension] for item in item_ids]
        right = [indexes[1][item][dimension] for item in item_ids]
        absolute_differences = [abs(a - b) for a, b in zip(left, right, strict=True)]
        per_dimension[dimension] = {
            "rater_means": {
                rater_ids[0]: statistics.fmean(left),
                rater_ids[1]: statistics.fmean(right),
            },
            "exact_agreement_rate": sum(a == b for a, b in zip(left, right, strict=True))
            / len(left),
            "absolute_difference_ge_2_items": sum(value >= 2 for value in absolute_differences),
            "quadratic_weighted_kappa": quadratic_weighted_kappa(left, right),
            "spearman_rho": spearman_rho(left, right),
            "mean_absolute_deviation": mean_absolute_deviation(left, right),
        }
    major_any_dimension = []
    for item in item_ids:
        differing = [
            dimension
            for dimension in DIMENSIONS
            if abs(indexes[0][item][dimension] - indexes[1][item][dimension]) >= 2
        ]
        if differing:
            major_any_dimension.append({"blind_item_id": item, "dimensions": differing})
    major_overall = [
        item
        for item in item_ids
        if abs(indexes[0][item]["Overall"] - indexes[1][item]["Overall"]) >= 2
    ]
    return {
        "rater_ids": rater_ids,
        "items": len(item_ids),
        "per_dimension": per_dimension,
        "major_disagreement": {
            "definition": "absolute ordinal-score difference >= 2",
            "items_any_dimension": len(major_any_dimension),
            "items_any_dimension_detail": major_any_dimension,
            "items_overall": len(major_overall),
            "overall_item_ids": major_overall,
        },
    }


def analyze_candidate(
    *,
    candidate_id: str,
    item_rows: Sequence[Mapping[str, Any]],
    adjudicated_rows: Sequence[Mapping[str, Any]],
    candidate_rows: Sequence[Mapping[str, Any]],
    pair_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compare one frozen evaluator identity with adjudicated human reference."""

    item_ids = [str(row["blind_item_id"]) for row in item_rows]
    reference = _score_index(adjudicated_rows, id_field="blind_item_id")
    candidate_subset = [row for row in candidate_rows if row["candidate_id"] == candidate_id]
    expected = set(item_ids)
    if set(reference) != expected:
        raise ValueError("reference must cover every frozen qualification item")
    candidate_rows_by_id: dict[str, Mapping[str, Any]] = {}
    candidate: dict[str, dict[str, int]] = {}
    for row in candidate_subset:
        item_id = str(row["blind_item_id"])
        if item_id in candidate_rows_by_id:
            raise ValueError(f"duplicate candidate score row for {item_id}")
        candidate_rows_by_id[item_id] = row
        if row.get("parse_valid") is True:
            candidate[item_id] = validate_scores(row["scores"])
    if set(candidate_rows_by_id) != expected:
        raise ValueError("candidate traces must cover every frozen qualification item")

    per_dimension: dict[str, Any] = {}
    for dimension in DIMENSIONS:
        valid_items = [item for item in item_ids if item in candidate]
        truth = [reference[item][dimension] for item in valid_items]
        predicted = [candidate[item][dimension] for item in valid_items]
        per_dimension[dimension] = {
            "valid_items": len(valid_items),
            "quadratic_weighted_kappa": quadratic_weighted_kappa(truth, predicted)
            if truth
            else None,
            "spearman_rho": spearman_rho(truth, predicted) if len(truth) >= 2 else None,
            "mean_absolute_deviation": mean_absolute_deviation(truth, predicted)
            if truth
            else None,
            "dynamic_range": max(predicted) - min(predicted) if predicted else None,
            "unique_ordinals": len(set(predicted)),
        }

    pairwise_by_kind: dict[str, dict[str, int | float | None]] = {}
    for kind in sorted({str(row["pair_kind"]) for row in pair_rows}):
        subset = [row for row in pair_rows if row["pair_kind"] == kind]
        agree = 0
        valid = 0
        judge_pref_variant = 0
        deltas: list[float] = []
        for pair in subset:
            control = str(pair["control_item_id"])
            variant = str(pair["variant_item_id"])
            if control not in reference or variant not in reference or control not in candidate or variant not in candidate:
                continue
            human_delta = reference[variant]["Overall"] - reference[control]["Overall"]
            judge_delta = candidate[variant]["Overall"] - candidate[control]["Overall"]
            valid += 1
            agree += _sign(human_delta) == _sign(judge_delta)
            judge_pref_variant += judge_delta > 0
            deltas.append(float(judge_delta))
        pairwise_by_kind[kind] = {
            "pairs": valid,
            "winner_agreement": agree / valid if valid else None,
            "mean_variant_minus_control_overall": statistics.fmean(deltas) if deltas else None,
            "variant_preference_rate": judge_pref_variant / valid if valid else None,
        }

    parse_valid = [bool(row.get("parse_valid")) for row in candidate_subset]
    latencies = [float(row["latency_seconds"]) for row in candidate_subset]
    costs = [float(row["cost_usd"]) for row in candidate_subset]
    return {
        "candidate_id": candidate_id,
        "items": len(item_ids),
        "valid_parse_rate": sum(parse_valid) / len(parse_valid),
        "per_dimension": per_dimension,
        "pairwise": pairwise_by_kind,
        "latency_seconds": {
            "mean": statistics.fmean(latencies),
            "median": statistics.median(latencies),
        },
        "cost_usd": {"total": sum(costs), "mean_per_item": statistics.fmean(costs)},
    }


def blocked_result(*, blockers: Sequence[str], evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Represent an honest incomplete qualification without fabricated metrics."""

    return {
        "protocol": "pm-paper1-esc-evaluator-qualification-results-v1",
        "status": "BLOCKED",
        "blockers": list(blockers),
        "recommendation": None,
        "selection_order": [
            "validity_and_human_agreement",
            "bias_and_sensitivity",
            "cost_and_latency",
        ],
        "forbidden_selection_basis": "which evaluator gives PM/Ours a higher score",
        "evidence": dict(evidence),
        "formal_ESC_Eval": False,
        "formal_outcome_calls": 0,
    }


def grouped_residual_bias(
    *,
    reference_scores: Mapping[str, Mapping[str, int]],
    candidate_scores: Mapping[str, Mapping[str, int]],
    item_groups: Mapping[str, str],
) -> dict[str, Any]:
    """Describe candidate-minus-human residuals by hidden system family/style.

    The mapping is joined only after blind ratings. It must never be included
    in candidate-evaluator prompts or human sheets.
    """

    grouped: dict[str, list[float]] = defaultdict(list)
    for item_id, group in item_groups.items():
        if item_id not in reference_scores or item_id not in candidate_scores:
            continue
        residual = statistics.fmean(
            candidate_scores[item_id][dimension] - reference_scores[item_id][dimension]
            for dimension in DIMENSIONS
        )
        grouped[group].append(residual)
    means = {
        group: statistics.fmean(values) for group, values in sorted(grouped.items()) if values
    }
    return {
        "mean_candidate_minus_human_by_group": means,
        "max_minus_min_group_residual": max(means.values()) - min(means.values())
        if len(means) >= 2
        else None,
        "interpretation": "descriptive hidden-group residual audit; not a utility filter",
    }
