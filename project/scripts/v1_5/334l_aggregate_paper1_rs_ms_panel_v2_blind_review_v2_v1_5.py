#!/usr/bin/env python3
"""Aggregate the 101 real blind-review results (333l) against the frozen
development-gate criteria (paper1_rs_ms_panel_v2_blind_review_v2_
development_gate_v1.json). Zero-API: reads only already-collected local
results. Fails closed if live results are not yet present -- this script
cannot run meaningfully before approval and execution.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import read_json, read_jsonl, write_json  # noqa: E402
from metacom_pm.v1_5_rs_ms_panel_v2_blind_review_v2_aggregator import (  # noqa: E402
    RISK_FAMILY_FIELDS,
    cluster_function,
    cluster_interaction,
    cluster_quality,
    cluster_risk,
    decode_quality_win,
    has_critical,
    overall_verdict,
    risk_increase_severity,
)

MANIFEST_DIR = ROOT / "outputs/pm_v1_5_paper1_rs_ms_panel_v2_blind_review_manifest_v2_20260813"
LIVE_DIR = ROOT / "outputs/pm_v1_5_paper1_rs_ms_panel_v2_blind_review_v2_live_20260813"
GATE_CONTRACT = ROOT / "data/pm_v1_5_contracts/paper1_rs_ms_panel_v2_blind_review_v2_development_gate_v1.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_rs_ms_panel_v2_blind_review_v2_aggregate_20260813"


def main() -> None:
    results_path = LIVE_DIR / "results_private.jsonl"
    if not results_path.exists():
        raise RuntimeError(
            "no live results yet -- this aggregator cannot run before the 101-call round is "
            "approved and executed; see paper1_rs_ms_panel_v2_blind_review_v2_execution_phase_v1.json"
        )
    gate = read_json(GATE_CONTRACT)
    if gate["status"] != "FROZEN_BEFORE_ANY_JUDGE_CALL":
        raise RuntimeError("development gate contract is not in its frozen state")

    private_map = {row["case_id"]: row for row in read_jsonl(MANIFEST_DIR / "private_map.jsonl")}
    quality_calls = {row["pair_id"]: row for row in read_jsonl(MANIFEST_DIR / "quality_calls_private.jsonl")}
    function_calls = {}
    for row in read_jsonl(MANIFEST_DIR / "function_calls_private.jsonl"):
        key = row.get("blind_item_id") or row.get("pair_id")
        function_calls[key] = row
    results = read_jsonl(results_path)
    if len(results) != 101:
        raise RuntimeError(f"expected 101 results, found {len(results)}")

    by_review_id: dict[str, dict[str, Any]] = {}
    for row in results:
        review = row.get("validated_review")
        if review is None:
            continue
        review_id = review.get("pair_id") or review.get("item_id") or review.get("blind_item_id")
        by_review_id[review_id] = review

    def risk_scores(item_id: str | None) -> dict[str, int] | None:
        if item_id is None:
            return None
        review = by_review_id.get(item_id)
        if review is None:
            return None
        return {family: int(review[family]) for family in RISK_FAMILY_FIELDS}

    rs_quality_rows, ms_quality_rows = [], []
    rs_risk_rows, ms_risk_rows, ms_rs_combined_risk_rows = [], [], []
    rs_function_rows, ms_function_rows = [], []
    interaction_rows = []
    missing: list[str] = []

    for case_id, case in private_map.items():
        owner = case["owner_cluster"]
        baseline_scores = risk_scores(case["risk_m0r0_item_id"])
        if baseline_scores is None:
            missing.append(f"{case_id}:baseline_risk")
            continue

        if case["rs_quality_pair_id"]:
            call = quality_calls[case["rs_quality_pair_id"]]
            review = by_review_id.get(case["rs_quality_pair_id"])
            if review is None:
                missing.append(f"{case_id}:rs_quality")
            else:
                rs_quality_rows.append({
                    "owner_cluster": owner,
                    "win_loss": decode_quality_win(verdict=review["verdict"], a_arm=call["a_arm"], b_arm=call["b_arm"], treatment_arm="M0+RS"),
                })
        if case["risk_m0rs_item_id"]:
            scores = risk_scores(case["risk_m0rs_item_id"])
            if scores is None:
                missing.append(f"{case_id}:rs_risk")
            else:
                rs_risk_rows.append({
                    "owner_cluster": owner,
                    "severity": risk_increase_severity(treatment_scores=scores, baseline_scores=baseline_scores),
                    "has_critical": has_critical(scores),
                })
        if case["rs_strategy_function_id"]:
            review = by_review_id.get(case["rs_strategy_function_id"])
            if review is None:
                missing.append(f"{case_id}:rs_function")
            else:
                rs_function_rows.append({"owner_cluster": owner, "label": review["label"]})

        if case["ms_quality_pair_id"]:
            call = quality_calls[case["ms_quality_pair_id"]]
            review = by_review_id.get(case["ms_quality_pair_id"])
            if review is None:
                missing.append(f"{case_id}:ms_quality")
            else:
                ms_quality_rows.append({
                    "owner_cluster": owner,
                    "win_loss": decode_quality_win(verdict=review["verdict"], a_arm=call["a_arm"], b_arm=call["b_arm"], treatment_arm="MS+R0"),
                })
        if case["risk_msr0_item_id"]:
            scores = risk_scores(case["risk_msr0_item_id"])
            if scores is None:
                missing.append(f"{case_id}:ms_risk")
            else:
                ms_risk_rows.append({
                    "owner_cluster": owner,
                    "severity": risk_increase_severity(treatment_scores=scores, baseline_scores=baseline_scores),
                    "has_critical": has_critical(scores),
                })
        if case["ms_function_independent_id"]:
            review = by_review_id.get(case["ms_function_independent_id"])
            if review is None:
                missing.append(f"{case_id}:ms_function")
            else:
                ms_function_rows.append({"owner_cluster": owner, "label": review["label"]})

        if case["risk_msrs_item_id"]:
            scores = risk_scores(case["risk_msrs_item_id"])
            if scores is None:
                missing.append(f"{case_id}:ms_rs_combined_risk")
            else:
                ms_rs_combined_risk_rows.append({
                    "owner_cluster": owner,
                    "severity": risk_increase_severity(treatment_scores=scores, baseline_scores=baseline_scores),
                    "has_critical": has_critical(scores),
                })
        if case["ms_rs_interaction_pair_id"]:
            review = by_review_id.get(case["ms_rs_interaction_pair_id"])
            if review is None:
                missing.append(f"{case_id}:interaction")
            else:
                interaction_rows.append({
                    "owner_cluster": owner,
                    "raw_verdict": review["verdict"],
                    "ms_rs_position": case["ms_rs_interaction_ms_rs_position"],
                })

    if missing:
        raise RuntimeError(f"aggregation incomplete, missing results for: {missing}")

    rs_quality = cluster_quality(rs_quality_rows)
    ms_quality = cluster_quality(ms_quality_rows)
    rs_risk = cluster_risk(rs_risk_rows)
    ms_risk = cluster_risk(ms_risk_rows)
    rs_function = cluster_function(rs_function_rows)
    ms_function = cluster_function(ms_function_rows)
    interaction = cluster_interaction(interaction_rows)
    combined_risk = cluster_risk(ms_rs_combined_risk_rows)

    verdict = overall_verdict(
        rs_quality=rs_quality["pass"], rs_risk=rs_risk["pass"], rs_function=rs_function["pass"],
        ms_quality=ms_quality["pass"], ms_risk=ms_risk["pass"], ms_function=ms_function["pass"],
        interaction=interaction["pass"], combined_risk=combined_risk["pass"],
    )

    report = {
        "protocol": "pm-v1.5-paper1-rs-ms-panel-v2-blind-review-v2-aggregate-v1",
        "gate_contract": str(GATE_CONTRACT.relative_to(ROOT)),
        "criteria": {
            "rs_quality": rs_quality, "ms_quality": ms_quality,
            "rs_risk": rs_risk, "ms_risk": ms_risk,
            "rs_function": rs_function, "ms_function": ms_function,
            "ms_rs_interaction": interaction, "ms_rs_combined_risk": combined_risk,
        },
        "verdict": verdict,
        "scope_limitation": gate["scope_limitation"],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    write_json(OUT / "report.json", report)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
