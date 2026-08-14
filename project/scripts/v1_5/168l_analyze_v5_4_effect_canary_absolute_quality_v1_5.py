#!/usr/bin/env python3
"""Analyze frozen absolute-quality reliability and canary paired uplifts."""

from __future__ import annotations

from collections import Counter
import json
import math
from pathlib import Path
from statistics import mean


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "outputs/pm_v1_5_v5_4_effect_canary_absolute_quality_20260810"
RESULTS = SOURCE / "results.jsonl"
MANIFEST = SOURCE / "absolute_quality_case_manifest_private.jsonl"
CANARY = ROOT / "outputs/pm_v1_5_v5_4_effect_canary_preflight_20260810/canary_effect_groups_private.jsonl"
CONTRACT = ROOT / "data/pm_v1_5_contracts/v5_4_effect_canary_absolute_quality_repair_v1.json"
OUT = ROOT / "outputs/pm_v1_5_v5_4_effect_canary_absolute_quality_analysis_20260810"
AXES = ("goal_advance", "emotional_attunement", "specific_positive_support", "clarity_naturalness")
REVIEWERS = ("REVIEWER_A", "REVIEWER_B")


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def average_ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(order):
        end = cursor + 1
        while end < len(order) and values[order[end]] == values[order[cursor]]:
            end += 1
        rank = (cursor + 1 + end) / 2
        for position in range(cursor, end):
            ranks[order[position]] = rank
        cursor = end
    return ranks


def pearson(left: list[float], right: list[float]) -> float | None:
    if not left or len(left) != len(right):
        return None
    lm, rm = mean(left), mean(right)
    numerator = sum((a - lm) * (b - rm) for a, b in zip(left, right))
    denominator = math.sqrt(sum((a - lm) ** 2 for a in left) * sum((b - rm) ** 2 for b in right))
    return numerator / denominator if denominator else None


def spearman(left: list[float], right: list[float]) -> float | None:
    return pearson(average_ranks(left), average_ranks(right))


def direction(value: float) -> str:
    if value >= 0.25:
        return "POSITIVE"
    if value <= -0.25:
        return "NEGATIVE"
    return "TIE"


def main() -> None:
    result_rows = rows(RESULTS)
    manifest_rows = rows(MANIFEST)
    canary = {row["effect_group_id"]: row for row in rows(CANARY)}
    contract = json.loads(CONTRACT.read_text())
    mapping = {(row["reviewer_id"], row["case_id"]): row for row in manifest_rows}
    scores: dict[tuple[str, str, str, str], dict] = {}
    status_counts = Counter()
    for batch in result_rows:
        reviewer = batch["reviewer_id"]
        for item in batch["judgment"]["cases"]:
            private = mapping[(reviewer, item["case_id"])]
            key = (reviewer, private["effect_group_id"], private["replicate_id"], private["arm"])
            scores[key] = item
            status_counts[item["assessment_status"]] += 1

    integrity = {
        "calls": len(result_rows),
        "unique_score_items": len(scores),
        "manifest_items": len(manifest_rows),
        "reviewer_call_counts": dict(Counter(row["reviewer_id"] for row in result_rows)),
        "assessment_status_counts": dict(status_counts),
        "complete": len(result_rows) == 16 and len(scores) == 96 and len(manifest_rows) == 96,
        "all_resolved": status_counts == Counter({"RESOLVED": 96}),
    }

    left_axis: list[float] = []
    right_axis: list[float] = []
    response_left: list[float] = []
    response_right: list[float] = []
    per_axis: dict[str, dict] = {}
    for axis in AXES:
        la, ra = [], []
        for group_id in sorted(canary):
            for replicate in ("r1", "r2", "r3"):
                for arm in ("ON", "OFF"):
                    la.append(scores[("REVIEWER_A", group_id, replicate, arm)][axis])
                    ra.append(scores[("REVIEWER_B", group_id, replicate, arm)][axis])
        per_axis[axis] = {
            "n": len(la),
            "exact_agreement": mean(a == b for a, b in zip(la, ra)),
            "within_one_point": mean(abs(a - b) <= 1 for a, b in zip(la, ra)),
            "mae": mean(abs(a - b) for a, b in zip(la, ra)),
            "spearman": spearman(la, ra),
        }
        left_axis.extend(la); right_axis.extend(ra)
    for group_id in sorted(canary):
        for replicate in ("r1", "r2", "r3"):
            for arm in ("ON", "OFF"):
                response_left.append(mean(scores[("REVIEWER_A", group_id, replicate, arm)][axis] for axis in AXES))
                response_right.append(mean(scores[("REVIEWER_B", group_id, replicate, arm)][axis] for axis in AXES))

    paired: list[dict] = []
    paired_left: list[float] = []
    paired_right: list[float] = []
    resolved_directions_left: list[str] = []
    resolved_directions_right: list[str] = []
    for group_id in sorted(canary):
        for replicate in ("r1", "r2", "r3"):
            reviewer_uplifts = {}
            for reviewer in REVIEWERS:
                on = mean(scores[(reviewer, group_id, replicate, "ON")][axis] for axis in AXES)
                off = mean(scores[(reviewer, group_id, replicate, "OFF")][axis] for axis in AXES)
                reviewer_uplifts[reviewer] = on - off
            left, right = reviewer_uplifts["REVIEWER_A"], reviewer_uplifts["REVIEWER_B"]
            paired_left.append(left); paired_right.append(right)
            ld, rd = direction(left), direction(right)
            dual_resolved = (ld == "TIE" and rd == "TIE") or (ld != "TIE" and rd != "TIE")
            if dual_resolved:
                resolved_directions_left.append(ld); resolved_directions_right.append(rd)
            paired.append({
                "effect_group_id": group_id,
                "component": canary[group_id]["component"],
                "replicate_id": replicate,
                "reviewer_a_uplift": left,
                "reviewer_b_uplift": right,
                "reviewer_a_direction": ld,
                "reviewer_b_direction": rd,
                "dual_direction_resolved": dual_resolved,
                "direction_agreement": dual_resolved and ld == rd,
                "panel_mean_uplift": mean((left, right)),
                "not_a_training_label": True,
            })

    direction_coverage = len(resolved_directions_left) / 24
    direction_agreement = mean(a == b for a, b in zip(resolved_directions_left, resolved_directions_right)) if resolved_directions_left else None
    reliability = {
        "axis_comparisons": len(left_axis),
        "axis_within_one_point_agreement": mean(abs(a - b) <= 1 for a, b in zip(left_axis, right_axis)),
        "axis_exact_agreement": mean(a == b for a, b in zip(left_axis, right_axis)),
        "axis_mae": mean(abs(a - b) for a, b in zip(left_axis, right_axis)),
        "per_axis": per_axis,
        "response_composite_n": len(response_left),
        "response_composite_spearman": spearman(response_left, response_right),
        "response_composite_pearson_diagnostic": pearson(response_left, response_right),
        "paired_uplift_n": len(paired_left),
        "paired_uplift_spearman": spearman(paired_left, paired_right),
        "paired_uplift_pearson_diagnostic": pearson(paired_left, paired_right),
        "paired_direction_dual_resolved": len(resolved_directions_left),
        "paired_direction_resolved_coverage": direction_coverage,
        "paired_direction_raw_agreement": direction_agreement,
    }
    gates = {
        "completion_and_exact_ids": integrity["complete"] and integrity["all_resolved"],
        "axis_within_one_point_ge_0_75": reliability["axis_within_one_point_agreement"] >= 0.75,
        "response_composite_spearman_ge_0_50": reliability["response_composite_spearman"] is not None and reliability["response_composite_spearman"] >= 0.50,
        "paired_uplift_spearman_ge_0_30": reliability["paired_uplift_spearman"] is not None and reliability["paired_uplift_spearman"] >= 0.30,
        "paired_direction_coverage_ge_0_50": direction_coverage >= 0.50,
        "paired_direction_agreement_ge_0_70": direction_agreement is not None and direction_agreement >= 0.70,
    }
    passed = all(gates.values())
    state_rows = []
    for group_id in sorted(canary):
        group_pairs = [row for row in paired if row["effect_group_id"] == group_id]
        state_rows.append({
            "effect_group_id": group_id,
            "component": canary[group_id]["component"],
            "panel_mean_uplift": mean(row["panel_mean_uplift"] for row in group_pairs) if passed else None,
            "replicate_uplifts": [row["panel_mean_uplift"] for row in group_pairs] if passed else [],
            "withheld_because_measurement_failed": not passed,
            "not_a_training_target": True,
        })
    resolved_state_values = [row["panel_mean_uplift"] for row in state_rows if row["panel_mean_uplift"] is not None]
    report = {
        "protocol": "pm-v1.5-v5.4-effect-canary-absolute-quality-analysis-v1",
        "status": "ABSOLUTE_QUALITY_MEASUREMENT_PASS" if passed else "ABSOLUTE_QUALITY_MEASUREMENT_FAIL_NO_TARGETS",
        "contract": contract["protocol"],
        "integrity": integrity,
        "reliability": reliability,
        "gates": gates,
        "measurement_pass": passed,
        "canary_effect_diagnostic": {
            "available_only_if_pass": True,
            "state_count": len(resolved_state_values),
            "nonconstant": len(set(resolved_state_values)) > 1 if resolved_state_values else False,
            "positive_states": sum(value > 0 for value in resolved_state_values),
            "tie_or_negative_states": sum(value <= 0 for value in resolved_state_values),
            "minimum": min(resolved_state_values) if resolved_state_values else None,
            "maximum": max(resolved_state_values) if resolved_state_values else None,
        },
        "pm_has_learned": False,
        "final_pm_pass_evaluated": False,
        "remaining_88_authorized": False,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    for name, output_rows in (("paired_replicate_diagnostics_not_training_labels.jsonl", paired), ("state_diagnostics_not_training_targets.jsonl", state_rows)):
        with (OUT / name).open("w") as handle:
            for row in output_rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
