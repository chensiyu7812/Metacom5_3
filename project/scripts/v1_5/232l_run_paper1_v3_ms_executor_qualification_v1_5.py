#!/usr/bin/env python3
"""Execute the exact hash-bound 64-call MS V3 meaning-absorption qualification."""

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
from metacom_pm.io import canonical_json, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402
from metacom_pm.paid_run_release import require_paid_run_release  # noqa: E402
from metacom_pm.v1_5_component_general_v3 import V3Candidate, build_component_general_plan_v3  # noqa: E402
from metacom_pm.v1_5_ms_same_stack_feasibility import SameStackGeneratorOutput  # noqa: E402
from metacom_pm.v1_5_response_program_v3 import execute_response_program_v3, response_generation_messages_v3  # noqa: E402


PROTOCOL = "pm-v1.5-paper1-v3-ms-executor-qualification-live-v1"
STAGE = "paper1_v3_ms_executor_qualification_v1"
AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_v3_ms_executor_qualification_execution_phase_v1.json"
CONFIG = ROOT / "configs/paper1_v3_ms_executor_qualification_execution_v1.json"
PREFLIGHT = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_qualification_preflight_v3_20260811"
AUDIT = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_qualification_preflight_audit_20260811/report.json"
CASES = PREFLIGHT / "qualification_cases_private.jsonl"
CALLS = PREFLIGHT / "physical_call_plan_private.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_qualification_live_20260811"
USD_CAP = 0.05


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def require_authority() -> dict[str, Any]:
    authority = read(AUTHORITY)
    active = authority["active_v3_phase"]
    if active["id"] != "MS_EXECUTOR_QUALIFICATION_EXECUTION":
        raise RuntimeError("MS executor qualification execution is not active")
    binding = active["active_phase_manifest"]
    if binding["path"] != str(PHASE.relative_to(ROOT)) or binding["sha256"] != sha256_file(PHASE):
        raise RuntimeError("MS executor live-phase authority binding drifted")
    phase = read(PHASE)
    for item in [*phase["input_bindings"], *phase["implementation_bindings"]]:
        if sha256_file(ROOT / item["path"]) != item["sha256"]:
            raise RuntimeError(f"live phase binding drifted: {item['path']}")
    return phase


def rebuild_plan(call: dict[str, Any], case: dict[str, Any]):
    action = call["requested_action_id"]
    ms_on = action in {"MS+R0", "MS+RS"}
    rs_on = action in {"M0+RS", "MS+RS"}
    candidates: dict[str, V3Candidate | None] = {component: None for component in ("MP", "MS", "ME", "RS")}
    if ms_on:
        candidates["MS"] = V3Candidate(
            component="MS",
            evidence_id=case["evidence_id"],
            meaning_cue="Interpret the single strictly past user-owned source supplied below as a tentative continuity cue; do not treat it as current or quote it.",
            exact_source=case["exact_source"],
            owner_id=case["runtime_owner_key"],
            time_status="STRICTLY_PAST_NOT_ASSUMED_CURRENT",
            allowed_response_change="If it materially helps, use the past meaning to acknowledge continuity or ask a more informed current-oriented question.",
            forbidden_inference="Do not copy the user's first-person wording, assume the past remains true, infer a trait or cause, or expose a memory record.",
            burden_units=1,
        )
    if rs_on:
        candidates["RS"] = V3Candidate(
            component="RS",
            evidence_id="rs_open_nonleading_v1",
            meaning_cue="Offer one open, non-leading invitation that helps the user identify what feels most important or manageable now.",
            exact_source="Frozen strategy card: one open, non-leading, low-burden invitation.",
            owner_id=None,
            time_status="CURRENT_STRATEGY_CARD",
            allowed_response_change="Make the reply's primary act one open, non-leading question or invitation.",
            forbidden_inference="Do not presuppose the answer, force disclosure, add a second task, or override a stop boundary.",
            burden_units=1,
        )
    return build_component_general_plan_v3(
        requested_action_id=action,
        current_user_id=case["runtime_owner_key"],
        candidates=candidates,
        pair_relations={"MS-RS": "COMPLEMENTARY"} if ms_on and rs_on else None,
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
    cases = {row["qualification_case_id"]: row for row in rows(CASES)}
    calls = rows(CALLS)
    audit = read(AUDIT)
    if audit["status"] != "PASS_EXACT_64_CALL_LIVE_PHASE_MAY_BE_HASH_BOUND" or len(calls) != 64 or len(cases) != 16:
        raise RuntimeError("frozen MS executor qualification preflight is not valid")
    for call in calls:
        case = cases[call["qualification_case_id"]]
        messages = response_generation_messages_v3(current_context=case["current_context"], current_goal=case["current_goal"], plan=rebuild_plan(call, case))
        if sha256_text(canonical_json(messages)) != call["messages_sha256"]:
            raise RuntimeError(f"provider-visible prompt drift: {call['physical_call_id']}")
    dry = {
        "protocol": PROTOCOL,
        "status": "LIVE_READY_EXACT_64_CALLS" if len(calls) == 64 else "PLAN_INVALID",
        "logical_primary_calls": 64,
        "maximum_semantic_calls_with_contamination_retry": 128,
        "maximum_transport_attempts": 256,
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
    require_paid_run_release(read(CONFIG), config_path=CONFIG, stage=STAGE, run=True, run_identity=args.run_identity)

    OUT.mkdir(parents=True, exist_ok=True)
    completed = {row["physical_call_id"]: row for row in rows(OUT / "generator_results_private.jsonl")}
    raw_records = {
        f"{row['physical_call_id']}:{row['semantic_call_number']}:{row['transport_attempt']}": row
        for row in rows(OUT / "raw_provider_attempts_before_guard.jsonl")
    }
    config = load_config(CONFIG)
    client = make_client(endpoint_from_config(config, "generator"))
    try:
        for index, call in enumerate(sorted(calls, key=lambda row: (row["within_state_call_order"], row["qualification_case_id"])), 1):
            if call["physical_call_id"] in completed:
                continue
            case = cases[call["qualification_case_id"]]
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
                "qualification_case_id": call["qualification_case_id"],
                "state_id": call["state_id"],
                "split_group_key": call["split_group_key"],
                "qualification_class_private": call["qualification_class_private"],
                "requested_action_id": call["requested_action_id"],
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
            if len(completed) % 8 == 0 or len(completed) == 64:
                print(f"MS executor qualification {len(completed)}/64", flush=True)
    finally:
        client.close()

    completed_rows = list(completed.values())
    report = {
        "protocol": PROTOCOL,
        "status": "MS_EXECUTOR_QUALIFICATION_GENERATION_COMPLETE_OFFLINE_SOURCE_AWARE_MEASUREMENT_REQUIRED" if len(completed_rows) == 64 else "MS_EXECUTOR_QUALIFICATION_GENERATION_INCOMPLETE",
        "logical_primary_calls_completed": len(completed_rows),
        "raw_transport_attempt_rows": len(raw_records),
        "execution_status_counts": dict(Counter(row["execution_status"] for row in completed_rows)),
        "guard_error_counts": dict(Counter(error for row in completed_rows for error in row["guard_errors"])),
        "requested_planned_exact": sum(row["requested_action_accounting"] == row["structurally_eligible_action_id"] == row["jointly_planned_action_id"] for row in completed_rows),
        "safe_personal_nonuse": sum(row["execution_status"] == "clean_safe_personal_nonuse" for row in completed_rows),
        "contamination_retries": sum(row["semantic_calls_made"] == 2 for row in completed_rows),
        "pm_refits": 0,
        "MP_ME_work": False,
        "teacher_class_provider_visible": False,
        "quality_risk_function_concluded": False,
        "artifacts": {
            "results": {"path": str((OUT / "generator_results_private.jsonl").relative_to(ROOT)), "sha256": sha256_file(OUT / "generator_results_private.jsonl")},
            "raw": {"path": str((OUT / "raw_provider_attempts_before_guard.jsonl").relative_to(ROOT)), "sha256": sha256_file(OUT / "raw_provider_attempts_before_guard.jsonl")},
        },
        "next": "ZERO_API_SOURCE_AWARE_EXECUTOR_QUALIFICATION_MEASUREMENT",
    }
    write_json(OUT / "live_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
