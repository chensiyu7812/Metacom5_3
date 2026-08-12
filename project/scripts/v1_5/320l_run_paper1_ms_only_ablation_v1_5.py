#!/usr/bin/env python3
"""Execute the exact hash-bound 19-call MS-only ablation."""

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


PROTOCOL = "pm-v1.5-paper1-ms-only-ablation-live-v1"
STAGE = "paper1_ms_only_ablation_v1"
AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
BUNDLE = ROOT / "data/pm_v1_5_contracts/paper1_active_execution_bundle_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_ms_only_ablation_execution_phase_v1.json"
CONFIG = ROOT / "configs/paper1_ms_only_ablation_execution_v1.json"
PREFLIGHT = ROOT / "outputs/pm_v1_5_paper1_ms_only_ablation_preflight_20260812"
CALLS = PREFLIGHT / "physical_call_plan_private.jsonl"
EXTERNAL_TEST_CASES = ROOT / "outputs/pm_v1_5_paper1_rs_ms_evoemo_external_test_preflight_20260812/qualification_cases_private.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_ms_only_ablation_live_20260812"
USD_CAP = 0.15
CURRENT_GOAL = "Respond supportively to the latest visible seeker turn. Advance its immediate emotional-support goal without inventing facts, overloading the reply, or assuming a past fact is still current."

MS_MEANING_CUE = (
    "Interpret the single strictly past user-owned source supplied below as a "
    "tentative continuity cue; do not treat it as current or quote it."
)
MS_ALLOWED_CHANGE = "If it materially helps, use the past meaning to acknowledge continuity or ask a more informed current-oriented question."
MS_FORBIDDEN = "Do not copy the user's first-person wording, assume the past remains true, infer a trait or cause, or expose a memory record."


def require_authority() -> dict[str, Any]:
    authority = read_json(AUTHORITY)
    bundle = read_json(BUNDLE)
    current = authority["current_execution_phase"]
    expected_bundle = {"path": str(BUNDLE.relative_to(ROOT)), "sha256": sha256_file(BUNDLE)}
    if current["id"] != "MS_ONLY_ABLATION_EXECUTION" or current["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("MS-only ablation execution is not current")
    if bundle["current_phase"]["id"] != "MS_ONLY_ABLATION_EXECUTION":
        raise RuntimeError("bundle does not point at this execution phase")
    phase = read_json(PHASE)
    for binding in phase["input_bindings"]:
        if sha256_file(ROOT / binding["path"]) != binding["sha256"]:
            raise RuntimeError(f"bound input drifted: {binding['role']}")
    return phase


def rebuild_plan(case: dict[str, Any]):
    candidates: dict[str, V3Candidate | None] = {c: None for c in ("MP", "MS", "ME", "RS")}
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
    return build_component_general_plan_v3(
        requested_action_id="MS+R0",
        current_user_id=case["runtime_owner_key"],
        candidates=candidates,
        pair_relations=None,
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
    cases = {row["case_id"]: row for row in read_jsonl(EXTERNAL_TEST_CASES)}
    calls = read_jsonl(CALLS)
    if len(calls) != 19:
        raise RuntimeError("exact 19-call plan required")
    for call in calls:
        case = cases[call["case_id"]]
        messages = response_generation_messages_v3(current_context=case["current_context"], current_goal=CURRENT_GOAL, plan=rebuild_plan(case))
        if sha256_text(canonical_json(messages)) != call["messages_sha256"]:
            raise RuntimeError(f"provider-visible prompt drift: {call['physical_call_id']}")

    dry = {
        "protocol": PROTOCOL,
        "status": "LIVE_READY_EXACT_19_MS_ONLY_ABLATION_CALLS",
        "logical_calls": 19,
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
        for call in sorted(calls, key=lambda row: row["case_id"]):
            if call["physical_call_id"] in completed:
                continue
            case = cases[call["case_id"]]
            plan = rebuild_plan(case)
            wrapper = FrozenCallClient(client, call, raw_records)
            execution = execute_response_program_v3(
                client=wrapper,
                response_schema=SameStackGeneratorOutput,
                current_context=case["current_context"],
                current_goal=CURRENT_GOAL,
                plan=plan,
                raw_persist=lambda _attempt, _raw: None,
            )
            result = wrapper.last_result
            completed[call["physical_call_id"]] = {
                "protocol": PROTOCOL,
                "physical_call_id": call["physical_call_id"],
                "case_id": call["case_id"],
                "state_id": call["state_id"],
                "requested_action_id": call["requested_action_id"],
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
            }
            write_jsonl(OUT / "generator_results_private.jsonl", list(completed.values()))
            print(f"MS-only ablation {len(completed)}/19", flush=True)
    finally:
        client.close()

    completed_rows = list(completed.values())
    status_counts: dict[str, int] = {}
    for row in completed_rows:
        status_counts[row["execution_status"]] = status_counts.get(row["execution_status"], 0) + 1
    complete = len(completed_rows) == 19
    report = {
        "protocol": PROTOCOL,
        "status": "MS_ONLY_ABLATION_COMPLETE_ZERO_API_MEASUREMENT_NEXT" if complete else "MS_ONLY_ABLATION_INCOMPLETE",
        "logical_calls_completed": len(completed_rows),
        "execution_status_counts": status_counts,
        "api_calls": 0,
        "pm_refits": 0,
        "next": "ZERO_API_QUALITY_RISK_MEASUREMENT_DESIGN",
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not complete:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
