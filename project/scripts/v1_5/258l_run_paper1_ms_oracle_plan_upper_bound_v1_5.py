#!/usr/bin/env python3
"""Execute the exact eight-call MS oracle-plan upper-bound probe."""

from __future__ import annotations

import argparse
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


STAGE = "paper1_ms_oracle_plan_upper_bound_v1"
AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_ms_oracle_plan_upper_bound_execution_phase_v1.json"
CONFIG = ROOT / "configs/paper1_ms_oracle_plan_upper_bound_execution_v1.json"
ORACLE = ROOT / "data/pm_v1_5_contracts/paper1_ms_oracle_semantic_plans_v1.json"
CASES = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_qualification_preflight_v3_20260811/qualification_cases_private.jsonl"
PREFLIGHT = ROOT / "outputs/pm_v1_5_paper1_ms_oracle_plan_upper_bound_preflight_20260811"
CALLS = PREFLIGHT / "physical_call_plan_private.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_ms_oracle_plan_upper_bound_live_20260811"
USD_CAP = 0.01


def build_plan(case: dict[str, Any], oracle: dict[str, Any]):
    candidate = V3Candidate(
        component="MS",
        evidence_id=case["evidence_id"],
        meaning_cue=(
            f"support_phase={oracle['support_phase']}; immediate_goal={oracle['immediate_goal']}; "
            f"candidate_increment={oracle['candidate_increment']}; "
            f"resource_disposition={oracle['oracle_disposition']}; "
            f"entity_link_status={oracle['entity_link_status']}"
        ),
        exact_source=case["exact_source"],
        owner_id=case["runtime_owner_key"],
        time_status="STRICTLY_PAST_NOT_ASSUMED_CURRENT",
        allowed_response_change=oracle["good_use"] + " " + oracle["nonuse_condition"],
        forbidden_inference=(
            oracle["forbidden_focus_shift"]
            + " Do not copy the source, assume it remains current, or expose this planning scaffold."
        ),
        burden_units=1,
    )
    return build_component_general_plan_v3(
        requested_action_id="MS+R0",
        current_user_id=case["runtime_owner_key"],
        candidates={"MP": None, "MS": candidate, "ME": None, "RS": None},
    )


def require_authority() -> dict[str, Any]:
    authority = read_json(AUTHORITY)
    active = authority["active_v3_phase"]
    if active["id"] != "MS_ORACLE_PLAN_UPPER_BOUND_EXECUTION":
        raise RuntimeError("oracle-plan live execution is not the unique active V3 phase")
    binding = active["active_phase_manifest"]
    if binding["path"] != str(PHASE.relative_to(ROOT)) or binding["sha256"] != sha256_file(PHASE):
        raise RuntimeError("active oracle phase binding drifted")
    phase = read_json(PHASE)
    for item in [*phase["input_bindings"], *phase["implementation_bindings"]]:
        if sha256_file(ROOT / item["path"]) != item["sha256"]:
            raise RuntimeError(f"phase binding drifted: {item['path']}")
    return phase


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
                    "protocol": "pm-v1.5-paper1-ms-oracle-plan-upper-bound-raw-v1",
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
                write_jsonl(OUT / "raw_provider_attempts_before_guard.jsonl", self.raw_records.values())
                self.last_result = result
                return result, parsed
            except Exception as exc:
                last_error = exc
                retry_class = getattr(exc, "last_retry_class", None)
                retryable = isinstance(exc, RetryableProviderError) and retry_class in {
                    "rate_limited_429", "request_timeout_408", "http_5xx", "network_timeout"
                }
                self.raw_records[key] = {
                    "protocol": "pm-v1.5-paper1-ms-oracle-plan-upper-bound-raw-v1",
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
                OUT.mkdir(parents=True, exist_ok=True)
                write_jsonl(OUT / "raw_provider_attempts_before_guard.jsonl", self.raw_records.values())
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
    calls = read_jsonl(CALLS)
    cases = {row["qualification_case_id"]: row for row in read_jsonl(CASES)}
    oracle = {row["qualification_case_id"]: row for row in read_json(ORACLE)["plans"]}
    if len(calls) != 8:
        raise RuntimeError("exact eight-call plan required")
    for call in calls:
        case = cases[call["qualification_case_id"]]
        plan = build_plan(case, oracle[call["qualification_case_id"]])
        messages = response_generation_messages_v3(
            current_context=case["current_context"], current_goal=case["current_goal"], plan=plan
        )
        if sha256_text(canonical_json(messages)) != call["messages_sha256"]:
            raise RuntimeError(f"provider-visible prompt drift: {call['physical_call_id']}")
    dry = {
        "status": "LIVE_READY_EXACT_8_ORACLE_PLAN_CALLS",
        "logical_primary_calls": 8,
        "maximum_semantic_calls_with_contamination_retry": 16,
        "maximum_transport_attempts": 32,
        "absolute_usd_cap": USD_CAP,
        "run_identity": phase["execution"]["run_identity"],
        "api_calls": 0,
    }
    print(json.dumps(dry, ensure_ascii=False, indent=2), flush=True)
    if not args.live:
        return
    if args.run_identity != phase["execution"]["run_identity"]:
        raise RuntimeError("run identity mismatch")
    if args.accept_usd_cap != USD_CAP:
        raise RuntimeError(f"must accept exact cap {USD_CAP:g}")
    config = load_config(CONFIG)
    require_paid_run_release(
        read_json(CONFIG), config_path=CONFIG, stage=STAGE, run=True, run_identity=args.run_identity
    )
    OUT.mkdir(parents=True, exist_ok=True)
    completed = {row["physical_call_id"]: row for row in read_jsonl(OUT / "generator_results_private.jsonl")} if (OUT / "generator_results_private.jsonl").exists() else {}
    raw_records = {
        f"{row['physical_call_id']}:{row['semantic_call_number']}:{row['transport_attempt']}": row
        for row in (read_jsonl(OUT / "raw_provider_attempts_before_guard.jsonl") if (OUT / "raw_provider_attempts_before_guard.jsonl").exists() else [])
    }
    client = make_client(endpoint_from_config(config, "generator"))
    try:
        for index, call in enumerate(calls, 1):
            if call["physical_call_id"] in completed:
                continue
            case = cases[call["qualification_case_id"]]
            plan = build_plan(case, oracle[call["qualification_case_id"]])
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
                "protocol": "pm-v1.5-paper1-ms-oracle-plan-upper-bound-result-v1",
                "physical_call_id": call["physical_call_id"],
                "qualification_case_id": call["qualification_case_id"],
                "state_id": call["state_id"],
                "split_group_key": call["split_group_key"],
                "oracle_disposition_private": call["oracle_disposition_private"],
                "requested_action_id": "MS+R0",
                "seed": call["seed"],
                "messages_sha256": call["messages_sha256"],
                "execution_status": execution.status,
                "guard_errors": list(execution.guard_errors),
                "semantic_calls_made": execution.calls_made,
                "generator_claimed": dict(execution.accounting.generator_claimed),
                "final_reply": execution.response.reply,
                "final_used_evidence_ids": list(execution.response.used_evidence_ids),
                "realized_response_act": execution.response.realized_response_act,
                "provider_usage_last_call": result.usage if result is not None else {},
                "provider_latency_ms_last_call": result.latency_ms if result is not None else None,
                "provider_finish_reason_last_call": result.normalized_finish_reason if result is not None else "no_valid_completion",
                "raw_provider_output_persisted_before_guard": any(key.startswith(call["physical_call_id"] + ":") for key in raw_records),
            }
            write_jsonl(OUT / "generator_results_private.jsonl", completed.values())
            print(f"oracle plan upper bound {len(completed)}/8", flush=True)
    finally:
        client.close()
    results = list(completed.values())
    report = {
        "protocol": "pm-v1.5-paper1-ms-oracle-plan-upper-bound-live-report-v1",
        "status": "ORACLE_PLAN_UPPER_BOUND_GENERATION_COMPLETE_MEASUREMENT_NOT_YET_RUN" if len(results) == 8 else "INCOMPLETE",
        "calls": len(results),
        "generator_claimed_ms": sum(bool(row["generator_claimed"]["MS"]) for row in results),
        "clean_or_safe_nonuse": sum(str(row["execution_status"]).startswith("clean") for row in results),
        "total_usage": {
            key: sum(float((row.get("provider_usage_last_call") or {}).get(key, 0) or 0) for row in results)
            for key in ("input_tokens", "output_tokens", "total_tokens")
        },
        "api_calls": len(results),
        "pm_fits": 0,
        "training_labels_created": 0,
        "next": "ZERO_API_BLIND_FUNCTION_AND_QUALITY_PACKET_USING_FROZEN_EXISTING_R0_GENERIC_MS_AND_NEW_ORACLE_ARMS",
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if len(results) != 8:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
