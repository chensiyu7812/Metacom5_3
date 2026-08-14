#!/usr/bin/env python3
"""Run the exact approved fair-generator judge qualification canary."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from metacom_pm.api import Endpoint, make_client  # noqa: E402
from metacom_pm.v3_generator_fair_judge import AbsoluteGuardrailReview, EIAPairReview  # noqa: E402

AUTHORITY = PROJECT_ROOT / "data" / "v3_authority"
PREFLIGHT = AUTHORITY / "g0_fair_judge_canary_preflight_v1.json"
ENDPOINTS = PROJECT_ROOT / "configs" / "paper1_rs_ms_quality_risk_measurement_endpoints_v1.json"
MANIFEST = PROJECT_ROOT / "outputs" / "v3_g0_fair_judge_canary_manifest_20260814" / "calls_private.jsonl"
DEFAULT_OUT = PROJECT_ROOT / "outputs" / "v3_g0_fair_judge_canary_live_20260814"
SCHEMAS = {"EIAPairReview": EIAPairReview, "AbsoluteGuardrailReview": AbsoluteGuardrailReview}


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(canonical(row) + "\n" for row in rows), encoding="utf-8")


def endpoint(raw: dict[str, Any]) -> Endpoint:
    return Endpoint(
        base_url=raw["base_url"], model=raw["model"], api_key_env=raw["api_key_env"],
        family=raw["family"], transport=raw["transport"],
        supports_strict_json_schema=raw["supports_strict_json_schema"],
        temperature_mode=raw.get("temperature_mode", "explicit"),
        max_output_tokens_parameter=raw.get("max_output_tokens_parameter", "max_tokens"),
        openai_reasoning_effort=raw.get("openai_reasoning_effort"),
    )


def observed_cost(rows: list[dict[str, Any]], config: dict[str, Any]) -> float:
    prompt = sum(int((row.get("usage") or {}).get("prompt_tokens") or 0) for row in rows)
    completion = sum(int((row.get("usage") or {}).get("completion_tokens") or 0) for row in rows)
    return prompt * float(config["input_usd_per_million_tokens"]) / 1_000_000 + completion * float(config["output_usd_per_million_tokens"]) / 1_000_000


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approved-identity", required=True)
    parser.add_argument("--max-usd", required=True, type=float)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    preflight = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    if preflight["status"] != "ZERO_CALL_PREFLIGHT_PASS_IDENTITY_SPECIFIC_APPROVAL_REQUIRED":
        raise RuntimeError("this judge canary was superseded before calls and cannot run")
    calls = read_jsonl(MANIFEST)
    if args.approved_identity != preflight["run_identity"]:
        raise RuntimeError("approved identity does not match the frozen judge canary")
    if args.max_usd <= 0:
        raise ValueError("max-usd must be positive")
    if sha_file(MANIFEST) != preflight["private_manifest_hashes"]["calls"] or len(calls) != 144:
        raise RuntimeError("private call manifest drifted")
    dry = {"status": "LIVE_READY", "run_identity": preflight["run_identity"], "logical_calls": len(calls), "max_usd": args.max_usd, "api_calls": 0}
    print(json.dumps(dry, indent=2), flush=True)
    if not args.live:
        return 0

    config = json.loads(ENDPOINTS.read_text(encoding="utf-8"))["candidates"]["openai_gpt_5_6_sol"]
    completed_rows = read_jsonl(args.out / "results_private.jsonl")
    raw_rows = read_jsonl(args.out / "raw_provider_outputs.jsonl")
    if any(row.get("run_identity") != preflight["run_identity"] for row in completed_rows + raw_rows):
        raise RuntimeError("existing output contains a different identity")
    completed = {row["logical_call_id"]: row for row in completed_rows}
    raw = {row["logical_call_id"]: row for row in raw_rows}
    client = make_client(endpoint(config))
    consecutive_failures = 0
    try:
        for call in calls:
            logical_id = call["logical_call_id"]
            if logical_id in completed:
                continue
            max_tokens = 500
            prompt_token_reserve = sum(len(message["content"]) for message in call["messages"]) / 3
            reserve_usd = prompt_token_reserve * float(config["input_usd_per_million_tokens"]) / 1_000_000 + max_tokens * float(config["output_usd_per_million_tokens"]) / 1_000_000
            spent = observed_cost(list(raw.values()), config)
            if spent + reserve_usd > args.max_usd:
                raise RuntimeError(f"approved ceiling cannot reserve the next call: spent={spent:.6f}, reserve={reserve_usd:.6f}, ceiling={args.max_usd:.6f}")
            schema = SCHEMAS[call["schema"]]
            validated = None
            error = None
            try:
                result, parsed = client.chat(call["messages"], temperature=0.0, max_tokens=max_tokens, seed=20260814, response_schema=schema, retries=1)
                raw[logical_id] = {
                    "run_identity": preflight["run_identity"], "logical_call_id": logical_id,
                    "request_hash": result.request_hash, "raw_text": result.text,
                    "raw_response": result.raw_response, "usage": result.usage,
                    "latency_ms": result.latency_ms, "finish_reason": result.normalized_finish_reason,
                }
                write_jsonl(args.out / "raw_provider_outputs.jsonl", list(raw.values()))
                if parsed is None:
                    raise ValueError("provider returned no schema-valid object")
                expected_id = logical_id
                observed_id = parsed.unit_id if call["schema"] == "EIAPairReview" else parsed.item_id
                if observed_id != expected_id:
                    raise ValueError("echoed id mismatch")
                if call["schema"] == "EIAPairReview" and parsed.eia_construct != call["construct"]:
                    raise ValueError("construct mismatch")
                validated = parsed.model_dump(mode="json")
                consecutive_failures = 0
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}: {exc}"
                consecutive_failures += 1
            completed[logical_id] = {
                "run_identity": preflight["run_identity"], "logical_call_id": logical_id,
                "kind": call["kind"], "screen_id": call["screen_id"], "construct": call["construct"],
                "orientation": call["orientation"], "repeat_of": call["repeat_of"],
                "schema_valid_and_locally_validated": validated is not None,
                "validated_review": validated, "error": error,
            }
            write_jsonl(args.out / "results_private.jsonl", list(completed.values()))
            print(f"judge {len(completed)}/144 kind={call['kind']} valid={validated is not None} spent_usd={observed_cost(list(raw.values()), config):.6f}", flush=True)
            if consecutive_failures >= 5:
                raise RuntimeError("five consecutive judge failures")
    finally:
        client.close()
    summary = {
        "protocol": "metacom-v3-g0-fair-judge-canary-live-v1",
        "status": f"LIVE_COMPLETE_{len(completed)}_OF_144",
        "run_identity": preflight["run_identity"],
        "completed": len(completed), "valid": sum(row["schema_valid_and_locally_validated"] for row in completed.values()),
        "actual_usd": observed_cost(list(raw.values()), config),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
