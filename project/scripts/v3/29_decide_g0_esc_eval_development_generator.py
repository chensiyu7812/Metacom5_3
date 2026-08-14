#!/usr/bin/env python3
"""Apply the frozen ESC-Eval development generator decision contract."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import random
from statistics import mean
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = PROJECT_ROOT / "data" / "v3_authority"
CONTRACT = AUTHORITY / "generator_esc_eval_development_decision_contract_v1.json"
CLOSEOUT = AUTHORITY / "g0_four_generator_full_screen_closeout_v1.json"


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _quantile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _bootstrap_interval(values: list[float], seed: str, draws: int = 10000) -> list[float]:
    rng = random.Random(int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16], 16))
    sampled = [mean(values[rng.randrange(len(values))] for _ in values) for _ in range(draws)]
    return [_quantile(sampled, 0.05), _quantile(sampled, 0.95)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aggregation-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.exists():
        raise RuntimeError("decision output exists; refusing overwrite")
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    closeout = json.loads(CLOSEOUT.read_text(encoding="utf-8"))
    aggregation = json.loads((args.aggregation_dir / "report.json").read_text(encoding="utf-8"))
    if aggregation.get("status") != "HUMAN_REVIEW_AGGREGATION_COMPLETE_READY_FOR_FROZEN_GENERATOR_DECISION":
        raise RuntimeError("human aggregation is not ready for a generator decision")
    if aggregation.get("packet_integrity_blockers") != 0:
        raise RuntimeError("packet integrity blocks generator selection")
    rows = _rows(args.aggregation_dir / "private_final_dialogue_scores.jsonl")
    if len(rows) != 72:
        raise RuntimeError("expected 72 final dialogue scores")
    candidates = sorted({row["candidate_id"] for row in rows})
    if set(candidates) != set(closeout["decision"]["reliability_eligible_for_quality_selection"]):
        raise RuntimeError("human review candidate set drifted from reliability eligibility")
    summaries = aggregation["candidate_summary"]
    floors = contract["hard_eligibility_gates"]["absolute_mean_floors"]
    critical = contract["hard_eligibility_gates"]["critical_project_guardrail_fail_maximum"]
    eligibility: dict[str, dict[str, Any]] = {}
    guard_counts: dict[str, dict[str, Counter[str]]] = {}
    for candidate in candidates:
        observed = closeout["candidates"][candidate]
        summary = summaries[candidate]
        guard_counts[candidate] = {
            guard: Counter(summary["project_guardrail_outcomes"][guard])
            for guard in summary["project_guardrail_outcomes"]
        }
        reasons: list[str] = []
        if observed["valid_turn_rate"] < contract["hard_eligibility_gates"]["valid_supporter_turn_rate_minimum"]:
            reasons.append("VALID_TURN_RATE")
        if observed["completed_dialogue_rate"] < contract["hard_eligibility_gates"]["complete_dialogue_rate_minimum"]:
            reasons.append("COMPLETE_DIALOGUE_RATE")
        for dimension, floor in floors.items():
            if summary["official_dimension_means"][dimension] < floor:
                reasons.append(f"ABSOLUTE_FLOOR:{dimension}")
        for guardrail, maximum in critical.items():
            if guard_counts[candidate][guardrail]["FAIL"] > maximum:
                reasons.append(f"CRITICAL_GUARDRAIL:{guardrail}")
        eligibility[candidate] = {"pass": not reasons, "failure_reasons": reasons}

    by_candidate_screen = {
        (row["candidate_id"], row["screen_id"]): row
        for row in rows
    }
    dimensions = contract["relative_quality_rule"]["comparison_dimensions"]
    ni = float(contract["relative_quality_rule"]["practical_noninferiority_margin_points"])
    advantage = float(contract["relative_quality_rule"]["strict_advantage_margin_points"])
    comparisons: dict[str, Any] = {}
    quality_advantages: set[tuple[str, str]] = set()
    equivalences: set[frozenset[str]] = set()
    for first in candidates:
        for second in candidates:
            if first >= second:
                continue
            screens = sorted(
                set(row["screen_id"] for row in rows if row["candidate_id"] == first)
                & set(row["screen_id"] for row in rows if row["candidate_id"] == second)
            )
            if len(screens) != 24:
                raise RuntimeError(f"paired card coverage drifted: {first}/{second}")
            key = f"{first}__vs__{second}"
            diffs: dict[str, Any] = {}
            for dimension in dimensions:
                values = [
                    by_candidate_screen[(first, screen)]["official_scores"][dimension]
                    - by_candidate_screen[(second, screen)]["official_scores"][dimension]
                    for screen in screens
                ]
                diffs[dimension] = {
                    "paired_mean_first_minus_second": mean(values),
                    "card_bootstrap_90_interval": _bootstrap_interval(values, f"{key}|{dimension}"),
                    "first_wins": sum(value > 0 for value in values),
                    "second_wins": sum(value < 0 for value in values),
                    "ties": sum(value == 0 for value in values),
                }
            comparisons[key] = diffs

            def delta(a: str, b: str, dimension: str) -> float:
                value = diffs[dimension]["paired_mean_first_minus_second"]
                return value if (a, b) == (first, second) else -value

            for a, b in ((first, second), (second, first)):
                noninferior = all(delta(a, b, dimension) >= ni for dimension in dimensions)
                strict = delta(a, b, "Overall") >= advantage or sum(
                    delta(a, b, dimension) >= advantage for dimension in ("Empathy", "Skill", "Information")
                ) >= 2
                if noninferior and strict:
                    quality_advantages.add((a, b))
            if all(abs(diffs[dimension]["paired_mean_first_minus_second"]) < advantage for dimension in dimensions):
                equivalences.add(frozenset((first, second)))

    def guard_no_regression(first: str, second: str) -> bool:
        return all(
            guard_counts[first][guardrail]["FAIL"] <= guard_counts[second][guardrail]["FAIL"] + 1
            for guardrail in ("low_burden", "no_premature_action")
        )

    remaining = {candidate for candidate in candidates if eligibility[candidate]["pass"]}
    removed: dict[str, str] = {}
    for candidate in sorted(list(remaining)):
        dominators = [
            other for other in remaining
            if other != candidate and (other, candidate) in quality_advantages and guard_no_regression(other, candidate)
        ]
        if dominators:
            removed[candidate] = "QUALITY_DOMINATED_BY:" + ",".join(sorted(dominators))
    remaining -= set(removed)
    thinking = "qwen37_plus_thinking_upper_bound"
    nonthinking = "qwen37_plus_nonthinking"
    if thinking in remaining and nonthinking in remaining and (thinking, nonthinking) not in quality_advantages:
        remaining.remove(thinking)
        removed[thinking] = "INCREMENTAL_THINKING_COST_NOT_JUSTIFIED_BY_REGISTERED_QUALITY_ADVANTAGE"

    selected: str | None = None
    reason = ""
    if len(remaining) == 1:
        selected = next(iter(remaining))
        reason = "UNIQUE_NONDOMINATED_ELIGIBLE_CONFIGURATION"
    elif remaining and all(frozenset((a, b)) in equivalences for a in remaining for b in remaining if a != b):
        operations = contract["observed_operations_bound_before_human_scores"]
        selected = min(remaining, key=lambda candidate: (operations[candidate]["observed_usd"], operations[candidate]["median_latency_ms"]))
        reason = "ALL_REMAINING_DEVELOPMENT_EQUIVALENT_OPERATIONS_TIE_BREAK"
    elif remaining:
        reason = "MATERIAL_QUALITY_TRADEOFF_PARETO_CONFIRMATION_REQUIRED"
    else:
        reason = "NO_CANDIDATE_PASSED_FROZEN_ELIGIBILITY_GATES"

    report = {
        "protocol": "metacom-v3-g0-esc-eval-development-generator-decision-v1",
        "status": "DEVELOPMENT_GENERATOR_SELECTED_CONFIRMATION_AND_EXECUTOR_PENDING" if selected else "NO_UNIQUE_DEVELOPMENT_GENERATOR",
        "contract_status": contract["status"],
        "eligibility": eligibility,
        "paired_comparisons": comparisons,
        "quality_advantages": sorted([list(pair) for pair in quality_advantages]),
        "development_equivalences": sorted([sorted(pair) for pair in equivalences]),
        "removed": removed,
        "remaining_pareto_set": sorted(remaining),
        "selected_development_generator": selected,
        "selection_reason": reason,
        "generator_fully_qualified": False,
        "required_next": [
            "approved-plan/evidence executor qualification",
            "outcome-blind stratified ESC-Eval English confirmation",
            "freeze exact generator route, mode, prompt, decoding, retry, and cost accounting for every PM and baseline arm"
        ],
        "api_calls": 0,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
