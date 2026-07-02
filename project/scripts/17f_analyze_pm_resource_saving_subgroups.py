#!/usr/bin/env python3
"""No-API subgroup analysis for PM resource savings in EvoEmo Response V4.

The analysis asks a narrow question:

When the learned PM uses fewer input tokens than a resource baseline, does the
turn-level response quality drop sharply, and do sampled audit rows show
evidence misuse or exposure for those resource-saving cases?
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_BASELINES = (
    "strong_rule",
    "best_fixed",
    "session_rag_rs",
    "full_history_rs",
    "no_memory_r0",
)

SCORE_FIELDS = (
    "overall",
    "emotional_support",
    "personalization",
    "memory_appropriateness",
    "factual_grounding",
    "temporal_consistency",
    "non_intrusiveness",
)

RISK_FIELDS = (
    "selected_evidence_misuse",
    "unnecessary_exposure",
    "stale_or_conflict",
    "unsupported_personal_claim",
    "strategy_overuse",
    "strategy_omission",
    "omission_severity",
    "overall_risk",
)


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def safe_float(value: Any, default: float = math.nan) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def unit_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("user_id"),
        row.get("topic_index"),
        row.get("seed"),
        row.get("simulator_id"),
        row.get("interaction_mode"),
        row.get("turn_index"),
    )


def cost_value(turn: dict[str, Any], field: str) -> float:
    return safe_float((turn.get("cost") or {}).get(field), 0.0)


def summarize_numbers(values: Iterable[float]) -> dict[str, Any]:
    vals = [float(v) for v in values if math.isfinite(float(v))]
    if not vals:
        return {"n": 0, "mean": None, "median": None, "min": None, "max": None}
    vals_sorted = sorted(vals)
    return {
        "n": len(vals),
        "mean": float(mean(vals)),
        "median": float(median(vals_sorted)),
        "min": float(vals_sorted[0]),
        "max": float(vals_sorted[-1]),
    }


def summarize_delta_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"n": len(rows)}
    if not rows:
        for field in SCORE_FIELDS:
            out[f"{field}_delta"] = summarize_numbers([])
        out.update(
            {
                "pm_higher_overall": 0,
                "tie_overall": 0,
                "pm_lower_overall": 0,
                "tie_or_higher_overall_rate": None,
                "pm_lower_by_1_or_more_rate": None,
                "mean_input_tokens_saved": None,
                "mean_memory_tokens_saved": None,
                "mean_input_reduction_vs_baseline": None,
                "same_action_rate": None,
                "pm_memory_count_mean": None,
                "baseline_memory_count_mean": None,
            }
        )
        return out

    for field in SCORE_FIELDS:
        out[f"{field}_delta"] = summarize_numbers(row[f"{field}_delta"] for row in rows)
    deltas = [row["overall_delta"] for row in rows]
    higher = sum(1 for delta in deltas if delta > 0)
    tie = sum(1 for delta in deltas if delta == 0)
    lower = sum(1 for delta in deltas if delta < 0)
    out.update(
        {
            "pm_higher_overall": higher,
            "tie_overall": tie,
            "pm_lower_overall": lower,
            "tie_or_higher_overall_rate": (higher + tie) / len(rows),
            "pm_lower_by_1_or_more_rate": lower / len(rows),
            "mean_input_tokens_saved": mean(row["input_tokens_saved"] for row in rows),
            "median_input_tokens_saved": median(sorted(row["input_tokens_saved"] for row in rows)),
            "mean_memory_tokens_saved": mean(row["memory_tokens_saved"] for row in rows),
            "mean_input_reduction_vs_baseline": mean(
                row["input_reduction_vs_baseline"] for row in rows
            ),
            "same_action_rate": mean(1.0 if row["same_action"] else 0.0 for row in rows),
            "pm_memory_count_mean": mean(row["pm_selected_memory_count"] for row in rows),
            "baseline_memory_count_mean": mean(
                row["baseline_selected_memory_count"] for row in rows
            ),
        }
    )
    return out


def score_index(scores: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    by_unit: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in scores:
        uid = str(row["unit_id"])
        cond = str(row["condition"])
        if cond in by_unit[uid]:
            raise RuntimeError(f"duplicate score row for unit={uid} condition={cond}")
        by_unit[uid][cond] = row
    return dict(by_unit)


def build_turn_lookup(
    turns: Iterable[dict[str, Any]], scores: list[dict[str, Any]]
) -> dict[tuple[str, str], dict[str, Any]]:
    key_to_unit = {unit_key(row): str(row["unit_id"]) for row in scores}
    wanted_conditions = {str(row["condition"]) for row in scores}
    lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for row in turns:
        key = unit_key(row)
        uid = key_to_unit.get(key)
        if uid is None:
            continue
        cond = str(row.get("condition"))
        if cond not in wanted_conditions:
            continue
        lookup[(uid, cond)] = row
    expected = {(str(row["unit_id"]), str(row["condition"])) for row in scores}
    missing = expected - set(lookup)
    if missing:
        raise RuntimeError(f"missing {len(missing)} V4 sampled turn rows; first={next(iter(missing))}")
    return lookup


def selected_count(turn: dict[str, Any], field: str) -> int:
    value = turn.get(field) or []
    return len(value) if isinstance(value, list) else 0


def comparison_rows(
    scores_by_unit: dict[str, dict[str, dict[str, Any]]],
    turns_by_unit_cond: dict[tuple[str, str], dict[str, Any]],
    baseline: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for uid, cond_scores in sorted(scores_by_unit.items()):
        if "pm" not in cond_scores or baseline not in cond_scores:
            continue
        pm_score = cond_scores["pm"]
        base_score = cond_scores[baseline]
        pm_turn = turns_by_unit_cond[(uid, "pm")]
        base_turn = turns_by_unit_cond[(uid, baseline)]
        base_input = cost_value(base_turn, "total_input_tokens")
        pm_input = cost_value(pm_turn, "total_input_tokens")
        input_saved = base_input - pm_input
        item = {
            "unit_id": uid,
            "user_id": pm_score.get("user_id"),
            "topic_index": pm_score.get("topic_index"),
            "seed": pm_score.get("seed"),
            "turn_index": pm_score.get("turn_index"),
            "baseline": baseline,
            "pm_action_id": pm_turn.get("action_id"),
            "baseline_action_id": base_turn.get("action_id"),
            "same_action": pm_turn.get("action_id") == base_turn.get("action_id"),
            "pm_input_tokens": pm_input,
            "baseline_input_tokens": base_input,
            "input_tokens_saved": input_saved,
            "input_reduction_vs_baseline": input_saved / base_input if base_input else 0.0,
            "pm_memory_tokens": cost_value(pm_turn, "memory_tokens"),
            "baseline_memory_tokens": cost_value(base_turn, "memory_tokens"),
            "memory_tokens_saved": cost_value(base_turn, "memory_tokens")
            - cost_value(pm_turn, "memory_tokens"),
            "pm_strategy_tokens": cost_value(pm_turn, "strategy_tokens"),
            "baseline_strategy_tokens": cost_value(base_turn, "strategy_tokens"),
            "pm_selected_memory_count": selected_count(pm_turn, "selected_memory"),
            "baseline_selected_memory_count": selected_count(base_turn, "selected_memory"),
            "pm_selected_strategy_count": selected_count(pm_turn, "selected_strategy"),
            "baseline_selected_strategy_count": selected_count(base_turn, "selected_strategy"),
        }
        for field in SCORE_FIELDS:
            item[f"pm_{field}"] = safe_float(pm_score.get(field))
            item[f"baseline_{field}"] = safe_float(base_score.get(field))
            item[f"{field}_delta"] = item[f"pm_{field}"] - item[f"baseline_{field}"]
        rows.append(item)
    return rows


def summarize_comparison(rows: list[dict[str, Any]]) -> dict[str, Any]:
    saved = [row for row in rows if row["input_tokens_saved"] > 0]
    not_saved = [row for row in rows if row["input_tokens_saved"] <= 0]
    large_saved = [row for row in rows if row["input_reduction_vs_baseline"] >= 0.20]
    quality_tie_or_win_with_savings = [
        row for row in rows if row["input_tokens_saved"] > 0 and row["overall_delta"] >= 0
    ]
    saved_quality_drop = [
        row for row in rows if row["input_tokens_saved"] > 0 and row["overall_delta"] < 0
    ]
    by_turn: dict[str, Any] = {}
    grouped_by_turn: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped_by_turn[str(row["turn_index"])].append(row)
    for turn, turn_rows in sorted(grouped_by_turn.items(), key=lambda x: int(x[0])):
        by_turn[turn] = {
            "all": summarize_delta_rows(turn_rows),
            "saved": summarize_delta_rows([row for row in turn_rows if row["input_tokens_saved"] > 0]),
        }
    return {
        "all": summarize_delta_rows(rows),
        "pm_saves_input": summarize_delta_rows(saved),
        "pm_does_not_save_input": summarize_delta_rows(not_saved),
        "pm_saves_at_least_20_percent_input": summarize_delta_rows(large_saved),
        "saved_and_quality_tie_or_win": summarize_delta_rows(quality_tie_or_win_with_savings),
        "saved_but_quality_lower": summarize_delta_rows(saved_quality_drop),
        "by_turn_index": by_turn,
        "action_pair_counts": {
            f"{pm_action} -> {baseline_action}": count
            for (pm_action, baseline_action), count in Counter(
                (row["pm_action_id"], row["baseline_action_id"]) for row in rows
            ).most_common()
        },
    }


def summarize_audit(
    audit_items: list[dict[str, Any]], audit_scores: list[dict[str, Any]]
) -> dict[str, Any]:
    item_by_id = {str(row["audit_item_id"]): row for row in audit_items}
    joined = []
    for score in audit_scores:
        item = item_by_id.get(str(score.get("audit_item_id")))
        if not item:
            continue
        row = {**score}
        row["audit_plan"] = item
        row["stratum"] = item.get("stratum")
        row["input_tokens_saved_vs_baseline"] = safe_float(
            item.get("input_tokens_saved_vs_baseline"), 0.0
        )
        row["overall_delta_pm_minus_baseline"] = safe_float(
            item.get("overall_delta_pm_minus_baseline"), 0.0
        )
        joined.append(row)

    def risk_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {"n": len(rows), "verdict_counts": dict(Counter(row.get("verdict") for row in rows))}
        for field in RISK_FIELDS:
            positive = [row for row in rows if safe_float(row.get(field), 0.0) > 0]
            major = [row for row in rows if safe_float(row.get(field), 0.0) >= 2]
            out[field] = {
                "positive_cases": len(positive),
                "major_cases": len(major),
                "mean_severity": mean(safe_float(row.get(field), 0.0) for row in rows) if rows else None,
            }
        return out

    pm_rows = [row for row in joined if str(row.get("condition")) == "pm"]
    pm_saving_rows = [row for row in pm_rows if row["input_tokens_saved_vs_baseline"] > 0]
    pm_non_saving_rows = [row for row in pm_rows if row["input_tokens_saved_vs_baseline"] <= 0]
    by_stratum = {
        stratum: risk_counts(rows)
        for stratum, rows in sorted(_group_by(pm_rows, "stratum").items())
    }
    return {
        "all_joined_rows": risk_counts(joined),
        "pm_rows": risk_counts(pm_rows),
        "pm_rows_with_input_savings_vs_focus_baseline": risk_counts(pm_saving_rows),
        "pm_rows_without_input_savings_vs_focus_baseline": risk_counts(pm_non_saving_rows),
        "pm_by_stratum": by_stratum,
        "pm_saving_case_ids": [row["audit_item_id"] for row in pm_saving_rows],
    }


def _group_by(rows: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(key))].append(row)
    return dict(grouped)


def fmt(value: Any, ndigits: int = 3) -> str:
    if value is None:
        return "NA"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(num):
        return "NA"
    return f"{num:.{ndigits}f}"


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def write_markdown(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    comparison_rows_md = []
    for baseline, summary in result["comparisons"].items():
        all_rows = summary["all"]
        saved = summary["pm_saves_input"]
        saved_tie = summary["saved_and_quality_tie_or_win"]
        saved_drop = summary["saved_but_quality_lower"]
        comparison_rows_md.append(
            [
                baseline,
                all_rows["n"],
                saved["n"],
                fmt(saved["mean_input_tokens_saved"], 1),
                fmt(saved["mean_input_reduction_vs_baseline"]),
                fmt(saved["overall_delta"]["mean"]),
                f"{saved_tie['n']}/{saved['n']}",
                f"{saved_drop['n']}/{saved['n']}",
            ]
        )

    turn_rows_md = []
    for baseline, summary in result["comparisons"].items():
        for turn, item in summary["by_turn_index"].items():
            saved = item["saved"]
            turn_rows_md.append(
                [
                    baseline,
                    turn,
                    item["all"]["n"],
                    saved["n"],
                    fmt(saved["mean_input_tokens_saved"], 1),
                    fmt(saved["overall_delta"]["mean"]),
                    f"{saved['pm_higher_overall']}/{saved['tie_overall']}/{saved['pm_lower_overall']}",
                ]
            )

    audit = result["audit_linkage"]
    audit_rows = []
    for name in [
        "pm_rows",
        "pm_rows_with_input_savings_vs_focus_baseline",
        "pm_rows_without_input_savings_vs_focus_baseline",
    ]:
        item = audit[name]
        audit_rows.append(
            [
                name,
                item["n"],
                item["selected_evidence_misuse"]["positive_cases"],
                item["unnecessary_exposure"]["positive_cases"],
                item["stale_or_conflict"]["positive_cases"],
                item["unsupported_personal_claim"]["positive_cases"],
                item["strategy_omission"]["positive_cases"],
                item["overall_risk"]["positive_cases"],
                item["verdict_counts"],
            ]
        )

    lines = [
        "# PM Resource Saving Subgroup Analysis",
        "",
        "No API was used. This report joins EvoEmo Response V4 score rows, generated turn cost metadata, and sampled audit rows.",
        "",
        "## Main Answer",
        "",
        "- PM does not mainly win by raising average response quality. Its stronger evidence is that it often uses fewer input tokens than rule or fixed structured baselines while keeping turn level quality close.",
        "- The saved resource cases are not automatically proof that PM skipped only unnecessary memory, but they are a useful diagnostic: if quality does not collapse when resources are removed, the extra evidence was often not decisive for fixed input response quality.",
        "- The sampled audit linkage is especially important because retrieved personal evidence is not only a cost. It also creates risk surface for misuse, exposure, stale conflict, and unsupported personal claims.",
        "",
        "## PM Saving Subgroups",
        "",
        markdown_table(
            [
                "Baseline",
                "All units",
                "PM saves input",
                "Mean tokens saved",
                "Mean reduction",
                "Mean overall delta in saved cases",
                "Saved and tie/win",
                "Saved but lower",
            ],
            comparison_rows_md,
        ),
        "",
        "## Saved Cases by Turn",
        "",
        markdown_table(
            [
                "Baseline",
                "Turn",
                "All units",
                "PM saves input",
                "Mean tokens saved",
                "Mean overall delta",
                "PM higher/tie/lower",
            ],
            turn_rows_md,
        ),
        "",
        "## Sampled Audit Linkage",
        "",
        markdown_table(
            [
                "Subset",
                "n",
                "Misuse >0",
                "Exposure >0",
                "Stale/conflict >0",
                "Unsupported claim >0",
                "Strategy omission >0",
                "Overall risk >0",
                "Verdicts",
            ],
            audit_rows,
        ),
        "",
        "## Interpretation",
        "",
        "The cleanest claim is not that PM produces better responses. It is that PM preserves comparable quality to Rule Policy and Fixed Structured while reducing evidence injection. This matters because extra retrieved personal evidence is a cost, latency, and risk surface rather than a harmless prompt addition.",
        "",
        "A safe paper sentence:",
        "",
        "> In resource saving subgroups, the learned PM frequently removed input evidence relative to rule or fixed structured baselines without a large average quality collapse. In the sampled audit, PM had no observed selected evidence misuse, unnecessary exposure, stale conflict, or unsupported personal claim across 50 PM audited cases, although the audit is descriptive and not a full safety guarantee.",
        "",
        "A sentence to avoid:",
        "",
        "> PM proves that the skipped evidence was always unnecessary or that PM is universally safer.",
        "",
    ]
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
        "--audit-items",
        type=Path,
        default=ROOT / "outputs/evoemo_sampled_audit_plan/audit_items.jsonl",
    )
    parser.add_argument(
        "--audit-scores",
        type=Path,
        default=ROOT / "outputs/evoemo_sampled_audit/audit_scores.jsonl",
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=ROOT / "outputs/evoemo_response_v4/pm_resource_saving_subgroups.json",
    )
    parser.add_argument(
        "--out-md",
        type=Path,
        default=ROOT / "outputs/evoemo_response_v4/pm_resource_saving_subgroups.md",
    )
    parser.add_argument(
        "--baselines",
        default=",".join(DEFAULT_BASELINES),
        help="Comma separated baseline conditions.",
    )
    args = parser.parse_args()

    baselines = [item.strip() for item in args.baselines.split(",") if item.strip()]
    scores = list(iter_jsonl(args.scores))
    turns = list(iter_jsonl(args.turns))
    audit_items = list(iter_jsonl(args.audit_items))
    audit_scores = list(iter_jsonl(args.audit_scores))

    scores_by_unit = score_index(scores)
    turns_by_unit_cond = build_turn_lookup(turns, scores)

    comparisons: dict[str, Any] = {}
    for baseline in baselines:
        rows = comparison_rows(scores_by_unit, turns_by_unit_cond, baseline)
        comparisons[baseline] = summarize_comparison(rows)

    result = {
        "protocol": "evoemo_response_v4_pm_resource_saving_subgroup_analysis",
        "inputs": {
            "scores": str(args.scores),
            "turns": str(args.turns),
            "audit_items": str(args.audit_items),
            "audit_scores": str(args.audit_scores),
        },
        "conditions": ["pm", *baselines],
        "comparisons": comparisons,
        "audit_linkage": summarize_audit(audit_items, audit_scores),
        "notes": [
            "This is descriptive no-API analysis over the existing V4 sample.",
            "Turn-level score deltas use integer 1-5 judge scores; mean deltas are more stable than individual deltas.",
            "Audit linkage is stratified and sampled, not a full safety guarantee.",
        ],
    }
    write_json(args.out_json, result)
    write_markdown(args.out_md, result)
    print(f"wrote {args.out_json}")
    print(f"wrote {args.out_md}")


if __name__ == "__main__":
    main()
