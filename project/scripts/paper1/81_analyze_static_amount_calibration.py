#!/usr/bin/env python3
"""Recover generations and official scores, audit completeness, and — only under
an explicit researcher authorization — produce fold-external k recommendations.

Recovery and completeness auditing are always available and never write a score
that was not actually observed. A missing generation, an incomplete generation
or an official parse failure removes that target from *every* k of the affected
comparison and is disclosed; it is never filled with zero.

The recommendation step follows the frozen rule: weighted paired means on the
official task primary, owner-cluster bootstrap (2,000 replicates, seed 0),
one-SE admissible set, then fewest Generator input tokens, then smaller k, with
k=0 allowed. Its output is a recommendation under the official primary metric,
not a frozen k*.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import iter_jsonl, read_json, sha256_file, utc_now, write_json, write_jsonl
from metacom_pm.paper1.amount_calibration import recommend_amount
from metacom_pm.paper1.evaluation.static_official_scoring import PRIMARY_METRIC
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config

AUTHORITY = PROJECT / "data/paper1_authority/paper1_static_amount_calibration_execution_20260917_v1.json"
CONFIG = PROJECT / "configs/paper1_public_only.yaml"
PROTOCOL = "paper1-static-amount-calibration-analysis-v1"
GRID = (0, 1, 2, 3, 4)
HEADS = ("MP", "ME", "MS")
TASKS = ("qa", "summary")


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(path)


def collect(package: Path, generations: Path, scores: Path) -> tuple[list[dict], dict]:
    """Join the analytical design with whatever was actually generated and scored.

    The design has one row per (target, head, k); the shared true-OFF response is
    reused across heads, which is why 148 OFF generations back 444 analytical
    k=0 rows without ever being generated more than once.
    """
    summary = read_json(package / "preparation_summary.json")
    for name, digest in summary["package_artifacts"].items():
        if sha256_file(package / name) != digest:
            raise RuntimeError(f"calibration package file changed since preparation: {name}")
    design = list(iter_jsonl(package / "analytical_design.jsonl"))
    requests = {r["request_id"]: r for r in iter_jsonl(package / "generator_requests.jsonl")}

    generated: dict[str, dict] = {}
    if (generations / "responses").exists():
        for path in sorted((generations / "responses").glob("*.json")):
            record = read_json(path)
            request = requests.get(record["request_id"])
            if request is None or request["request_sha256"] != record["request_sha256"]:
                raise RuntimeError(f"generation does not belong to this package: {path.name}")
            generated[record["request_id"]] = record

    scored: dict[str, dict] = {}
    if (scores / "scores").exists():
        for path in sorted((scores / "scores").glob("*.json")):
            record = read_json(path)
            if record["request_id"] not in requests:
                raise RuntimeError(f"official score does not belong to this package: {path.name}")
            scored[record["request_id"]] = record

    rows, gaps = [], Counter()
    for row in design:
        request_id = row["request_id"]
        generation = generated.get(request_id)
        score = scored.get(request_id)
        quality, reason = None, None
        if generation is None:
            reason = "not_generated"
        elif generation.get("natural_end") is not True:
            reason = "generation_" + str(generation.get("finish_reason"))
        elif score is None:
            reason = "not_officially_scored"
        elif score["status"] != "SCORED" or score.get("official") is None:
            reason = "official_" + score["status"].lower()
        else:
            quality = score["official"]["quality"]
        if reason:
            gaps[reason] += 1
        rows.append({**row, "natural_end": generation.get("natural_end") if generation else None,
                     "finish_reason": generation.get("finish_reason") if generation else None,
                     "output_tokens": generation.get("output_tokens") if generation else None,
                     "quality": quality, "primary_metric": PRIMARY_METRIC[row["task"]],
                     "missing_reason": reason})
    coverage = {
        "analytical_rows": len(rows),
        "distinct_generation_requests": len(requests),
        "generations_present": len(generated),
        "generations_natural_end": sum(1 for g in generated.values() if g.get("natural_end")),
        "generations_incomplete": dict(Counter(
            g["finish_reason"] for g in generated.values() if not g.get("natural_end"))),
        "official_scores_present": len(scored),
        "official_scores_parsed": sum(1 for s in scored.values() if s.get("official")),
        "rows_with_quality": sum(1 for r in rows if r["quality"] is not None),
        "row_gaps_by_reason": dict(gaps),
        "missing_is_never_zero": True,
    }
    return rows, coverage


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path,
                        default=PROJECT / "outputs/paper1_calibration/static_sample_20260917_v1")
    parser.add_argument("--generations", type=Path,
                        default=PROJECT / "outputs/paper1_calibration/static_generation_20260917_v1")
    parser.add_argument("--scores", type=Path,
                        default=PROJECT / "outputs/paper1_calibration/static_official_scores_20260917_v1")
    parser.add_argument("--out", type=Path,
                        default=PROJECT / "outputs/paper1_calibration/static_amount_analysis_20260917_v1")
    parser.add_argument("--recommend", action="store_true",
                        help="produce fold-external k recommendations; requires explicit authorization")
    parser.add_argument("--bootstrap", type=int, default=2000)
    args = parser.parse_args()

    assert_pre_outcome_locked(load_public_only_config(CONFIG))
    authority = read_json(AUTHORITY)
    rows, coverage = collect(args.package, args.generations, args.scores)
    args.out.mkdir(parents=True, exist_ok=True)
    write_jsonl(args.out / "analysis_rows.jsonl", rows)

    report = {"protocol": PROTOCOL, "generated_at": utc_now(), "coverage": coverage,
              "authority_sha256": sha256_file(AUTHORITY),
              "recommendation_authorized": bool(
                  authority.get("rq2_memory_amount_calibration_recommendation_authorized")),
              "k_star_frozen": False, "formal_outcomes": 0, "PM_training_runs": 0,
              "scope_note": ("QA and Summary static amounts only. RS 52 calibration cards and the DG "
                             "live per-turn seeker calibration are not part of this batch, so this is "
                             "not complete amount calibration.")}

    if not args.recommend:
        report["status"] = "RECOVERY_AND_COVERAGE_ONLY"
        atomic_json(args.out / "coverage_report.json", report)
        print(json.dumps({"status": report["status"], **coverage}, ensure_ascii=False, indent=2))
        return

    if not report["recommendation_authorized"]:
        raise RuntimeError(
            "fold-external k recommendation requires the researcher to set "
            "rq2_memory_amount_calibration_recommendation_authorized; coverage report is at "
            f"{args.out / 'coverage_report.json'}")

    recommendations, failures = [], []
    for task in TASKS:
        for head in HEADS:
            for fold in sorted({r["outer_fold"] for r in rows}):
                try:
                    result = recommend_amount(rows, task=task, head=head, held_out_fold=fold,
                                              grid=GRID, seed=0, bootstrap_replicates=args.bootstrap)
                except ValueError as exc:
                    failures.append({"task": task, "head": head, "held_out_fold": fold,
                                     "reason": str(exc)})
                    continue
                result["primary_metric"] = PRIMARY_METRIC[task]
                recommendations.append(result)
    write_jsonl(args.out / "k_recommendations.jsonl", recommendations)
    expansion = [r for r in recommendations if r["expand_once_to_6_8"]]
    report.update(
        status="RECOMMENDED_NOT_FROZEN",
        recommendation_cells=len(recommendations),
        cells_without_a_recommendation=failures,
        prespecified_6_8_expansion_triggered=[{k: r[k] for k in ["task", "head", "held_out_fold"]}
                                              for r in expansion],
        summary_requires_official_subscore_and_full_history_review=True,
        selection_rule=("highest weighted mean official primary; one-SE admissible set; then fewest mean "
                        "Generator input tokens, then smaller k; k=0 allowed"),
        cluster_unit="owner", bootstrap_replicates=args.bootstrap, bootstrap_seed=0)
    atomic_json(args.out / "recommendation_report.json", report)
    print(json.dumps({"status": report["status"], "cells": len(recommendations),
                      "failed_cells": len(failures), **coverage}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
