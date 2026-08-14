#!/usr/bin/env python3
"""Run the exact fresh-identity RS ESConv quality/risk blind measurement."""

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
from metacom_pm.v1_5_rs_ms_quality_risk_blind_review import RSMSQualityBlindReview, RSMSRiskBlindReview  # noqa: E402


STAGE = "paper1_rs_esconv_quality_risk_measurement_v1"
AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
BUNDLE = ROOT / "data/pm_v1_5_contracts/paper1_active_execution_bundle_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_rs_esconv_quality_risk_measurement_execution_phase_v1.json"
CONFIG = ROOT / "configs/paper1_rs_esconv_quality_risk_measurement_execution_v1.json"
ENDPOINTS = ROOT / "configs/paper1_rs_ms_quality_risk_measurement_endpoints_v1.json"
PREFLIGHT = ROOT / "outputs/pm_v1_5_paper1_rs_esconv_quality_risk_measurement_preflight_20260812"
PLAN = PREFLIGHT / "call_plan_private.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_rs_esconv_quality_risk_measurement_live_20260812"
USD_CAP = 0.7
SCHEMAS = {"quality": RSMSQualityBlindReview, "risk": RSMSRiskBlindReview}


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
        anthropic_strict_tool_use=bool(raw.get("anthropic_strict_tool_use", False)),
        gemini_thinking_budget=(int(raw["gemini_thinking_budget"]) if raw.get("gemini_thinking_budget") is not None else None),
        openai_reasoning_effort=(str(raw["openai_reasoning_effort"]) if raw.get("openai_reasoning_effort") is not None else None),
    )


def _require_authority() -> dict[str, Any]:
    authority = read_json(AUTHORITY)
    bundle = read_json(BUNDLE)
    current = authority["current_execution_phase"]
    expected_bundle = {"path": str(BUNDLE.relative_to(ROOT)), "sha256": sha256_file(BUNDLE)}
    expected_phase = {"path": str(PHASE.relative_to(ROOT)), "sha256": sha256_file(PHASE)}
    if current["id"] != "RS_ESCONV_QUALITY_RISK_MEASUREMENT_EXECUTION" or current["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("RS ESConv quality/risk measurement execution is not current")
    if bundle["current_phase"]["id"] != "RS_ESCONV_QUALITY_RISK_MEASUREMENT_EXECUTION" or bundle["current_phase"]["parent_phase"] != expected_phase:
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
    endpoint_records = read_json(ENDPOINTS)["candidates"]
    for call in calls:
        if call["messages_sha256"] != sha256_text(canonical_json(call["messages"])):
            raise RuntimeError(f"prompt drift: {call['logical_call_id']}")
        schema_cls = SCHEMAS[call["kind"]]
        if call["schema_sha256"] != sha256_text(canonical_json(schema_cls.model_json_schema())):
            raise RuntimeError("schema drift")
    dry = {
        "status": f"LIVE_READY_EXACT_{len(calls)}_RS_ESCONV_QUALITY_RISK_CALLS",
        "logical_calls": len(calls),
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

    results: list[dict[str, Any]] = []
    raw: list[dict[str, Any]] = []
    if OUT.exists():
        existing_results = read_jsonl(OUT / "results_private.jsonl") if (OUT / "results_private.jsonl").exists() else []
        existing_raw = read_jsonl(OUT / "raw_provider_outputs_before_local_validation.jsonl") if (OUT / "raw_provider_outputs_before_local_validation.jsonl").exists() else []
        plan_ids = [call["logical_call_id"] for call in calls]
        existing_ids = [row["logical_call_id"] for row in existing_results]
        if existing_ids != plan_ids[: len(existing_ids)]:
            raise RuntimeError("existing partial results do not match the authorized call plan prefix")
        results = existing_results
        raw = existing_raw
        calls = calls[len(existing_results):]
        if not calls:
            print(json.dumps({"status": "ALREADY_COMPLETE", "logical_calls": len(results)}, ensure_ascii=False, indent=2))
            return
    else:
        OUT.mkdir(parents=True)

    clients: dict[str, Any] = {}
    try:
        for index, call in enumerate(calls, len(results) + 1):
            endpoint_key = call["endpoint_key"]
            schema_cls = SCHEMAS[call["kind"]]
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
                    response_schema=schema_cls,
                    retries=2,
                )
                raw.append({
                    "protocol": "pm-v1.5-paper1-rs-esconv-quality-risk-measurement-raw-v1",
                    "logical_call_id": call["logical_call_id"],
                    "kind": call["kind"],
                    "reviewer_id": call["reviewer_id"],
                    "item_id": call["item_id"],
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
                expected_id_field = "pair_id" if call["kind"] == "quality" else "item_id"
                if getattr(parsed, expected_id_field) != call["item_id"]:
                    raise ValueError("item_id_mismatch")
                validated = parsed.model_dump(mode="json")
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
            results.append({
                "protocol": "pm-v1.5-paper1-rs-esconv-quality-risk-measurement-result-v1",
                "logical_call_id": call["logical_call_id"],
                "kind": call["kind"],
                "reviewer_id": call["reviewer_id"],
                "endpoint_key": endpoint_key,
                "item_id": call["item_id"],
                "messages_sha256": call["messages_sha256"],
                "schema_valid_and_locally_validated": validated is not None,
                "validated_review": validated,
                "error": error,
                "usage": result.usage if result is not None else {},
                "latency_ms": result.latency_ms if result is not None else None,
                "finish_reason": result.normalized_finish_reason if result is not None else "exception_before_result",
            })
            write_jsonl(OUT / "results_private.jsonl", results)
            print(f"RS ESConv quality/risk measurement {len(results)} kind={call['kind']} valid={validated is not None}", flush=True)
    finally:
        for client in clients.values():
            client.close()

    usage = {
        key: sum(int((row.get("usage") or {}).get(key, 0) or 0) for row in results)
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
    }
    complete = len(results) == len({row["logical_call_id"] for row in read_jsonl(PLAN)})
    report = {
        "protocol": "pm-v1.5-paper1-rs-esconv-quality-risk-measurement-live-report-v1",
        "status": "MEASUREMENT_CALLS_COMPLETE_ZERO_API_ANALYSIS_NEXT" if complete else "MEASUREMENT_CALLS_INCOMPLETE",
        "logical_calls": len(results),
        "valid_results": sum(row["schema_valid_and_locally_validated"] for row in results),
        "usage": usage,
        "next": "ZERO_API_DEBLIND_AND_ANALYZE",
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not complete:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
