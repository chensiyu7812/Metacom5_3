#!/usr/bin/env python3
"""No-API sample plan for EvoEmo memory / strategy audit.

The script selects a stratified set of V4 fixed-input units for a later small
audit pilot. It does not call any model API and does not create final audit
claims.
"""

from __future__ import annotations

import argparse
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable

from metacom_pm.io import iter_jsonl, utc_now, write_json, write_jsonl


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_CONDITIONS = (
    "pm",
    "strong_rule",
    "best_fixed",
    "session_rag_rs",
    "no_memory_r0",
)


def _unit_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("user_id"),
        int(row.get("topic_index")),
        int(row.get("seed")),
        str(row.get("simulator_id")),
        str(row.get("interaction_mode")),
        int(row.get("turn_index")),
    )


def _unit_key_dict(key: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "user_id": key[0],
        "topic_index": key[1],
        "seed": key[2],
        "simulator_id": key[3],
        "interaction_mode": key[4],
        "turn_index": key[5],
    }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return numeric if math.isfinite(numeric) else default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _load_scores(path: Path) -> dict[tuple[Any, ...], dict[str, dict[str, Any]]]:
    by_unit: dict[tuple[Any, ...], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in iter_jsonl(path):
        key = _unit_key(row)
        condition = str(row["condition"])
        if condition in by_unit[key]:
            raise RuntimeError(f"duplicate score row for {key}/{condition}")
        by_unit[key][condition] = row
    return dict(by_unit)


def _load_turns(
    path: Path,
    *,
    units: set[tuple[Any, ...]],
    conditions: set[str],
) -> dict[tuple[Any, ...], dict[str, dict[str, Any]]]:
    by_unit: dict[tuple[Any, ...], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in iter_jsonl(path):
        key = _unit_key(row)
        condition = str(row.get("condition"))
        if key not in units or condition not in conditions:
            continue
        if condition in by_unit[key]:
            raise RuntimeError(f"duplicate turn row for {key}/{condition}")
        by_unit[key][condition] = row
    missing = []
    for key in sorted(units):
        for condition in sorted(conditions):
            if condition not in by_unit.get(key, {}):
                missing.append((key, condition))
    if missing:
        raise RuntimeError(f"missing {len(missing)} turn rows; first={missing[0]}")
    return dict(by_unit)


def _condition_feature(
    turn: dict[str, Any],
    score: dict[str, Any],
) -> dict[str, Any]:
    cost = turn.get("cost") or {}
    selected_memory = turn.get("selected_memory") or []
    selected_strategy = turn.get("selected_strategy") or []
    memory_sources = Counter(str(item.get("source") or "UNKNOWN") for item in selected_memory)
    action_id = str(turn.get("action_id") or score.get("action_id") or "")
    return {
        "condition": str(turn.get("condition")),
        "action_id": action_id,
        "overall": _safe_float(score.get("overall")),
        "memory_appropriateness": _safe_float(score.get("memory_appropriateness")),
        "factual_grounding": _safe_float(score.get("factual_grounding")),
        "non_intrusiveness": _safe_float(score.get("non_intrusiveness")),
        "selected_memory_count": len(selected_memory),
        "selected_strategy_count": len(selected_strategy),
        "memory_sources": dict(memory_sources),
        "total_input_tokens": _safe_float(cost.get("total_input_tokens")),
        "output_tokens": _safe_float(cost.get("output_tokens")),
        "memory_tokens": _safe_float(cost.get("memory_tokens")),
        "strategy_tokens": _safe_float(cost.get("strategy_tokens")),
        "retrieval_calls": _safe_float(cost.get("retrieval_calls")),
        "rs_called": action_id.endswith("+RS") or bool(selected_strategy),
        "r0_called": action_id.endswith("+R0"),
    }


def _build_units(
    scores_by_unit: dict[tuple[Any, ...], dict[str, dict[str, Any]]],
    turns_by_unit: dict[tuple[Any, ...], dict[str, dict[str, Any]]],
    *,
    conditions: list[str],
) -> list[dict[str, Any]]:
    units = []
    for key in sorted(scores_by_unit):
        score_conds = scores_by_unit[key]
        turn_conds = turns_by_unit[key]
        if any(cond not in score_conds or cond not in turn_conds for cond in conditions):
            continue
        condition_features = {
            cond: _condition_feature(turn_conds[cond], score_conds[cond])
            for cond in conditions
        }
        pm = condition_features["pm"]
        comparisons = {}
        for baseline in conditions:
            if baseline == "pm":
                continue
            base = condition_features[baseline]
            base_input = base["total_input_tokens"]
            pm_input = pm["total_input_tokens"]
            comparisons[baseline] = {
                "overall_delta_pm_minus_baseline": pm["overall"] - base["overall"],
                "memory_appropriateness_delta_pm_minus_baseline": (
                    pm["memory_appropriateness"] - base["memory_appropriateness"]
                ),
                "non_intrusiveness_delta_pm_minus_baseline": (
                    pm["non_intrusiveness"] - base["non_intrusiveness"]
                ),
                "input_reduction_vs_baseline": (
                    (base_input - pm_input) / base_input if base_input else None
                ),
                "input_tokens_saved_vs_baseline": base_input - pm_input,
                "same_action": pm["action_id"] == base["action_id"],
            }
        units.append(
            {
                "unit_key": _unit_key_dict(key),
                "unit_key_tuple": key,
                "unit_id": str(score_conds["pm"].get("unit_id")),
                "conditions": condition_features,
                "comparisons": comparisons,
            }
        )
    return units


def _rank_key(*values: float) -> tuple[float, ...]:
    return tuple(float(v) for v in values)


def _make_candidate(
    unit: dict[str, Any],
    *,
    stratum: str,
    focus_conditions: list[str],
    modules: list[str],
    priority_score: float,
    reason: str,
    baseline: str | None = None,
) -> dict[str, Any]:
    pm = unit["conditions"]["pm"]
    item = {
        "stratum": stratum,
        "priority_score": float(priority_score),
        "unit_id": unit["unit_id"],
        "unit_key": unit["unit_key"],
        "focus_conditions": focus_conditions,
        "audit_modules": modules,
        "reason": reason,
        "pm_action_id": pm["action_id"],
        "pm_overall": pm["overall"],
        "pm_total_input_tokens": pm["total_input_tokens"],
        "pm_memory_tokens": pm["memory_tokens"],
        "pm_selected_memory_count": pm["selected_memory_count"],
        "pm_selected_strategy_count": pm["selected_strategy_count"],
        "pm_memory_sources": pm["memory_sources"],
    }
    if baseline:
        base = unit["conditions"][baseline]
        comp = unit["comparisons"][baseline]
        item.update(
            {
                "baseline": baseline,
                "baseline_action_id": base["action_id"],
                "baseline_overall": base["overall"],
                "baseline_total_input_tokens": base["total_input_tokens"],
                "overall_delta_pm_minus_baseline": comp[
                    "overall_delta_pm_minus_baseline"
                ],
                "input_reduction_vs_baseline": comp["input_reduction_vs_baseline"],
                "input_tokens_saved_vs_baseline": comp[
                    "input_tokens_saved_vs_baseline"
                ],
                "same_action": comp["same_action"],
            }
        )
    return item


def _stratum_candidates(units: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    strata: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for unit in units:
        pm = unit["conditions"]["pm"]
        strong = unit["conditions"]["strong_rule"]
        best = unit["conditions"]["best_fixed"]
        session = unit["conditions"]["session_rag_rs"]
        no_memory = unit["conditions"]["no_memory_r0"]

        strong_comp = unit["comparisons"]["strong_rule"]
        best_comp = unit["comparisons"]["best_fixed"]
        session_comp = unit["comparisons"]["session_rag_rs"]
        no_mem_comp = unit["comparisons"]["no_memory_r0"]

        if not strong_comp["same_action"]:
            score = _safe_float(strong_comp["input_tokens_saved_vs_baseline"]) + 100 * (
                1.0 + strong_comp["overall_delta_pm_minus_baseline"]
            )
            strata["pm_vs_strong_rule_action_disagreement"].append(
                _make_candidate(
                    unit,
                    stratum="pm_vs_strong_rule_action_disagreement",
                    focus_conditions=["pm", "strong_rule"],
                    modules=[
                        "selected_evidence_misuse",
                        "unnecessary_exposure",
                        "strategy_overuse",
                    ],
                    priority_score=score,
                    reason="PM and strong_rule choose different actions while V4 response quality is comparable overall.",
                    baseline="strong_rule",
                )
            )

        if _safe_float(best_comp["input_reduction_vs_baseline"], -999) > 0:
            score = 1000 * _safe_float(best_comp["input_reduction_vs_baseline"]) + 50 * (
                1.0 + best_comp["overall_delta_pm_minus_baseline"]
            )
            strata["pm_vs_best_fixed_resource_saving"].append(
                _make_candidate(
                    unit,
                    stratum="pm_vs_best_fixed_resource_saving",
                    focus_conditions=["pm", "best_fixed"],
                    modules=[
                        "selected_evidence_misuse",
                        "unnecessary_exposure",
                        "source_set_appropriateness",
                    ],
                    priority_score=score,
                    reason="PM uses fewer resources than best_fixed, useful for auditing whether omitted sources were unnecessary.",
                    baseline="best_fixed",
                )
            )

        if session_comp["overall_delta_pm_minus_baseline"] < 0 and _safe_float(
            session_comp["input_reduction_vs_baseline"], -999
        ) > 0:
            quality_gap = -session_comp["overall_delta_pm_minus_baseline"]
            score = 1000 * quality_gap + 100 * _safe_float(
                session_comp["input_reduction_vs_baseline"]
            )
            strata["pm_vs_session_quality_cost_tradeoff"].append(
                _make_candidate(
                    unit,
                    stratum="pm_vs_session_quality_cost_tradeoff",
                    focus_conditions=["pm", "session_rag_rs"],
                    modules=[
                        "omission_with_authorized_context",
                        "selected_evidence_misuse",
                        "source_set_appropriateness",
                    ],
                    priority_score=score,
                    reason="session_rag_rs scores higher but costs more; audit whether PM omitted useful session evidence or saved unnecessary exposure.",
                    baseline="session_rag_rs",
                )
            )

        if no_mem_comp["overall_delta_pm_minus_baseline"] < 0:
            quality_gap = -no_mem_comp["overall_delta_pm_minus_baseline"]
            exposure = pm["selected_memory_count"] + pm["selected_strategy_count"]
            score = 1000 * quality_gap + 25 * exposure
            strata["pm_vs_no_memory_quality_loss"].append(
                _make_candidate(
                    unit,
                    stratum="pm_vs_no_memory_quality_loss",
                    focus_conditions=["pm", "no_memory_r0"],
                    modules=[
                        "unnecessary_exposure",
                        "unsupported_personal_claim",
                        "strategy_overuse",
                    ],
                    priority_score=score,
                    reason="no_memory_r0 scores higher; audit whether PM's resource use was intrusive, stale, or over-structured.",
                    baseline="no_memory_r0",
                )
            )

        high_resource_score = (
            pm["total_input_tokens"]
            + 0.5 * pm["memory_tokens"]
            + 100 * pm["selected_memory_count"]
            + 50 * pm["selected_strategy_count"]
        )
        strata["pm_high_resource_exposure"].append(
            _make_candidate(
                unit,
                stratum="pm_high_resource_exposure",
                focus_conditions=["pm"],
                modules=[
                    "selected_evidence_misuse",
                    "unnecessary_exposure",
                    "stale_or_conflict",
                    "unsupported_personal_claim",
                ],
                priority_score=high_resource_score,
                reason="PM uses comparatively high memory/strategy resources; audit exposure and stale/conflict risk.",
            )
        )

        if pm["r0_called"] or pm["selected_strategy_count"] == 0:
            score = 1000 + (strong["overall"] - pm["overall"]) * 100
            strata["pm_low_resource_or_r0"].append(
                _make_candidate(
                    unit,
                    stratum="pm_low_resource_or_r0",
                    focus_conditions=["pm", "strong_rule"],
                    modules=[
                        "strategy_omission",
                        "omission_with_authorized_context",
                        "response_support_sufficiency",
                    ],
                    priority_score=score,
                    reason="PM suppresses Strategy RAG or chooses R0; audit possible strategy omission against strong_rule.",
                    baseline="strong_rule",
                )
            )

        if (
            strong_comp["overall_delta_pm_minus_baseline"] >= 0
            and _safe_float(strong_comp["input_reduction_vs_baseline"], -999) > 0
        ) or (
            best_comp["overall_delta_pm_minus_baseline"] >= 0
            and _safe_float(best_comp["input_reduction_vs_baseline"], -999) > 0
        ):
            score = max(
                _safe_float(strong_comp["input_tokens_saved_vs_baseline"]),
                _safe_float(best_comp["input_tokens_saved_vs_baseline"]),
            ) + 100 * pm["overall"]
            strata["pm_quality_tie_or_win_with_savings"].append(
                _make_candidate(
                    unit,
                    stratum="pm_quality_tie_or_win_with_savings",
                    focus_conditions=["pm", "strong_rule", "best_fixed"],
                    modules=[
                        "positive_control_resource_saving",
                        "selected_evidence_misuse",
                        "source_set_appropriateness",
                    ],
                    priority_score=score,
                    reason="PM ties or beats conservative baselines while saving resources; audit as positive control.",
                )
            )

        if pm["action_id"] not in {"MSE+RS"}:
            rarity_score = {
                "ME+R0": 900,
                "MS+R0": 850,
                "MP+R0": 840,
                "ME+RS": 700,
                "MPE+RS": 650,
                "MS+RS": 600,
                "MP+RS": 550,
                "MPMS+RS": 500,
            }.get(pm["action_id"], 300)
            strata["rare_pm_actions"].append(
                _make_candidate(
                    unit,
                    stratum="rare_pm_actions",
                    focus_conditions=["pm"],
                    modules=[
                        "action_diversity_check",
                        "selected_evidence_misuse",
                        "strategy_overuse",
                    ],
                    priority_score=rarity_score + pm["overall"],
                    reason="Covers rare PM actions so the audit is not dominated by MSE+RS.",
                )
            )

    for items in strata.values():
        items.sort(
            key=lambda x: (
                -x["priority_score"],
                str(x["unit_key"]["user_id"]),
                int(x["unit_key"]["topic_index"]),
                int(x["unit_key"]["seed"]),
                int(x["unit_key"]["turn_index"]),
            )
        )
    return dict(strata)


def _select_items(
    strata: dict[str, list[dict[str, Any]]],
    *,
    per_stratum: int,
    target_units: int,
) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    scenario_counts: Counter[str] = Counter()
    order = [
        "pm_vs_strong_rule_action_disagreement",
        "pm_vs_best_fixed_resource_saving",
        "pm_vs_session_quality_cost_tradeoff",
        "pm_vs_no_memory_quality_loss",
        "pm_high_resource_exposure",
        "pm_low_resource_or_r0",
        "pm_quality_tie_or_win_with_savings",
        "rare_pm_actions",
    ]

    def scenario_id(item: dict[str, Any]) -> str:
        key = item["unit_key"]
        return f"{key['user_id']}::{key['topic_index']}"

    def add_item(item: dict[str, Any], stratum: str) -> bool:
        key = item["unit_id"]
        if key in selected:
            selected[key].setdefault("covered_strata", []).append(stratum)
            return False
        copied = dict(item)
        copied["covered_strata"] = [stratum]
        selected[key] = copied
        scenario_counts[scenario_id(copied)] += 1
        return True

    # First pass: preserve stratum coverage while preferring fresh scenarios.
    for stratum in order:
        added = 0
        for item in strata.get(stratum, []):
            if item["unit_id"] in selected:
                selected[item["unit_id"]].setdefault("covered_strata", []).append(stratum)
                continue
            if scenario_counts[scenario_id(item)] > 0:
                continue
            if add_item(item, stratum):
                added += 1
            if added >= per_stratum or len(selected) >= target_units:
                break
        if len(selected) >= target_units:
            break

    # Second pass: fill under-covered strata even if a scenario repeats.
    for stratum in order:
        if len(selected) >= target_units:
            break
        current = sum(
            1 for item in selected.values() if stratum in item.get("covered_strata", [])
        )
        if current >= per_stratum:
            continue
        for item in strata.get(stratum, []):
            if item["unit_id"] in selected:
                selected[item["unit_id"]].setdefault("covered_strata", []).append(stratum)
                continue
            if add_item(item, stratum):
                current += 1
            if current >= per_stratum or len(selected) >= target_units:
                break

    if len(selected) < target_units:
        all_items = sorted(
            (item for values in strata.values() for item in values),
            key=lambda x: (
                scenario_counts[scenario_id(x)],
                -x["priority_score"],
                x["unit_id"],
            ),
        )
        for item in all_items:
            key = item["unit_id"]
            if key in selected:
                selected[key].setdefault("covered_strata", []).append(item["stratum"])
                continue
            add_item(item, item["stratum"])
            if len(selected) >= target_units:
                break
    result = list(selected.values())
    result.sort(
        key=lambda x: (
            int(x["unit_key"]["topic_index"]),
            str(x["unit_key"]["user_id"]),
            int(x["unit_key"]["seed"]),
            int(x["unit_key"]["turn_index"]),
            x["unit_id"],
        )
    )
    for i, item in enumerate(result, 1):
        item["audit_item_id"] = f"audit_v4_{i:03d}"
    return result


def _estimate_condition_call_tokens(item: dict[str, Any], condition: str, unit: dict[str, Any]) -> int:
    feat = unit["conditions"][condition]
    # Selected-evidence audit prompts can be shorter than generation prompts,
    # but this conservative estimate keeps the later budget gate honest.
    return int(feat["total_input_tokens"] + feat["output_tokens"] + 450)


def _estimate_omission_tokens(item: dict[str, Any], unit: dict[str, Any]) -> int:
    full = unit["conditions"].get("session_rag_rs") or unit["conditions"]["pm"]
    if "full_history_rs" in unit["conditions"]:
        full = unit["conditions"]["full_history_rs"]
    pm = unit["conditions"]["pm"]
    return int(full["total_input_tokens"] + pm["output_tokens"] + 650)


def _audit_cost_estimate(
    selected: list[dict[str, Any]],
    units_by_id: dict[str, dict[str, Any]],
    *,
    max_omission_units: int,
    estimated_output_tokens_per_call: int,
    input_usd_per_mtok: float,
    output_usd_per_mtok: float,
) -> dict[str, Any]:
    selected_calls = []
    omission_calls = []
    omission_used = 0
    for item in selected:
        unit = units_by_id[item["unit_id"]]
        for condition in item["focus_conditions"]:
            if condition == "no_memory_r0":
                # no-memory responses are included only when comparing possible
                # overuse; they do not need a selected-evidence audit call.
                continue
            selected_calls.append(
                {
                    "audit_item_id": item["audit_item_id"],
                    "condition": condition,
                    "estimated_input_tokens": _estimate_condition_call_tokens(
                        item, condition, unit
                    ),
                }
            )
        if (
            "omission_with_authorized_context" in item["audit_modules"]
            and omission_used < max_omission_units
        ):
            omission_calls.append(
                {
                    "audit_item_id": item["audit_item_id"],
                    "estimated_input_tokens": _estimate_omission_tokens(item, unit),
                }
            )
            omission_used += 1
    input_tokens = sum(c["estimated_input_tokens"] for c in selected_calls + omission_calls)
    output_tokens = estimated_output_tokens_per_call * (len(selected_calls) + len(omission_calls))
    return {
        "status": "ESTIMATED_NO_API",
        "selected_evidence_or_strategy_calls": len(selected_calls),
        "authorized_context_omission_calls": len(omission_calls),
        "total_estimated_calls": len(selected_calls) + len(omission_calls),
        "estimated_input_tokens": input_tokens,
        "estimated_output_tokens": output_tokens,
        "estimated_cost_usd": input_tokens / 1e6 * input_usd_per_mtok
        + output_tokens / 1e6 * output_usd_per_mtok,
        "pricing": {
            "input_usd_per_mtok": input_usd_per_mtok,
            "output_usd_per_mtok": output_usd_per_mtok,
        },
        "estimated_output_tokens_per_call": estimated_output_tokens_per_call,
        "max_omission_units": max_omission_units,
        "note": "Planning estimate only. A real audit script must do its own dry-run hash and budget gate before API calls.",
    }


def _summarize_selection(selected: list[dict[str, Any]]) -> dict[str, Any]:
    by_stratum = Counter()
    focus = Counter()
    modules = Counter()
    actions = Counter()
    turns = Counter()
    users = set()
    scenarios = set()
    topics = set()
    for item in selected:
        for stratum in item.get("covered_strata") or [item["stratum"]]:
            by_stratum[stratum] += 1
        for condition in item["focus_conditions"]:
            focus[condition] += 1
        for module in item["audit_modules"]:
            modules[module] += 1
        actions[item["pm_action_id"]] += 1
        turns[str(item["unit_key"]["turn_index"])] += 1
        users.add(item["unit_key"]["user_id"])
        scenarios.add((item["unit_key"]["user_id"], item["unit_key"]["topic_index"]))
        topics.add(int(item["unit_key"]["topic_index"]))
    return {
        "selected_items": len(selected),
        "unique_users": len(users),
        "unique_scenarios": len(scenarios),
        "unique_topics": len(topics),
        "turn_counts": dict(sorted(turns.items())),
        "pm_action_counts": dict(actions.most_common()),
        "focus_condition_counts": dict(focus.most_common()),
        "audit_module_counts": dict(modules.most_common()),
        "covered_strata_counts": dict(by_stratum.most_common()),
    }


def _write_markdown(path: Path, *, plan: dict[str, Any], items: list[dict[str, Any]]) -> None:
    def table(headers: list[str], rows: list[list[Any]]) -> str:
        lines = [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
        ]
        for row in rows:
            lines.append("| " + " | ".join(str(x) for x in row) + " |")
        return "\n".join(lines)

    summary = plan["selection_summary"]
    estimate = plan["cost_estimate"]
    top_rows = []
    for item in items[:18]:
        top_rows.append(
            [
                item["audit_item_id"],
                item["unit_key"]["user_id"],
                item["unit_key"]["topic_index"],
                item["unit_key"]["seed"],
                item["unit_key"]["turn_index"],
                item["pm_action_id"],
                ",".join(item["focus_conditions"]),
                ",".join(item.get("covered_strata") or [item["stratum"]]),
            ]
        )
    lines = [
        "# EvoEmo Sampled Memory / Strategy Audit No-API Plan",
        "",
        f"生成时间：{utc_now()}",
        "",
        "本文件只是抽样和预算计划，不包含 API judge 结果，不能作为 audit 结论。",
        "",
        "## Design Rationale",
        "",
        "- 优先审计 `pm` vs `strong_rule` / `best_fixed`：V4 response quality 接近，但 PM 更省资源。",
        "- 纳入 `pm` vs `session_rag_rs`：session_rag 分数较高但成本更大，用于审计 quality-cost tradeoff。",
        "- 纳入 `pm` vs `no_memory_r0`：用于检查资源使用是否造成不必要暴露或过度结构化。",
        "- 覆盖 PM 高资源、低资源/R0、罕见 action，避免 audit 被 `MSE+RS` 主导。",
        "",
        "## Sample Summary",
        "",
        f"- selected items: {summary['selected_items']}",
        f"- unique users: {summary['unique_users']}",
        f"- unique scenarios `(user_id, topic_index)`: {summary['unique_scenarios']}",
        f"- unique topics: {summary['unique_topics']}",
        f"- turn counts: {summary['turn_counts']}",
        f"- PM action counts: {summary['pm_action_counts']}",
        f"- focus condition counts: {summary['focus_condition_counts']}",
        f"- audit module counts: {summary['audit_module_counts']}",
        "",
        "## Cost Estimate",
        "",
        f"- selected-evidence / strategy calls: {estimate['selected_evidence_or_strategy_calls']}",
        f"- authorized-context omission calls: {estimate['authorized_context_omission_calls']}",
        f"- total estimated calls: {estimate['total_estimated_calls']}",
        f"- estimated input tokens: {estimate['estimated_input_tokens']}",
        f"- estimated output tokens: {estimate['estimated_output_tokens']}",
        f"- estimated cost: ${estimate['estimated_cost_usd']:.2f}",
        "",
        "真实 audit API 脚本仍必须先做 dry-run hash、budget gate 和小样本 pilot；不能直接 full-run。",
        "",
        "## Preview Items",
        "",
        table(
            [
                "id",
                "user",
                "topic",
                "seed",
                "turn",
                "pm_action",
                "focus",
                "covered_strata",
            ],
            top_rows,
        ),
        "",
        "## Audit Modules",
        "",
        "- `selected_evidence_misuse`: selected memory 是否被错误使用、过度使用或引入 unsupported personal claim。",
        "- `unnecessary_exposure`: 资源是否暴露了当前回复不需要的个人事实。",
        "- `stale_or_conflict`: selected memory 是否与更新信息冲突或被过时使用。",
        "- `source_set_appropriateness`: PM 选择的 source set 是否相对 baseline 足够。",
        "- `strategy_overuse`: Strategy RAG 是否导致过度结构化、过早建议或语气不自然。",
        "- `strategy_omission`: PM 关闭或弱化 strategy 时是否遗漏明显需要的支持策略。",
        "- `omission_with_authorized_context`: 少量高价值样本使用 evaluator-only context 审计遗漏，必须严格限量。",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scores",
        type=Path,
        default=ROOT / "outputs/evoemo_response_v4/response_scores.jsonl",
    )
    parser.add_argument(
        "--turns",
        type=Path,
        default=ROOT / "outputs/evoemo_selective/turns.jsonl",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "outputs/evoemo_sampled_audit_plan",
    )
    parser.add_argument("--per-stratum", type=int, default=6)
    parser.add_argument("--target-units", type=int, default=40)
    parser.add_argument("--max-omission-units", type=int, default=12)
    parser.add_argument("--estimated-output-tokens-per-call", type=int, default=450)
    parser.add_argument("--input-usd-per-mtok", type=float, default=2.50)
    parser.add_argument("--output-usd-per-mtok", type=float, default=10.0)
    args = parser.parse_args()

    conditions = list(DEFAULT_CONDITIONS)
    scores_by_unit = _load_scores(args.scores)
    units = set(scores_by_unit)
    turns_by_unit = _load_turns(
        args.turns, units=units, conditions=set(conditions)
    )
    units_full = _build_units(
        scores_by_unit, turns_by_unit, conditions=conditions
    )
    units_by_id = {unit["unit_id"]: unit for unit in units_full}
    strata = _stratum_candidates(units_full)
    selected = _select_items(
        strata, per_stratum=args.per_stratum, target_units=args.target_units
    )
    cost_estimate = _audit_cost_estimate(
        selected,
        units_by_id,
        max_omission_units=args.max_omission_units,
        estimated_output_tokens_per_call=args.estimated_output_tokens_per_call,
        input_usd_per_mtok=args.input_usd_per_mtok,
        output_usd_per_mtok=args.output_usd_per_mtok,
    )

    plan = {
        "status": "PLANNED_NO_API",
        "created_at": utc_now(),
        "protocol": "evoemo_sampled_memory_strategy_audit_plan_v1",
        "inputs": {
            "scores": str(args.scores),
            "turns": str(args.turns),
        },
        "parameters": {
            "conditions": conditions,
            "per_stratum": args.per_stratum,
            "target_units": args.target_units,
            "max_omission_units": args.max_omission_units,
            "estimated_output_tokens_per_call": args.estimated_output_tokens_per_call,
        },
        "candidate_pool": {
            "v4_units": len(units_full),
            "strata_candidate_counts": {
                key: len(value) for key, value in sorted(strata.items())
            },
        },
        "selection_summary": _summarize_selection(selected),
        "cost_estimate": cost_estimate,
        "guardrails": {
            "no_api_calls": True,
            "requires_future_dry_run_hash": True,
            "requires_pilot_before_api_full_run": True,
            "recommended_pilot_items": min(8, len(selected)),
            "raw_rows_manual_gate": "raw_rows <= expected_calls * 1.10",
            "do_not_use_as_audit_result": True,
        },
        "audit_items": selected,
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.out_dir / "audit_sample_plan.json", plan)
    write_jsonl(args.out_dir / "audit_items.jsonl", selected)
    _write_markdown(args.out_dir / "audit_sample_plan.md", plan=plan, items=selected)
    print(
        {
            "status": "PLANNED_NO_API",
            "out_dir": str(args.out_dir),
            "selected_items": len(selected),
            "estimated_calls": cost_estimate["total_estimated_calls"],
            "estimated_cost_usd": round(cost_estimate["estimated_cost_usd"], 4),
        }
    )


if __name__ == "__main__":
    main()
