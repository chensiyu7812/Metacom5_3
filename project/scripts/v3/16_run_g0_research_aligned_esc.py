#!/usr/bin/env python3
"""Run the uncapped, prior-work-grounded G0 supporter comparison.

The provider max-output parameter is deliberately omitted. Raw dialogue and
provider responses stay in a private, identity-bound, append-only ledger.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
AUTHORITY_DIR = PROJECT_ROOT / "data" / "v3_authority"
CONTRACT_PATH = AUTHORITY_DIR / "g0_research_aligned_generator_contract_v2.json"
PROMPT_PATH = AUTHORITY_DIR / "g0_research_aligned_supporter_prompt_v1.json"
PREFLIGHT_PATH = AUTHORITY_DIR / "g0_research_aligned_generator_preflight_v2.json"
MANIFEST_PATH = AUTHORITY_DIR / "g0_research_aligned_screening_manifest_v2.jsonl"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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


def _supporter_prompt() -> str:
    prompt = _load_json(PROMPT_PATH)
    return "\n\n".join(section.strip() for section in prompt["prompt_sections"])


def _git_head(repo: Path) -> str:
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()


def _load_selected_cards(esc_eval: Path, limit: int) -> list[dict[str, Any]]:
    contract = _load_json(CONTRACT_PATH)
    if _git_head(esc_eval) != contract["dialogue_surface"]["esc_eval_commit"]:
        raise RuntimeError("ESC-Eval checkout is not at the frozen commit")
    raw = json.loads((esc_eval / "data" / "card_high_en.json").read_text(encoding="utf-8"))
    by_key = {f"{row['language']}::{row['source']}::{row['id']}": row for row in raw}
    selected = []
    for identity in _read_jsonl(MANIFEST_PATH)[:limit]:
        card = by_key.get(identity["card_key"])
        if card is None or _sha_text(card["base"]) != identity["role_card_sha256"]:
            raise RuntimeError(f"role-card identity drift: {identity['card_key']}")
        selected.append({"identity": identity, "card": card})
    return selected


def _role_prompt(card_text: str) -> str:
    return (
        "I hope you can role-play as a person with worries and communicate with an AI assistant. "
        "Here is your character card:'" + card_text
        + "\n' Please simulate a natural human conversation as much as possible. "
        "Avoid behaving like a machine and refrain from mentioning that you are an AI assistant. "
        "Gradually reveal your worries throughout our multiple conversations."
    )


def _role_seed(card_key: str, turn: int) -> int:
    return int(_sha_text(f"metacom-v3-g0r2-role-seed|{card_key}|{turn}")[:8], 16)


def _load_role_model(path: Path, device: str):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    expected = "2e2a4733d2e71da242f348aad165fe171acd5df7"
    if path.resolve().name != expected:
        raise RuntimeError("ESC-Role local path does not end in the frozen revision")
    tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(path, local_files_only=True, torch_dtype=torch.bfloat16, device_map={"": device}).eval()
    return torch, tokenizer, model


def _generate_role(torch, tokenizer, model, messages: list[dict[str, str]], *, device: str, seed: int) -> str:
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    rendered = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer([rendered], return_tensors="pt").to(device)
    with torch.inference_mode():
        generated = model.generate(
            **inputs,
            max_new_tokens=512,
            do_sample=True,
            temperature=0.7,
            top_p=0.8,
            top_k=20,
            repetition_penalty=1.05,
            pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
        )
    text = tokenizer.decode(generated[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True).strip()
    if not text:
        raise RuntimeError("ESC-Role produced an empty turn")
    return text


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


def _is_qwen(candidate_id: str) -> bool:
    return candidate_id.startswith("qwen37_plus_")


def _qwen_call_cost(usage: dict[str, Any]) -> float:
    prompt = int(usage.get("prompt_tokens", 0))
    completion = int(usage.get("completion_tokens", 0))
    if prompt <= 256_000:
        input_rate, output_rate = 0.4, 1.6
    else:
        input_rate, output_rate = 1.2, 4.8
    return (prompt * input_rate + completion * output_rate) / 1_000_000


def _qwen_spend(events: list[dict[str, Any]]) -> float:
    return sum(_qwen_call_cost(row.get("usage") or {}) for row in events if row.get("event") == "qwen_physical_attempt")


def _qwen_pre_call_reserve(messages: list[dict[str, str]]) -> dict[str, float | int]:
    # Every tokenizer token contains at least one input byte. Adding 4096
    # tokens covers chat-template/provider framing while keeping the bound
    # deliberately conservative and independently reproducible.
    input_upper_tokens = len(_canonical(messages).encode("utf-8")) + 4096
    if input_upper_tokens > 1_000_000:
        raise RuntimeError("conservative Qwen input bound exceeds documented context")
    if input_upper_tokens <= 256_000:
        input_rate, output_rate = 0.4, 1.6
    else:
        input_rate, output_rate = 1.2, 4.8
    reserve = (input_upper_tokens * input_rate + 65_536 * output_rate) / 1_000_000
    return {"input_upper_tokens": input_upper_tokens, "reserve_usd": reserve}


def _completed(events: list[dict[str, Any]]) -> set[str]:
    return {row["unit_id"] for row in events if row.get("event") == "supporter_succeeded"}


def _terminal(events: list[dict[str, Any]]) -> set[tuple[str, str]]:
    return {(row["card_key"], row["candidate_id"]) for row in events if row.get("event") == "trajectory_terminal_failure"}


def _pending_roles(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["unit_id"]: row for row in events if row.get("event") == "role_generated"}


def _history(events: list[dict[str, Any]], card_key: str, candidate_id: str) -> list[dict[str, str]]:
    rows = [row for row in events if row.get("event") == "supporter_succeeded" and row.get("card_key") == card_key and row.get("candidate_id") == candidate_id]
    rows.sort(key=lambda row: row["turn"])
    history: list[dict[str, str]] = []
    for row in rows:
        history.extend([{"role": "user", "content": row["seeker_text"]}, {"role": "assistant", "content": row["supporter_text"]}])
    return history


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--esc-eval", required=True, type=Path)
    parser.add_argument("--role-model", required=True, type=Path)
    parser.add_argument("--role-device", default="cuda:0")
    parser.add_argument("--approved-identity", required=True)
    parser.add_argument("--max-usd", required=True, type=float)
    parser.add_argument("--limit", type=int, default=2)
    parser.add_argument("--out", type=Path, default=PROJECT_ROOT / "outputs" / "v3_g0_research_aligned_generator_v2_20260814")
    args = parser.parse_args()
    contract = _load_json(CONTRACT_PATH)
    preflight = _load_json(PREFLIGHT_PATH)
    if args.approved_identity != preflight["run_identity"]:
        raise RuntimeError("approved identity does not match the frozen research-aligned preflight")
    if not 1 <= args.limit <= int(preflight["sample"]["development_cards"]):
        raise ValueError("limit is outside the frozen development sample")
    if args.max_usd <= 0:
        raise ValueError("max-usd must be positive")
    for candidate in contract["candidates"]:
        if not os.environ.get(candidate["api_key_env"]):
            raise RuntimeError(f"missing {candidate['api_key_env']}")

    selected = _load_selected_cards(args.esc_eval, args.limit)
    args.out.mkdir(parents=True, exist_ok=True)
    ledger = args.out / "private_turn_ledger.jsonl"
    budget_ledger = args.out / "qwen_budget_ledger.jsonl"
    events = _read_jsonl(ledger)
    budget_events = _read_jsonl(budget_ledger)
    if any(row.get("run_identity") != preflight["run_identity"] for row in events + budget_events):
        raise RuntimeError("existing ledger contains another run identity")
    if _qwen_spend(budget_events) > args.max_usd:
        raise RuntimeError("existing Qwen spend exceeds the approved ceiling")

    prompt_text = _supporter_prompt()
    prompt_hash = _sha_text(prompt_text)
    if prompt_hash != preflight["prompt"]["joined_prompt_sha256"]:
        raise RuntimeError("supporter prompt drifted")
    torch, tokenizer, role_model = _load_role_model(args.role_model, args.role_device)
    from metacom_pm.api import OpenAICompatibleClient, RetryableProviderError, chat_request_payload

    clients = {row["candidate_id"]: OpenAICompatibleClient(_candidate_endpoint(row)) for row in contract["candidates"]}
    try:
        for card_index, item in enumerate(selected):
            identity, card = item["identity"], item["card"]
            candidates = list(contract["candidates"])
            rotation = card_index % len(candidates)
            candidates = candidates[rotation:] + candidates[:rotation]
            for candidate in candidates:
                cid = candidate["candidate_id"]
                card_key = identity["card_key"]
                if (card_key, cid) in _terminal(_read_jsonl(ledger)):
                    continue
                close_trajectory = False
                for turn in range(1, int(contract["shared_generation_contract"]["turns_per_dialogue"]) + 1):
                    events = _read_jsonl(ledger)
                    unit_id = f"{identity['screen_id']}::{cid}::turn{turn}"
                    if unit_id in _completed(events):
                        continue
                    history = _history(events, card_key, cid)
                    if len(history) != (turn - 1) * 2:
                        raise RuntimeError(f"non-contiguous history before {unit_id}")
                    seeker_messages = [
                        {"role": "system", "content": _role_prompt(card["base"])},
                        {"role": "user", "content": "Hello, I'm your personal assistant. You can confide in me about any worries or concerns you may have!"},
                    ]
                    for prior in history:
                        seeker_messages.append({"role": "assistant" if prior["role"] == "user" else "user", "content": prior["content"]})
                    pending = _pending_roles(events)
                    if unit_id in pending:
                        seeker_text = pending[unit_id]["seeker_text"]
                    else:
                        seeker_text = _generate_role(torch, tokenizer, role_model, seeker_messages, device=args.role_device, seed=_role_seed(card_key, turn))
                        _append_jsonl(ledger, {
                            "event": "role_generated", "run_identity": preflight["run_identity"], "unit_id": unit_id,
                            "screen_id": identity["screen_id"], "card_key": card_key, "candidate_id": cid,
                            "turn": turn, "role_seed": _role_seed(card_key, turn), "seeker_text": seeker_text,
                            "timestamp_unix": time.time(),
                        })
                    supporter_messages = [{"role": "system", "content": prompt_text}, *history, {"role": "user", "content": seeker_text}]
                    endpoint = _candidate_endpoint(candidate)
                    payload = chat_request_payload(endpoint, supporter_messages, temperature=0.0, max_tokens=None, seed=None, response_schema=None)
                    if "max_tokens" in payload or "max_completion_tokens" in payload:
                        raise RuntimeError("researcher output cap leaked into provider payload")
                    attempt = 0
                    while True:
                        attempt += 1
                        reserve = None
                        if _is_qwen(cid):
                            reserve = _qwen_pre_call_reserve(supporter_messages)
                            spend = _qwen_spend(_read_jsonl(budget_ledger))
                            if spend + float(reserve["reserve_usd"]) > args.max_usd:
                                raise RuntimeError(
                                    f"approved Qwen ceiling cannot reserve next uncapped call: spent={spend:.6f}, reserve={float(reserve['reserve_usd']):.6f}, ceiling={args.max_usd:.6f}"
                                )
                        try:
                            call, _ = clients[cid].chat(supporter_messages, temperature=0.0, max_tokens=None, retries=1)
                        except RetryableProviderError as exc:
                            if _is_qwen(cid):
                                _append_jsonl(budget_ledger, {
                                    "event": "qwen_physical_attempt", "run_identity": preflight["run_identity"],
                                    "unit_id": unit_id, "candidate_id": cid, "physical_attempt": attempt,
                                    "usage": exc.usage or {}, "pre_call_reserve": reserve, "timestamp_unix": time.time(),
                                })
                            _append_jsonl(ledger, {
                                "event": "supporter_failed", "run_identity": preflight["run_identity"], "unit_id": unit_id,
                                "card_key": card_key, "candidate_id": cid, "turn": turn, "physical_attempt": attempt,
                                "failure_class": exc.last_retry_class, "status_code": exc.last_status_code,
                                "usage": exc.usage or {}, "timestamp_unix": time.time(),
                            })
                            transient = exc.last_retry_class in {"rate_limited_429", "request_timeout_408", "http_5xx", "network_timeout"}
                            if not transient:
                                raise
                            if attempt >= 2:
                                _append_jsonl(ledger, {
                                    "event": "trajectory_terminal_failure", "run_identity": preflight["run_identity"],
                                    "screen_id": identity["screen_id"], "card_key": card_key, "candidate_id": cid,
                                    "terminal_turn": turn, "terminal_failure_class": exc.last_retry_class,
                                    "attempts_exhausted": attempt, "timestamp_unix": time.time(),
                                })
                                close_trajectory = True
                                break
                            time.sleep(min(float(exc.retry_after_seconds or 5.0), 30.0))
                            continue
                        if _is_qwen(cid):
                            _append_jsonl(budget_ledger, {
                                "event": "qwen_physical_attempt", "run_identity": preflight["run_identity"],
                                "unit_id": unit_id, "candidate_id": cid, "physical_attempt": attempt,
                                "usage": call.usage, "pre_call_reserve": reserve, "timestamp_unix": time.time(),
                            })
                        completion_tokens = int(call.usage.get("completion_tokens", 0))
                        _append_jsonl(ledger, {
                            "event": "supporter_succeeded", "run_identity": preflight["run_identity"], "unit_id": unit_id,
                            "screen_id": identity["screen_id"], "card_key": card_key, "source": identity["source"],
                            "candidate_id": cid, "model": candidate["model"], "enable_thinking": candidate.get("enable_thinking"),
                            "turn": turn, "seeker_text": seeker_text, "supporter_text": call.text,
                            "supporter_prompt_sha256": prompt_hash, "request_hash": call.request_hash,
                            "researcher_output_token_cap": None, "provider_output_parameter_omitted": True,
                            "usage": call.usage, "latency_ms": call.latency_ms,
                            "completion_tokens_per_second": (completion_tokens / (call.latency_ms / 1000.0)) if completion_tokens and call.latency_ms > 0 else None,
                            "output_characters": len(call.text), "output_words_whitespace": len(call.text.split()),
                            "ends_terminal_punctuation": call.text.rstrip().endswith((".", "!", "?", "…", "\"", "'")),
                            "provider_finish_reason": call.provider_finish_reason,
                            "normalized_finish_reason": call.normalized_finish_reason,
                            "raw_response": call.raw_response, "timestamp_unix": time.time(),
                        })
                        break
                    if close_trajectory:
                        break
    finally:
        for client in clients.values():
            client.close()

    events = _read_jsonl(ledger)
    selected_keys = {item["identity"]["card_key"] for item in selected}
    terminal_success = [row for row in events if row.get("event") == "supporter_succeeded" and row.get("card_key") in selected_keys]
    terminal_failures = [row for row in events if row.get("event") == "trajectory_terminal_failure" and row.get("card_key") in selected_keys]
    expected_turns = args.limit * int(contract["shared_generation_contract"]["turns_per_dialogue"]) * len(contract["candidates"])
    summary = {
        "protocol": "metacom-v3-g0-research-aligned-run-summary-v2",
        "run_identity": preflight["run_identity"],
        "cards_requested": args.limit,
        "successful_turns": len(terminal_success),
        "terminal_trajectories": len(terminal_failures),
        "expected_turns_if_no_trajectory_failure": expected_turns,
        "qwen_actual_usd": _qwen_spend(_read_jsonl(budget_ledger)),
        "researcher_output_token_cap": None,
        "quality_judged": False,
        "canary_selects_generator": False,
        "next": "Close out transport/completion/latency, then separately approve order-swapped ESC-Judge quality comparisons."
    }
    (args.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
