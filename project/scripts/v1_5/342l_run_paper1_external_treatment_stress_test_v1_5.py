#!/usr/bin/env python3
"""Execute the exact approved 18-owner/90-call external-corpus stress test."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.api import RetryableProviderError, make_client  # noqa: E402
from metacom_pm.config import endpoint_from_config, load_config  # noqa: E402
from metacom_pm.io import canonical_json, read_json, read_jsonl, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402
from metacom_pm.paid_run_release import require_paid_run_release  # noqa: E402
from metacom_pm.v1_5_ms_same_stack_feasibility import SameStackGeneratorOutput  # noqa: E402


PROTOCOL = "pm-v1.5-paper1-external-treatment-stress-test-live-v1"
STAGE = "paper1_external_treatment_stress_test_v1"
STAGE_ID = "EXTERNAL_TREATMENT_STRESS_TEST_EXECUTION"
AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
BUNDLE = ROOT / "data/pm_v1_5_contracts/paper1_active_execution_bundle_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_external_treatment_stress_test_execution_phase_v1.json"
CONFIG = ROOT / "configs/paper1_external_treatment_stress_test_execution_v1.json"
PREFLIGHT = ROOT / "outputs/pm_v1_5_paper1_external_treatment_stress_test_preflight_20260813/report.json"
CALL_PLAN = ROOT / "outputs/pm_v1_5_paper1_external_treatment_stress_test_preflight_20260813/call_plan_private.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_external_treatment_stress_test_live_20260813"
USD_CAP = 0.0
EXPECTED_CALLS = 90
EXPECTED_OWNERS = 18
EXPECTED_ARMS = {"always_off", "full", "minus_RS", "minus_MP", "minus_MS"}


def require_authority() -> dict[str, Any]:
    authority = read_json(AUTHORITY)
    bundle = read_json(BUNDLE)
    expected_bundle = {"path": str(BUNDLE.relative_to(ROOT)), "sha256": sha256_file(BUNDLE)}
    current = authority["current_execution_phase"]
    alias = authority["active_v3_phase"]
    if current["id"] != STAGE_ID or current["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("external treatment stress test is not the current execution phase")
    if alias.get("compatibility_alias_of") != "current_execution_phase" or alias["id"] != STAGE_ID or alias["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("authority compatibility alias drifted")
    if bundle["current_phase"]["id"] != STAGE_ID:
        raise RuntimeError("bundle does not point at this execution phase")
    phase = read_json(PHASE)
    for binding in phase["input_bindings"] + phase["implementation_bindings"]:
        if sha256_file(ROOT / binding["path"]) != binding["sha256"]:
            raise RuntimeError(f"bound input drifted: {binding['role']}")
    return phase


def validate_calls(calls: list[dict[str, Any]], phase: dict[str, Any]) -> None:
    if len(calls) != EXPECTED_CALLS:
        raise RuntimeError(f"exact {EXPECTED_CALLS}-call plan required, got {len(calls)}")
    if len({row["runtime_owner_key"] for row in calls}) != EXPECTED_OWNERS:
        raise RuntimeError("owner coverage drifted")
    if Counter(row["arm"] for row in calls) != Counter({arm: EXPECTED_OWNERS for arm in EXPECTED_ARMS}):
        raise RuntimeError("five-arm coverage drifted")
    if len({row["physical_call_id"] for row in calls}) != EXPECTED_CALLS:
        raise RuntimeError("physical call IDs are not unique")
    for row in calls:
        if sha256_text(canonical_json(row["messages"])) != row["messages_sha256"]:
            raise RuntimeError(f"message hash drifted: {row['physical_call_id']}")
        if row["generator"] != phase["execution"]["generator"]:
            raise RuntimeError(f"generator drifted: {row['physical_call_id']}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--run-identity")
    parser.add_argument("--accept-usd-cap", type=float)
    args = parser.parse_args()

    phase = require_authority()
    preflight = read_json(PREFLIGHT)
    calls = read_jsonl(CALL_PLAN)
    validate_calls(calls, phase)
    if preflight["run_identity"] != phase["execution"]["run_identity"]:
        raise RuntimeError("preflight and execution-phase identities differ")

    dry = {
        "protocol": PROTOCOL,
        "status": "LIVE_READY_EXACT_18_OWNER_90_CALL_EXTERNAL_DIAGNOSTIC",
        "logical_calls": len(calls),
        "owners": len({row["runtime_owner_key"] for row in calls}),
        "arms": dict(Counter(row["arm"] for row in calls)),
        "absolute_usd_cap": USD_CAP,
        "run_identity": phase["execution"]["run_identity"],
        "api_calls": 0,
    }
    print(json.dumps(dry, ensure_ascii=False, indent=2), flush=True)
    if not args.live:
        return
    if args.run_identity != phase["execution"]["run_identity"]:
        raise RuntimeError("run identity does not match live phase")
    if args.accept_usd_cap != USD_CAP:
        raise RuntimeError(f"must accept exact frozen cap {USD_CAP:g}")
    require_paid_run_release(
        read_json(CONFIG),
        config_path=CONFIG,
        stage=STAGE,
        run=True,
        run_identity=args.run_identity,
    )

    OUT.mkdir(parents=True, exist_ok=True)
    results_path = OUT / "generator_results_private.jsonl"
    raw_path = OUT / "raw_provider_attempts_before_guard.jsonl"
    completed = {row["physical_call_id"]: row for row in read_jsonl(results_path)} if results_path.exists() else {}
    raw_records = {row["physical_call_id"]: row for row in read_jsonl(raw_path)} if raw_path.exists() else {}
    client = make_client(endpoint_from_config(load_config(CONFIG), "generator"))

    for call in sorted(calls, key=lambda row: row["physical_call_id"]):
        if call["physical_call_id"] in completed:
            continue
        last_error: Exception | None = None
        for attempt in (1, 2):
            try:
                result, parsed = client.chat(
                    call["messages"],
                    temperature=call["temperature"],
                    max_tokens=call["max_output_tokens"],
                    seed=call["seed"],
                    response_schema=SameStackGeneratorOutput,
                    retries=1,
                )
                raw_records[call["physical_call_id"]] = {
                    "protocol": PROTOCOL,
                    "physical_call_id": call["physical_call_id"],
                    "attempt": attempt,
                    "succeeded": parsed is not None,
                    "request_hash": result.request_hash,
                    "usage": result.usage,
                    "latency_ms": result.latency_ms,
                    "finish_reason": result.normalized_finish_reason,
                    "raw_text_before_guard": result.text,
                    "raw_response_before_guard": result.raw_response,
                    "parsed_before_guard": parsed.model_dump(mode="json") if parsed is not None else None,
                    "error": None if parsed is not None else "provider returned no schema-valid output",
                }
                write_jsonl(raw_path, list(raw_records.values()))
                if parsed is None:
                    last_error = RuntimeError("no schema-valid output")
                    continue
                completed[call["physical_call_id"]] = {
                    "protocol": PROTOCOL,
                    "physical_call_id": call["physical_call_id"],
                    "case_id": call["case_id"],
                    "state_id": call["state_id"],
                    "runtime_owner_key": call["runtime_owner_key"],
                    "arm": call["arm"],
                    "requested_action_id": call["requested_action_id"],
                    "messages_sha256": call["messages_sha256"],
                    "reply": parsed.reply,
                    "used_evidence_ids": list(parsed.used_evidence_ids),
                    "realized_response_act": parsed.realized_response_act,
                    "provider_usage": result.usage,
                    "provider_latency_ms": result.latency_ms,
                    "provider_finish_reason": result.normalized_finish_reason,
                }
                write_jsonl(results_path, list(completed.values()))
                print(f"external treatment stress test {len(completed)}/{EXPECTED_CALLS}", flush=True)
                last_error = None
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                raw_records[call["physical_call_id"]] = {
                    "protocol": PROTOCOL,
                    "physical_call_id": call["physical_call_id"],
                    "attempt": attempt,
                    "succeeded": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
                write_jsonl(raw_path, list(raw_records.values()))
                if not isinstance(exc, RetryableProviderError) or attempt == 2:
                    break
        if call["physical_call_id"] not in completed and last_error is not None:
            print(f"FAILED {call['physical_call_id']}: {last_error}", flush=True)

    usage = Counter()
    for row in completed.values():
        for key, value in (row.get("provider_usage") or {}).items():
            if isinstance(value, (int, float)):
                usage[key] += value
    arm_counts = Counter(row["arm"] for row in completed.values())
    summary = {
        "protocol": PROTOCOL,
        "status": f"LIVE_COMPLETE_{len(completed)}_OF_{EXPECTED_CALLS}",
        "run_identity": phase["execution"]["run_identity"],
        "completed": len(completed),
        "total": EXPECTED_CALLS,
        "owners_completed": len({row["runtime_owner_key"] for row in completed.values()}),
        "arm_counts": dict(sorted(arm_counts.items())),
        "provider_usage": dict(usage),
        "observed_cost_usd": 0.0,
        "output_directory": str(OUT.relative_to(ROOT)),
    }
    write_json(OUT / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
