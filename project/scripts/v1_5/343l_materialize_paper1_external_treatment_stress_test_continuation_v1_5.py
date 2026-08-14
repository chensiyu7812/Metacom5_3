#!/usr/bin/env python3
"""Freeze the exact missing-call continuation after the 42/90 429 partial run."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import canonical_json, read_json, read_jsonl, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402

ORIGINAL_PLAN = ROOT / "outputs/pm_v1_5_paper1_external_treatment_stress_test_preflight_20260813/call_plan_private.jsonl"
PARTIAL_RESULTS = ROOT / "outputs/pm_v1_5_paper1_external_treatment_stress_test_live_20260813/generator_results_private.jsonl"
PARTIAL_CLOSEOUT = ROOT / "data/pm_v1_5_contracts/paper1_external_treatment_stress_test_partial_closeout_v1.json"
CONFIG = ROOT / "configs/paper1_external_treatment_stress_test_continuation_v1.json"
RUNNER = ROOT / "scripts/v1_5/344l_run_paper1_external_treatment_stress_test_continuation_v1_5.py"
OUT = ROOT / "outputs/pm_v1_5_paper1_external_treatment_stress_test_continuation_preflight_20260813"
PARENT_IDENTITY = "ebc61ee4b7e9d563034528d8a2095a729ab72d660c8c73991cb4bddf63b164e8"


def main() -> None:
    if OUT.exists():
        raise RuntimeError("continuation preflight exists; refusing overwrite")
    plan = read_jsonl(ORIGINAL_PLAN)
    completed = {row["physical_call_id"]: row for row in read_jsonl(PARTIAL_RESULTS)}
    remaining = [row for row in plan if row["physical_call_id"] not in completed]
    if len(plan) != 90 or len(completed) != 42 or len(remaining) != 48:
        raise RuntimeError("expected exact 90/42/48 original-completed-remaining split")
    if any(completed[row["physical_call_id"]]["messages_sha256"] != row["messages_sha256"] for row in plan if row["physical_call_id"] in completed):
        raise RuntimeError("completed prompt hash drifted")
    identity_payload = {
        "protocol": "pm-v1.5-paper1-external-treatment-stress-test-continuation-identity-v1",
        "parent_identity": PARENT_IDENTITY,
        "partial_results_sha256": sha256_file(PARTIAL_RESULTS),
        "partial_closeout_sha256": sha256_file(PARTIAL_CLOSEOUT),
        "config_sha256": sha256_file(CONFIG),
        "runner_sha256": sha256_file(RUNNER),
        "call_ids": [row["physical_call_id"] for row in remaining],
        "message_hashes": [row["messages_sha256"] for row in remaining],
        "transport_only_change": {"pace_seconds": 1.5, "rate_limit_backoff_seconds": 30.0, "maximum_attempts_per_missing_call": 3},
    }
    run_identity = sha256_text(canonical_json(identity_payload))
    OUT.mkdir(parents=True)
    call_path = OUT / "call_plan_private.jsonl"
    write_jsonl(call_path, remaining)
    report = {
        "protocol": "pm-v1.5-paper1-external-treatment-stress-test-continuation-preflight-v1",
        "status": "PASS_EXACT_48_MISSING_CALL_CONTINUATION_APPROVAL_REQUIRED",
        "run_identity": run_identity,
        "parent_identity": PARENT_IDENTITY,
        "carried_successes": 42,
        "new_logical_calls": 48,
        "combined_target": 90,
        "remaining_arm_counts": dict(sorted(Counter(row["arm"] for row in remaining).items())),
        "scientific_plan_changes": 0,
        "transport_only_change": identity_payload["transport_only_change"],
        "estimated_cost_usd": 0.0,
        "proposed_absolute_usd_cap": 0.0,
        "checks": {"no_success_rerun": not (set(completed) & {row["physical_call_id"] for row in remaining}), "all_remaining_from_original_plan": all(row in plan for row in remaining), "all_prompt_hashes_unchanged": all(sha256_text(canonical_json(row["messages"])) == row["messages_sha256"] for row in remaining)},
        "artifacts": {"call_plan": {"path": str(call_path.relative_to(ROOT)), "sha256": sha256_file(call_path)}, "partial_results": {"path": str(PARTIAL_RESULTS.relative_to(ROOT)), "sha256": sha256_file(PARTIAL_RESULTS)}, "partial_closeout": {"path": str(PARTIAL_CLOSEOUT.relative_to(ROOT)), "sha256": sha256_file(PARTIAL_CLOSEOUT)}, "config": {"path": str(CONFIG.relative_to(ROOT)), "sha256": sha256_file(CONFIG)}, "runner": {"path": str(RUNNER.relative_to(ROOT)), "sha256": sha256_file(RUNNER)}},
        "authorization": {"api_calls": 0, "generator_calls": 0, "judge_calls": 0, "fits": 0},
        "next": "Request explicit approval for this exact continuation identity and $0 cap."
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
