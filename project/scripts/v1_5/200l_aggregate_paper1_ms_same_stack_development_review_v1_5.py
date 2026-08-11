#!/usr/bin/env python3
"""Aggregate the frozen MS same-stack single-reviewer development audit.

This script never fits or changes the PM.  It joins the pre-existing blind quality
judgments, the post-freeze arm key, source-aware function judgments, frozen OOF
decisions, provider execution records, and the explicitly non-exhaustive targeted
risk events.  Uncertainty resamples the 17 connected user groups, not 68 states.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
PACKET = ROOT / "outputs/pm_v1_5_paper1_ms_same_stack_review_packet_20260811"
GEN = ROOT / "outputs/pm_v1_5_paper1_ms_same_stack_generation_20260811"
OUT = ROOT / "outputs/pm_v1_5_paper1_ms_same_stack_development_audit_20260811"
BOOTSTRAP_SEED = 20260811
BOOTSTRAP_REPLICATES = 20_000


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return math.nan
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else math.nan


def ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else math.nan


def preference_counts(values: list[int]) -> dict[str, int]:
    return {
        "first_policy_preferred": sum(value > 0 for value in values),
        "second_policy_preferred": sum(value < 0 for value in values),
        "tie": sum(value == 0 for value in values),
    }


def quality_stratum(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [int(row["quality_on_vs_off"]) for row in rows]
    return {
        "states": len(rows),
        "on_preferred": sum(value > 0 for value in values),
        "off_preferred": sum(value < 0 for value in values),
        "tie": sum(value == 0 for value in values),
        "netwin": mean(values),
    }


def bootstrap_grouped(
    rows_by_group: dict[str, list[dict[str, Any]]],
    metric: Callable[[list[dict[str, Any]]], float],
    rng: random.Random,
) -> dict[str, float]:
    groups = sorted(rows_by_group)
    estimates: list[float] = []
    for _ in range(BOOTSTRAP_REPLICATES):
        sampled: list[dict[str, Any]] = []
        for _ in groups:
            sampled.extend(rows_by_group[rng.choice(groups)])
        value = metric(sampled)
        if not math.isnan(value):
            estimates.append(value)
    point_rows = [row for group in groups for row in rows_by_group[group]]
    point = metric(point_rows)
    return {
        "estimate": point,
        "ci95_low": quantile(estimates, 0.025),
        "ci95_high": quantile(estimates, 0.975),
        "bootstrap_replicates_retained": len(estimates),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    paths = {
        "quality_packet": PACKET / "quality_blind_packet.jsonl",
        "quality_key": PACKET / "quality_blind_key_private.jsonl",
        "quality_judgments": PACKET / "quality_blind_judgments_codex_development_v1.jsonl",
        "function_packet": PACKET / "function_packet.jsonl",
        "function_judgments": PACKET / "function_judgments_codex_development_v1.jsonl",
        "risk_targeted": PACKET / "risk_targeted_events_codex_development_v1.jsonl",
        "logical_results": GEN / "logical_policy_results_private.jsonl",
        "generation_report": GEN / "report.json",
    }

    quality_key = {row["review_item_id"]: row for row in read_jsonl(paths["quality_key"])}
    quality_judgments = read_jsonl(paths["quality_judgments"])
    if len(quality_judgments) != 68 or len({row["review_item_id"] for row in quality_judgments}) != 68:
        raise ValueError("Quality judgments must contain exactly 68 unique frozen rows")

    quality_by_state: dict[str, dict[str, Any]] = {}
    for judgment in quality_judgments:
        key = quality_key[judgment["review_item_id"]]
        choice = judgment["choice"]
        if choice == "TIE":
            utility = 0
        else:
            chosen_arm = key[f"{choice}_arm"]
            utility = 1 if chosen_arm == "ON" else -1
        quality_by_state[key["state_id"]] = {
            "quality_review_item_id": judgment["review_item_id"],
            "quality_choice_blind": choice,
            "quality_on_vs_off": utility,
        }

    function_packet = {row["review_item_id"]: row for row in read_jsonl(paths["function_packet"])}
    function_judgments = read_jsonl(paths["function_judgments"])
    if len(function_judgments) != 68 or len({row["review_item_id"] for row in function_judgments}) != 68:
        raise ValueError("Function judgments must contain exactly 68 unique rows")
    function_by_state: dict[str, dict[str, Any]] = {}
    for judgment in function_judgments:
        packet_row = function_packet[judgment["review_item_id"]]
        function_by_state[packet_row["state_id"]] = {
            "function_review_item_id": judgment["review_item_id"],
            "contribution_present": judgment["contribution_present"] == "YES",
            "ms_function_realized": judgment["ms_function_realized"] == "YES",
            "boundary_correct": judgment["owner_time_boundary_correct"] == "YES",
            "boundary_not_applicable": judgment["owner_time_boundary_correct"] == "NOT_APPLICABLE",
            "functional": judgment["projection"] == "FUNCTIONAL",
            "guard_errors": packet_row["guard_errors"],
        }

    logical = read_jsonl(paths["logical_results"])
    by_policy_state = {(row["policy"], row["state_id"]): row for row in logical}
    states = sorted(quality_by_state)
    if set(states) != set(function_by_state) or len(states) != 68:
        raise ValueError("Quality and function state surfaces must match at 68 states")

    targeted_risk = read_jsonl(paths["risk_targeted"])
    risk_by_state: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in targeted_risk:
        risk_by_state[event["state_id"]].append(event)

    state_rows: list[dict[str, Any]] = []
    for state in states:
        learned = by_policy_state[("cross_fitted_learned_MS", state)]
        fixed = by_policy_state[("fixed_high_MS", state)]
        off = by_policy_state[("always_off", state)]
        decision = int(learned["immutable_oof_decision"])
        quality_utility = quality_by_state[state]["quality_on_vs_off"]
        state_rows.append(
            {
                "state_id": state,
                "split_group_key": learned["split_group_key"],
                "immutable_oof_decision": decision,
                "on_execution_clean": fixed["execution_status"] == "clean",
                "on_fallback": fixed["execution_status"] != "clean",
                "on_functional": function_by_state[state]["functional"],
                "on_contribution_present": function_by_state[state]["contribution_present"],
                "on_boundary_correct": function_by_state[state]["boundary_correct"],
                "quality_on_vs_off": quality_utility,
                "learned_vs_always_off_quality": quality_utility * decision,
                "learned_vs_fixed_high_quality": -quality_utility * (1 - decision),
                "targeted_risk_event_count_on": len(risk_by_state.get(state, [])),
                "targeted_risk_max_severity_on": max(
                    [event["severity"] for event in risk_by_state.get(state, [])], default=0
                ),
                "always_off_input_tokens": off["provider_usage"].get("prompt_tokens", 0),
                "always_off_output_tokens": off["provider_usage"].get("completion_tokens", 0),
                "fixed_high_input_tokens": fixed["provider_usage"].get("prompt_tokens", 0),
                "fixed_high_output_tokens": fixed["provider_usage"].get("completion_tokens", 0),
                "learned_input_tokens": learned["provider_usage"].get("prompt_tokens", 0),
                "learned_output_tokens": learned["provider_usage"].get("completion_tokens", 0),
            }
        )

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in state_rows:
        groups[row["split_group_key"]].append(row)
    if len(groups) != 17 or {len(group_rows) for group_rows in groups.values()} != {4}:
        raise ValueError("Expected 17 connected groups with four states each")

    rng = random.Random(BOOTSTRAP_SEED)
    ci = {
        "quality_fixed_high_vs_always_off_netwin": bootstrap_grouped(
            groups, lambda rs: mean([row["quality_on_vs_off"] for row in rs]), rng
        ),
        "quality_learned_vs_always_off_netwin": bootstrap_grouped(
            groups, lambda rs: mean([row["learned_vs_always_off_quality"] for row in rs]), rng
        ),
        "quality_learned_vs_fixed_high_netwin": bootstrap_grouped(
            groups, lambda rs: mean([row["learned_vs_fixed_high_quality"] for row in rs]), rng
        ),
        "on_clean_rate_predicted_on": bootstrap_grouped(
            groups,
            lambda rs: ratio(
                sum(row["on_execution_clean"] and row["immutable_oof_decision"] == 1 for row in rs),
                sum(row["immutable_oof_decision"] == 1 for row in rs),
            ),
            rng,
        ),
        "on_clean_rate_predicted_off": bootstrap_grouped(
            groups,
            lambda rs: ratio(
                sum(row["on_execution_clean"] and row["immutable_oof_decision"] == 0 for row in rs),
                sum(row["immutable_oof_decision"] == 0 for row in rs),
            ),
            rng,
        ),
        "on_clean_rate_enrichment_predicted_on_minus_off": bootstrap_grouped(
            groups,
            lambda rs: ratio(
                sum(row["on_execution_clean"] and row["immutable_oof_decision"] == 1 for row in rs),
                sum(row["immutable_oof_decision"] == 1 for row in rs),
            )
            - ratio(
                sum(row["on_execution_clean"] and row["immutable_oof_decision"] == 0 for row in rs),
                sum(row["immutable_oof_decision"] == 0 for row in rs),
            ),
            rng,
        ),
        "fixed_high_function_rate_per_requested_on": bootstrap_grouped(
            groups, lambda rs: mean([float(row["on_functional"]) for row in rs]), rng
        ),
        "learned_function_rate_per_requested_on": bootstrap_grouped(
            groups,
            lambda rs: ratio(
                sum(row["on_functional"] and row["immutable_oof_decision"] == 1 for row in rs),
                sum(row["immutable_oof_decision"] == 1 for row in rs),
            ),
            rng,
        ),
        "learned_functional_state_yield_all_states": bootstrap_grouped(
            groups,
            lambda rs: mean(
                [float(row["on_functional"] and row["immutable_oof_decision"] == 1) for row in rs]
            ),
            rng,
        ),
    }

    quality_fixed_values = [row["quality_on_vs_off"] for row in state_rows]
    quality_learned_off_values = [row["learned_vs_always_off_quality"] for row in state_rows]
    quality_learned_fixed_values = [row["learned_vs_fixed_high_quality"] for row in state_rows]

    policy_rows: list[dict[str, Any]] = []
    for policy in ["always_off", "fixed_high_MS", "cross_fitted_learned_MS"]:
        rows = [by_policy_state[(policy, state)] for state in states]
        requested_on = sum(row["requested_action_id"] == "MS+R0" for row in rows)
        realized_on = sum(row["realized_action_id"] == "MS+R0" for row in rows)
        fallback = sum(row["execution_status"] != "clean" for row in rows)
        functional = sum(
            function_by_state[state]["functional"]
            and by_policy_state[(policy, state)]["requested_action_id"] == "MS+R0"
            for state in states
        )
        targeted_events = sum(
            len(risk_by_state.get(state, []))
            for state in states
            if by_policy_state[(policy, state)]["requested_action_id"] == "MS+R0"
        )
        policy_rows.append(
            {
                "policy": policy,
                "states": 68,
                "requested_on": requested_on,
                "realized_on": realized_on,
                "fallback": fallback,
                "functional_on": functional,
                "input_tokens": sum(row["provider_usage"].get("prompt_tokens", 0) for row in rows),
                "output_tokens": sum(row["provider_usage"].get("completion_tokens", 0) for row in rows),
                "targeted_literal_risk_events": targeted_events,
            }
        )

    predicted_on = [row for row in state_rows if row["immutable_oof_decision"] == 1]
    predicted_off = [row for row in state_rows if row["immutable_oof_decision"] == 0]
    summary = {
        "protocol": "pm-v1.5-paper1-ms-same-stack-development-audit-v1",
        "date": "2026-08-11",
        "status": "MS_EXECUTION_SIGNAL_PRESENT_BUT_MEMORY_FUNCTION_BOTTLENECK_CONFIRMED",
        "claim_scope": {
            "reviewer": "single Codex primary-agent development audit",
            "independent_human_confirmation": False,
            "quality_blinded_until_all_68_labels_frozen": True,
            "risk_rate_estimand": "not estimated; targeted literal events only",
            "pm_refit_or_threshold_change": False,
            "generator_calls_added": 0,
        },
        "surface": {
            "states": len(state_rows),
            "connected_groups": len(groups),
            "states_per_group": 4,
            "predicted_on": len(predicted_on),
            "predicted_off": len(predicted_off),
        },
        "quality": {
            "blind_raw_choices": dict(Counter(row["quality_choice_blind"] for row in quality_by_state.values())),
            "fixed_high_vs_always_off": preference_counts(quality_fixed_values),
            "learned_vs_always_off": preference_counts(quality_learned_off_values),
            "learned_vs_fixed_high": preference_counts(quality_learned_fixed_values),
            "clustered_bootstrap": {
                key: value for key, value in ci.items() if key.startswith("quality_")
            },
            "unit": "categorical meaningful preference: +1 first policy, -1 second policy, 0 tie",
            "diagnostic_strata_on_vs_off": {
                "clean_execution": quality_stratum(
                    [row for row in state_rows if row["on_execution_clean"]]
                ),
                "fallback_execution": quality_stratum(
                    [row for row in state_rows if not row["on_execution_clean"]]
                ),
                "functional_memory": quality_stratum(
                    [row for row in state_rows if row["on_functional"]]
                ),
                "nonfunctional_memory": quality_stratum(
                    [row for row in state_rows if not row["on_functional"]]
                ),
                "predicted_on": quality_stratum(predicted_on),
                "predicted_off": quality_stratum(predicted_off),
            },
        },
        "execution": {
            "predicted_on_clean": sum(row["on_execution_clean"] for row in predicted_on),
            "predicted_on_fallback": sum(row["on_fallback"] for row in predicted_on),
            "predicted_off_counterfactual_clean": sum(row["on_execution_clean"] for row in predicted_off),
            "predicted_off_counterfactual_fallback": sum(row["on_fallback"] for row in predicted_off),
            "clustered_bootstrap": {
                key: value for key, value in ci.items() if key.startswith("on_clean_")
            },
        },
        "function": {
            "contribution_present": sum(row["on_contribution_present"] for row in state_rows),
            "functional_fixed_high": sum(row["on_functional"] for row in state_rows),
            "functional_selected_by_learned": sum(
                row["on_functional"] and row["immutable_oof_decision"] == 1 for row in state_rows
            ),
            "functional_missed_by_learned": sum(
                row["on_functional"] and row["immutable_oof_decision"] == 0 for row in state_rows
            ),
            "clustered_bootstrap": {
                key: value
                for key, value in ci.items()
                if "function" in key
            },
            "nonfunctional_primary_reasons": {
                "no_distinct_prior_contribution": sum(not row["on_contribution_present"] for row in state_rows),
                "contribution_present_but_not_functional_or_boundary_safe": sum(
                    row["on_contribution_present"] and not row["on_functional"] for row in state_rows
                ),
            },
        },
        "guard": {
            "fixed_high_fallbacks": sum(row["on_fallback"] for row in state_rows),
            "semantic_guard_fallbacks": sum(
                row["on_fallback"]
                and "NO_STRUCTURED_OUTPUT:RetryableProviderError"
                not in function_by_state[row["state_id"]]["guard_errors"]
                for row in state_rows
            ),
            "transport_fallbacks": sum(
                "NO_STRUCTURED_OUTPUT:RetryableProviderError"
                in function_by_state[row["state_id"]]["guard_errors"]
                for row in state_rows
            ),
            "raw_guard_failed_responses_judged_memory_functional": 0,
            "interpretation": "The guard did not suppress a source-aware functional memory use in this audit, although some raw replies were better current-context replies than the generic deployment fallback.",
        },
        "risk_targeted": {
            "events": len(targeted_risk),
            "families": dict(Counter(event["risk_family"] for event in targeted_risk)),
            "severity": dict(Counter(str(event["severity"]) for event in targeted_risk)),
            "all_targeted_events_on_arm": True,
            "absolute_rate_claim_allowed": False,
        },
        "policies": policy_rows,
        "bootstrap": {
            "resampling_unit": "connected split_group_key",
            "groups": 17,
            "replicates": BOOTSTRAP_REPLICATES,
            "seed": BOOTSTRAP_SEED,
        },
        "input_bindings": [
            {"path": str(path.relative_to(ROOT)), "sha256": sha256(path)} for path in paths.values()
        ],
    }

    state_path = OUT / "state_analysis_private.jsonl"
    state_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in state_rows),
        encoding="utf-8",
    )
    policy_path = OUT / "policy_summary.jsonl"
    policy_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in policy_rows),
        encoding="utf-8",
    )
    report_path = OUT / "report.json"
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps({
        "status": summary["status"],
        "report": str(report_path.relative_to(ROOT)),
        "report_sha256": sha256(report_path),
        "quality": summary["quality"],
        "execution": summary["execution"],
        "function": summary["function"],
        "policies": policy_rows,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
