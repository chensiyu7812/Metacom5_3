#!/usr/bin/env python3
"""Aggregate all six completed formal shards and run the frozen OOF heads."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_v5_3_public_learnability_analysis import (  # noqa: E402
    COMPONENTS,
    formal_oof_head_analysis,
)
from metacom_pm.v1_5_v5_3_semantic_ms_retrieval import (  # noqa: E402
    BgeM3Encoder,
    DEFAULT_BGE_M3_SNAPSHOT,
)


MANIFEST_DIR = ROOT / "outputs/pm_v1_5_v5_3_public_formal_effect_manifest_20260809"
RESULT_DIR = ROOT / "outputs/pm_v1_5_v5_3_public_formal_qf_20260809"
OUT = ROOT / "outputs/pm_v1_5_v5_3_public_formal_oof_20260809"


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _load_complete_panel() -> tuple[list[dict], dict]:
    manifest_contract = json.loads((MANIFEST_DIR / "contract.json").read_text())
    expected_identity = manifest_contract["manifest_identity"]
    rows: list[dict] = []
    reports = []
    for fold in range(1, 7):
        result_path = RESULT_DIR / "shards" / f"fold_{fold}_results.jsonl"
        report_path = RESULT_DIR / "shards" / f"fold_{fold}_report.json"
        if not result_path.exists() or not report_path.exists():
            raise RuntimeError("all six completed formal fold shards are required before OOF analysis")
        report = json.loads(report_path.read_text())
        fold_rows = _jsonl(result_path)
        if report.get("status") != "COMPLETE" or report.get("groups_completed") != 96:
            raise RuntimeError(f"formal fold {fold} is not complete")
        if len(fold_rows) != 96 or any(int(row["outer_fold"]) != fold for row in fold_rows):
            raise RuntimeError(f"formal fold {fold} row count or fold binding is invalid")
        if any(row.get("manifest_identity") != expected_identity for row in fold_rows):
            raise RuntimeError(f"formal fold {fold} manifest identity drift")
        if report.get("automatic_risk_judge_calls") != 0:
            raise RuntimeError("disqualified automatic risk judge appeared in formal results")
        rows.extend(fold_rows)
        reports.append(report)

    ids = [str(row["effect_group_id"]) for row in rows]
    checks = {
        "576_rows": len(rows) == 576,
        "576_unique_effect_groups": len(set(ids)) == 576,
        "144_per_component": Counter(row["component"] for row in rows)
        == Counter({component: 144 for component in COMPONENTS}),
        "quality_complete": all(row.get("quality_effect") is not None for row in rows),
        "function_complete": all(row.get("functional") is not None for row in rows),
        "six_complete_reports": len(reports) == 6,
        "manifest_hash_matches_report": all(
            report.get("manifest_sha256")
            == sha256_file(MANIFEST_DIR / "effect_group_manifest_private.jsonl")
            for report in reports
        ),
    }
    if not all(checks.values()):
        raise RuntimeError(f"formal completion audit failed: {checks}")
    return rows, checks


def main() -> None:
    rows, completion_checks = _load_complete_panel()
    manifest_rows = _jsonl(MANIFEST_DIR / "effect_group_manifest_private.jsonl")
    manifest_by_group = {str(row["effect_group_id"]): row for row in manifest_rows}
    if set(manifest_by_group) != {str(row["effect_group_id"]) for row in rows}:
        raise RuntimeError("formal results do not exactly cover the frozen manifest")

    encoder = BgeM3Encoder(DEFAULT_BGE_M3_SNAPSHOT)
    analysis = {}
    predictions = []
    for component in COMPONENTS:
        component_results = [row for row in rows if row["component"] == component]
        component_manifest = [manifest_by_group[row["effect_group_id"]] for row in component_results]
        texts = [
            text
            for row in component_manifest
            for text in (row["current_user_text"], row["candidate_text"])
        ]
        vectors = encoder.encode(texts)
        result = formal_oof_head_analysis(
            component=component,
            result_rows=component_results,
            manifest_by_group=manifest_by_group,
            state_vectors=vectors[0::2],
            candidate_vectors=vectors[1::2],
        )
        predictions.extend(result.pop("predictions"))
        analysis[component] = result

    all_pass = all(row["formal_head_pass"] for row in analysis.values())
    report = {
        "protocol": "pm-v1.5-v5.3-public-formal-oof-analysis-v1",
        "status": "ALL_FOUR_FORMAL_HEADS_PASS" if all_pass else "PARTIAL_OR_NO_FORMAL_HEAD_PASS_FAIL_CLOSED",
        "completion_checks": completion_checks,
        "analysis": analysis,
        "passed_heads": [key for key, value in analysis.items() if value["formal_head_pass"]],
        "failed_heads": [key for key, value in analysis.items() if not value["formal_head_pass"]],
        "policy_status": "HEAD_OOF_COMPLETE_JOINT_PROJECTION_NOT_YET_FROZEN",
        "automatic_risk_used": False,
        "api_calls_for_analysis": 0,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    write_json(OUT / "formal_oof_report.json", report)
    write_jsonl(OUT / "formal_oof_predictions_private.jsonl", predictions)
    write_json(
        OUT / "completion_audit.json",
        {
            "protocol": report["protocol"],
            "status": "PASS",
            "checks": completion_checks,
            "manifest_sha256": sha256_file(MANIFEST_DIR / "effect_group_manifest_private.jsonl"),
            "result_shard_sha256": {
                str(fold): sha256_file(RESULT_DIR / "shards" / f"fold_{fold}_results.jsonl")
                for fold in range(1, 7)
            },
            "api_calls": 0,
        },
    )
    print(
        {
            "status": report["status"],
            "passed_heads": report["passed_heads"],
            "failed_heads": report["failed_heads"],
            "relative_mse": {
                key: round(value["relative_mse"], 3) if value["relative_mse"] is not None else None
                for key, value in analysis.items()
            },
            "spearman": {key: round(value["oof_spearman"], 3) for key, value in analysis.items()},
        }
    )


if __name__ == "__main__":
    main()
