"""Serial Gemini qualification transport with resumable, budgeted attempts.

No reference ratings enter provider requests. This runner produces measurement
traces, never PM labels or official benchmark outcomes.
"""

from __future__ import annotations

import json
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx

from metacom_pm.io import canonical_json, iter_jsonl, sha256_text, utc_now, write_json
from metacom_pm.paper1.api_budget import (
    ApiBudgetReservation, CumulativePaper1ApiBudgetLedger, PAPER1_OPTIONAL_STOP_USD,
)
from metacom_pm.paper1.evaluation.pairwise_teacher import parse_pairwise_teacher_response

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
MODEL = "gemini-2.5-flash-lite"
STAGE = "pairwise_teacher_qualification_v2"
STAGE_CAP = Decimal("0.10")
INPUT_RATE = Decimal("0.10")
OUTPUT_RATE = Decimal("0.40")
INPUT_ACCOUNTING_ALLOWANCE = 256


def cost(input_tokens: int, output_tokens: int) -> Decimal:
    if any(type(n) is not int or n < 0 for n in (input_tokens, output_tokens)):
        raise ValueError("token counts must be nonnegative integers")
    return (Decimal(input_tokens) * INPUT_RATE + Decimal(output_tokens) * OUTPUT_RATE) / 1000000


def validate_requests(rows: list[dict[str, Any]], identity: dict[str, Any]) -> None:
    if len(rows) != identity["exact_request_manifest"]["presentations"]:
        raise ValueError("request count differs from frozen manifest")
    ids, hashes = set(), set()
    g = identity["generation"]
    expected_config = {
        "maxOutputTokens": g["maxOutputTokens"], "responseJsonSchema": g["responseJsonSchema"],
        "responseMimeType": g["responseMimeType"], "seed": g["seed"],
        "temperature": g["temperature"], "thinkingConfig": g["thinking_config"],
    }
    for row in rows:
        pid, body = row["presentation_id"], row["body"]
        if not isinstance(pid, str) or not pid or pid in ids:
            raise ValueError("duplicate or missing presentation")
        ids.add(pid)
        if row["request_model"] != MODEL or identity["model"]["request_model"] != MODEL:
            raise ValueError("model drift")
        if set(body) != {"contents", "generationConfig"} or body["generationConfig"] != expected_config:
            raise ValueError("generation config, tools, or request fields drifted")
        if sha256_text(canonical_json(body)) != row["body_sha256"]:
            raise ValueError("body hash mismatch")
        if row["body_sha256"] in hashes:
            raise ValueError("duplicate paid request body")
        hashes.add(row["body_sha256"])
        if row["maximum_output_tokens"] != g["maxOutputTokens"]:
            raise ValueError("output token reservation differs from request")


def check_model(client: httpx.Client) -> dict[str, Any]:
    response = client.get(f"{BASE_URL}/models/{MODEL}")
    if response.status_code != 200:
        raise RuntimeError(f"model metadata HTTP {response.status_code}")
    metadata = response.json()
    if metadata.get("name") != f"models/{MODEL}" or metadata.get("version") != "001":
        raise RuntimeError("frozen Gemini model/version is unavailable")
    methods = metadata.get("supportedGenerationMethods", [])
    if not {"generateContent", "countTokens"} <= set(methods):
        raise RuntimeError("model lacks frozen generation/token-count methods")
    return metadata


def count_requests(client: httpx.Client, rows: list[dict[str, Any]], output: Path) -> dict[str, Any]:
    """Read-only provider preflight; does not invoke generateContent."""
    metadata = check_model(client)
    count_path = output / "provider_token_counts.json"
    binding = sha256_text(canonical_json([{k: r[k] for k in ("presentation_id", "body_sha256")} for r in rows]))
    state = {"protocol": "paper1-gemini-provider-counts-v1", "binding_sha256": binding,
             "model_version": "001", "counts": {}}
    if count_path.exists():
        saved = json.loads(count_path.read_text())
        if saved["binding_sha256"] != binding or saved["model_version"] != "001":
            raise RuntimeError("provider preflight cache identity changed")
        state = saved
    for row in rows:
        key = row["body_sha256"]
        if key not in state["counts"]:
            response = client.post(f"{BASE_URL}/models/{MODEL}:countTokens", json={
                "generateContentRequest": {"model": f"models/{MODEL}", **row["body"]}
            })
            if response.status_code != 200:
                raise RuntimeError(f"countTokens HTTP {response.status_code}")
            total = response.json().get("totalTokens")
            if type(total) is not int or total <= 0:
                raise RuntimeError("invalid provider input token count")
            state["counts"][key] = total
            state["checked_at"] = utc_now()
            write_json(count_path, state)
        total = state["counts"][key]
        if type(total) is not int or not 0 < total + INPUT_ACCOUNTING_ALLOWANCE <= metadata["inputTokenLimit"]:
            raise RuntimeError("provider input count exceeds frozen envelope")
    maximum = sum((cost(state["counts"][r["body_sha256"]] + INPUT_ACCOUNTING_ALLOWANCE,
                        r["maximum_output_tokens"]) for r in rows), Decimal("0"))
    result = {**state, "metadata": metadata, "completed_counts": len(rows),
              "input_accounting_allowance_per_call": INPUT_ACCOUNTING_ALLOWANCE,
              "first_attempt_reservation_sum_usd": str(maximum),
              "all_first_attempts_fit_stage_cap": maximum <= STAGE_CAP,
              "retries_included": False, "generateContent_calls": 0}
    write_json(output / "provider_preflight.json", result)
    return result


def parsed_response(payload: dict[str, Any]) -> dict[str, str]:
    candidates = payload.get("candidates", [])
    if len(candidates) != 1 or candidates[0].get("finishReason") != "STOP":
        raise ValueError("teacher output absent, blocked, or incomplete")
    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts or any(set(p) != {"text"} or not isinstance(p["text"], str) for p in parts):
        raise ValueError("unexpected teacher thought/tool/nontext part")
    raw = "".join(p["text"] for p in parts)
    verdict = parse_pairwise_teacher_response(raw)
    return {"verdict": verdict.verdict, "rationale": verdict.rationale}


def reported_cost(payload: dict[str, Any]) -> Decimal | None:
    usage = payload.get("usageMetadata", {})
    inp, out = usage.get("promptTokenCount"), usage.get("candidatesTokenCount")
    thought = usage.get("thoughtsTokenCount", 0)
    if type(thought) is not int or thought < 0:
        raise ValueError("invalid reported thinking token count")
    if inp is None or out is None:
        return None  # Unknown billing is charged conservatively at reservation.
    # The frozen request remains thinkingBudget=0. Provider-reported thinking
    # is an observed discrepancy, not permission to omit billable output.
    cost(inp, out)  # Validate fields separately (including rejecting bool).
    return cost(inp, out + thought)


def run_requests(
    client: httpx.Client, rows: list[dict[str, Any]], provider: dict[str, Any],
    ledger: CumulativePaper1ApiBudgetLedger, output: Path, *, authorized: bool = False,
    saved_settlement_reconciliations: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    if authorized is not True:
        raise PermissionError("separate researcher authorization is required")
    check_model(client)
    expected_binding = sha256_text(canonical_json([{k: r[k] for k in ("presentation_id", "body_sha256")} for r in rows]))
    if provider["binding_sha256"] != expected_binding or provider["model_version"] != "001":
        raise RuntimeError("provider preflight belongs to different requests/model")
    if not provider["all_first_attempts_fit_stage_cap"]:
        raise RuntimeError("first-attempt envelope exceeds stage cap")
    # Caller holds the cumulative ledger file lock throughout this serial run.
    existing = list(iter_jsonl(ledger.path)) if ledger.path.exists() else []
    events = {}
    for event in existing:
        events.setdefault(event["reservation_id"], []).append(event)
    completed, version = [], None
    for row in rows:
        logical = f"{STAGE}:{row['presentation_id']}"
        call_hash = sha256_text(canonical_json({"model": MODEL, "body_sha256": row["body_sha256"]}))
        maximum = cost(provider["counts"][row["body_sha256"]] + INPUT_ACCOUNTING_ALLOWANCE,
                       row["maximum_output_tokens"])
        terminal = None
        for attempt in (1, 2):
            rid = f"{logical}:{attempt}"
            cache = output / "attempts" / f"{sha256_text(rid)}.json"
            history = events.get(rid, [])
            if history:
                if history[0]["call_hash"] != call_hash:
                    raise RuntimeError("ledger call identity drift")
                if not cache.exists():
                    raise RuntimeError("interrupted attempt without saved response; do not rebill blindly")
                record = json.loads(cache.read_text())
                if record["call_hash"] != call_hash or record["presentation_id"] != row["presentation_id"]:
                    raise RuntimeError("cached attempt identity drift")
                reservation = ApiBudgetReservation(rid, Decimal(history[0]["maximum_cost_usd"]))
                if record["response_sha256"] != sha256_text(canonical_json(record["response"])):
                    raise RuntimeError("cached response integrity mismatch")
            else:
                if cache.exists():
                    raise RuntimeError("response cache without a budget reservation")
                # The shared ledger names every second attempt PRIMARY_RETRY.
                # A teacher retry is still optional work and may not consume
                # the protected primary-run reserve or cross the USD 43 stop.
                if ledger.accounted_cost_usd + maximum > PAPER1_OPTIONAL_STOP_USD:
                    raise RuntimeError("optional teacher work including retries must stop at USD 43")
                reservation = ledger.reserve(
                    reservation_id=rid, logical_call_id=logical, call_hash=call_hash, stage=STAGE,
                    provider="Google Gemini Developer API", model=MODEL, maximum_cost_usd=maximum,
                    call_class="OPTIONAL" if attempt == 1 else "PRIMARY_RETRY", stage_hard_cap_usd=STAGE_CAP,
                )
                record = {"presentation_id": row["presentation_id"], "body_sha256": row["body_sha256"],
                          "call_hash": call_hash, "attempt": attempt, "started_at": utc_now(),
                          "response": {}, "http_status": None, "transport_error": None}
                start = time.monotonic()
                try:
                    response = client.post(f"{BASE_URL}/models/{MODEL}:generateContent", json=row["body"])
                    record["http_status"] = response.status_code
                    # Preserve the raw HTTP body as well as parsed JSON for malformed replies.
                    record["raw_http_body"] = response.text
                    try:
                        record["response"] = response.json()
                    except ValueError:
                        record["response"] = {}
                except httpx.TimeoutException:
                    record["transport_error"] = "network_timeout"
                except httpx.TransportError:
                    record["transport_error"] = "network_transport_error"
                record["latency_ms"] = (time.monotonic() - start) * 1000
                record["response_sha256"] = sha256_text(canonical_json(record["response"]))
                write_json(cache, record)  # Durable response before ledger settlement.
            payload = record["response"]
            if not isinstance(payload, dict):
                payload = {}
            response_version = payload.get("modelVersion")
            parsed, reason = None, None
            fatal = False
            if record["http_status"] in (400, 401, 403, 404):
                fatal, reason = True, f"provider_configuration_HTTP_{record['http_status']}"
            retryable = record["http_status"] in (408, 429) or (
                record["http_status"] is not None and 500 <= record["http_status"] <= 599
            ) or record["transport_error"] == "network_timeout"
            try:
                actual = reported_cost(payload)
            except (ValueError, RuntimeError):
                actual, fatal, reason = None, True, "provider_usage_outside_frozen_contract"
            usage = payload.get("usageMetadata", {})
            if actual is not None and (
                usage["candidatesTokenCount"] + usage.get("thoughtsTokenCount", 0) > row["maximum_output_tokens"]
                or usage["promptTokenCount"] > provider["counts"][row["body_sha256"]] + INPUT_ACCOUNTING_ALLOWANCE
            ):
                fatal, reason = True, "provider_usage_exceeds_reserved_token_envelope"
            if record["http_status"] == 200:
                if not isinstance(response_version, str) or not response_version:
                    fatal, reason = True, "missing_model_version"
                elif version is not None and response_version != version:
                    fatal, reason = True, "mixed_response_model_versions"
                else:
                    version = response_version
                try:
                    parsed = parsed_response(payload)
                except ValueError:
                    retryable, reason = True, reason or "invalid_structured_output"
            success = parsed is not None and not fatal
            reconciled = False
            if len(history) < 2:
                ledger.settle(reservation, actual_cost_usd=actual,
                              outcome="SUCCEEDED" if success else "FAILED")
            elif (history[-1]["outcome"] == "SUCCEEDED") != success:
                proof = (saved_settlement_reconciliations or {}).get(rid, {})
                reconciled = (
                    success and actual is not None
                    and history[-1]["outcome"] == "FAILED"
                    and history[-1].get("accounting") == "unknown_cost_charged_at_reserved_maximum"
                    and actual <= Decimal(history[-1]["actual_cost_usd"])
                    and proof.get("response_sha256") == record["response_sha256"]
                    and proof.get("call_hash") == call_hash
                    and proof.get("reason") == "saved_valid_response_rejected_by_removed_zero_thinking_usage_assumption"
                )
                if not reconciled:
                    raise RuntimeError("cached parse disagrees with settled ledger")
            if fatal:
                raise RuntimeError(reason)
            terminal = {"presentation_id": row["presentation_id"], "body_sha256": row["body_sha256"],
                        "status": "SUCCEEDED" if success else "OPERATIONAL_FAILURE",
                        "parsed_verdict": parsed["verdict"] if success else None,
                        "verdict": parsed["verdict"] if success else "uncertain",
                        "rationale": parsed["rationale"] if success else None,
                        "reason": None if success else (reason or record["transport_error"] or f"HTTP_{record['http_status']}"),
                        "model_version": response_version, "attempts": attempt,
                        "provider_reported_cost_usd": str(actual) if actual is not None else None,
                        "provider_reported_thinking_tokens": usage.get("thoughtsTokenCount", 0),
                        "thinking_usage_despite_requested_zero": usage.get("thoughtsTokenCount", 0) != 0,
                        "saved_settlement_reconciled_without_rebilling": reconciled}
            if success or not retryable or attempt == 2:
                break
            if not history:
                time.sleep(1)
        completed.append(terminal)
        write_json(output / "results.json", completed)
        print(json.dumps({"completed": len(completed), "scheduled": len(rows),
                          "status": terminal["status"], "stage_cost_usd": str(ledger.accounted_stage_cost_usd(STAGE))}), flush=True)
    return completed
