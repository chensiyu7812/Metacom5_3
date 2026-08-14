#!/usr/bin/env python3
"""Continue the sole G4B2 HTTP-529 no-completion call; never rerun successes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.api import Endpoint, ProviderRequestError, RetryableProviderError, StructuredOutputValidationError, make_client  # noqa: E402
from metacom_pm.io import append_jsonl, canonical_json, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402
from metacom_pm.paid_run_release import require_paid_run_release  # noqa: E402
from metacom_pm.v1_5_g4b_anchored_review_v2 import G4BSuitabilityReview, prompt_messages, validate_review  # noqa: E402


ITEM_ID = "g4review_018c774d40263c714d3a2a4b"
REVIEWER_ID = "REVIEWER_A"
CONFIG = ROOT / "configs/paper1_v3_g4b2_mp_public_529_continuation_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_v3_g4b2_mp_public_529_continuation_phase_v1.json"
AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
ENDPOINTS = ROOT / "configs/pm_v1_5_strict_judge_bakeoff_v1.json"
PLAN = ROOT / "outputs/pm_v1_5_paper1_v3_g4b2_mp_public_preflight_v2_20260811/call_plan.jsonl"
PACKET = ROOT / "outputs/pm_v1_5_paper1_v3_g4a_packet_v2_20260811/reviewer_a_packet.jsonl"
ORIGINAL = ROOT / "outputs/pm_v1_5_paper1_v3_g4b2_mp_public_reviews_20260811"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_g4b2_mp_public_529_continuation_20260811"
STAGE = "paper1_v3_g4b2_mp_public_529_no_completion_continuation_v1"


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def endpoint(raw: dict[str, Any]) -> Endpoint:
    return Endpoint(
        base_url=raw["base_url"], model=raw["model"], api_key_env=raw["api_key_env"],
        timeout_seconds=240.0, family=raw["family"], transport=raw["transport"],
        supports_strict_json_schema=raw["supports_strict_json_schema"],
        temperature_mode=raw.get("temperature_mode") or "explicit",
        max_output_tokens_parameter=raw.get("max_output_tokens_parameter") or "max_tokens",
        anthropic_strict_tool_use=bool(raw.get("anthropic_strict_tool_use", False)),
        openai_reasoning_effort=raw.get("openai_reasoning_effort"),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-identity", required=True)
    parser.add_argument("--accept-usd-cap", type=float, required=True)
    args = parser.parse_args()
    phase = read(PHASE)
    authority = read(AUTHORITY)
    if authority["active_v3_phase"]["id"] != "G4B2_MP_PUBLIC_529_NO_COMPLETION_CONTINUATION":
        raise RuntimeError("continuation is not active")
    active_binding = authority["active_v3_phase"]["active_phase_manifest"]
    if active_binding["path"] != str(PHASE.relative_to(ROOT)) or active_binding["sha256"] != sha256_file(PHASE):
        raise RuntimeError("active continuation phase binding drifted")
    for binding in [*phase["input_bindings"], *phase["implementation_bindings"]]:
        if sha256_file(ROOT / binding["path"]) != binding["sha256"]:
            raise RuntimeError(f"binding drifted: {binding['path']}")
    cap = float(phase["execution"]["absolute_usd_cap"])
    if args.accept_usd_cap != cap:
        raise RuntimeError("must accept exact continuation cap")
    config = read(CONFIG)
    require_paid_run_release(config, config_path=CONFIG, stage=STAGE, run=True, run_identity=args.run_identity)

    original_raw = [row for row in rows(ORIGINAL / "raw_physical_attempts.jsonl") if row["review_item_id"] == ITEM_ID]
    original_valid = [row for row in rows(ORIGINAL / "reviewer_a_public_reviews.jsonl") if row["review_item_id"] == ITEM_ID]
    if len(original_raw) != 1 or original_valid or original_raw[0]["provider_text"] is not None or (original_raw[0]["raw_response"] or {}).get("status_code") != 529:
        raise RuntimeError("source is not the exact sole HTTP-529 no-completion case")
    plan = next(row for row in rows(PLAN) if row["review_item_id"] == ITEM_ID and row["reviewer_id"] == REVIEWER_ID)
    item = next(row for row in rows(PACKET) if row["review_item_id"] == ITEM_ID)
    messages = prompt_messages(item, REVIEWER_ID)
    if sha256_text(canonical_json(messages)) != plan["prompt_sha256"]:
        raise RuntimeError("prompt drifted")

    OUT.mkdir(parents=True, exist_ok=False)
    endpoints = read(ENDPOINTS)
    raw_ep = endpoints["candidates"][plan["endpoint_key"]]
    client = make_client(endpoint(raw_ep))
    result = None
    try:
        for attempt in (1, 2):
            call = None
            error: BaseException | None = None
            try:
                call, parsed = client.chat(
                    messages, temperature=0.0, max_tokens=500,
                    seed=int(plan["request_parameters"]["seed"]),
                    response_schema=G4BSuitabilityReview, retries=1,
                )
            except (StructuredOutputValidationError, RetryableProviderError, ProviderRequestError) as exc:
                error = exc
                call = getattr(exc, "call", None)
            append_jsonl(OUT / "raw_physical_attempts.jsonl", {
                "protocol": "pm-v1.5-paper1-v3-g4b2-529-continuation-raw-v1",
                "attempt_index": attempt, "reviewer_id": REVIEWER_ID, "review_item_id": ITEM_ID,
                "request_hash": getattr(call, "request_hash", None) or getattr(error, "request_hash", None),
                "provider_text": getattr(call, "text", None) or getattr(error, "provider_text", None),
                "usage": getattr(call, "usage", None) or getattr(error, "usage", None),
                "error_type": type(error).__name__ if error else None, "error": str(error) if error else None,
                "response_diagnostics": getattr(error, "response_diagnostics", None),
            })
            if error is None and call is not None:
                try:
                    result = validate_review(parsed, item)
                except ValueError:
                    break
                result.update({
                    "protocol": "pm-v1.5-paper1-v3-g4b2-529-continuation-result-v1",
                    "reviewer_id": REVIEWER_ID, "component": "MP", "call_stage": "PUBLIC",
                    "endpoint_key": plan["endpoint_key"], "model": plan["model"],
                    "request_hash": call.request_hash,
                    "raw_response_text_sha256": hashlib.sha256(call.text.encode()).hexdigest(),
                    "review_position": plan["review_position"],
                })
                write_jsonl(OUT / "review.jsonl", [result])
                break
            if not isinstance(error, RetryableProviderError) or error.last_retry_class not in {"http_5xx", "network_timeout", "rate_limited_429", "request_timeout_408"}:
                break
    finally:
        client.close()
    attempts = rows(OUT / "raw_physical_attempts.jsonl")
    report = {
        "protocol": "pm-v1.5-paper1-v3-g4b2-529-continuation-report-v1",
        "status": "G4B2_MP_PUBLIC_529_CONTINUATION_COMPLETE" if result else "G4B2_MP_PUBLIC_529_CONTINUATION_INCOMPLETE",
        "source_had_no_completion": True, "source_407_successes_rerun": 0,
        "logical_calls": 1, "physical_attempts": len(attempts), "completed_valid_reviews": int(result is not None),
        "private_mapping_read": False, "labels_created": 0,
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
