#!/usr/bin/env python3
"""Run the frozen MS same-stack physical calls with raw-first persistence."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import statistics
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.api import RetryableProviderError, make_client  # noqa: E402
from metacom_pm.config import endpoint_from_config, load_config  # noqa: E402
from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_memory_response_plan_v2 import (  # noqa: E402
    build_memory_response_plan,
    execute_memory_response,
)
from metacom_pm.v1_5_memory_realization_v2 import build_joint_composition_plan  # noqa: E402
from metacom_pm.v1_5_ms_same_stack_feasibility import SameStackGeneratorOutput  # noqa: E402


PROTOCOL = "pm-v1.5-paper1-ms-same-stack-generation-v1"
AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_ms_same_stack_live_execution_phase_v1.json"
PREFLIGHT = ROOT / "outputs/pm_v1_5_paper1_ms_same_stack_preflight_20260811"
PLAN = PREFLIGHT / "physical_call_plan_private.jsonl"
ALIASES = PREFLIGHT / "logical_policy_aliases_private.jsonl"
PREFLIGHT_REPORT = PREFLIGHT / "report.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_ms_same_stack_generation_20260811"
USD_CAP = 0.05


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


class RawPersistingClient:
    def __init__(self, client, *, call: dict[str, Any], raw_rows: dict[str, dict[str, Any]]):
        self.client = client
        self.call = call
        self.raw_rows = raw_rows
        self.last_success: dict[str, Any] | None = None

    def chat(self, messages, *, response_schema):
        last_error: Exception | None = None
        for attempt in (1, 2):
            try:
                result, parsed = self.client.chat(
                    messages,
                    temperature=float(self.call["temperature"]),
                    max_tokens=int(self.call["max_output_tokens"]),
                    seed=int(self.call["seed"]),
                    response_schema=response_schema,
                    retries=1,
                )
                record = {
                    "protocol": PROTOCOL,
                    "physical_call_id": self.call["physical_call_id"],
                    "attempt": attempt,
                    "succeeded": parsed is not None,
                    "request_hash": result.request_hash,
                    "usage": result.usage,
                    "latency_ms": result.latency_ms,
                    "finish_reason": result.normalized_finish_reason,
                    "raw_structured_provider_reply_before_guard": parsed.model_dump(mode="json") if parsed is not None else None,
                    "error": None if parsed is not None else "provider returned no parsed structured output",
                }
                self.raw_rows[f"{self.call['physical_call_id']}:{attempt}"] = record
                write_jsonl(OUT / "raw_provider_attempts_before_guard.jsonl", list(self.raw_rows.values()))
                self.last_success = record
                return result, parsed
            except Exception as exc:
                last_error = exc
                retry_class = getattr(exc, "last_retry_class", None)
                retryable = isinstance(exc, RetryableProviderError) and retry_class in {
                    "rate_limited_429", "request_timeout_408", "http_5xx", "network_timeout"
                }
                record = {
                    "protocol": PROTOCOL,
                    "physical_call_id": self.call["physical_call_id"],
                    "attempt": attempt,
                    "succeeded": False,
                    "request_hash": getattr(exc, "request_hash", None),
                    "usage": getattr(exc, "usage", None) or {},
                    "latency_ms": None,
                    "finish_reason": "transport_retry" if retryable and attempt == 1 else "transport_failure",
                    "raw_structured_provider_reply_before_guard": None,
                    "retry_class": retry_class,
                    "error": f"{type(exc).__name__}: {exc}",
                }
                self.raw_rows[f"{self.call['physical_call_id']}:{attempt}"] = record
                write_jsonl(OUT / "raw_provider_attempts_before_guard.jsonl", list(self.raw_rows.values()))
                if not retryable or attempt == 2:
                    break
                time.sleep(max(float(getattr(exc, "retry_after_seconds", 0.0) or 0.0), 1.0))
        return last_error or RuntimeError("provider call failed"), None


def rebuild_plan(call: dict[str, Any]):
    on = call["feasible_action_id"] == "MS+R0"
    composition = build_joint_composition_plan(
        requested_action_id=call["requested_action_id"],
        realized_content={"MS": call["selected_exact_span"]} if on else {},
    )
    return build_memory_response_plan(
        composition=composition,
        current_goal="Respond supportively to the latest visible user message with one coherent low-burden reply.",
        current_user_id=call["runtime_owner_key"],
        evidence_ids={"MS": call["evidence_id"]} if on else {},
    )


def aggregate(completed: list[dict[str, Any]], aliases: list[dict[str, Any]]) -> dict[str, Any]:
    result_by_id = {row["physical_call_id"]: row for row in completed}
    logical = [
        {
            **alias,
            "arm": result_by_id[alias["physical_call_id"]]["arm"],
            "requested_action_id": result_by_id[alias["physical_call_id"]]["requested_action_id"],
            "feasible_action_id": result_by_id[alias["physical_call_id"]]["feasible_action_id"],
            "realized_action_id": result_by_id[alias["physical_call_id"]]["realized_action_id"],
            "execution_status": result_by_id[alias["physical_call_id"]]["execution_status"],
            "final_reply": result_by_id[alias["physical_call_id"]]["final_reply"],
            "guard_errors": result_by_id[alias["physical_call_id"]]["guard_errors"],
            "provider_usage": result_by_id[alias["physical_call_id"]]["provider_usage"],
        }
        for alias in aliases
    ]
    write_jsonl(OUT / "logical_policy_results_private.jsonl", logical)
    by_arm = defaultdict(list)
    for row in completed:
        by_arm[row["arm"]].append(row)
    def usage_value(row, key):
        return float((row.get("provider_usage") or {}).get(key) or 0)
    arm_summary = {}
    for arm, arm_rows in sorted(by_arm.items()):
        arm_summary[arm] = {
            "n": len(arm_rows),
            "clean": sum(row["execution_status"] == "clean" for row in arm_rows),
            "fallback": sum(row["execution_status"] != "clean" for row in arm_rows),
            "requested_realized_exact": sum(row["requested_action_id"] == row["realized_action_id"] for row in arm_rows),
            "input_tokens_sum": sum(usage_value(row, "prompt_tokens") + usage_value(row, "input_tokens") for row in arm_rows),
            "output_tokens_sum": sum(usage_value(row, "completion_tokens") + usage_value(row, "output_tokens") for row in arm_rows),
            "latency_ms_median": statistics.median([row["provider_latency_ms"] for row in arm_rows if row["provider_latency_ms"] is not None]) if any(row["provider_latency_ms"] is not None for row in arm_rows) else None,
        }
    pair_by_state = defaultdict(dict)
    for row in completed:
        pair_by_state[row["state_id"]][row["arm"]] = row
    exact_ties = sum(
        pair["ON"]["final_reply"].strip() == pair["OFF"]["final_reply"].strip()
        for pair in pair_by_state.values() if set(pair) == {"ON", "OFF"}
    )
    return {
        "protocol": PROTOCOL,
        "status": "MS_SAME_STACK_GENERATION_COMPLETE_BLIND_MEASUREMENT_MAY_BEGIN" if len(completed) == 136 else "MS_SAME_STACK_GENERATION_INCOMPLETE",
        "physical_calls_completed": len(completed),
        "logical_policy_results": len(logical),
        "arm_summary": arm_summary,
        "guard_error_counts": dict(Counter(error for row in completed for error in row["guard_errors"])),
        "provider_finish_reason_counts": dict(Counter(str(row["provider_finish_reason"]) for row in completed)),
        "paired_exact_reply_ties": exact_ties,
        "raw_provider_attempt_rows": len(rows(OUT / "raw_provider_attempts_before_guard.jsonl")),
        "PM_refit_or_threshold_change": False,
        "quality_risk_function_judged": False,
        "response_generation_api_calls": len(completed),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--accept-usd-cap", type=float)
    args = parser.parse_args()
    authority = read(AUTHORITY)
    live = authority["current_phase"]["system_feasibility_design_candidate"].get("live_execution") or {}
    if live.get("path") != str(PHASE.relative_to(ROOT)) or live.get("sha256") != sha256_file(PHASE):
        raise RuntimeError("same-stack live phase is not authority-bound")
    phase = read(PHASE)
    for binding in phase["input_bindings"] + phase["implementation_bindings"]:
        if sha256_file(ROOT / binding["path"]) != binding["sha256"]:
            raise RuntimeError(f"live phase binding drifted: {binding['path']}")
    preflight = read(PREFLIGHT_REPORT)
    if preflight["status"] != "MS_SAME_STACK_PREFLIGHT_PASS_LIVE_EXECUTION_MAY_BE_SEPARATELY_AUTHORIZED":
        raise RuntimeError("same-stack preflight did not pass")
    plan = rows(PLAN)
    aliases = rows(ALIASES)
    dry = {
        "protocol": PROTOCOL,
        "status": "LIVE_READY" if len(plan) == 136 and len(aliases) == 204 else "PLAN_INVALID",
        "physical_calls": len(plan),
        "logical_observations": len(aliases),
        "accepted_usd_cap_required": USD_CAP,
        "generator_price": "NVIDIA hosted prototype endpoint currently free; cap protects configuration drift",
        "api_calls": 0,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    write_json(OUT / "generation_preflight.json", dry)
    print(json.dumps(dry, ensure_ascii=False, indent=2), flush=True)
    if not args.live:
        return
    if args.accept_usd_cap is None or args.accept_usd_cap < USD_CAP:
        raise SystemExit(f"live execution requires --accept-usd-cap {USD_CAP:g}")
    config = load_config(ROOT / "configs/experiment.yaml")
    client = make_client(endpoint_from_config(config, "generator"))
    completed = {row["physical_call_id"]: row for row in rows(OUT / "generator_results_private.jsonl")}
    raw_attempts = {
        f"{row['physical_call_id']}:{row['attempt']}": row
        for row in rows(OUT / "raw_provider_attempts_before_guard.jsonl")
    }
    ordered = sorted(plan, key=lambda row: (int(row["within_state_call_order"]), row["state_id"]))
    try:
        for index, call in enumerate(ordered, start=1):
            call_id = call["physical_call_id"]
            if call_id in completed:
                continue
            wrapper = RawPersistingClient(client, call=call, raw_rows=raw_attempts)
            execution = execute_memory_response(
                wrapper,
                SameStackGeneratorOutput,
                call["messages"],
                rebuild_plan(call),
            )
            success = wrapper.last_success or {}
            completed[call_id] = {
                "protocol": PROTOCOL,
                "physical_call_id": call_id,
                "state_id": call["state_id"],
                "split_group_key": call["split_group_key"],
                "arm": call["arm"],
                "seed": call["seed"],
                "messages_sha256": call["messages_sha256"],
                "actual_rank1_id": call["actual_rank1_id"],
                "selected_exact_span": call["selected_exact_span"],
                "evidence_id": call["evidence_id"],
                "requested_action_id": execution.requested_action_id,
                "feasible_action_id": execution.feasible_action_id,
                "realized_action_id": execution.realized_action_id,
                "execution_status": execution.status,
                "guard_errors": list(execution.guard_errors),
                "final_reply": execution.response.reply,
                "final_used_evidence_ids": list(execution.response.used_evidence_ids),
                "reported_used_evidence_ids": list(execution.response.reported_used_evidence_ids),
                "provider_usage": success.get("usage") or {},
                "provider_latency_ms": success.get("latency_ms"),
                "provider_finish_reason": success.get("finish_reason") or "no_valid_completion",
                "raw_provider_output_persisted_before_guard": any(key.startswith(call_id + ":") for key in raw_attempts),
            }
            write_jsonl(OUT / "generator_results_private.jsonl", list(completed.values()))
            if len(completed) % 10 == 0 or len(completed) == 136:
                print(f"same-stack generation {len(completed)}/136", flush=True)
    finally:
        client.close()
    completed_rows = list(completed.values())
    report = aggregate(completed_rows, aliases)
    report["accepted_usd_cap"] = args.accept_usd_cap
    report["artifacts"] = {
        "generator_results": {"path": str((OUT / "generator_results_private.jsonl").relative_to(ROOT)), "sha256": sha256_file(OUT / "generator_results_private.jsonl")},
        "raw_attempts": {"path": str((OUT / "raw_provider_attempts_before_guard.jsonl").relative_to(ROOT)), "sha256": sha256_file(OUT / "raw_provider_attempts_before_guard.jsonl")},
        "logical_results": {"path": str((OUT / "logical_policy_results_private.jsonl").relative_to(ROOT)), "sha256": sha256_file(OUT / "logical_policy_results_private.jsonl")},
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
