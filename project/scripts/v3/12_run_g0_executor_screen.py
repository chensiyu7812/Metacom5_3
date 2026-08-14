#!/usr/bin/env python3
"""Run the frozen G0 executor capability screen.

This is a development-only generator diagnostic over previously used packets.
It is not a held-out PM effect experiment. Provider payloads and generations
remain in a private, resumable ledger under project/outputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
AUTHORITY_DIR = PROJECT_ROOT / "data" / "v3_authority"
CONTRACT_PATH = AUTHORITY_DIR / "g0_generator_bakeoff_contract_v1.json"
PREFLIGHT_PATH = AUTHORITY_DIR / "g0_generator_bakeoff_preflight_v1.json"
MANIFEST_PATH = AUTHORITY_DIR / "g0_executor_screening_manifest_v1.jsonl"
DEFAULT_SOURCE_DIR = (
    PROJECT_ROOT.parent
    / "private_evidence"
    / "current_20260813"
    / "pm_v1_5_r0_delta_four_arm_development_panel_20260813"
)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(_canonical(record) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _require_ledger_identity(events: list[dict[str, Any]], run_identity: str, label: str) -> None:
    mismatched = [row for row in events if row.get("run_identity") != run_identity]
    if mismatched:
        raise RuntimeError(f"{label} contains {len(mismatched)} event(s) from another run identity")


def _candidate_endpoint(record: dict[str, Any]):
    from metacom_pm.api import Endpoint

    return Endpoint(
        base_url=record["base_url"],
        model=record["model"],
        api_key_env=record["api_key_env"],
        timeout_seconds=240.0,
        family=record["candidate_id"],
        transport="openai_chat_completions",
        enable_thinking=record.get("enable_thinking"),
    )


def _load_selected_calls(source_dir: Path) -> list[dict[str, Any]]:
    preflight = _load_json(PREFLIGHT_PATH)
    contract = _load_json(CONTRACT_PATH)
    source_path = source_dir / "physical_call_plan_private.jsonl"
    expected_source_hash = contract["executor_screen"]["source_artifact_sha256"]
    if _sha_file(source_path) != expected_source_hash:
        raise RuntimeError("executor private source artifact drifted")
    manifest_bytes = MANIFEST_PATH.read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != preflight["executor_sample"]["manifest_sha256"]:
        raise RuntimeError("executor public manifest drifted")
    manifest = _read_jsonl(MANIFEST_PATH)
    source = _read_jsonl(source_path)
    by_prompt: dict[str, list[dict[str, Any]]] = {}
    for row in source:
        by_prompt.setdefault(row["messages_sha256"], []).append(row)

    selected: list[dict[str, Any]] = []
    for identity in manifest:
        matches = by_prompt.get(identity["prompt_sha256"], [])
        if len(matches) != 1:
            raise RuntimeError("executor prompt commitment does not resolve uniquely")
        call = matches[0]
        if call["requested_action_id"] != identity["source_action_id"]:
            raise RuntimeError("executor source action drifted")
        if _sha_text(_canonical(call["messages"])) != identity["prompt_sha256"]:
            raise RuntimeError("executor provider-visible prompt drifted")
        selected.append({"identity": identity, "call": call})
    if len(selected) != 32:
        raise RuntimeError("exact 32-call executor plan required")
    return selected


def _qwen_cost_usd(events: list[dict[str, Any]]) -> float:
    prompt = completion = 0
    for row in events:
        if row.get("candidate_id") != "qwen37_plus_primary_challenger":
            continue
        usage = row.get("usage") or {}
        if usage:
            prompt += int(usage.get("prompt_tokens", 0))
            completion += int(usage.get("completion_tokens", 0))
        else:
            prompt += 8192
            completion += 256
    cny = (prompt * 2.998 + completion * 11.991) / 1_000_000
    return cny / 7.0


def _qwen_max_call_usd() -> float:
    return ((8192 * 2.998 + 256 * 11.991) / 1_000_000) / 7.0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--approved-identity", required=True)
    parser.add_argument("--max-usd", required=True, type=float)
    parser.add_argument("--limit", type=int, default=16)
    parser.add_argument(
        "--out",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "v3_g0_executor_screen_20260813",
    )
    parser.add_argument(
        "--qwen-budget-ledger",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "v3_g0_generator_bakeoff_20260813" / "qwen_budget_ledger.jsonl",
    )
    args = parser.parse_args()
    contract = _load_json(CONTRACT_PATH)
    preflight = _load_json(PREFLIGHT_PATH)
    if args.approved_identity != preflight["run_identity"]:
        raise RuntimeError("approved identity does not match the frozen G0 preflight")
    ceiling = float(preflight["cost_ceiling"]["conservative_usd_stop_limit"])
    if args.max_usd < ceiling:
        raise RuntimeError(f"max-usd must cover the frozen conservative ceiling {ceiling:.2f}")
    if not 1 <= args.limit <= 16:
        raise ValueError("limit must be between 1 and 16")
    for candidate in contract["candidates"]:
        if not os.environ.get(candidate["api_key_env"]):
            raise RuntimeError(f"missing {candidate['api_key_env']}")

    selected_all = _load_selected_calls(args.source_dir)
    packet_ids = list(dict.fromkeys(row["identity"]["packet_id"] for row in selected_all))[: args.limit]
    selected = [row for row in selected_all if row["identity"]["packet_id"] in set(packet_ids)]
    args.out.mkdir(parents=True, exist_ok=True)
    ledger = args.out / "private_executor_ledger.jsonl"
    events = _read_jsonl(ledger)
    _require_ledger_identity(events, preflight["run_identity"], "executor ledger")
    budget_events = _read_jsonl(args.qwen_budget_ledger)
    _require_ledger_identity(budget_events, preflight["run_identity"], "Qwen budget ledger")
    completed = {
        (row["packet_id"], row["screen_arm"], row["candidate_id"])
        for row in events
        if row.get("event") in {
            "executor_succeeded", "executor_invalid_output", "executor_terminal_failure"
        }
    }
    from metacom_pm.api import OpenAICompatibleClient, RetryableProviderError
    from metacom_pm.v1_5_ms_same_stack_feasibility import SameStackGeneratorOutput

    clients = {
        row["candidate_id"]: OpenAICompatibleClient(_candidate_endpoint(row))
        for row in contract["candidates"]
    }
    try:
        for packet_index, item in enumerate(selected):
            identity, call = item["identity"], item["call"]
            candidates = list(contract["candidates"])
            rotation = packet_index % len(candidates)
            candidates = candidates[rotation:] + candidates[:rotation]
            for candidate in candidates:
                cid = candidate["candidate_id"]
                unit = (identity["packet_id"], identity["screen_arm"], cid)
                if unit in completed:
                    continue
                attempt = 0
                while True:
                    attempt += 1
                    if cid == "qwen37_plus_primary_challenger" and _qwen_cost_usd(_read_jsonl(args.qwen_budget_ledger)) + _qwen_max_call_usd() > args.max_usd:
                        raise RuntimeError("approved Qwen cost ceiling reached")
                    try:
                        result, parsed = clients[cid].chat(
                            call["messages"],
                            temperature=0.0,
                            max_tokens=256,
                            response_schema=SameStackGeneratorOutput,
                            retries=1,
                        )
                    except RetryableProviderError as exc:
                        if cid == "qwen37_plus_primary_challenger":
                            _append_jsonl(
                                args.qwen_budget_ledger,
                                {
                                    "event": "qwen_physical_attempt",
                                    "run_identity": preflight["run_identity"],
                                    "surface": "executor",
                                    "packet_id": identity["packet_id"],
                                    "screen_arm": identity["screen_arm"],
                                    "candidate_id": cid,
                                    "physical_attempt": attempt,
                                    "usage": exc.usage or {},
                                    "timestamp_unix": time.time(),
                                },
                            )
                        _append_jsonl(
                            ledger,
                            {
                                "event": "executor_failed",
                                "run_identity": preflight["run_identity"],
                                "packet_id": identity["packet_id"],
                                "screen_arm": identity["screen_arm"],
                                "candidate_id": cid,
                                "physical_attempt": attempt,
                                "failure_class": exc.last_retry_class,
                                "status_code": exc.last_status_code,
                                "usage": exc.usage or {},
                                "timestamp_unix": time.time(),
                            },
                        )
                        retryable = exc.last_retry_class in {
                            "rate_limited_429", "request_timeout_408", "http_5xx", "network_timeout"
                        }
                        if not retryable:
                            raise
                        if attempt >= 2:
                            _append_jsonl(
                                ledger,
                                {
                                    "event": "executor_terminal_failure",
                                    "run_identity": preflight["run_identity"],
                                    "packet_id": identity["packet_id"],
                                    "owner_cluster_id": identity["owner_cluster_id"],
                                    "screen_arm": identity["screen_arm"],
                                    "source_action_id": identity["source_action_id"],
                                    "candidate_id": cid,
                                    "failure_class": exc.last_retry_class,
                                    "attempts_exhausted": attempt,
                                    "timestamp_unix": time.time(),
                                },
                            )
                            break
                        time.sleep(min(float(exc.retry_after_seconds or 5.0), 30.0))
                        continue
                    usage = result.usage
                    if cid == "qwen37_plus_primary_challenger":
                        _append_jsonl(
                            args.qwen_budget_ledger,
                            {
                                "event": "qwen_physical_attempt",
                                "run_identity": preflight["run_identity"],
                                "surface": "executor",
                                "packet_id": identity["packet_id"],
                                "screen_arm": identity["screen_arm"],
                                "candidate_id": cid,
                                "physical_attempt": attempt,
                                "usage": usage,
                                "timestamp_unix": time.time(),
                            },
                        )
                    if int(usage.get("prompt_tokens", 0)) > 8192 or int(usage.get("completion_tokens", 0)) > 256:
                        raise RuntimeError(f"token budget contract exceeded at {unit}: {usage}")
                    _append_jsonl(
                        ledger,
                        {
                            "event": "executor_succeeded" if parsed is not None else "executor_invalid_output",
                            "run_identity": preflight["run_identity"],
                            "packet_id": identity["packet_id"],
                            "owner_cluster_id": identity["owner_cluster_id"],
                            "screen_arm": identity["screen_arm"],
                            "source_action_id": identity["source_action_id"],
                            "candidate_id": cid,
                            "model": candidate["model"],
                            "physical_attempt": attempt,
                            "prompt_sha256": identity["prompt_sha256"],
                            "request_hash": result.request_hash,
                            "usage": usage,
                            "latency_ms": result.latency_ms,
                            "provider_finish_reason": result.provider_finish_reason,
                            "raw_text": result.text,
                            "raw_response": result.raw_response,
                            "parsed": parsed.model_dump(mode="json") if parsed is not None else None,
                            "timestamp_unix": time.time(),
                        },
                    )
                    break
    finally:
        for client in clients.values():
            client.close()

    events = _read_jsonl(ledger)
    terminal = [
        row for row in events
        if row.get("event") in {
            "executor_succeeded", "executor_invalid_output", "executor_terminal_failure"
        }
        and row.get("packet_id") in set(packet_ids)
    ]
    expected = args.limit * 2 * len(contract["candidates"])
    summary = {
        "protocol": "metacom-v3-g0-executor-screen-run-summary-v1",
        "run_identity": preflight["run_identity"],
        "terminal_calls": len(terminal),
        "valid_structured_outputs": sum(row["event"] == "executor_succeeded" for row in terminal),
        "invalid_structured_outputs": sum(row["event"] == "executor_invalid_output" for row in terminal),
        "transport_terminal_failures": sum(row["event"] == "executor_terminal_failure" for row in terminal),
        "expected_calls": expected,
        "complete": len(terminal) == expected,
        "qwen_estimated_usd_across_g0_surfaces": _qwen_cost_usd(_read_jsonl(args.qwen_budget_ledger)),
        "held_out": False,
        "formal_pm_evidence": False,
        "next": "Score frozen executor outcomes; retain invalid outputs under ITT and do not infer individual-head effects.",
    }
    (args.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
