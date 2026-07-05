#!/usr/bin/env python3
"""Summarize observed EvoEmo generation latency from existing turn logs.

This is a no-API diagnostic. It uses the latency fields written during
EvoEmo selective generation and reports them as observed deployment traces,
not as a randomized latency benchmark.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]

DEFAULT_TURNS = ROOT / "outputs" / "evoemo_selective" / "turns.jsonl"
DEFAULT_OUT_DIR = ROOT / "outputs" / "evoemo_response_v4"

LABELS = {
    "no_memory_r0": "Context Only",
    "no_memory_rs": "Strategy Only",
    "pm": "Learned Selector",
    "strong_rule": "Rule Selector",
    "best_fixed": "Fixed All Structured",
    "all_structured_rs": "All Structured",
    "session_rag_rs": "Session Retrieval",
    "full_history_rs": "Full History",
}

PAPER_CONDITIONS = [
    "no_memory_r0",
    "pm",
    "strong_rule",
    "best_fixed",
    "session_rag_rs",
    "full_history_rs",
]

FIELD_SPECS = [
    ("latency_ms", "latency_ms"),
    ("generation_latency_ms", "generation_latency_ms"),
    ("retrieval_latency_ms", "retrieval_latency_ms"),
    ("pm_inference_ms", "pm_inference_ms"),
    ("pre_evidence_compute_ms", "pre_evidence_compute_ms"),
    ("total_input_tokens", "total_input_tokens"),
    ("output_tokens", "output_tokens"),
    ("retrieval_calls", "retrieval_calls"),
]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _cost(row: dict[str, Any], key: str) -> float | None:
    cost = row.get("cost") or {}
    if key in cost and cost[key] is not None:
        return float(cost[key])
    if key in row and row[key] is not None:
        return float(row[key])
    return None


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * pct
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    frac = pos - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def _summarize(values: Iterable[float]) -> dict[str, float | int | None]:
    vals = [float(v) for v in values if v is not None]
    if not vals:
        return {"n": 0, "mean": None, "median": None, "p95": None, "min": None, "max": None}
    return {
        "n": len(vals),
        "mean": statistics.fmean(vals),
        "median": statistics.median(vals),
        "p95": _percentile(vals, 0.95),
        "min": min(vals),
        "max": max(vals),
    }


def _round_nested(value: Any, digits: int = 3) -> Any:
    if isinstance(value, float):
        return round(value, digits)
    if isinstance(value, dict):
        return {k: _round_nested(v, digits) for k, v in value.items()}
    if isinstance(value, list):
        return [_round_nested(v, digits) for v in value]
    return value


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_condition: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_condition[row["condition"]].append(row)

    conditions: dict[str, Any] = {}
    for condition in sorted(by_condition):
        condition_rows = by_condition[condition]
        metrics = {}
        for metric_name, field in FIELD_SPECS:
            metrics[metric_name] = _summarize(_cost(row, field) for row in condition_rows)
        conditions[condition] = {
            "label": LABELS.get(condition, condition),
            "n": len(condition_rows),
            "metrics": metrics,
        }

    return {
        "status": "DIAGNOSTIC",
        "source": str(DEFAULT_TURNS.relative_to(ROOT)),
        "row_count": len(rows),
        "condition_count": len(conditions),
        "interpretation_boundary": (
            "Observed online generation latency from existing logs. This excludes "
            "training and judge calls and should be treated as a deployment-oriented "
            "diagnostic rather than a randomized confirmatory latency benchmark."
        ),
        "primary_resource_metric": (
            "Mean input tokens remains the primary resource-cost metric; latency is "
            "reported as an additional operational diagnostic because network and "
            "provider scheduling noise were not experimentally controlled."
        ),
        "paper_conditions": PAPER_CONDITIONS,
        "condition_summary": conditions,
    }


def _row_for_csv(condition: str, entry: dict[str, Any]) -> dict[str, Any]:
    metrics = entry["metrics"]
    return {
        "condition": condition,
        "label": entry["label"],
        "n": entry["n"],
        "latency_mean_ms": metrics["latency_ms"]["mean"],
        "latency_median_ms": metrics["latency_ms"]["median"],
        "latency_p95_ms": metrics["latency_ms"]["p95"],
        "generation_mean_ms": metrics["generation_latency_ms"]["mean"],
        "retrieval_mean_ms": metrics["retrieval_latency_ms"]["mean"],
        "pm_inference_mean_ms": metrics["pm_inference_ms"]["mean"],
        "pre_evidence_mean_ms": metrics["pre_evidence_compute_ms"]["mean"],
        "mean_input_tokens": metrics["total_input_tokens"]["mean"],
        "mean_output_tokens": metrics["output_tokens"]["mean"],
        "mean_retrieval_calls": metrics["retrieval_calls"]["mean"],
    }


def write_csv(summary: dict[str, Any], path: Path) -> None:
    rows = [
        _row_for_csv(condition, summary["condition_summary"][condition])
        for condition in summary["condition_summary"]
    ]
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: round(v, 3) if isinstance(v, float) else v for k, v in row.items()})


def _markdown_table(summary: dict[str, Any], conditions: list[str]) -> str:
    lines = [
        "| Condition | n | Mean latency ms | Median latency ms | P95 latency ms | Mean input tokens | Mean retrieval ms | Mean generation ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for condition in conditions:
        if condition not in summary["condition_summary"]:
            continue
        entry = summary["condition_summary"][condition]
        metrics = entry["metrics"]
        lines.append(
            "| {label} | {n} | {lat_mean:.1f} | {lat_med:.1f} | {lat_p95:.1f} | "
            "{tok_mean:.1f} | {ret_mean:.1f} | {gen_mean:.1f} |".format(
                label=entry["label"],
                n=entry["n"],
                lat_mean=metrics["latency_ms"]["mean"],
                lat_med=metrics["latency_ms"]["median"],
                lat_p95=metrics["latency_ms"]["p95"],
                tok_mean=metrics["total_input_tokens"]["mean"],
                ret_mean=metrics["retrieval_latency_ms"]["mean"],
                gen_mean=metrics["generation_latency_ms"]["mean"],
            )
        )
    return "\n".join(lines)


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    md = f"""# EvoEmo Observed Online Latency Diagnostic

Source: `{summary['source']}`

Status: `{summary['status']}`

This file summarizes latency fields recorded during EvoEmo selective generation.
The values describe observed online traces from user turn to generated response.
They exclude training, judging, and post hoc statistical analysis. Because the
generation run was not designed as a randomized latency benchmark, these numbers
should be reported as deployment diagnostics, while input tokens remain the
primary resource cost metric.

## Paper Conditions

{_markdown_table(summary, PAPER_CONDITIONS)}

## All Conditions

{_markdown_table(summary, list(summary['condition_summary'].keys()))}

## Interpretation

- Learned Selector is slower than Context Only, as expected, because it invokes memory and strategy resources.
- Learned Selector has lower observed mean latency than Rule Selector, Session Retrieval, and Full History in this run.
- Policy inference overhead is small compared with retrieval and generation latency.
- Latency is not perfectly proportional to token count; retrieval path, provider scheduling, and response generation variance also matter.
- Use this as an operational diagnostic, not as confirmatory evidence of universal serving latency.
"""
    path.write_text(md, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--turns", type=Path, default=DEFAULT_TURNS)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    rows = _read_jsonl(args.turns)
    summary = build_summary(rows)
    summary["source"] = str(args.turns.relative_to(ROOT) if args.turns.is_relative_to(ROOT) else args.turns)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / "observed_latency_diagnostic.json"
    csv_path = args.out_dir / "observed_latency_by_condition.csv"
    md_path = args.out_dir / "observed_latency_diagnostic.md"

    json_path.write_text(json.dumps(_round_nested(summary), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(summary, csv_path)
    write_markdown(summary, md_path)

    print(json.dumps({
        "status": "COMPLETE",
        "rows": len(rows),
        "outputs": {
            "json": str(json_path),
            "csv": str(csv_path),
            "markdown": str(md_path),
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
