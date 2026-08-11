#!/usr/bin/env python3
"""Recover first replies after fixing trace-only telemetry responsibility in V3."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_ms_same_stack_feasibility import SameStackGeneratorOutput  # noqa: E402
from metacom_pm.v1_5_response_program_v3 import execute_response_program_v3  # noqa: E402


RUNNER_PATH = ROOT / "scripts/v1_5/232l_run_paper1_v3_ms_executor_qualification_v1_5.py"
spec = importlib.util.spec_from_file_location("frozen_ms_executor_runner", RUNNER_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot import frozen MS executor plan reconstruction")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

PREFLIGHT = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_qualification_preflight_v3_20260811"
CASES = PREFLIGHT / "qualification_cases_private.jsonl"
CALLS = PREFLIGHT / "physical_call_plan_private.jsonl"
LIVE = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_qualification_live_20260811"
RAW = LIVE / "raw_provider_attempts_before_guard.jsonl"
ORIGINAL = LIVE / "generator_results_private.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_trace_recovery_20260811"


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


@dataclass
class Parsed:
    payload: dict[str, Any]

    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        if mode != "json":
            raise ValueError("only JSON projection is supported")
        return self.payload


class FirstRawOnlyClient:
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload
        self.calls = 0

    def chat(self, messages, *, response_schema):
        self.calls += 1
        if self.calls > 1:
            raise RuntimeError("patched trace recovery unexpectedly requested regeneration")
        return {"offline_replay": True}, Parsed(self.payload)


def main() -> None:
    if OUT.exists():
        raise RuntimeError("trace recovery output exists; refusing overwrite")
    cases = {row["qualification_case_id"]: row for row in rows(CASES)}
    calls = {row["physical_call_id"]: row for row in rows(CALLS)}
    original = {row["physical_call_id"]: row for row in rows(ORIGINAL)}
    first_raw = {
        row["physical_call_id"]: row
        for row in rows(RAW)
        if row["semantic_call_number"] == 1 and row["succeeded"] is True
    }
    if not (len(cases) == 16 and len(calls) == len(original) == len(first_raw) == 64):
        raise RuntimeError("live first-response denominator is incomplete")

    recovered = []
    for call_id, call in calls.items():
        case = cases[call["qualification_case_id"]]
        payload = first_raw[call_id]["parsed_before_guard"]
        plan = runner.rebuild_plan(call, case)
        replay = FirstRawOnlyClient(payload)
        execution = execute_response_program_v3(
            client=replay,
            response_schema=SameStackGeneratorOutput,
            current_context=case["current_context"],
            current_goal=case["current_goal"],
            plan=plan,
            raw_persist=lambda _attempt, _raw: None,
        )
        if execution.calls_made != 1 or replay.calls != 1:
            raise RuntimeError(f"first response still requires a content-contamination retry: {call_id}")
        recovered.append(
            {
                "protocol": "pm-v1.5-paper1-v3-ms-executor-trace-recovered-result-v1",
                "physical_call_id": call_id,
                "qualification_case_id": call["qualification_case_id"],
                "state_id": call["state_id"],
                "split_group_key": call["split_group_key"],
                "qualification_class_private": call["qualification_class_private"],
                "negative_stratum_private": case["negative_stratum"],
                "requested_action_id": call["requested_action_id"],
                "seed": call["seed"],
                "first_raw_request_hash": first_raw[call_id]["request_hash"],
                "original_live_execution_status": original[call_id]["execution_status"],
                "recovered_execution_status": execution.status,
                "trace_errors_sanitized": list(execution.guard_errors),
                "final_reply": execution.response.reply,
                "sanitized_used_evidence_ids": list(execution.response.used_evidence_ids),
                "generator_claimed": dict(execution.accounting.generator_claimed),
                "semantic_calls_required_under_patched_v3": 1,
                "source_is_saved_first_raw_response": True,
            }
        )

    OUT.mkdir(parents=True)
    results_path = OUT / "recovered_first_response_results_private.jsonl"
    write_jsonl(results_path, recovered)
    statuses = Counter(row["recovered_execution_status"] for row in recovered)
    report = {
        "protocol": "pm-v1.5-paper1-v3-ms-executor-trace-only-recovery-report-v1",
        "status": "PASS_FIRST_RESPONSES_RECOVERED_ZERO_API_SOURCE_AWARE_MEASUREMENT_MAY_BEGIN",
        "rows": len(recovered),
        "original_content_retries_caused_only_by_trace": sum(row["original_live_execution_status"] == "clean_after_personal_resource_removal" for row in recovered),
        "recovered_status_counts": dict(statuses),
        "first_reply_content_contamination_requiring_retry": 0,
        "extra_paid_calls_reused_as_outcomes": 0,
        "recovery_rule": "Preserve the saved first natural-language reply; intersect generator telemetry with authorized evidence IDs; never interpret generator telemetry as function gold.",
        "scientific_boundary": {
            "quality_risk_function_scored": False,
            "pm_refit": False,
            "labels_changed": False,
            "MP_ME_work": False,
            "api_calls": 0,
        },
        "input_bindings": {
            "calls": sha256_file(CALLS),
            "cases": sha256_file(CASES),
            "raw": sha256_file(RAW),
            "original_results": sha256_file(ORIGINAL),
            "patched_response_program_v3": sha256_file(ROOT / "src/metacom_pm/v1_5_response_program_v3.py"),
            "frozen_plan_reconstruction": sha256_file(RUNNER_PATH),
        },
        "artifact": {"path": str(results_path.relative_to(ROOT)), "sha256": sha256_file(results_path)},
        "next": "ZERO_API_SOURCE_AWARE_FUNCTION_RISK_AND_PAIRED_QUALITY_MEASUREMENT_DESIGN",
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
