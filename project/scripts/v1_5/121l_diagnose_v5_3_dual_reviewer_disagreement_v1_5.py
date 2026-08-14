#!/usr/bin/env python3
"""Segment V5.3 calibration disagreement by component and label direction."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import write_json  # noqa: E402


DIR = ROOT / "outputs/pm_v1_5_v5_3_dual_reviewer_calibration_20260810"
COMPONENTS = ("MP", "MS", "ME", "RS")


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _pair_summary(pairs: list[tuple[str, str]]) -> dict[str, Any]:
    confusion = Counter(f"A:{left}|B:{right}" for left, right in pairs)
    agreed = sum(left == right for left, right in pairs)
    return {
        "n": len(pairs),
        "raw_agreement": _rate(agreed, len(pairs)),
        "reviewer_A_counts": dict(Counter(left for left, _ in pairs)),
        "reviewer_B_counts": dict(Counter(right for _, right in pairs)),
        "confusion": dict(confusion),
    }


def main() -> None:
    packet = _jsonl(DIR / "review_packet_blind.jsonl")
    review_a = {row["calibration_id"]: row for row in _jsonl(DIR / "reviewer_A_completed.jsonl")}
    review_b = {row["calibration_id"]: row for row in _jsonl(DIR / "reviewer_B_completed.jsonl")}
    if not (len(packet) == len(review_a) == len(review_b) == 64):
        raise RuntimeError("complete aligned reviews required")
    meta = {row["calibration_id"]: row for row in packet}

    pairs: dict[str, dict[str, list[tuple[str, str]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    consensus: dict[str, Counter[str]] = {component: Counter() for component in COMPONENTS}
    clean_consensus_groups: Counter[str] = Counter()
    group_details: list[dict[str, Any]] = []

    for calibration_id, item in meta.items():
        component = str(item["component"])
        left = review_a[calibration_id]
        right = review_b[calibration_id]
        candidate_left = (
            "CLEAR" if left["candidate_truth"] == "VALID_APPLICABLE" else "NONCLEAR"
        )
        candidate_right = (
            "CLEAR" if right["candidate_truth"] == "VALID_APPLICABLE" else "NONCLEAR"
        )
        for segment in ("ALL", component):
            pairs[segment]["candidate"].append((candidate_left, candidate_right))
        if candidate_left == candidate_right:
            consensus[component][f"candidate:{candidate_left}"] += 1
        else:
            consensus[component]["candidate:DISAGREE"] += 1

        left_rep = {row["replicate_id"]: row for row in left["replicates"]}
        right_rep = {row["replicate_id"]: row for row in right["replicates"]}
        qualified_consensus = 0
        preference_consensus = Counter()
        risk_safe_consensus = 0
        group_disagreement_dimensions = Counter()
        for replicate_id in sorted(left_rep):
            lrep = left_rep[replicate_id]
            rrep = right_rep[replicate_id]
            function_left = (
                "QUALIFIED" if lrep["functional_execution"] == "FUNCTIONAL" else "NONQUALIFIED"
            )
            function_right = (
                "QUALIFIED" if rrep["functional_execution"] == "FUNCTIONAL" else "NONQUALIFIED"
            )
            for segment in ("ALL", component):
                pairs[segment]["function"].append((function_left, function_right))
                pairs[segment]["preference"].append(
                    (lrep["response_preference"], rrep["response_preference"])
                )
                pairs[segment]["risk"].append(
                    (lrep["resource_risk_attribution"], rrep["resource_risk_attribution"])
                )
            if function_left == function_right:
                consensus[component][f"function:{function_left}"] += 1
                qualified_consensus += int(function_left == "QUALIFIED")
            else:
                consensus[component]["function:DISAGREE"] += 1
                group_disagreement_dimensions["function"] += 1
            if lrep["response_preference"] == rrep["response_preference"]:
                label = str(lrep["response_preference"])
                consensus[component][f"preference:{label}"] += 1
                preference_consensus[label] += 1
            else:
                consensus[component]["preference:DISAGREE"] += 1
                group_disagreement_dimensions["preference"] += 1
            if lrep["resource_risk_attribution"] == rrep["resource_risk_attribution"]:
                label = str(lrep["resource_risk_attribution"])
                consensus[component][f"risk:{label}"] += 1
                risk_safe_consensus += int(label == "SAFE")
            else:
                consensus[component]["risk:DISAGREE"] += 1
                group_disagreement_dimensions["risk"] += 1

        candidate_consensus_clear = candidate_left == candidate_right == "CLEAR"
        fully_labelable = (
            candidate_consensus_clear
            and qualified_consensus >= 2
            and risk_safe_consensus == 3
            and sum(preference_consensus.values()) == 3
        )
        clean_consensus_groups[component] += int(fully_labelable)
        group_details.append(
            {
                "calibration_id": calibration_id,
                "component": component,
                "candidate_type": item["candidate_type"],
                "candidate_A": candidate_left,
                "candidate_B": candidate_right,
                "qualified_function_consensus_replicates": qualified_consensus,
                "risk_safe_consensus_replicates": risk_safe_consensus,
                "preference_consensus": dict(preference_consensus),
                "disagreement_dimensions": dict(group_disagreement_dimensions),
                "provisionally_fully_labelable_before_adjudication": fully_labelable,
            }
        )

    segments = {
        segment: {
            dimension: _pair_summary(values)
            for dimension, values in dimensions.items()
        }
        for segment, dimensions in pairs.items()
    }
    report = {
        "protocol": "pm-v1.5-v5.3-dual-reviewer-disagreement-diagnosis-v1",
        "status": "ROOT_DISAGREEMENT_SHAPE_ESTABLISHED_NO_TRAINING",
        "grain": {
            "candidate": "64 effect groups",
            "function_preference_risk": "192 paired replicates",
            "component_groups": 16,
            "component_replicates": 48,
        },
        "segments": segments,
        "consensus_counts_by_component": {
            component: dict(consensus[component]) for component in COMPONENTS
        },
        "provisionally_fully_labelable_groups_by_component": dict(clean_consensus_groups),
        "provisionally_fully_labelable_groups_total": sum(clean_consensus_groups.values()),
        "group_details": group_details,
        "diagnosis": [
            "Reviewer B is systematically more permissive on candidate applicability, functional use, and ON preference; disagreement is directional rather than random.",
            "The combined multi-axis review prompt permits candidate/function/preference judgments to influence each other and should not be used as one gold-producing instrument.",
            "Consensus-only rows are safer than either reviewer alone but cannot unlock training until bidirectional label and independent-cluster support are checked.",
            "The next calibration must decompose candidate, function, quality, and risk into separate blinded roles on a new outcome-hidden sample.",
        ],
        "api_calls": 0,
    }
    write_json(DIR / "disagreement_diagnostics.json", report)
    print(json.dumps({
        "status": report["status"],
        "fully_labelable": report["provisionally_fully_labelable_groups_total"],
        "by_component": report["provisionally_fully_labelable_groups_by_component"],
        "component_agreement": {
            component: {
                dimension: report["segments"][component][dimension]["raw_agreement"]
                for dimension in ("candidate", "function", "preference", "risk")
            }
            for component in COMPONENTS
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
