#!/usr/bin/env python3
"""Run the exact approved MS/MP V1.1 blind-review manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.api import Endpoint, make_client  # noqa: E402
from metacom_pm.config import load_config  # noqa: E402
from metacom_pm.io import read_json, read_jsonl, sha256_file, write_json, write_jsonl  # noqa: E402
from metacom_pm.paid_run_release import require_paid_run_release  # noqa: E402
from metacom_pm.v1_5_function_observability_v2_blind_review import FunctionObservabilityV2BlindReview  # noqa: E402
from metacom_pm.v1_5_mp_function_pair_blind_review import MPFunctionPairBlindReview  # noqa: E402
from metacom_pm.v1_5_rs_ms_quality_risk_blind_review import RSMSQualityBlindReview  # noqa: E402
from metacom_pm.v1_5_source_aware_risk_blind_review import SourceAwareRiskBlindReview  # noqa: E402

PROTOCOL = "pm-v1.5-paper1-ms-mp-v1-1-blind-review-live-v1"
STAGE = "paper1_ms_mp_v1_1_blind_review_v1"
STAGE_ID = "MS_MP_V1_1_BLIND_REVIEW_EXECUTION"
AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
BUNDLE = ROOT / "data/pm_v1_5_contracts/paper1_active_execution_bundle_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_ms_mp_v1_1_blind_review_execution_phase_v1.json"
CONFIG = ROOT / "configs/paper1_ms_mp_v1_1_blind_review_execution_v1.json"
MANIFEST = ROOT / "outputs/pm_v1_5_paper1_ms_mp_v1_1_blind_review_manifest_20260813"
OUT = ROOT / "outputs/pm_v1_5_paper1_ms_mp_v1_1_blind_review_live_20260813"
USD_CAP = 1.1
SAFE_KEYS = frozenset({"messages", "temperature", "max_output_tokens", "seed", "schema_sha256"})
SCHEMA = {
    "ms_quality": RSMSQualityBlindReview, "mp_quality": RSMSQualityBlindReview,
    "ms_risk": SourceAwareRiskBlindReview, "mp_risk": SourceAwareRiskBlindReview,
    "ms_function": FunctionObservabilityV2BlindReview,
    "mp_function_pair": MPFunctionPairBlindReview,
}
ID_FIELD = {
    "ms_quality": "pair_id", "mp_quality": "pair_id", "ms_risk": "item_id",
    "mp_risk": "item_id", "ms_function": "blind_item_id", "mp_function_pair": "pair_id",
}


def endpoint(raw: dict[str, Any]) -> Endpoint:
    return Endpoint(base_url=raw["base_url"], model=raw["model"], api_key_env=raw["api_key_env"],
        family=raw["family"], transport=raw["transport"],
        supports_strict_json_schema=raw["supports_strict_json_schema"],
        temperature_mode=raw.get("temperature_mode", "explicit"),
        max_output_tokens_parameter=raw.get("max_output_tokens_parameter", "max_tokens"),
        openai_reasoning_effort=raw.get("openai_reasoning_effort"))


def require_authority() -> dict[str, Any]:
    authority, bundle, phase = read_json(AUTHORITY), read_json(BUNDLE), read_json(PHASE)
    expected = {"path": str(BUNDLE.relative_to(ROOT)), "sha256": sha256_file(BUNDLE)}
    if authority["current_execution_phase"]["id"] != STAGE_ID or authority["current_execution_phase"]["active_phase_manifest"] != expected:
        raise RuntimeError("blind review execution is not current")
    if bundle["current_phase"]["id"] != STAGE_ID:
        raise RuntimeError("bundle does not point at blind review execution")
    for b in phase["bindings"]:
        if b["role"] != "execution_phase" and sha256_file(ROOT / b["path"]) != b["sha256"]:
            raise RuntimeError(f"bound input drifted: {b['role']}")
    return phase


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--live", action="store_true")
    ap.add_argument("--run-identity"); ap.add_argument("--accept-usd-cap", type=float); args = ap.parse_args()
    phase = require_authority()
    calls = read_jsonl(MANIFEST / "calls_private.jsonl")
    if len(calls) != 50 or any(set(c["public_call"]) != SAFE_KEYS for c in calls):
        raise RuntimeError("exact provider-safe 50-call plan required")
    dry = {"protocol": PROTOCOL, "status": "LIVE_READY_EXACT_50_BLIND_REVIEW_CALLS",
        "logical_calls": 50, "absolute_usd_cap": USD_CAP,
        "run_identity": phase["execution"]["run_identity"], "api_calls": 0}
    print(json.dumps(dry, ensure_ascii=False, indent=2), flush=True)
    if not args.live: return
    if args.run_identity != phase["execution"]["run_identity"] or args.accept_usd_cap != USD_CAP:
        raise RuntimeError("identity or exact cap mismatch")
    require_paid_run_release(read_json(CONFIG), config_path=CONFIG, stage=STAGE, run=True, run_identity=args.run_identity)
    OUT.mkdir(parents=True, exist_ok=True)
    completed = {r["logical_call_id"]: r for r in read_jsonl(OUT / "results_private.jsonl")} if (OUT / "results_private.jsonl").exists() else {}
    raw = {r["logical_call_id"]: r for r in read_jsonl(OUT / "raw_provider_outputs_before_validation.jsonl")} if (OUT / "raw_provider_outputs_before_validation.jsonl").exists() else {}
    ec = load_config(ROOT / "configs/paper1_rs_ms_quality_risk_measurement_endpoints_v1.json")["candidates"]["openai_gpt_5_6_sol"]
    client = make_client(endpoint(ec)); consecutive = 0
    try:
        for call in sorted(calls, key=lambda r: r["logical_call_id"]):
            if call["logical_call_id"] in completed: continue
            pub, schema = call["public_call"], SCHEMA[call["kind"]]
            validated = None; error = None
            try:
                result, parsed = client.chat(pub["messages"], temperature=pub["temperature"],
                    max_tokens=pub["max_output_tokens"], seed=pub["seed"], response_schema=schema, retries=2)
                raw[call["logical_call_id"]] = {"protocol": PROTOCOL, "logical_call_id": call["logical_call_id"],
                    "request_hash": result.request_hash, "raw_text_before_validation": result.text,
                    "raw_response_before_validation": result.raw_response,
                    "parsed_before_local_validation": parsed.model_dump(mode="json") if parsed else None,
                    "usage": result.usage, "latency_ms": result.latency_ms, "finish_reason": result.normalized_finish_reason}
                write_jsonl(OUT / "raw_provider_outputs_before_validation.jsonl", list(raw.values()))
                if parsed is None: raise ValueError("no schema-valid output")
                expected = call.get(ID_FIELD[call["kind"]])
                if getattr(parsed, ID_FIELD[call["kind"]]) != expected: raise ValueError("id mismatch")
                validated = parsed.model_dump(mode="json"); consecutive = 0
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}: {exc}"; consecutive += 1
            completed[call["logical_call_id"]] = {"protocol": PROTOCOL, "logical_call_id": call["logical_call_id"],
                "kind": call["kind"], "component": call["component"], "case_id": call["case_id"],
                "owner_cluster": call["owner_cluster"], "schema_valid_and_locally_validated": validated is not None,
                "validated_review": validated, "error": error}
            write_jsonl(OUT / "results_private.jsonl", list(completed.values()))
            print(f"judge {len(completed)}/50 kind={call['kind']} valid={validated is not None}", flush=True)
            if consecutive >= 5: raise RuntimeError("five consecutive failures")
    finally: client.close()
    summary = {"protocol": PROTOCOL, "status": f"LIVE_COMPLETE_{len(completed)}_OF_50",
        "run_identity": phase["execution"]["run_identity"], "completed": len(completed), "total": 50,
        "output_directory": str(OUT.relative_to(ROOT))}
    write_json(OUT / "summary.json", summary); print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__": main()
