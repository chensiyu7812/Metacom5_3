#!/usr/bin/env python3
"""Run the pinned ESC-Eval public English interaction surface on hosted candidates."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
AUTHORITY = ROOT / "data" / "v3_authority"
CONTRACT_PATH = AUTHORITY / "g0_official_protocol_english331_contract_v1.json"
MANIFEST_PATH = AUTHORITY / "g0_official_protocol_english331_manifest_v1.jsonl"
PREFLIGHT_PATH = AUTHORITY / "g0_official_protocol_english331_preflight_v1.json"
BASE_PATH = Path(__file__).with_name("16_run_g0_research_aligned_esc.py")

spec = importlib.util.spec_from_file_location("metacom_g0_base", BASE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load frozen G0 runtime helpers")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


def _load_cards(esc_eval: Path, limit: int, commit: str):
    if base._git_head(esc_eval) != commit:
        raise RuntimeError("ESC-Eval checkout is not at the frozen commit")
    cards = json.loads((esc_eval / "data" / "card_high_en.json").read_text(encoding="utf-8"))
    by_key = {f"{row['language']}::{row['source']}::{row['id']}": row for row in cards}
    selected = []
    for identity in base._read_jsonl(MANIFEST_PATH)[:limit]:
        card = by_key.get(identity["card_key"])
        if card is None or base._sha_text(card["base"]) != identity["role_card_sha256"]:
            raise RuntimeError(f"role-card drift: {identity['card_key']}")
        selected.append({"identity": identity, "card": card})
    return selected


def _role_seed(card_key: str, turn: int) -> int:
    return int(base._sha_text(f"metacom-v3-g0-official-english331-role|{card_key}|{turn}")[:8], 16)


def _capped_qwen_reserve(messages: list[dict[str, str]], max_output_tokens: int) -> dict[str, float | int]:
    input_upper = len(base._canonical(messages).encode("utf-8")) + 4096
    if input_upper > 1_000_000:
        raise RuntimeError("conservative Qwen input bound exceeds documented context")
    if input_upper <= 256_000:
        input_rate, output_rate = 0.4, 1.6
    else:
        input_rate, output_rate = 1.2, 4.8
    reserve = (input_upper * input_rate + max_output_tokens * output_rate) / 1_000_000
    return {"input_upper_tokens": input_upper, "output_cap_tokens": max_output_tokens, "reserve_usd": reserve}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--esc-eval", required=True, type=Path)
    parser.add_argument("--role-model", required=True, type=Path)
    parser.add_argument("--role-device", default="cuda:0")
    parser.add_argument("--approved-identity", required=True)
    parser.add_argument("--max-usd", required=True, type=float)
    parser.add_argument("--limit", type=int, default=331)
    parser.add_argument("--out", type=Path, default=ROOT / "outputs" / "v3_g0_official_protocol_english331_v1_20260814")
    args = parser.parse_args()

    contract = base._load_json(CONTRACT_PATH)
    preflight = base._load_json(PREFLIGHT_PATH)
    if args.approved_identity != preflight["run_identity"]:
        raise RuntimeError("approved identity mismatch")
    if not 1 <= args.limit <= 331:
        raise ValueError("limit must be between 1 and 331")
    if args.max_usd <= 0:
        raise ValueError("max-usd must be positive")
    for candidate in contract["candidates"]:
        if not os.environ.get(candidate["api_key_env"]):
            raise RuntimeError(f"missing {candidate['api_key_env']}")

    selected = _load_cards(args.esc_eval, args.limit, contract["primary_sources"]["repository_commit"])
    args.out.mkdir(parents=True, exist_ok=True)
    ledger = args.out / "private_turn_ledger.jsonl"
    budget_ledger = args.out / "qwen_budget_ledger.jsonl"
    all_existing = base._read_jsonl(ledger) + base._read_jsonl(budget_ledger)
    if any(row.get("run_identity") != preflight["run_identity"] for row in all_existing):
        raise RuntimeError("existing ledger contains another identity")
    if base._qwen_spend(base._read_jsonl(budget_ledger)) > args.max_usd:
        raise RuntimeError("existing spend exceeds ceiling")

    supporter_prompt = contract["official_interaction_surface"]["supporter_system_prompt"]
    prompt_hash = base._sha_text(supporter_prompt)
    if prompt_hash != preflight["official_surface"]["supporter_system_prompt_sha256"]:
        raise RuntimeError("official supporter prompt drift")
    torch, tokenizer, role_model = base._load_role_model(args.role_model, args.role_device)
    from metacom_pm.api import OpenAICompatibleClient, RetryableProviderError, chat_request_payload

    clients = {row["candidate_id"]: OpenAICompatibleClient(base._candidate_endpoint(row)) for row in contract["candidates"]}
    try:
        for card_index, item in enumerate(selected):
            identity, card = item["identity"], item["card"]
            candidates = list(contract["candidates"])
            rotation = card_index % len(candidates)
            candidates = candidates[rotation:] + candidates[:rotation]
            for candidate in candidates:
                cid, card_key = candidate["candidate_id"], identity["card_key"]
                if (card_key, cid) in base._terminal(base._read_jsonl(ledger)):
                    continue
                close_trajectory = False
                for turn in range(1, 6):
                    events = base._read_jsonl(ledger)
                    unit_id = f"{identity['screen_id']}::{cid}::turn{turn}"
                    if unit_id in base._completed(events):
                        continue
                    history = base._history(events, card_key, cid)
                    if len(history) != (turn - 1) * 2:
                        raise RuntimeError(f"non-contiguous history before {unit_id}")
                    seeker_messages = [
                        {"role": "system", "content": base._role_prompt(card["base"])},
                        {"role": "user", "content": "Hello, I'm your personal assistant. You can confide in me about any worries or concerns you may have!"}
                    ]
                    for prior in history:
                        seeker_messages.append({"role": "assistant" if prior["role"] == "user" else "user", "content": prior["content"]})
                    pending = base._pending_roles(events)
                    if unit_id in pending:
                        seeker_text = pending[unit_id]["seeker_text"]
                    else:
                        seeker_text = base._generate_role(torch, tokenizer, role_model, seeker_messages, device=args.role_device, seed=_role_seed(card_key, turn))
                        base._append_jsonl(ledger, {
                            "event": "role_generated", "run_identity": preflight["run_identity"], "unit_id": unit_id,
                            "screen_id": identity["screen_id"], "card_key": card_key, "candidate_id": cid,
                            "turn": turn, "role_seed": _role_seed(card_key, turn), "seeker_text": seeker_text,
                            "timestamp_unix": time.time()
                        })
                    supporter_messages = [{"role": "system", "content": supporter_prompt}, *history, {"role": "user", "content": seeker_text}]
                    cap = int(candidate["max_output_tokens"])
                    endpoint = base._candidate_endpoint(candidate)
                    payload = chat_request_payload(endpoint, supporter_messages, temperature=0.0, max_tokens=cap, seed=None, response_schema=None)
                    if "max_tokens" not in payload and "max_completion_tokens" not in payload:
                        raise RuntimeError("official wrapper output cap missing from payload")
                    attempt = 0
                    while True:
                        attempt += 1
                        reserve = None
                        if base._is_qwen(cid):
                            reserve = _capped_qwen_reserve(supporter_messages, cap)
                            spend = base._qwen_spend(base._read_jsonl(budget_ledger))
                            if spend + float(reserve["reserve_usd"]) > args.max_usd:
                                raise RuntimeError(f"Qwen ceiling cannot reserve next call: spent={spend:.6f}, reserve={float(reserve['reserve_usd']):.6f}, ceiling={args.max_usd:.6f}")
                        try:
                            call, _ = clients[cid].chat(supporter_messages, temperature=0.0, max_tokens=cap, retries=1)
                        except RetryableProviderError as exc:
                            if base._is_qwen(cid):
                                base._append_jsonl(budget_ledger, {"event": "qwen_physical_attempt", "run_identity": preflight["run_identity"], "unit_id": unit_id, "candidate_id": cid, "physical_attempt": attempt, "usage": exc.usage or {}, "pre_call_reserve": reserve, "timestamp_unix": time.time()})
                            base._append_jsonl(ledger, {"event": "supporter_failed", "run_identity": preflight["run_identity"], "unit_id": unit_id, "card_key": card_key, "candidate_id": cid, "turn": turn, "physical_attempt": attempt, "failure_class": exc.last_retry_class, "status_code": exc.last_status_code, "usage": exc.usage or {}, "timestamp_unix": time.time()})
                            transient = exc.last_retry_class in {"rate_limited_429", "request_timeout_408", "http_5xx", "network_timeout"}
                            if not transient:
                                raise
                            if attempt >= 2:
                                base._append_jsonl(ledger, {"event": "trajectory_terminal_failure", "run_identity": preflight["run_identity"], "screen_id": identity["screen_id"], "card_key": card_key, "candidate_id": cid, "terminal_turn": turn, "terminal_failure_class": exc.last_retry_class, "attempts_exhausted": attempt, "timestamp_unix": time.time()})
                                close_trajectory = True
                                break
                            time.sleep(min(float(exc.retry_after_seconds or 5.0), 30.0))
                            continue
                        if base._is_qwen(cid):
                            base._append_jsonl(budget_ledger, {"event": "qwen_physical_attempt", "run_identity": preflight["run_identity"], "unit_id": unit_id, "candidate_id": cid, "physical_attempt": attempt, "usage": call.usage, "pre_call_reserve": reserve, "timestamp_unix": time.time()})
                        base._append_jsonl(ledger, {
                            "event": "supporter_succeeded", "run_identity": preflight["run_identity"], "unit_id": unit_id,
                            "screen_id": identity["screen_id"], "card_key": card_key, "source": identity["source"],
                            "candidate_id": cid, "model": candidate["model"], "enable_thinking": candidate.get("enable_thinking"),
                            "turn": turn, "seeker_text": seeker_text, "supporter_text": call.text,
                            "supporter_prompt_sha256": prompt_hash, "request_hash": call.request_hash,
                            "official_wrapper_output_cap": cap, "usage": call.usage, "latency_ms": call.latency_ms,
                            "provider_finish_reason": call.provider_finish_reason, "normalized_finish_reason": call.normalized_finish_reason,
                            "raw_response": call.raw_response, "timestamp_unix": time.time()
                        })
                        break
                    if close_trajectory:
                        break
    finally:
        for client in clients.values():
            client.close()

    events = base._read_jsonl(ledger)
    selected_keys = {item["identity"]["card_key"] for item in selected}
    success = [row for row in events if row.get("event") == "supporter_succeeded" and row.get("card_key") in selected_keys]
    failures = [row for row in events if row.get("event") == "trajectory_terminal_failure" and row.get("card_key") in selected_keys]
    summary = {
        "protocol": "metacom-v3-g0-official-protocol-english331-run-summary-v1",
        "run_identity": preflight["run_identity"], "cards_requested": args.limit,
        "successful_turns": len(success), "terminal_trajectories": len(failures),
        "expected_turns_if_no_failure": args.limit * 5 * 2,
        "qwen_actual_usd": base._qwen_spend(base._read_jsonl(budget_ledger)),
        "official_pass_line": None, "quality_scored": False,
        "next": "Run the pinned ESC-RANK profile and a frozen source-stratified official-rubric human anchor."
    }
    (args.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
