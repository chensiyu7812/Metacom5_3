#!/usr/bin/env python3
"""Execute the exact hash-bound RS+MS EvoEmo executor pilot (real generator calls)."""

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
from metacom_pm.v1_5_component_general_v3 import V3Candidate, build_component_general_plan_v3  # noqa: E402
from metacom_pm.v1_5_ms_same_stack_feasibility import SameStackGeneratorOutput  # noqa: E402
from metacom_pm.v1_5_response_program_v3 import execute_response_program_v3, response_generation_messages_v3  # noqa: E402


PROTOCOL = "pm-v1.5-paper1-rs-ms-evoemo-executor-pilot-live-v1"
STAGE = "paper1_rs_ms_evoemo_executor_pilot_v1"
AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
BUNDLE = ROOT / "data/pm_v1_5_contracts/paper1_active_execution_bundle_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_rs_ms_evoemo_executor_pilot_execution_phase_v1.json"
CONFIG = ROOT / "configs/paper1_rs_ms_evoemo_executor_pilot_execution_v1.json"
PREFLIGHT = ROOT / "outputs/pm_v1_5_paper1_rs_ms_evoemo_executor_pilot_preflight_20260812"
CASES = PREFLIGHT / "qualification_cases_private.jsonl"
CALLS = PREFLIGHT / "physical_call_plan_private.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_rs_ms_evoemo_executor_pilot_live_20260812"
USD_CAP = 0.05

MS_MEANING_CUE = (
    "Interpret the single strictly past user-owned source supplied below as a "
    "tentative continuity cue; do not treat it as current or quote it."
)
MS_ALLOWED_CHANGE = "If it materially helps, use the past meaning to acknowledge continuity or ask a more informed current-oriented question."
MS_FORBIDDEN = "Do not copy the user's first-person wording, assume the past remains true, infer a trait or cause, or expose a memory record."
RS_STATIC_EVIDENCE_ID = "rs_open_nonleading_v1"
RS_STATIC_EXACT_SOURCE = "Frozen strategy card: one open, non-leading, low-burden invitation."
RS_STATIC_MEANING_CUE = "Offer one open, non-leading invitation that helps the user identify what feels most important or manageable now."
RS_STATIC_ALLOWED_CHANGE = "Make the reply's primary act one open, non-leading question or invitation."
RS_STATIC_FORBIDDEN = "Do not presuppose the answer, force disclosure, add a second task, or override a stop boundary."


def require_authority() -> dict[str, Any]:
    authority = read_json(AUTHORITY)
    bundle = read_json(BUNDLE)
    current = authority["current_execution_phase"]
    alias = authority["active_v3_phase"]
    expected_bundle = {"path": str(BUNDLE.relative_to(ROOT)), "sha256": sha256_file(BUNDLE)}
    expected_phase = {"path": str(PHASE.relative_to(ROOT)), "sha256": sha256_file(PHASE)}
    if current["id"] != "RS_MS_EVOEMO_EXECUTOR_PILOT_EXECUTION" or current["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("RS+MS EvoEmo executor pilot execution is not current")
    if alias.get("compatibility_alias_of") != "current_execution_phase" or alias["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("authority alias drifted")
    if bundle["current_phase"]["id"] != "RS_MS_EVOEMO_EXECUTOR_PILOT_EXECUTION" or bundle["current_phase"]["parent_phase"] != expected_phase:
        raise RuntimeError("bundle does not point at this execution phase")
    phase = read_json(PHASE)
    for binding in [*phase["input_bindings"], *phase["implementation_bindings"]]:
        if sha256_file(ROOT / binding["path"]) != binding["sha256"]:
            raise RuntimeError(f"bound input drifted: {binding['role']}")
    return phase


def rebuild_plan(call: dict[str, Any], case: dict[str, Any]):
    action = call["requested_action_id"]
    is_routed = call["is_routed"]
    candidates: dict[str, V3Candidate | None] = {component: None for component in ("MP", "MS", "ME", "RS")}
    if is_routed and case["ms_decision"] == "ON":
        candidates["MS"] = V3Candidate(
            component="MS",
            evidence_id=case["ms_evidence_id"],
            meaning_cue=MS_MEANING_CUE,
            exact_source=case["ms_exact_source"],
            owner_id=case["runtime_owner_key"],
            time_status="STRICTLY_PAST_NOT_ASSUMED_CURRENT",
            allowed_response_change=MS_ALLOWED_CHANGE,
            forbidden_inference=MS_FORBIDDEN,
            burden_units=1,
        )
    if is_routed and case["rs_decision"] == "ON":
        candidates["RS"] = V3Candidate(
            component="RS",
            evidence_id=RS_STATIC_EVIDENCE_ID,
            meaning_cue=RS_STATIC_MEANING_CUE,
            exact_source=RS_STATIC_EXACT_SOURCE,
            owner_id=None,
            time_status="CURRENT_STRATEGY_CARD",
            allowed_response_change=RS_STATIC_ALLOWED_CHANGE,
            forbidden_inference=RS_STATIC_FORBIDDEN,
            burden_units=1,
        )
    return build_component_general_plan_v3(
        requested_action_id=action,
        current_user_id=case["runtime_owner_key"],
        candidates=candidates,
        pair_relations={"MS-RS": "COMPLEMENTARY"} if is_routed and case["ms_decision"] == "ON" and case["rs_decision"] == "ON" else None,
    )


class FrozenCallClient:
    def __init__(self, client: Any, call: dict[str, Any], raw_records: dict[str, dict[str, Any]]):
        self.client = client
        self.call = call
        self.raw_records = raw_records
        self.semantic_call_number = 0
        self.last_result: Any = None

    def chat(self, messages, *, response_schema):
        self.semantic_call_number += 1
        last_error: Exception | None = None
        for transport_attempt in (1, 2):
            key = f"{self.call['physical_call_id']}:{self.semantic_call_number}:{transport_attempt}"
            try:
                result, parsed = self.client.chat(
                    messages,
                    temperature=float(self.call["temperature"]),
                    max_tokens=int(self.call["max_output_tokens"]),
                    seed=int(self.call["seed"]),
                    response_schema=response_schema,
                    retries=1,
                )
                self.raw_records[key] = {
                    "protocol": PROTOCOL,
                    "physical_call_id": self.call["physical_call_id"],
                    "semantic_call_number": self.semantic_call_number,
                    "transport_attempt": transport_attempt,
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
                write_jsonl(OUT / "raw_provider_attempts_before_guard.jsonl", list(self.raw_records.values()))
                self.last_result = result
                return result, parsed
            except Exception as exc:
                last_error = exc
                retry_class = getattr(exc, "last_retry_class", None)
                retryable = isinstance(exc, RetryableProviderError) and retry_class in {"rate_limited_429", "request_timeout_408", "http_5xx", "network_timeout"}
                self.raw_records[key] = {
                    "protocol": PROTOCOL,
                    "physical_call_id": self.call["physical_call_id"],
                    "semantic_call_number": self.semantic_call_number,
                    "transport_attempt": transport_attempt,
                    "succeeded": False,
                    "request_hash": getattr(exc, "request_hash", None),
                    "usage": getattr(exc, "usage", None) or {},
                    "latency_ms": None,
                    "finish_reason": "transport_retry" if retryable and transport_attempt == 1 else "transport_failure",
                    "raw_text_before_guard": None,
                    "raw_response_before_guard": None,
                    "parsed_before_guard": None,
                    "retry_class": retry_class,
                    "error": f"{type(exc).__name__}: {exc}",
                }
                write_jsonl(OUT / "raw_provider_attempts_before_guard.jsonl", list(self.raw_records.values()))
                if not retryable or transport_attempt == 2:
                    break
                time.sleep(max(float(getattr(exc, "retry_after_seconds", 0.0) or 0.0), 1.0))
        return last_error or RuntimeError("provider call failed"), None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--run-identity")
    parser.add_argument("--accept-usd-cap", type=float)
    args = parser.parse_args()
    phase = require_authority()
    cases = {row["case_id"]: row for row in read_jsonl(CASES)}
    calls = read_jsonl(CALLS)
    preflight_report = read_json(PREFLIGHT / "report.json")
    if preflight_report["status"] != "RS_MS_EVOEMO_PILOT_PREFLIGHT_PASS_LIVE_PHASE_MAY_BE_DESIGNED" or preflight_report["failed_checks"]:
        raise RuntimeError("frozen RS+MS EvoEmo executor pilot preflight is not valid")
    for call in calls:
        case = cases[call["case_id"]]
        messages = response_generation_messages_v3(current_context=case["current_context"], current_goal=case["current_goal"], plan=rebuild_plan(call, case))
        if sha256_text(canonical_json(messages)) != call["messages_sha256"]:
            raise RuntimeError(f"provider-visible prompt drift: {call['physical_call_id']}")
    dry = {
        "protocol": PROTOCOL,
        "status": f"LIVE_READY_EXACT_{len(calls)}_CALLS",
        "logical_primary_calls": len(calls),
        "maximum_semantic_calls_with_contamination_retry": len(calls) * 2,
        "maximum_transport_attempts": len(calls) * 4,
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
    require_paid_run_release(read_json(CONFIG), config_path=CONFIG, stage=STAGE, run=True, run_identity=args.run_identity)

    OUT.mkdir(parents=True, exist_ok=True)
    completed = {row["physical_call_id"]: row for row in read_jsonl(OUT / "generator_results_private.jsonl")} if (OUT / "generator_results_private.jsonl").exists() else {}
    raw_records = {
        f"{row['physical_call_id']}:{row['semantic_call_number']}:{row['transport_attempt']}": row
        for row in (read_jsonl(OUT / "raw_provider_attempts_before_guard.jsonl") if (OUT / "raw_provider_attempts_before_guard.jsonl").exists() else [])
    }
    config = load_config(CONFIG)
    client = make_client(endpoint_from_config(config, "generator"))
    try:
        for call in sorted(calls, key=lambda row: (row["is_baseline"] is False, row["case_id"])):
            if call["physical_call_id"] in completed:
                continue
            case = cases[call["case_id"]]
            plan = rebuild_plan(call, case)
            wrapper = FrozenCallClient(client, call, raw_records)
            execution = execute_response_program_v3(
                client=wrapper,
                response_schema=SameStackGeneratorOutput,
                current_context=case["current_context"],
                current_goal=case["current_goal"],
                plan=plan,
                raw_persist=lambda _attempt, _raw: None,
            )
            result = wrapper.last_result
            completed[call["physical_call_id"]] = {
                "protocol": PROTOCOL,
                "physical_call_id": call["physical_call_id"],
                "case_id": call["case_id"],
                "state_id": call["state_id"],
                "split_group_key": call["split_group_key"],
                "requested_action_id": call["requested_action_id"],
                "is_baseline": call["is_baseline"],
                "is_routed": call["is_routed"],
                "seed": call["seed"],
                "messages_sha256": call["messages_sha256"],
                "execution_status": execution.status,
                "guard_errors": list(execution.guard_errors),
                "semantic_calls_made": execution.calls_made,
                "requested_action_accounting": execution.accounting.requested_action_id,
                "structurally_eligible_action_id": execution.accounting.structurally_eligible_action_id,
                "jointly_planned_action_id": execution.accounting.jointly_planned_action_id,
                "generator_claimed": dict(execution.accounting.generator_claimed),
                "final_reply": execution.response.reply,
                "final_used_evidence_ids": list(execution.response.used_evidence_ids),
                "realized_response_act": execution.response.realized_response_act,
                "provider_usage_last_call": result.usage if result is not None else {},
                "provider_latency_ms_last_call": result.latency_ms if result is not None else None,
                "provider_finish_reason_last_call": result.normalized_finish_reason if result is not None else "no_valid_completion",
                "raw_provider_output_persisted_before_guard": any(key.startswith(call["physical_call_id"] + ":") for key in raw_records),
            }
            write_jsonl(OUT / "generator_results_private.jsonl", list(completed.values()))
            print(f"RS+MS EvoEmo pilot {len(completed)}/{len(calls)}", flush=True)
    finally:
        client.close()

    completed_rows = list(completed.values())
    complete = len(completed_rows) == len(calls)
    report = {
        "protocol": PROTOCOL,
        "status": "RS_MS_EVOEMO_PILOT_GENERATION_COMPLETE_PAIRED_BASELINE_MEASUREMENT_REQUIRED" if complete else "RS_MS_EVOEMO_PILOT_GENERATION_INCOMPLETE_RESUME_NEXT_INVOCATION",
        "logical_primary_calls_completed": len(completed_rows),
        "raw_transport_attempt_rows": len(raw_records),
        "execution_status_counts": dict(Counter(row["execution_status"] for row in completed_rows)),
        "guard_error_counts": dict(Counter(error for row in completed_rows for error in row["guard_errors"])),
        "requested_planned_exact": sum(row["requested_action_accounting"] == row["structurally_eligible_action_id"] == row["jointly_planned_action_id"] for row in completed_rows),
        "safe_personal_nonuse": sum(row["execution_status"] == "clean_safe_personal_nonuse" for row in completed_rows),
        "contamination_retries": sum(row["semantic_calls_made"] == 2 for row in completed_rows),
        "pm_refits": 0,
        "MP_ME_work": False,
        "quality_risk_function_concluded": False,
        "artifacts": {
            "results": {"path": str((OUT / "generator_results_private.jsonl").relative_to(ROOT)), "sha256": sha256_file(OUT / "generator_results_private.jsonl")},
            "raw": {"path": str((OUT / "raw_provider_attempts_before_guard.jsonl").relative_to(ROOT)), "sha256": sha256_file(OUT / "raw_provider_attempts_before_guard.jsonl")},
        },
        "next": "ZERO_API_PAIRED_BASELINE_VS_ROUTED_MEASUREMENT" if complete else "RERUN_WITH_SAME_RUN_IDENTITY_TO_RESUME",
    }
    write_json(OUT / "live_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not complete:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
