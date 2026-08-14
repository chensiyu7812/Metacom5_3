#!/usr/bin/env python3
"""Run the corrected Nemotron 3 Nano two-card operational canary."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
AUTHORITY_DIR = PROJECT_ROOT / "data" / "v3_authority"
CONTRACT_PATH = AUTHORITY_DIR / "g0_nemotron30b_transport_canary_contract_v1.json"
PREFLIGHT_PATH = AUTHORITY_DIR / "g0_nemotron30b_transport_canary_preflight_v1.json"
BASE_RUNNER_PATH = PROJECT_ROOT / "scripts" / "v3" / "16_run_g0_research_aligned_esc.py"


def _base():
    spec = importlib.util.spec_from_file_location("g0_research_aligned_base", BASE_RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load frozen G0 helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("percentile requires observations")
    index = (len(ordered) - 1) * quantile
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = index - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _physical_failures(events: list[dict[str, Any]], failure_class: str) -> int:
    return sum(
        row.get("event") == "supporter_failed" and row.get("failure_class") == failure_class
        for row in events
    )


def _early_stop_reason(events: list[dict[str, Any]]) -> str | None:
    if _physical_failures(events, "rate_limited_429") >= 2:
        return "TWO_EXPLICIT_HTTP_429_ATTEMPTS"
    terminals = [row for row in events if row.get("event") == "trajectory_terminal_failure"]
    if len(terminals) >= 2:
        return "TWO_TERMINAL_TRANSIENT_FAILURES"
    successes = [row for row in events if row.get("event") == "supporter_succeeded"]
    if len(successes) >= 3 and statistics.median(float(row["latency_ms"]) for row in successes) > 45_000:
        return "THREE_SUCCESS_MEDIAN_ABOVE_45_SECONDS"
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--esc-eval", required=True, type=Path)
    parser.add_argument("--role-model", required=True, type=Path)
    parser.add_argument("--role-device", default="cuda:0")
    parser.add_argument("--approved-identity", required=True)
    parser.add_argument("--max-usd", required=True, type=float)
    parser.add_argument(
        "--out",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "v3_g0_nemotron30b_transport_canary_v1_20260814",
    )
    args = parser.parse_args()
    if args.max_usd != 0:
        raise ValueError("the frozen NVIDIA hosted canary ceiling is exactly $0")

    contract = _load_json(CONTRACT_PATH)
    preflight = _load_json(PREFLIGHT_PATH)
    if args.approved_identity != preflight["run_identity"]:
        raise RuntimeError("approved identity does not match frozen Nemotron preflight")
    candidate = contract["candidate"]
    if not os.environ.get(candidate["api_key_env"]):
        raise RuntimeError(f"missing {candidate['api_key_env']}")

    base = _base()
    selected = base._load_selected_cards(args.esc_eval, 2)
    prompt_text = base._supporter_prompt()
    if base._sha_text(prompt_text) != preflight["prompt_sha256"]:
        raise RuntimeError("supporter prompt drifted")

    args.out.mkdir(parents=True, exist_ok=True)
    ledger = args.out / "private_turn_ledger.jsonl"
    existing = base._read_jsonl(ledger)
    if any(row.get("run_identity") != preflight["run_identity"] for row in existing):
        raise RuntimeError("existing ledger contains another run identity")

    from metacom_pm.api import Endpoint, OpenAICompatibleClient, RetryableProviderError, chat_request_payload

    endpoint = Endpoint(
        base_url=candidate["base_url"],
        model=candidate["model"],
        api_key_env=candidate["api_key_env"],
        timeout_seconds=240.0,
        family=candidate["candidate_id"],
        transport="openai_chat_completions",
    )
    client = OpenAICompatibleClient(endpoint)
    torch, tokenizer, role_model = base._load_role_model(args.role_model, args.role_device)
    early_stop = None
    try:
        for item in selected:
            identity, card = item["identity"], item["card"]
            card_key = identity["card_key"]
            for turn in range(1, 6):
                events = base._read_jsonl(ledger)
                early_stop = _early_stop_reason(events)
                if early_stop:
                    break
                unit_id = f"{identity['screen_id']}::{candidate['candidate_id']}::turn{turn}"
                if unit_id in base._completed(events):
                    continue
                history = base._history(events, card_key, candidate["candidate_id"])
                if len(history) != (turn - 1) * 2:
                    raise RuntimeError(f"non-contiguous history before {unit_id}")
                seeker_messages = [
                    {"role": "system", "content": base._role_prompt(card["base"])},
                    {"role": "user", "content": "Hello, I'm your personal assistant. You can confide in me about any worries or concerns you may have!"},
                ]
                for prior in history:
                    seeker_messages.append({
                        "role": "assistant" if prior["role"] == "user" else "user",
                        "content": prior["content"],
                    })
                pending = base._pending_roles(events)
                if unit_id in pending:
                    seeker_text = pending[unit_id]["seeker_text"]
                else:
                    seeker_text = base._generate_role(
                        torch,
                        tokenizer,
                        role_model,
                        seeker_messages,
                        device=args.role_device,
                        seed=base._role_seed(card_key, turn),
                    )
                    base._append_jsonl(ledger, {
                        "event": "role_generated", "run_identity": preflight["run_identity"],
                        "unit_id": unit_id, "screen_id": identity["screen_id"], "card_key": card_key,
                        "candidate_id": candidate["candidate_id"], "turn": turn,
                        "role_seed": base._role_seed(card_key, turn), "seeker_text": seeker_text,
                        "timestamp_unix": time.time(),
                    })
                supporter_messages = [
                    {"role": "system", "content": prompt_text},
                    *history,
                    {"role": "user", "content": seeker_text},
                ]
                payload = chat_request_payload(
                    endpoint, supporter_messages, temperature=0.0,
                    max_tokens=None, seed=None, response_schema=None,
                )
                if "max_tokens" in payload or "max_completion_tokens" in payload:
                    raise RuntimeError("researcher output cap leaked into Nemotron payload")
                trajectory_terminal = False
                for physical_attempt in (1, 2):
                    try:
                        call, _ = client.chat(
                            supporter_messages, temperature=0.0,
                            max_tokens=None, retries=1,
                        )
                    except RetryableProviderError as exc:
                        base._append_jsonl(ledger, {
                            "event": "supporter_failed", "run_identity": preflight["run_identity"],
                            "unit_id": unit_id, "card_key": card_key,
                            "candidate_id": candidate["candidate_id"], "turn": turn,
                            "physical_attempt": physical_attempt,
                            "failure_class": exc.last_retry_class,
                            "status_code": exc.last_status_code,
                            "retry_after_seconds": exc.retry_after_seconds,
                            "response_diagnostics": exc.response_diagnostics,
                            "usage": exc.usage or {}, "timestamp_unix": time.time(),
                        })
                        transient = exc.last_retry_class in {
                            "rate_limited_429", "request_timeout_408", "http_5xx", "network_timeout"
                        }
                        if not transient:
                            raise
                        if physical_attempt == 2:
                            base._append_jsonl(ledger, {
                                "event": "trajectory_terminal_failure", "run_identity": preflight["run_identity"],
                                "screen_id": identity["screen_id"], "card_key": card_key,
                                "candidate_id": candidate["candidate_id"], "terminal_turn": turn,
                                "terminal_failure_class": exc.last_retry_class,
                                "attempts_exhausted": physical_attempt, "timestamp_unix": time.time(),
                            })
                            trajectory_terminal = True
                            break
                        time.sleep(min(float(exc.retry_after_seconds or 5.0), 30.0))
                        continue
                    base._append_jsonl(ledger, {
                        "event": "supporter_succeeded", "run_identity": preflight["run_identity"],
                        "unit_id": unit_id, "screen_id": identity["screen_id"], "card_key": card_key,
                        "source": identity["source"], "candidate_id": candidate["candidate_id"],
                        "model": candidate["model"], "reasoning_mode": candidate["reasoning_mode"],
                        "turn": turn, "physical_attempt": physical_attempt,
                        "seeker_text": seeker_text, "supporter_text": call.text,
                        "supporter_prompt_sha256": preflight["prompt_sha256"],
                        "request_hash": call.request_hash, "researcher_output_token_cap": None,
                        "provider_output_parameter_omitted": True, "usage": call.usage,
                        "latency_ms": call.latency_ms, "provider_finish_reason": call.provider_finish_reason,
                        "normalized_finish_reason": call.normalized_finish_reason,
                        "raw_response": call.raw_response, "timestamp_unix": time.time(),
                    })
                    break
                if trajectory_terminal:
                    break
            if early_stop:
                break
    finally:
        client.close()

    events = base._read_jsonl(ledger)
    successes = [row for row in events if row.get("event") == "supporter_succeeded"]
    failures = [row for row in events if row.get("event") == "supporter_failed"]
    terminals = [row for row in events if row.get("event") == "trajectory_terminal_failure"]
    latencies = [float(row["latency_ms"]) for row in successes]
    early_stop = early_stop or _early_stop_reason(events)
    summary = {
        "protocol": "metacom-v3-g0-nemotron30b-transport-run-summary-v1",
        "run_identity": preflight["run_identity"],
        "model": candidate["model"],
        "successful_turns": len(successes),
        "first_attempt_successful_turns": sum(row.get("physical_attempt") == 1 for row in successes),
        "failed_physical_attempts": len(failures),
        "explicit_429_physical_attempts": _physical_failures(events, "rate_limited_429"),
        "failure_classes": {
            name: sum(row.get("failure_class") == name for row in failures)
            for name in sorted({str(row.get("failure_class")) for row in failures})
        },
        "terminal_trajectories": len(terminals),
        "early_stop_reason": early_stop,
        "latency_ms": {
            "median": statistics.median(latencies) if latencies else None,
            "p90": _percentile(latencies, 0.9) if latencies else None,
        },
        "researcher_output_token_cap": None,
        "quality_judged": False,
        "canary_selects_generator": False,
        "observed_cost_usd": 0,
    }
    (args.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
