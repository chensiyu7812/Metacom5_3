#!/usr/bin/env python3
"""Run the exact 12-call fresh-identity Gemini-thinking probe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.api import Endpoint, make_client  # noqa: E402
from metacom_pm.io import canonical_json, read_json, read_jsonl, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402
from metacom_pm.paid_run_release import require_paid_run_release  # noqa: E402
from metacom_pm.v1_5_ms_source_annotated_suitability_review import (  # noqa: E402
    MSSourceAnnotatedSuitabilityReview,
    validate_review,
)


STAGE = "paper1_ms_gemini_thinking_probe_v1"
AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
BUNDLE = ROOT / "data/pm_v1_5_contracts/paper1_active_execution_bundle_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_ms_gemini_thinking_probe_execution_phase_v1.json"
CONFIG = ROOT / "configs/paper1_ms_gemini_thinking_probe_execution_v1.json"
ENDPOINTS = ROOT / "configs/paper1_ms_gemini_thinking_endpoints_v1.json"
CONTROLS = ROOT / "outputs/pm_v1_5_paper1_ms_realistic_anchor_set_20260812/realistic_anchor_controls_blind.jsonl"
PLAN = ROOT / "outputs/pm_v1_5_paper1_ms_gemini_thinking_probe_preflight_20260812/call_plan_private.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_ms_gemini_thinking_probe_live_20260812"
USD_CAP = 0.75


def _endpoint(raw: dict[str, Any]) -> Endpoint:
    return Endpoint(
        base_url=str(raw["base_url"]),
        model=str(raw["model"]),
        api_key_env=str(raw["api_key_env"]),
        family=str(raw["family"]),
        transport=str(raw["transport"]),
        supports_strict_json_schema=bool(raw["supports_strict_json_schema"]),
        temperature_mode=str(raw.get("temperature_mode", "explicit")),
        max_output_tokens_parameter=str(raw.get("max_output_tokens_parameter", "max_tokens")),
        gemini_thinking_budget=(int(raw["gemini_thinking_budget"]) if raw.get("gemini_thinking_budget") is not None else None),
        openai_reasoning_effort=(str(raw["openai_reasoning_effort"]) if raw.get("openai_reasoning_effort") is not None else None),
    )


def _require_authority() -> dict[str, Any]:
    authority = read_json(AUTHORITY)
    bundle = read_json(BUNDLE)
    current = authority["current_execution_phase"]
    alias = authority["active_v3_phase"]
    expected_bundle = {"path": str(BUNDLE.relative_to(ROOT)), "sha256": sha256_file(BUNDLE)}
    expected_phase = {"path": str(PHASE.relative_to(ROOT)), "sha256": sha256_file(PHASE)}
    if current["id"] != "MS_GEMINI_THINKING_PROBE_EXECUTION" or current["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("gemini thinking probe execution is not current")
    if alias.get("compatibility_alias_of") != "current_execution_phase" or alias["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("authority alias drifted")
    if bundle["current_phase"]["id"] != "MS_GEMINI_THINKING_PROBE_EXECUTION" or bundle["current_phase"]["parent_phase"] != expected_phase:
        raise RuntimeError("bundle does not point at this execution phase")
    phase = read_json(PHASE)
    for binding in phase["input_bindings"]:
        if sha256_file(ROOT / binding["path"]) != binding["sha256"]:
            raise RuntimeError(f"bound input drifted: {binding['role']}")
    return phase


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--run-identity")
    parser.add_argument("--accept-usd-cap", type=float)
    args = parser.parse_args()
    phase = _require_authority()
    config = read_json(CONFIG)
    calls = read_jsonl(PLAN)
    controls = {row["repair_item_id"]: row for row in read_jsonl(CONTROLS)}
    endpoint_records = read_json(ENDPOINTS)["candidates"]
    if len(calls) != 12 or len({row["logical_call_id"] for row in calls}) != 12:
        raise RuntimeError("exact 12-call plan required")
    for call in calls:
        if call["messages_sha256"] != sha256_text(canonical_json(call["messages"])):
            raise RuntimeError(f"prompt drift: {call['logical_call_id']}")
        if call["schema_sha256"] != sha256_text(canonical_json(MSSourceAnnotatedSuitabilityReview.model_json_schema())):
            raise RuntimeError("schema drift")
    dry = {
        "status": "LIVE_READY_EXACT_12_GEMINI_THINKING_PROBE_CALLS",
        "logical_calls": 12,
        "maximum_physical_attempts": 24,
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
        raise RuntimeError(f"must accept exact cap {USD_CAP}")
    require_paid_run_release(config, config_path=CONFIG, stage=STAGE, run=True, run_identity=args.run_identity)
    if OUT.exists():
        raise RuntimeError("live output already exists; identity is one-shot")
    OUT.mkdir(parents=True)

    clients: dict[str, Any] = {}
    results: list[dict[str, Any]] = []
    raw: list[dict[str, Any]] = []
    try:
        for index, call in enumerate(calls, 1):
            endpoint_key = call["endpoint_key"]
            if endpoint_key not in clients:
                clients[endpoint_key] = make_client(_endpoint(endpoint_records[endpoint_key]))
            result = None
            parsed = None
            error = None
            validated = None
            try:
                result, parsed = clients[endpoint_key].chat(
                    call["messages"],
                    temperature=float(call["temperature"]),
                    max_tokens=int(call["max_output_tokens"]),
                    seed=int(call["seed"]),
                    response_schema=MSSourceAnnotatedSuitabilityReview,
                    retries=2,
                )
                raw.append({
                    "protocol": "pm-v1.5-paper1-ms-gemini-thinking-probe-raw-v1",
                    "logical_call_id": call["logical_call_id"],
                    "reviewer_id": call["reviewer_id"],
                    "repair_item_id": call["repair_item_id"],
                    "request_hash": result.request_hash,
                    "raw_text_before_validation": result.text,
                    "raw_response_before_validation": result.raw_response,
                    "parsed_before_local_validation": parsed.model_dump(mode="json") if parsed is not None else None,
                    "usage": result.usage,
                    "latency_ms": result.latency_ms,
                    "finish_reason": result.normalized_finish_reason,
                })
                write_jsonl(OUT / "raw_provider_outputs_before_local_validation.jsonl", raw)
                if parsed is None:
                    raise ValueError("provider returned no schema-valid output")
                validated = validate_review(parsed, controls[call["repair_item_id"]])
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
            results.append({
                "protocol": "pm-v1.5-paper1-ms-gemini-thinking-probe-result-v1",
                "logical_call_id": call["logical_call_id"],
                "reviewer_id": call["reviewer_id"],
                "endpoint_key": endpoint_key,
                "model": call["model"],
                "repair_item_id": call["repair_item_id"],
                "messages_sha256": call["messages_sha256"],
                "schema_valid_and_locally_validated": validated is not None,
                "validated_review": validated,
                "error": error,
                "usage": result.usage if result is not None else {},
                "latency_ms": result.latency_ms if result is not None else None,
                "finish_reason": result.normalized_finish_reason if result is not None else "exception_before_result",
            })
            write_jsonl(OUT / "control_results_private.jsonl", results)
            print(f"gemini thinking probe {index}/12 valid={validated is not None}", flush=True)
    finally:
        for client in clients.values():
            client.close()

    usage = {
        key: sum(int((row.get("usage") or {}).get(key, 0) or 0) for row in results)
        for key in ("input_tokens", "output_tokens", "total_tokens")
    }
    report = {
        "protocol": "pm-v1.5-paper1-ms-gemini-thinking-probe-live-report-v1",
        "status": "PROBE_CALLS_COMPLETE_ZERO_API_AUDIT_NEXT" if len(results) == 12 else "PROBE_CALLS_INCOMPLETE",
        "logical_calls": len(results),
        "valid_results": sum(row["schema_valid_and_locally_validated"] for row in results),
        "usage": usage,
        "training_labels_created_or_changed": 0,
        "public_201_calls": 0,
        "pm_fits": 0,
        "next": "ZERO_API_COMBINE_WITH_REUSED_GPT56_RESULT_AND_AUDIT",
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if len(results) != 12:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
