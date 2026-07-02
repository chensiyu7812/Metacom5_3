#!/usr/bin/env python3
"""No-API balanced paired audit plan for EvoEmo V4.

This plan is intentionally different from the earlier stratified sampled audit.
It selects the same V4 fixed-input units for every policy in the audit so that
risk comparisons are paired by unit rather than driven by different samples.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

from metacom_pm.io import iter_jsonl, utc_now, write_json, write_jsonl


ROOT = Path(__file__).resolve().parents[1]

FOCUS_CONDITIONS = (
    "pm",
    "strong_rule",
    "best_fixed",
    "session_rag_rs",
)

AUDIT_MODULES = (
    "selected_evidence_misuse",
    "unnecessary_exposure",
    "stale_or_conflict",
    "unsupported_personal_claim",
    "source_set_appropriateness",
    "strategy_overuse",
    "strategy_omission",
    "response_support_sufficiency",
)

STRATUM_TARGETS = {
    "pm_quality_tie_or_win_with_savings": 20,
    "pm_saves_but_quality_lower": 15,
    "session_quality_higher_cost_tradeoff": 10,
    "pm_high_resource": 5,
}


def unit_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(row.get("user_id")),
        int(row.get("topic_index")),
        int(row.get("seed")),
        str(row.get("simulator_id")),
        str(row.get("interaction_mode")),
        int(row.get("turn_index")),
    )


def unit_key_dict(key: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "user_id": key[0],
        "topic_index": key[1],
        "seed": key[2],
        "simulator_id": key[3],
        "interaction_mode": key[4],
        "turn_index": key[5],
    }


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def selected_count(turn: dict[str, Any], field: str) -> int:
    value = turn.get(field) or []
    return len(value) if isinstance(value, list) else 0


def cost_value(turn: dict[str, Any], field: str) -> float:
    return safe_float((turn.get("cost") or {}).get(field), 0.0)


def load_scores(path: Path) -> dict[tuple[Any, ...], dict[str, dict[str, Any]]]:
    out: dict[tuple[Any, ...], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in iter_jsonl(path):
        key = unit_key(row)
        condition = str(row["condition"])
        if condition in out[key]:
            raise RuntimeError(f"duplicate score row for {key}/{condition}")
        out[key][condition] = row
    return dict(out)


def load_turns(
    path: Path,
    *,
    units: set[tuple[Any, ...]],
    conditions: set[str],
) -> dict[tuple[Any, ...], dict[str, dict[str, Any]]]:
    out: dict[tuple[Any, ...], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in iter_jsonl(path):
        key = unit_key(row)
        condition = str(row.get("condition"))
        if key not in units or condition not in conditions:
            continue
        if condition in out[key]:
            raise RuntimeError(f"duplicate turn row for {key}/{condition}")
        out[key][condition] = row
    missing = []
    for key in units:
        for condition in conditions:
            if condition not in out.get(key, {}):
                missing.append((key, condition))
    if missing:
        raise RuntimeError(f"missing {len(missing)} turn rows; first={missing[0]}")
    return dict(out)


def condition_feature(turn: dict[str, Any], score: dict[str, Any]) -> dict[str, Any]:
    action_id = str(turn.get("action_id") or score.get("action_id") or "")
    return {
        "condition": str(turn.get("condition")),
        "action_id": action_id,
        "overall": safe_float(score.get("overall")),
        "memory_appropriateness": safe_float(score.get("memory_appropriateness")),
        "factual_grounding": safe_float(score.get("factual_grounding")),
        "non_intrusiveness": safe_float(score.get("non_intrusiveness")),
        "total_input_tokens": cost_value(turn, "total_input_tokens"),
        "memory_tokens": cost_value(turn, "memory_tokens"),
        "strategy_tokens": cost_value(turn, "strategy_tokens"),
        "output_tokens": cost_value(turn, "output_tokens"),
        "retrieval_calls": cost_value(turn, "retrieval_calls"),
        "selected_memory_count": selected_count(turn, "selected_memory"),
        "selected_strategy_count": selected_count(turn, "selected_strategy"),
        "rs_called": action_id.endswith("+RS") or selected_count(turn, "selected_strategy") > 0,
    }


def build_units(
    scores_by_unit: dict[tuple[Any, ...], dict[str, dict[str, Any]]],
    turns_by_unit: dict[tuple[Any, ...], dict[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    units = []
    for key in sorted(scores_by_unit):
        if any(cond not in scores_by_unit[key] for cond in FOCUS_CONDITIONS):
            continue
        if any(cond not in turns_by_unit.get(key, {}) for cond in FOCUS_CONDITIONS):
            continue
        conditions = {
            cond: condition_feature(turns_by_unit[key][cond], scores_by_unit[key][cond])
            for cond in FOCUS_CONDITIONS
        }
        pm = conditions["pm"]
        comparisons = {}
        for baseline in FOCUS_CONDITIONS:
            if baseline == "pm":
                continue
            base = conditions[baseline]
            saved = base["total_input_tokens"] - pm["total_input_tokens"]
            comparisons[baseline] = {
                "overall_delta_pm_minus_baseline": pm["overall"] - base["overall"],
                "input_tokens_saved_vs_baseline": saved,
                "input_reduction_vs_baseline": (
                    saved / base["total_input_tokens"] if base["total_input_tokens"] else 0.0
                ),
                "same_action": pm["action_id"] == base["action_id"],
            }
        units.append(
            {
                "unit_id": str(scores_by_unit[key]["pm"]["unit_id"]),
                "unit_key": unit_key_dict(key),
                "conditions": conditions,
                "comparisons": comparisons,
            }
        )
    return units


def scenario_id(unit: dict[str, Any]) -> str:
    key = unit["unit_key"]
    return f"{key['user_id']}::{key['topic_index']}"


def candidate_item(unit: dict[str, Any], *, stratum: str, priority: float, reason: str) -> dict[str, Any]:
    pm = unit["conditions"]["pm"]
    return {
        "stratum": stratum,
        "priority_score": float(priority),
        "unit_id": unit["unit_id"],
        "unit_key": unit["unit_key"],
        "focus_conditions": list(FOCUS_CONDITIONS),
        "audit_modules": list(AUDIT_MODULES),
        "reason": reason,
        "pm_action_id": pm["action_id"],
        "pm_overall": pm["overall"],
        "pm_total_input_tokens": pm["total_input_tokens"],
        "pm_memory_tokens": pm["memory_tokens"],
        "pm_selected_memory_count": pm["selected_memory_count"],
        "pm_selected_strategy_count": pm["selected_strategy_count"],
        "comparisons": unit["comparisons"],
        "condition_actions": {
            condition: unit["conditions"][condition]["action_id"]
            for condition in FOCUS_CONDITIONS
        },
        "condition_overall_scores": {
            condition: unit["conditions"][condition]["overall"]
            for condition in FOCUS_CONDITIONS
        },
        "condition_total_input_tokens": {
            condition: unit["conditions"][condition]["total_input_tokens"]
            for condition in FOCUS_CONDITIONS
        },
    }


def make_strata(units: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    strata: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for unit in units:
        pm = unit["conditions"]["pm"]
        strong = unit["conditions"]["strong_rule"]
        best = unit["conditions"]["best_fixed"]
        session = unit["conditions"]["session_rag_rs"]
        strong_comp = unit["comparisons"]["strong_rule"]
        best_comp = unit["comparisons"]["best_fixed"]
        session_comp = unit["comparisons"]["session_rag_rs"]

        rule_or_fixed_savings = max(
            strong_comp["input_tokens_saved_vs_baseline"],
            best_comp["input_tokens_saved_vs_baseline"],
        )
        best_rule_fixed_delta = max(
            strong_comp["overall_delta_pm_minus_baseline"],
            best_comp["overall_delta_pm_minus_baseline"],
        )
        worst_rule_fixed_delta = min(
            strong_comp["overall_delta_pm_minus_baseline"],
            best_comp["overall_delta_pm_minus_baseline"],
        )

        if rule_or_fixed_savings > 0 and best_rule_fixed_delta >= 0:
            strata["pm_quality_tie_or_win_with_savings"].append(
                candidate_item(
                    unit,
                    stratum="pm_quality_tie_or_win_with_savings",
                    priority=rule_or_fixed_savings + 100 * pm["overall"],
                    reason=(
                        "PM ties or beats at least one rule/fixed baseline while "
                        "saving input evidence."
                    ),
                )
            )

        if rule_or_fixed_savings > 0 and worst_rule_fixed_delta < 0:
            strata["pm_saves_but_quality_lower"].append(
                candidate_item(
                    unit,
                    stratum="pm_saves_but_quality_lower",
                    priority=rule_or_fixed_savings + 250 * abs(worst_rule_fixed_delta),
                    reason=(
                        "PM saves input evidence but scores lower than at least one "
                        "rule/fixed baseline; audit possible omission or risk tradeoff."
                    ),
                )
            )

        if (
            session_comp["input_tokens_saved_vs_baseline"] > 0
            and session["overall"] > pm["overall"]
        ):
            strata["session_quality_higher_cost_tradeoff"].append(
                candidate_item(
                    unit,
                    stratum="session_quality_higher_cost_tradeoff",
                    priority=(
                        session_comp["input_tokens_saved_vs_baseline"]
                        + 400 * (session["overall"] - pm["overall"])
                    ),
                    reason=(
                        "Session Retrieval scores higher but costs more; audit whether "
                        "extra session evidence creates risk or reveals a PM omission."
                    ),
                )
            )

        high_resource_priority = (
            pm["total_input_tokens"]
            + 0.5 * pm["memory_tokens"]
            + 120 * pm["selected_memory_count"]
            + 60 * pm["selected_strategy_count"]
        )
        strata["pm_high_resource"].append(
            candidate_item(
                unit,
                stratum="pm_high_resource",
                priority=high_resource_priority,
                reason=(
                    "PM itself uses comparatively high evidence; audit whether PM "
                    "creates exposure, stale use, or strategy overuse in its own calls."
                ),
            )
        )

    for rows in strata.values():
        rows.sort(
            key=lambda x: (
                -x["priority_score"],
                str(x["unit_key"]["user_id"]),
                int(x["unit_key"]["topic_index"]),
                int(x["unit_key"]["seed"]),
                int(x["unit_key"]["turn_index"]),
            )
        )
    return dict(strata)


def select_items(strata: dict[str, list[dict[str, Any]]], *, target_units: int) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    scenario_counts: Counter[str] = Counter()

    def add(item: dict[str, Any], stratum: str) -> bool:
        unit_id = item["unit_id"]
        if unit_id in selected:
            covered = selected[unit_id].setdefault("covered_strata", [])
            if stratum not in covered:
                covered.append(stratum)
            return False
        copied = dict(item)
        copied["primary_stratum"] = stratum
        copied["covered_strata"] = [stratum]
        selected[unit_id] = copied
        scenario_counts[scenario_id(copied)] += 1
        return True

    # First pass favors scenario diversity within each pre-registered stratum.
    for stratum, target in STRATUM_TARGETS.items():
        added = 0
        for item in strata.get(stratum, []):
            if item["unit_id"] in selected:
                covered = selected[item["unit_id"]].setdefault("covered_strata", [])
                if stratum not in covered:
                    covered.append(stratum)
                continue
            if scenario_counts[scenario_id(item)] > 0:
                continue
            if add(item, stratum):
                added += 1
            if added >= target:
                break

    # Second pass fills target counts even if scenarios repeat.
    for stratum, target in STRATUM_TARGETS.items():
        current = sum(
            1
            for item in selected.values()
            if str(item.get("primary_stratum") or item["stratum"]) == stratum
        )
        for item in strata.get(stratum, []):
            if current >= target:
                break
            if item["unit_id"] in selected:
                covered = selected[item["unit_id"]].setdefault("covered_strata", [])
                if stratum not in covered:
                    covered.append(stratum)
                continue
            if add(item, stratum):
                current += 1

    if len(selected) < target_units:
        all_items = sorted(
            [item for rows in strata.values() for item in rows],
            key=lambda x: (scenario_counts[scenario_id(x)], -x["priority_score"], x["unit_id"]),
        )
        for item in all_items:
            if item["unit_id"] in selected:
                covered = selected[item["unit_id"]].setdefault("covered_strata", [])
                if item["stratum"] not in covered:
                    covered.append(item["stratum"])
                continue
            add(item, item["stratum"])
            if len(selected) >= target_units:
                break

    result = list(selected.values())[:target_units]
    result.sort(
        key=lambda x: (
            int(x["unit_key"]["topic_index"]),
            str(x["unit_key"]["user_id"]),
            int(x["unit_key"]["seed"]),
            int(x["unit_key"]["turn_index"]),
            x["unit_id"],
        )
    )
    for index, item in enumerate(result, 1):
        item["audit_item_id"] = f"paired_audit_v1_{index:03d}"
    return result


def summarize_selection(items: list[dict[str, Any]]) -> dict[str, Any]:
    focus = Counter()
    covered = Counter()
    primary = Counter()
    turns = Counter()
    actions = Counter()
    users = set()
    topics = set()
    scenarios = set()
    for item in items:
        for condition in item["focus_conditions"]:
            focus[condition] += 1
        primary[str(item.get("primary_stratum") or item["stratum"])] += 1
        for stratum in item.get("covered_strata") or [item["stratum"]]:
            covered[stratum] += 1
        turns[str(item["unit_key"]["turn_index"])] += 1
        actions[str(item["pm_action_id"])] += 1
        users.add(str(item["unit_key"]["user_id"]))
        topics.add(int(item["unit_key"]["topic_index"]))
        scenarios.add((str(item["unit_key"]["user_id"]), int(item["unit_key"]["topic_index"])))
    return {
        "selected_units": len(items),
        "planned_selected_calls": len(items) * len(FOCUS_CONDITIONS),
        "focus_condition_counts": dict(focus.most_common()),
        "primary_stratum_counts": dict(primary.most_common()),
        "covered_strata_counts": dict(covered.most_common()),
        "turn_counts": dict(sorted(turns.items())),
        "pm_action_counts": dict(actions.most_common()),
        "unique_users": len(users),
        "unique_topic_index_values": len(topics),
        "unique_scenarios": len(scenarios),
    }


def estimate_plan_cost(items: list[dict[str, Any]], *, estimated_output_tokens_per_call: int) -> dict[str, Any]:
    # Planning-only estimate. The API evaluator dry-run is authoritative.
    input_tokens = 0.0
    calls = 0
    max_input = 0.0
    for item in items:
        for condition in FOCUS_CONDITIONS:
            total = safe_float(item["condition_total_input_tokens"].get(condition), 0.0)
            output = 70.0
            est = total + output + 550.0
            input_tokens += est
            max_input = max(max_input, est)
            calls += 1
    output_tokens = calls * int(estimated_output_tokens_per_call)
    return {
        "status": "PLANNING_ONLY",
        "planned_calls": calls,
        "estimated_input_tokens": int(input_tokens),
        "estimated_output_tokens": output_tokens,
        "max_estimated_input_tokens_per_call": int(max_input),
        "estimated_cost_usd_gpt4o": input_tokens / 1e6 * 2.5 + output_tokens / 1e6 * 10.0,
        "note": "Use scripts/17e dry-run for the authoritative cost hash before any API run.",
    }


def table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(value) for value in row) + " |")
    return "\n".join(lines)


def write_markdown(path: Path, *, plan: dict[str, Any], items: list[dict[str, Any]]) -> None:
    preview = []
    for item in items[:20]:
        preview.append(
            [
                item["audit_item_id"],
                item["unit_key"]["user_id"],
                item["unit_key"]["topic_index"],
                item["unit_key"]["seed"],
                item["unit_key"]["turn_index"],
                item["pm_action_id"],
                item.get("primary_stratum") or item["stratum"],
                ",".join(item.get("covered_strata") or [item["stratum"]]),
            ]
        )
    summary = plan["selection_summary"]
    estimate = plan["planning_cost_estimate"]
    lines = [
        "# EvoEmo Balanced Paired Evidence Audit Plan",
        "",
        f"Generated at: {utc_now()}",
        "",
        "This is a no-API plan. It is not an audit result.",
        "",
        "## Purpose",
        "",
        "The earlier sampled audit was descriptive because policies were not audited on the same units and baseline sample sizes were small. This plan selects the same 50 V4 fixed-input units for four policies: Learned PM, Rule Policy, Fixed All Structured, and Session Retrieval.",
        "",
        "## Pre-registered Risk Metrics",
        "",
        "- Primary: major evidence risk indicator, defined as any severity >= 2 in selected evidence misuse, unnecessary exposure, stale/conflict, or unsupported personal claim.",
        "- Primary severity score: max severity over the four evidence risk fields above.",
        "- Secondary: strategy overuse and strategy omission, reported separately from evidence misuse.",
        "- Secondary: source set appropriateness and response support sufficiency.",
        "- Cost and response quality are not folded into the risk score; they are reported as separate tradeoff dimensions.",
        "",
        "## Selection Summary",
        "",
        f"- selected units: {summary['selected_units']}",
        f"- planned selected audit calls: {summary['planned_selected_calls']}",
        f"- unique users: {summary['unique_users']}",
        f"- unique topic index values: {summary['unique_topic_index_values']}",
        f"- unique scenarios: {summary['unique_scenarios']}",
        f"- turn counts: {summary['turn_counts']}",
        f"- PM action counts: {summary['pm_action_counts']}",
        f"- focus condition counts: {summary['focus_condition_counts']}",
        f"- primary stratum counts: {summary['primary_stratum_counts']}",
        f"- covered strata counts: {summary['covered_strata_counts']}",
        "",
        "## Planning Cost Estimate",
        "",
        f"- planned calls: {estimate['planned_calls']}",
        f"- planning estimated input tokens: {estimate['estimated_input_tokens']}",
        f"- planning estimated output tokens: {estimate['estimated_output_tokens']}",
        f"- planning estimated GPT-4o cost: ${estimate['estimated_cost_usd_gpt4o']:.2f}",
        "",
        "The evaluator dry-run remains authoritative and must be run before any API call.",
        "",
        "## Preview",
        "",
        table(
            ["id", "user", "topic", "seed", "turn", "pm_action", "primary", "covered"],
            preview,
        ),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scores", type=Path, default=ROOT / "outputs/evoemo_response_v4/response_scores.jsonl")
    parser.add_argument("--turns", type=Path, default=ROOT / "outputs/evoemo_selective/turns.jsonl")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "outputs/evoemo_balanced_paired_audit_plan")
    parser.add_argument("--target-units", type=int, default=50)
    parser.add_argument("--estimated-output-tokens-per-call", type=int, default=450)
    args = parser.parse_args()

    scores_by_unit = load_scores(args.scores)
    units = set(scores_by_unit)
    turns_by_unit = load_turns(args.turns, units=units, conditions=set(FOCUS_CONDITIONS))
    unit_rows = build_units(scores_by_unit, turns_by_unit)
    strata = make_strata(unit_rows)
    selected = select_items(strata, target_units=args.target_units)
    if len(selected) != args.target_units:
        raise RuntimeError(f"selected {len(selected)} units, expected {args.target_units}")

    plan = {
        "status": "PLANNED_NO_API",
        "created_at": utc_now(),
        "protocol": "evoemo_balanced_paired_evidence_audit_plan_v1",
        "inputs": {
            "scores": str(args.scores),
            "turns": str(args.turns),
        },
        "parameters": {
            "target_units": args.target_units,
            "focus_conditions": list(FOCUS_CONDITIONS),
            "stratum_targets": dict(STRATUM_TARGETS),
            "estimated_output_tokens_per_call": args.estimated_output_tokens_per_call,
        },
        "pre_registered_metrics": {
            "primary_major_evidence_risk_indicator": {
                "fields": [
                    "selected_evidence_misuse",
                    "unnecessary_exposure",
                    "stale_or_conflict",
                    "unsupported_personal_claim",
                ],
                "positive_threshold": "any field >= 2",
                "note": "strategy omission is not mixed into primary evidence misuse risk",
            },
            "primary_evidence_risk_severity": "max severity over primary evidence fields",
            "secondary_strategy_risk": ["strategy_overuse", "strategy_omission"],
            "paired_unit": "same user/topic/seed/turn audited for every focus condition",
        },
        "candidate_pool": {
            "v4_units_with_all_focus_conditions": len(unit_rows),
            "strata_candidate_counts": {k: len(v) for k, v in sorted(strata.items())},
        },
        "selection_summary": summarize_selection(selected),
        "planning_cost_estimate": estimate_plan_cost(
            selected,
            estimated_output_tokens_per_call=args.estimated_output_tokens_per_call,
        ),
        "guardrails": {
            "no_api_calls": True,
            "requires_evaluator_dry_run_hash": True,
            "requires_frozen_plan_before_reportable_api": True,
            "requires_pilot_before_full_run": True,
            "recommended_pilot_units": 12,
            "recommended_pilot_calls": 12 * len(FOCUS_CONDITIONS),
            "raw_rows_manual_gate": "raw_rows <= expected_calls * 1.10",
            "do_not_use_as_audit_result": True,
        },
        "audit_items": selected,
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "audit_sample_plan.json", plan)
    write_jsonl(args.out_dir / "audit_items.jsonl", selected)
    write_markdown(args.out_dir / "audit_sample_plan.md", plan=plan, items=selected)
    print(
        {
            "status": "PLANNED_NO_API",
            "out_dir": str(args.out_dir),
            "selected_units": len(selected),
            "planned_calls": len(selected) * len(FOCUS_CONDITIONS),
            "planning_estimated_cost_usd": round(
                plan["planning_cost_estimate"]["estimated_cost_usd_gpt4o"], 4
            ),
        }
    )


if __name__ == "__main__":
    main()
