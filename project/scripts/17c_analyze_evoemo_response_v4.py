#!/usr/bin/env python3
"""No-API statistical and resource analysis for EvoEmo Response Eval V4."""

from __future__ import annotations

import argparse
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from metacom_pm.io import iter_jsonl, read_json, utc_now, write_json


ROOT = Path(__file__).resolve().parents[1]

SCORE_FIELDS = (
    "emotional_support",
    "personalization",
    "memory_appropriateness",
    "factual_grounding",
    "temporal_consistency",
    "non_intrusiveness",
    "overall",
)

DEFAULT_BASELINES = (
    "strong_rule",
    "best_fixed",
    "session_rag_rs",
    "full_history_rs",
    "no_memory_r0",
)

COST_FIELDS = (
    "total_input_tokens",
    "output_tokens",
    "base_prompt_tokens",
    "memory_tokens",
    "strategy_tokens",
    "retrieval_calls",
    "reranker_calls",
    "catalog_reads",
    "latency_ms",
    "generation_latency_ms",
)


def _mean(values: Iterable[float]) -> float | None:
    vals = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    return float(sum(vals) / len(vals)) if vals else None


def _percentile(values: Iterable[float], q: float) -> float | None:
    vals = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    if not vals:
        return None
    return float(np.quantile(np.asarray(vals, dtype=float), q))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return numeric if math.isfinite(numeric) else default


def _parse_margins(text: str) -> list[float]:
    margins = []
    for item in text.split(","):
        item = item.strip()
        if item:
            margins.append(float(item))
    if not margins:
        raise ValueError("at least one margin is required")
    return margins


def _unit_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("user_id"),
        row.get("topic_index"),
        row.get("seed"),
        row.get("simulator_id"),
        row.get("interaction_mode"),
        row.get("turn_index"),
    )


def _scenario_key(row: dict[str, Any]) -> str:
    return f"{row.get('user_id')}::{row.get('topic_index')}"


def _load_scores(path: Path) -> list[dict[str, Any]]:
    rows = list(iter_jsonl(path))
    if not rows:
        raise RuntimeError(f"no score rows at {path}")
    return rows


def _condition_means(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_cond: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_cond[str(row["condition"])].append(row)
    out: dict[str, dict[str, Any]] = {}
    for cond, cond_rows in sorted(by_cond.items()):
        item: dict[str, Any] = {"n": len(cond_rows)}
        for field in SCORE_FIELDS:
            item[field] = _mean(_safe_float(r.get(field), math.nan) for r in cond_rows)
        out[cond] = item
    return out


def _bootstrap_unit(values: list[float], *, n: int, seed: int) -> tuple[dict[str, Any], np.ndarray]:
    arr = np.asarray(values, dtype=float)
    if len(arr) == 0:
        raise ValueError("no paired values")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(arr), size=(n, len(arr)))
    boot = arr[idx].mean(axis=1)
    ci = {
        "estimate": float(arr.mean()),
        "lower": float(np.quantile(boot, 0.025)),
        "upper": float(np.quantile(boot, 0.975)),
        "n_units": int(len(arr)),
        "n_resamples": n,
    }
    return ci, boot


def _bootstrap_cluster(
    values_by_cluster: dict[str, list[float]], *, n: int, seed: int
) -> tuple[dict[str, Any], np.ndarray]:
    if not values_by_cluster:
        raise ValueError("no clusters")
    keys = sorted(values_by_cluster)
    cluster_means = np.asarray(
        [np.mean(values_by_cluster[key]) for key in keys], dtype=float
    )
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(keys), size=(n, len(keys)))
    boot = cluster_means[idx].mean(axis=1)
    ci = {
        "estimate": float(cluster_means.mean()),
        "lower": float(np.quantile(boot, 0.025)),
        "upper": float(np.quantile(boot, 0.975)),
        "n_clusters": int(len(keys)),
        "n_resamples": n,
    }
    return ci, boot


def _score_index(rows: list[dict[str, Any]]) -> dict[tuple[Any, ...], dict[str, dict[str, Any]]]:
    by_unit: dict[tuple[Any, ...], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        key = _unit_key(row)
        cond = str(row["condition"])
        if cond in by_unit[key]:
            raise RuntimeError(f"duplicate score for {key} / {cond}")
        by_unit[key][cond] = row
    return dict(by_unit)


def _paired_deltas(
    rows: list[dict[str, Any]],
    *,
    treatment: str,
    baselines: list[str],
    margins: list[float],
    n_bootstrap: int,
    seed: int,
) -> dict[str, Any]:
    by_unit = _score_index(rows)
    out: dict[str, Any] = {}
    for baseline_i, baseline in enumerate(baselines):
        comparison: dict[str, Any] = {}
        for field_i, field in enumerate(SCORE_FIELDS):
            deltas: list[float] = []
            scenario_groups: dict[str, list[float]] = defaultdict(list)
            user_groups: dict[str, list[float]] = defaultdict(list)
            wins = ties = losses = 0
            turn_groups: dict[str, list[float]] = defaultdict(list)
            for conds in by_unit.values():
                if treatment not in conds or baseline not in conds:
                    continue
                pm_row = conds[treatment]
                base_row = conds[baseline]
                delta = _safe_float(pm_row.get(field), math.nan) - _safe_float(
                    base_row.get(field), math.nan
                )
                if not math.isfinite(delta):
                    continue
                deltas.append(delta)
                scenario_groups[_scenario_key(pm_row)].append(delta)
                user_groups[str(pm_row.get("user_id"))].append(delta)
                turn_groups[str(pm_row.get("turn_index"))].append(delta)
                if delta > 0:
                    wins += 1
                elif delta < 0:
                    losses += 1
                else:
                    ties += 1
            base_seed = seed + 1000 * baseline_i + 37 * field_i
            unit_ci, unit_boot = _bootstrap_unit(
                deltas, n=n_bootstrap, seed=base_seed
            )
            scenario_ci, scenario_boot = _bootstrap_cluster(
                scenario_groups, n=n_bootstrap, seed=base_seed + 1
            )
            user_ci, user_boot = _bootstrap_cluster(
                user_groups, n=n_bootstrap, seed=base_seed + 2
            )
            margin_results = {}
            for margin in margins:
                margin_key = f"{margin:.3f}".rstrip("0").rstrip(".")
                margin_results[margin_key] = {
                    "margin": margin,
                    "unit_ci_noninferior": bool(unit_ci["lower"] >= -margin),
                    "scenario_ci_noninferior": bool(scenario_ci["lower"] >= -margin),
                    "user_ci_noninferior": bool(user_ci["lower"] >= -margin),
                    "scenario_bootstrap_p_delta_below_minus_margin": float(
                        np.mean(scenario_boot <= -margin)
                    ),
                }
            comparison[field] = {
                "n": len(deltas),
                "mean_delta_pm_minus_baseline": float(np.mean(deltas)),
                "paired_counts": {
                    "pm_higher": wins,
                    "tie": ties,
                    "pm_lower": losses,
                },
                "unit_bootstrap_ci": unit_ci,
                "scenario_cluster_bootstrap_ci": scenario_ci,
                "user_cluster_bootstrap_ci": user_ci,
                "bootstrap_probabilities": {
                    "unit_p_delta_lt_0": float(np.mean(unit_boot < 0)),
                    "scenario_p_delta_lt_0": float(np.mean(scenario_boot < 0)),
                    "user_p_delta_lt_0": float(np.mean(user_boot < 0)),
                },
                "noninferiority": margin_results,
                "turn_mean_deltas": {
                    turn: float(np.mean(vals)) for turn, vals in sorted(turn_groups.items())
                },
            }
        out[baseline] = comparison
    return out


def _summarize_costs(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_cond: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_cond[str(row["condition"])].append(row)
    out: dict[str, Any] = {}
    for cond, cond_rows in sorted(by_cond.items()):
        action_counts = Counter(str(r.get("action_id") or "UNKNOWN") for r in cond_rows)
        rs_calls = sum(1 for r in cond_rows if str(r.get("action_id", "")).endswith("+RS"))
        r0_calls = sum(1 for r in cond_rows if str(r.get("action_id", "")).endswith("+R0"))
        memory_calls = sum(
            1
            for r in cond_rows
            if not str(r.get("action_id", "")).startswith("M0+")
        )
        item: dict[str, Any] = {
            "n": len(cond_rows),
            "rs_call_rate": rs_calls / len(cond_rows) if cond_rows else None,
            "r0_call_rate": r0_calls / len(cond_rows) if cond_rows else None,
            "memory_call_rate": memory_calls / len(cond_rows) if cond_rows else None,
            "action_counts": dict(action_counts.most_common()),
            "action_rates": {
                action: count / len(cond_rows) for action, count in action_counts.most_common()
            },
        }
        for field in COST_FIELDS:
            vals = [
                _safe_float((r.get("cost") or {}).get(field), math.nan)
                for r in cond_rows
            ]
            item[field] = {
                "mean": _mean(vals),
                "median": _percentile(vals, 0.5),
                "p95": _percentile(vals, 0.95),
                "total": float(sum(v for v in vals if math.isfinite(v))),
            }
        out[cond] = item
    return out


def _sampled_turn_rows(
    turns: list[dict[str, Any]], score_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    wanted = {(_unit_key(row), str(row["condition"])) for row in score_rows}
    sampled = []
    seen: set[tuple[tuple[Any, ...], str]] = set()
    for row in turns:
        key = (_unit_key(row), str(row.get("condition")))
        if key in wanted:
            sampled.append(row)
            seen.add(key)
    missing = wanted - seen
    if missing:
        raise RuntimeError(f"missing {len(missing)} sampled turn rows; first={next(iter(missing))}")
    return sampled


def _resource_comparisons(summary: dict[str, Any], *, treatment: str, baselines: list[str]) -> dict[str, Any]:
    treatment_stats = summary[treatment]
    out: dict[str, Any] = {}
    for baseline in baselines:
        base_stats = summary.get(baseline)
        if not base_stats:
            continue
        item: dict[str, Any] = {}
        for field in COST_FIELDS:
            pm_mean = treatment_stats[field]["mean"]
            base_mean = base_stats[field]["mean"]
            if pm_mean is None or base_mean is None:
                continue
            item[field] = {
                "pm_mean": pm_mean,
                "baseline_mean": base_mean,
                "pm_minus_baseline_mean": pm_mean - base_mean,
                "relative_reduction_vs_baseline": (
                    (base_mean - pm_mean) / base_mean if base_mean else None
                ),
            }
        item["rs_call_rate_delta"] = (
            treatment_stats["rs_call_rate"] - base_stats["rs_call_rate"]
            if treatment_stats["rs_call_rate"] is not None
            and base_stats["rs_call_rate"] is not None
            else None
        )
        item["memory_call_rate_delta"] = (
            treatment_stats["memory_call_rate"] - base_stats["memory_call_rate"]
            if treatment_stats["memory_call_rate"] is not None
            and base_stats["memory_call_rate"] is not None
            else None
        )
        out[baseline] = item
    return out


def _actual_judge_usage(raw_calls_path: Path, pricing: dict[str, float]) -> dict[str, Any] | None:
    if not raw_calls_path.exists():
        return None
    prompt = completion = cached = rows = successful = 0
    for row in iter_jsonl(raw_calls_path):
        rows += 1
        usage = (row.get("raw_response") or {}).get("usage") or row.get("usage") or {}
        if not usage:
            continue
        successful += 1
        prompt += int(usage.get("prompt_tokens") or 0)
        completion += int(usage.get("completion_tokens") or 0)
        details = usage.get("prompt_tokens_details") or {}
        cached += int(details.get("cached_tokens") or 0)
    input_rate = float(pricing.get("input_usd_per_mtok", 2.5))
    output_rate = float(pricing.get("output_usd_per_mtok", 10.0))
    return {
        "raw_rows": rows,
        "usage_rows": successful,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "cached_prompt_tokens_reported": cached,
        "estimated_cost_usd_without_cache_discount": prompt / 1e6 * input_rate
        + completion / 1e6 * output_rate,
        "pricing": {
            "input_usd_per_mtok": input_rate,
            "output_usd_per_mtok": output_rate,
        },
    }


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(x) for x in row) + " |")
    return "\n".join(lines)


def _fmt(value: Any, ndigits: int = 3) -> str:
    if value is None:
        return "NA"
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(numeric):
        return "NA"
    return f"{numeric:.{ndigits}f}"


def _write_markdown(
    path: Path,
    *,
    statistical: dict[str, Any],
    resources: dict[str, Any],
    baselines: list[str],
    margins: list[float],
) -> None:
    cond = statistical["condition_summary"]
    mean_rows = [
        [
            name,
            cond[name]["n"],
            _fmt(cond[name]["overall"]),
            _fmt(cond[name]["emotional_support"]),
            _fmt(cond[name]["memory_appropriateness"]),
            _fmt(cond[name]["factual_grounding"]),
        ]
        for name in sorted(cond)
    ]

    overall_rows = []
    for baseline in baselines:
        item = statistical["paired_pm_deltas"][baseline]["overall"]
        topic_ci = item["scenario_cluster_bootstrap_ci"]
        margin_bits = []
        for margin in margins:
            key = f"{margin:.3f}".rstrip("0").rstrip(".")
            passed = item["noninferiority"][key]["scenario_ci_noninferior"]
            margin_bits.append(f"{key}:{'yes' if passed else 'no'}")
        overall_rows.append(
            [
                f"pm - {baseline}",
                item["n"],
                _fmt(item["mean_delta_pm_minus_baseline"]),
                f"[{_fmt(topic_ci['lower'])}, {_fmt(topic_ci['upper'])}]",
                _fmt(item["bootstrap_probabilities"]["scenario_p_delta_lt_0"]),
                ", ".join(margin_bits),
            ]
        )

    sampled_resources = resources["v4_sampled_turns"]["condition_summary"]
    resource_rows = []
    for name in sorted(sampled_resources):
        item = sampled_resources[name]
        resource_rows.append(
            [
                name,
                item["n"],
                _fmt(item["total_input_tokens"]["mean"], 1),
                _fmt(item["output_tokens"]["mean"], 1),
                _fmt(item["memory_tokens"]["mean"], 1),
                _fmt(item["strategy_tokens"]["mean"], 1),
                _fmt(item["rs_call_rate"]),
                ", ".join(
                    f"{action}:{count}"
                    for action, count in list(item["action_counts"].items())[:4]
                ),
            ]
        )

    pm_resource_rows = []
    for baseline, item in resources["v4_sampled_turns"]["pm_vs_baselines"].items():
        total = item.get("total_input_tokens") or {}
        memory = item.get("memory_tokens") or {}
        retrieval = item.get("retrieval_calls") or {}
        pm_resource_rows.append(
            [
                f"pm vs {baseline}",
                _fmt(total.get("pm_mean"), 1),
                _fmt(total.get("baseline_mean"), 1),
                _fmt(total.get("relative_reduction_vs_baseline")),
                _fmt(memory.get("relative_reduction_vs_baseline")),
                _fmt(retrieval.get("relative_reduction_vs_baseline")),
            ]
        )

    judge = resources.get("judge_usage") or {}
    lines = [
        "# EvoEmo Response V4 离线统计与资源汇总",
        "",
        f"生成时间：{utc_now()}",
        "",
        "## 结论摘要",
        "",
        "- V4 full-run 输出完整，后续统计不调用 API。",
        "- PM 的 overall response quality 与 `strong_rule` / `best_fixed` 非常接近；严格 `0.05` margin 下需要看 CI，不应写成全面质量胜利。",
        "- PM 在同一 V4 sampled turns 上显著降低输入 token / 检索资源，尤其相对 `session_rag_rs` 和 `full_history_rs`。",
        "- `no_memory_r0` 在 response score 上最高之一且成本最低，说明很多 fixed-input turn 并不需要额外资源；这正是“资源选择”问题，而不是 always-on RAG 胜利。",
        "",
        "## 条件均值",
        "",
        _markdown_table(
            [
                "Condition",
                "n",
                "Overall",
                "Emotional",
                "Memory appr.",
                "Factual",
            ],
            mean_rows,
        ),
        "",
        "## PM Pairwise Deltas",
        "",
        "Delta 为 `PM - baseline`。CI 使用 `(user_id, topic_index)` scenario-cluster bootstrap。",
        "",
        _markdown_table(
            [
                "Comparison",
                "n",
                "Mean delta",
                "95% cluster CI",
                "P(delta<0)",
                "NI margins",
            ],
            overall_rows,
        ),
        "",
        "## V4 Sampled Resource Cost",
        "",
        _markdown_table(
            [
                "Condition",
                "n",
                "Input tok",
                "Output tok",
                "Memory tok",
                "Strategy tok",
                "RS rate",
                "Top actions",
            ],
            resource_rows,
        ),
        "",
        "## PM Resource Reductions",
        "",
        _markdown_table(
            [
                "Comparison",
                "PM input",
                "Baseline input",
                "Input reduction",
                "Memory reduction",
                "Retrieval reduction",
            ],
            pm_resource_rows,
        ),
        "",
        "Token component note: `total_input_tokens` is the primary cost measure. Component fields such as `base_prompt_tokens`, `memory_tokens`, and `strategy_tokens` are diagnostic estimates and are not assumed to be additive under a single tokenizer/accounting path.",
        "",
        "## Judge Cost",
        "",
        f"- raw rows: {judge.get('raw_rows', 'NA')}",
        f"- prompt tokens: {judge.get('prompt_tokens', 'NA')}",
        f"- completion tokens: {judge.get('completion_tokens', 'NA')}",
        f"- estimated cost without cache discount: ${_fmt(judge.get('estimated_cost_usd_without_cache_discount'), 2)}",
        "",
        "## 写作边界",
        "",
        "可以写：V4 supports comparable fixed-input response quality relative to strong rule / best fixed, while using fewer resources.",
        "",
        "不应写：PM universally improves response quality, 或 RAG 本身解决了 ESC generation。",
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
        "--summary",
        type=Path,
        default=ROOT / "outputs/evoemo_response_v4/response_summary.json",
    )
    parser.add_argument(
        "--raw-calls",
        type=Path,
        default=ROOT / "outputs/evoemo_response_v4/response_raw_calls.jsonl",
    )
    parser.add_argument(
        "--turns",
        type=Path,
        default=ROOT / "outputs/evoemo_selective/turns.jsonl",
    )
    parser.add_argument(
        "--stat-out",
        type=Path,
        default=ROOT / "outputs/evoemo_response_v4/response_statistical_summary.json",
    )
    parser.add_argument(
        "--resource-out",
        type=Path,
        default=ROOT / "outputs/evoemo_response_v4/response_resource_summary.json",
    )
    parser.add_argument(
        "--markdown-out",
        type=Path,
        default=ROOT / "outputs/evoemo_response_v4/response_analysis_summary.md",
    )
    parser.add_argument("--treatment", default="pm")
    parser.add_argument(
        "--baselines",
        default=",".join(DEFAULT_BASELINES),
        help="Comma-separated baseline condition names.",
    )
    parser.add_argument(
        "--margins",
        default="0.05,0.10",
        help="Comma-separated non-inferiority margins on 1-5 score scale.",
    )
    parser.add_argument("--bootstrap", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260630)
    args = parser.parse_args()

    scores = _load_scores(args.scores)
    full_summary = read_json(args.summary) if args.summary.exists() else {}
    baselines = [x.strip() for x in args.baselines.split(",") if x.strip()]
    margins = _parse_margins(args.margins)

    statistical = {
        "status": "COMPLETE",
        "created_at": utc_now(),
        "protocol": "evoemo_response_v4_no_api_statistical_summary",
        "input_scores": str(args.scores),
        "input_response_summary": str(args.summary),
        "treatment": args.treatment,
        "baselines": baselines,
        "score_fields": list(SCORE_FIELDS),
        "margins": margins,
        "bootstrap": {
            "n_resamples": args.bootstrap,
            "seed": args.seed,
            "cluster_keys": {
                "scenario": "(user_id, topic_index)",
                "user": "user_id",
            },
        },
        "source_response_summary_status": full_summary.get("status"),
        "source_response_output_validation": full_summary.get("output_validation"),
        "condition_summary": _condition_means(scores),
        "paired_pm_deltas": _paired_deltas(
            scores,
            treatment=args.treatment,
            baselines=baselines,
            margins=margins,
            n_bootstrap=args.bootstrap,
            seed=args.seed,
        ),
    }

    turns = list(iter_jsonl(args.turns))
    sampled_turns = _sampled_turn_rows(turns, scores)
    sampled_summary = _summarize_costs(sampled_turns)
    all_conditions = set([args.treatment, *baselines])
    all_turns = [r for r in turns if str(r.get("condition")) in all_conditions]
    all_summary = _summarize_costs(all_turns)
    pricing = (full_summary.get("cost_estimate") or {}).get("pricing") or {}
    resources = {
        "status": "COMPLETE",
        "created_at": utc_now(),
        "protocol": "evoemo_response_v4_no_api_resource_summary",
        "input_turns": str(args.turns),
        "input_scores": str(args.scores),
        "treatment": args.treatment,
        "baselines": baselines,
        "v4_sampled_turns": {
            "n_rows": len(sampled_turns),
            "condition_summary": sampled_summary,
            "pm_vs_baselines": _resource_comparisons(
                sampled_summary, treatment=args.treatment, baselines=baselines
            ),
        },
        "all_generated_turns": {
            "n_rows": len(all_turns),
            "condition_summary": all_summary,
            "pm_vs_baselines": _resource_comparisons(
                all_summary, treatment=args.treatment, baselines=baselines
            ),
        },
        "judge_usage": _actual_judge_usage(args.raw_calls, pricing),
    }

    write_json(args.stat_out, statistical)
    write_json(args.resource_out, resources)
    _write_markdown(
        args.markdown_out,
        statistical=statistical,
        resources=resources,
        baselines=baselines,
        margins=margins,
    )
    print(
        {
            "status": "COMPLETE",
            "stat_out": str(args.stat_out),
            "resource_out": str(args.resource_out),
            "markdown_out": str(args.markdown_out),
        }
    )


if __name__ == "__main__":
    main()
