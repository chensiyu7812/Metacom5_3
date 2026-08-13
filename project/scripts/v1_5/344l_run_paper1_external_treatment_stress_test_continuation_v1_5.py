#!/usr/bin/env python3
"""Run only the 48 missing calls from the consumed 42/90 stress-test run."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.api import RetryableProviderError, make_client  # noqa: E402
from metacom_pm.config import endpoint_from_config, load_config  # noqa: E402
from metacom_pm.io import canonical_json, read_json, read_jsonl, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402
from metacom_pm.paid_run_release import require_paid_run_release  # noqa: E402
from metacom_pm.v1_5_ms_same_stack_feasibility import SameStackGeneratorOutput  # noqa: E402

STAGE = "paper1_external_treatment_stress_test_continuation_v1"
STAGE_ID = "EXTERNAL_TREATMENT_STRESS_TEST_CONTINUATION_EXECUTION"
PROTOCOL = "pm-v1.5-paper1-external-treatment-stress-test-continuation-live-v1"
AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
BUNDLE = ROOT / "data/pm_v1_5_contracts/paper1_active_execution_bundle_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_external_treatment_stress_test_continuation_execution_phase_v1.json"
CONFIG = ROOT / "configs/paper1_external_treatment_stress_test_continuation_v1.json"
REPORT = ROOT / "outputs/pm_v1_5_paper1_external_treatment_stress_test_continuation_preflight_20260813/report.json"
CALL_PLAN = ROOT / "outputs/pm_v1_5_paper1_external_treatment_stress_test_continuation_preflight_20260813/call_plan_private.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_external_treatment_stress_test_continuation_live_20260813"
EXPECTED = 48
USD_CAP = 0.0
PACE_SECONDS = 1.5
RATE_LIMIT_BACKOFF_SECONDS = 30.0


def require_authority() -> dict[str, Any]:
    authority = read_json(AUTHORITY)
    bundle = read_json(BUNDLE)
    expected_bundle = {"path": str(BUNDLE.relative_to(ROOT)), "sha256": sha256_file(BUNDLE)}
    current = authority["current_execution_phase"]
    alias = authority["active_v3_phase"]
    if current["id"] != STAGE_ID or current["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("continuation is not current")
    if alias.get("compatibility_alias_of") != "current_execution_phase" or alias["id"] != STAGE_ID or alias["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("authority compatibility alias drifted")
    if bundle["current_phase"]["id"] != STAGE_ID:
        raise RuntimeError("bundle does not point at continuation")
    phase = read_json(PHASE)
    for binding in phase["input_bindings"] + phase["implementation_bindings"]:
        if sha256_file(ROOT / binding["path"]) != binding["sha256"]:
            raise RuntimeError(f"bound input drifted: {binding['role']}")
    return phase


def is_rate_limit(exc: Exception) -> bool:
    return "429" in str(exc) or "rate_limit" in str(exc).lower()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--run-identity")
    parser.add_argument("--accept-usd-cap", type=float)
    args = parser.parse_args()
    phase = require_authority()
    report = read_json(REPORT)
    calls = read_jsonl(CALL_PLAN)
    if len(calls) != EXPECTED or len({row["physical_call_id"] for row in calls}) != EXPECTED:
        raise RuntimeError("continuation must contain exactly 48 unique calls")
    for call in calls:
        if sha256_text(canonical_json(call["messages"])) != call["messages_sha256"]:
            raise RuntimeError(f"message hash drifted: {call['physical_call_id']}")
    if report["run_identity"] != phase["execution"]["run_identity"]:
        raise RuntimeError("continuation report/phase identity drifted")
    dry = {"protocol": PROTOCOL, "status": "LIVE_READY_EXACT_48_MISSING_CALL_CONTINUATION", "logical_calls": len(calls), "absolute_usd_cap": USD_CAP, "run_identity": report["run_identity"], "api_calls": 0}
    print(json.dumps(dry, ensure_ascii=False, indent=2), flush=True)
    if not args.live:
        return
    if args.run_identity != report["run_identity"] or args.accept_usd_cap != USD_CAP:
        raise RuntimeError("live identity or cap mismatch")
    require_paid_run_release(read_json(CONFIG), config_path=CONFIG, stage=STAGE, run=True, run_identity=args.run_identity)
    OUT.mkdir(parents=True, exist_ok=True)
    result_path = OUT / "generator_results_private.jsonl"
    raw_path = OUT / "raw_provider_attempts_before_guard.jsonl"
    completed = {row["physical_call_id"]: row for row in read_jsonl(result_path)} if result_path.exists() else {}
    raw_rows = read_jsonl(raw_path) if raw_path.exists() else []
    client = make_client(endpoint_from_config(load_config(CONFIG), "generator"))
    for call in sorted(calls, key=lambda row: row["physical_call_id"]):
        if call["physical_call_id"] in completed:
            continue
        for attempt in (1, 2, 3):
            try:
                result, parsed = client.chat(call["messages"], temperature=call["temperature"], max_tokens=call["max_output_tokens"], seed=call["seed"], response_schema=SameStackGeneratorOutput, retries=1)
                raw_rows.append({"protocol": PROTOCOL, "physical_call_id": call["physical_call_id"], "attempt": attempt, "succeeded": parsed is not None, "request_hash": result.request_hash, "usage": result.usage, "latency_ms": result.latency_ms, "finish_reason": result.normalized_finish_reason, "raw_text_before_guard": result.text, "raw_response_before_guard": result.raw_response, "parsed_before_guard": parsed.model_dump(mode="json") if parsed is not None else None, "error": None if parsed is not None else "provider returned no schema-valid output"})
                write_jsonl(raw_path, raw_rows)
                if parsed is None:
                    continue
                completed[call["physical_call_id"]] = {"protocol": PROTOCOL, "physical_call_id": call["physical_call_id"], "case_id": call["case_id"], "state_id": call["state_id"], "runtime_owner_key": call["runtime_owner_key"], "arm": call["arm"], "requested_action_id": call["requested_action_id"], "messages_sha256": call["messages_sha256"], "reply": parsed.reply, "used_evidence_ids": list(parsed.used_evidence_ids), "realized_response_act": parsed.realized_response_act, "provider_usage": result.usage, "provider_latency_ms": result.latency_ms, "provider_finish_reason": result.normalized_finish_reason}
                write_jsonl(result_path, list(completed.values()))
                print(f"external continuation {len(completed)}/{EXPECTED}", flush=True)
                break
            except Exception as exc:  # noqa: BLE001
                raw_rows.append({"protocol": PROTOCOL, "physical_call_id": call["physical_call_id"], "attempt": attempt, "succeeded": False, "error": f"{type(exc).__name__}: {exc}"})
                write_jsonl(raw_path, raw_rows)
                if not isinstance(exc, RetryableProviderError) or attempt == 3:
                    print(f"FAILED {call['physical_call_id']}: {exc}", flush=True)
                    break
                if is_rate_limit(exc):
                    time.sleep(RATE_LIMIT_BACKOFF_SECONDS)
            time.sleep(PACE_SECONDS)
        time.sleep(PACE_SECONDS)
    usage = Counter()
    for row in completed.values():
        for key, value in (row.get("provider_usage") or {}).items():
            if isinstance(value, (int, float)):
                usage[key] += value
    summary = {"protocol": PROTOCOL, "status": f"LIVE_COMPLETE_{len(completed)}_OF_{EXPECTED}", "run_identity": report["run_identity"], "completed": len(completed), "total": EXPECTED, "arm_counts": dict(Counter(row["arm"] for row in completed.values())), "provider_usage": dict(usage), "observed_cost_usd": 0.0, "output_directory": str(OUT.relative_to(ROOT))}
    write_json(OUT / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
