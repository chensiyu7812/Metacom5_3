#!/usr/bin/env python3
"""Probe the frozen Paper-1 Generator through the reference streaming client.

This is a zero-outcome infrastructure probe, not an evaluator run.  It sends
one exact official-aligned QA/No-Memory request, measures same-process
monotonic send-to-first-visible-text and send-to-completion latency, and
retains only the response hash.  A deterministic HTTP rejection is never
retried.  Every live attempt is reserved in the cumulative paid-API ledger.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import canonical_json, read_json, sha256_file, sha256_text, utc_now, write_json  # noqa: E402
from metacom_pm.paper1.api_budget import (  # noqa: E402
    ApiBudgetReservation,
    CumulativePaper1ApiBudgetLedger,
)
from metacom_pm.paper1.contracts import (  # noqa: E402
    EndToEndLatencyRecord,
    LatencyMeasurementSurface,
    WarmState,
)
from metacom_pm.paper1.data.memory_source import (  # noqa: E402
    enumerate_targets,
    load_sanitized_runtime_users,
)
from metacom_pm.paper1.execution.rq2_prompts import build_static_rq2_request  # noqa: E402


MODEL = "meta/llama-3.1-8b-instruct"
BASE_URL = "https://integrate.api.nvidia.com"
STAGE = "token_call_latency_pilots"
STAGE_HARD_CAP_USD = Decimal("1.00")
PROBE_RESERVATION_USD = Decimal("0.01")
PROTOCOL = "paper1-frozen-generator-streaming-availability-probe-v1"


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--recover-interrupted-http-status",
        type=int,
        help=(
            "Settle and record an already-reserved attempt whose local error-body "
            "handler crashed after this observed HTTP status. Makes no network call."
        ),
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=PROJECT
        / "data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json",
    )
    parser.add_argument(
        "--catalog-snapshot",
        type=Path,
        default=Path("/tmp/paper1_nim_models.json"),
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=PROJECT / "outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=PROJECT
        / "outputs/paper1_reference_client_latency_pilot_v1/frozen_generator_probe.json",
    )
    return parser.parse_args()


def _request(source: Path) -> tuple[Any, dict[str, Any]]:
    users = load_sanitized_runtime_users(source)
    targets = enumerate_targets(users)
    target = next(target for target in targets if target.task_type.value == "qa")
    request = build_static_rq2_request(
        task_type=target.task_type,
        question=target.visible_query_text or "",
    )
    payload = {
        "model": MODEL,
        "messages": [message.model_dump(mode="json") for message in request.messages],
        "temperature": 0,
        "max_tokens": request.max_output_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    return (target, payload)


def _catalog_summary(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"available": False, "catalog_sha256": None, "model_listed": None}
    data = read_json(path)
    models = sorted(
        str(row.get("id"))
        for row in data.get("data", [])
        if isinstance(row, dict) and row.get("id")
    )
    return {
        "available": True,
        "catalog_sha256": sha256_file(path),
        "catalog_model_count": len(models),
        "model_listed": MODEL in models,
    }


def _stream_call(payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    send_ns = time.monotonic_ns()
    first_ns: int | None = None
    final_ns: int | None = None
    visible_parts: list[str] = []
    usage: dict[str, int] = {}
    finish_reason: str | None = None
    status_code: int | None = None
    response_headers: dict[str, str] = {}
    try:
        with httpx.Client(timeout=httpx.Timeout(180.0), http2=False) as client:
            with client.stream(
                "POST",
                f"{BASE_URL}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "text/event-stream",
                    "Content-Type": "application/json",
                },
                json=payload,
            ) as response:
                status_code = response.status_code
                response_headers = {
                    key: value
                    for key, value in response.headers.items()
                    if key.casefold()
                    in {"content-type", "date", "x-request-id", "nvapi-reqid"}
                }
                if response.status_code >= 400:
                    body = b"".join(response.iter_bytes())
                    final_ns = time.monotonic_ns()
                    return {
                        "status": "HTTP_REJECTED",
                        "status_code": response.status_code,
                        "terminal_ms": (final_ns - send_ns) / 1_000_000,
                        "response_body_sha256": sha256_text(
                            body.decode("utf-8", errors="replace")
                        ),
                        "retryable": response.status_code
                        in {408, 429, 500, 502, 503, 504},
                        "response_headers": response_headers,
                    }
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    body = line[5:].strip()
                    if not body or body == "[DONE]":
                        continue
                    chunk = json.loads(body)
                    if isinstance(chunk.get("usage"), dict):
                        usage = {
                            str(key): int(value)
                            for key, value in chunk["usage"].items()
                            if isinstance(value, int)
                        }
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    choice = choices[0]
                    if choice.get("finish_reason") is not None:
                        finish_reason = str(choice["finish_reason"])
                    delta = choice.get("delta") or {}
                    content = delta.get("content")
                    if isinstance(content, str) and content:
                        if first_ns is None:
                            first_ns = time.monotonic_ns()
                        visible_parts.append(content)
                final_ns = time.monotonic_ns()
    except Exception as exc:  # transport outcome must remain auditable
        final_ns = time.monotonic_ns()
        return {
            "status": "TRANSPORT_FAILED",
            "exception_type": type(exc).__name__,
            "exception_message_sha256": sha256_text(str(exc)),
            "terminal_ms": (final_ns - send_ns) / 1_000_000,
            "retryable": isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)),
        }

    text = "".join(visible_parts)
    return {
        "status": "SUCCEEDED",
        "status_code": status_code,
        "provider_request_to_first_content_ms": (
            (first_ns - send_ns) / 1_000_000 if first_ns is not None else None
        ),
        "provider_request_to_completion_ms": (final_ns - send_ns) / 1_000_000,
        "response_sha256": sha256_text(text),
        "visible_character_count": len(text),
        "usage": usage,
        "finish_reason": finish_reason or "unknown",
        "response_headers": response_headers,
        "retryable": False,
    }


def main() -> int:
    args = _args()
    target, payload = _request(args.source)
    call_hash = sha256_text(canonical_json(payload))
    preflight = {
        "protocol": PROTOCOL,
        "created_at": utc_now(),
        "mode": "LIVE" if args.live else "DRY_RUN",
        "zero_outcome_probe": True,
        "formal_outcome_calls": 0,
        "pm_training_runs": 0,
        "target_id": target.target_id,
        "task_type": target.task_type.value,
        "arm": "No_Memory",
        "provider": "NVIDIA hosted NIM",
        "base_url": BASE_URL,
        "model": MODEL,
        "temperature": 0,
        "max_output_tokens": 256,
        "stream": True,
        "stream_usage_requested": True,
        "request_messages_sha256": sha256_text(canonical_json(payload["messages"])),
        "physical_call_sha256": call_hash,
        "response_content_retained": False,
        "response_quality_inspected_or_scored": False,
        "catalog": _catalog_summary(args.catalog_snapshot),
        "budget": {
            "stage": STAGE,
            "researcher_authorized_incremental_hard_cap_usd": str(STAGE_HARD_CAP_USD),
            "maximum_probe_reservation_usd": str(PROBE_RESERVATION_USD),
            "retry_policy": "no retry for deterministic HTTP rejection; at most one separately reserved retry for retryable transport failure",
        },
    }
    if not args.live:
        write_json(args.out, preflight | {"status": "DRY_RUN_READY"})
        print(canonical_json(preflight | {"status": "DRY_RUN_READY"}))
        return 0

    if args.recover_interrupted_http_status is not None:
        ledger = CumulativePaper1ApiBudgetLedger(args.ledger)
        settled = ledger.settle(
            ApiBudgetReservation(
                reservation_id=f"{call_hash}:attempt:1",
                maximum_cost_usd=PROBE_RESERVATION_USD,
            ),
            actual_cost_usd=None,
            outcome="FAILED",
        )
        result = {
            "status": "HTTP_REJECTED",
            "status_code": args.recover_interrupted_http_status,
            "terminal_ms": None,
            "response_body_sha256": None,
            "retryable": args.recover_interrupted_http_status
            in {408, 429, 500, 502, 503, 504},
            "local_trace_note": (
                "same attempt observed the recorded HTTP status, but the original "
                "error-body reader raised StreamClosed before the result artifact was written"
            ),
        }
        output = preflight | {
            "status": result["status"],
            "completed_at": utc_now(),
            "result": result,
            "budget": preflight["budget"]
            | {
                "accounted_probe_cost_usd": str(settled),
                "accounted_stage_cost_usd": str(ledger.accounted_stage_cost_usd(STAGE)),
                "accounted_paper1_total_usd": str(ledger.accounted_cost_usd),
                "paper1_remaining_usd": str(ledger.remaining_usd),
            },
        }
        write_json(args.out, output)
        print(canonical_json(output))
        return 2

    api_key = os.environ.get("NVIDIA_API_KEY", "")
    if not api_key:
        raise RuntimeError("NVIDIA_API_KEY is not set")
    ledger = CumulativePaper1ApiBudgetLedger(args.ledger)
    reservation = ledger.reserve(
        reservation_id=f"{call_hash}:attempt:1",
        logical_call_id=call_hash,
        call_hash=call_hash,
        stage=STAGE,
        provider="NVIDIA hosted NIM",
        model=MODEL,
        maximum_cost_usd=PROBE_RESERVATION_USD,
        call_class="PRIMARY",
        stage_hard_cap_usd=STAGE_HARD_CAP_USD,
    )
    result = _stream_call(payload, api_key)
    succeeded = result["status"] == "SUCCEEDED"
    # NVIDIA's hosted prototyping endpoint exposes no public per-token tariff
    # in this frozen route. Charge an unavailable/unknown-cost call at the
    # full conservative reservation; a successful call is also conservatively
    # accounted at the reservation until provider billing evidence exists.
    settled = ledger.settle(
        reservation,
        actual_cost_usd=None,
        outcome="SUCCEEDED" if succeeded else "FAILED",
    )
    output: dict[str, Any] = preflight | {
        "status": result["status"],
        "completed_at": utc_now(),
        "result": result,
        "budget": preflight["budget"]
        | {
            "accounted_probe_cost_usd": str(settled),
            "accounted_stage_cost_usd": str(ledger.accounted_stage_cost_usd(STAGE)),
            "accounted_paper1_total_usd": str(ledger.accounted_cost_usd),
            "paper1_remaining_usd": str(ledger.remaining_usd),
        },
    }
    if succeeded:
        first = result["provider_request_to_first_content_ms"]
        completion = result["provider_request_to_completion_ms"]
        if first is None:
            raise RuntimeError("stream completed without visible content")
        usage = result["usage"]
        output["latency_record"] = EndToEndLatencyRecord(
            trace_id=f"probe-{call_hash[:20]}",
            measurement_surface=LatencyMeasurementSurface.REFERENCE_CLIENT,
            time_block_id="generator-availability-probe-000",
            target_microblock_id=f"probe-{target.target_id}",
            randomized_sequence_position=0,
            client_region="Asia/Tokyo-local-reference-client",
            warm_state=WarmState.COLD,
            concurrency=1,
            connection_reuse=False,
            policy_decision_ms=0.0,
            retrieval_embedding_ms=0.0,
            resource_render_pack_ms=0.0,
            provider_request_to_first_content_ms=first,
            provider_request_to_completion_ms=completion,
            client_send_to_first_visible_text_ms=first,
            client_send_to_final_visible_text_ms=completion,
            streaming_observed=True,
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            retry_count=0,
            finish_reason=str(result["finish_reason"]),
            metadata={
                "configuration_id": "QA_OFF_probe",
                "physical_call_sha256": call_hash,
                "response_sha256": result["response_sha256"],
            },
        ).model_dump(mode="json")
    write_json(args.out, output)
    print(canonical_json(output))
    return 0 if succeeded else 2


if __name__ == "__main__":
    raise SystemExit(main())
