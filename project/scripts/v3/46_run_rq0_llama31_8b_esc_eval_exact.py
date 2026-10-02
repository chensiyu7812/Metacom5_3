#!/usr/bin/env python3
"""Run hosted Llama 3.1 8B through the ESC-Eval evaluate.py protocol."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
AUTHORITY = ROOT / "data" / "v3_authority"
CONTRACT_PATH = AUTHORITY / "rq0_llama31_8b_esc_eval_exact_contract_v1.json"
PREFLIGHT_PATH = AUTHORITY / "rq0_llama31_8b_esc_eval_exact_preflight_v1.json"
BASE_PATH = Path(__file__).with_name("16_run_g0_research_aligned_esc.py")

spec = importlib.util.spec_from_file_location("rq0_exact_helpers", BASE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load append-only runtime helpers")
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)


def _role_prompt(card_text: str) -> str:
    return (
        "I hope you can role-play as a person with worries and communicate with an AI assistant. "
        "Here is your character card:'" + card_text
        + "\n' Please simulate a natural human conversation as much as possible. "
        "Avoid behaving like a machine and refrain from mentioning that you are an AI assistant. "
        "Gradually reveal your worries throughout our multiple conversations."
    )


def _load_role_model(path: Path, device: str):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if path.resolve().name != "2e2a4733d2e71da242f348aad165fe171acd5df7":
        raise RuntimeError("ESC-Role revision drifted")
    tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        path, local_files_only=True, torch_dtype="auto", device_map={"": device}
    ).eval()
    return torch, tokenizer, model


def _generate_official_role(tokenizer, model, messages, device: str) -> str:
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    model_inputs = tokenizer([text], return_tensors="pt").to(device)
    generated_ids = model.generate(model_inputs.input_ids, max_new_tokens=512)
    generated_ids = [
        output_ids[len(input_ids):]
        for input_ids, output_ids in zip(model_inputs.input_ids, generated_ids)
    ]
    response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
    if not response.strip():
        raise RuntimeError("ESC-Role produced an empty response")
    return response


def _official_result(cards: list[dict], events: list[dict], initial: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for index, card in enumerate(cards):
        card_key = f"{card['language']}::{card['source']}::{card['id']}"
        rows = [
            row for row in events
            if row.get("event") == "supporter_succeeded" and row.get("card_key") == card_key
        ]
        rows.sort(key=lambda row: row["turn"])
        if len(rows) != 5:
            continue
        dialogue = ["AI assistant：" + initial]
        for row in rows:
            dialogue.append("ESC-Role：" + row["seeker_text"])
            dialogue.append("AI assistant：" + row["supporter_text"])
        result[str(index)] = dialogue
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--esc-eval", required=True, type=Path)
    parser.add_argument("--role-model", required=True, type=Path)
    parser.add_argument("--role-device", default="cuda:0")
    parser.add_argument("--approved-identity", required=True)
    parser.add_argument("--limit", type=int, default=331)
    parser.add_argument(
        "--out", type=Path,
        default=ROOT / "outputs" / "v3_rq0_llama31_8b_esc_eval_exact_v1_20260815",
    )
    args = parser.parse_args()
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    preflight = json.loads(PREFLIGHT_PATH.read_text(encoding="utf-8"))
    if args.approved_identity != preflight["run_identity"]:
        raise RuntimeError("approved identity mismatch")
    if not 1 <= args.limit <= 331:
        raise ValueError("limit must be between 1 and 331")
    candidate = contract["candidate"]
    if not os.environ.get(candidate["api_key_env"]):
        raise RuntimeError(f"missing {candidate['api_key_env']}")
    git_head = subprocess.run(
        ["git", "-C", str(args.esc_eval), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    if git_head != contract["official_interaction"]["source_commit"]:
        raise RuntimeError("ESC-Eval checkout drifted")
    cards_path = args.esc_eval / "data" / "card_high_en.json"
    if helpers._sha_text(cards_path.read_text(encoding="utf-8")) != preflight["cards_text_sha256"]:
        raise RuntimeError("official English role-card file drifted")
    cards = json.loads(cards_path.read_text(encoding="utf-8"))[:args.limit]

    args.out.mkdir(parents=True, exist_ok=True)
    ledger = args.out / "private_turn_ledger.jsonl"
    existing = helpers._read_jsonl(ledger)
    if any(row.get("run_identity") != preflight["run_identity"] for row in existing):
        raise RuntimeError("existing ledger contains another identity")
    torch, tokenizer, role_model = _load_role_model(args.role_model, args.role_device)
    from metacom_pm.api import OpenAICompatibleClient, RetryableProviderError, chat_request_payload

    endpoint = helpers._candidate_endpoint(candidate)
    client = OpenAICompatibleClient(endpoint)
    official = contract["official_interaction"]
    initial = official["initial_utterance"]
    supporter_prompt = official["supporter_system_prompt"]
    cap = int(official["generator_generation"]["max_new_tokens"])
    try:
        for index, card in enumerate(cards):
            card_key = f"{card['language']}::{card['source']}::{card['id']}"
            screen_id = "esc331_" + helpers._sha_text(card_key)[:16]
            if (card_key, candidate["candidate_id"]) in helpers._terminal(helpers._read_jsonl(ledger)):
                continue
            close = False
            for turn in range(1, 6):
                events = helpers._read_jsonl(ledger)
                unit_id = f"{screen_id}::{candidate['candidate_id']}::turn{turn}"
                if unit_id in helpers._completed(events):
                    continue
                history = helpers._history(events, card_key, candidate["candidate_id"])
                if len(history) != (turn - 1) * 2:
                    raise RuntimeError(f"non-contiguous history before {unit_id}")
                role_messages = [
                    {"role": "system", "content": _role_prompt(card["base"])},
                    {"role": "user", "content": initial},
                ]
                for prior in history:
                    role_messages.append({
                        "role": "assistant" if prior["role"] == "user" else "user",
                        "content": prior["content"],
                    })
                pending = helpers._pending_roles(events)
                if unit_id in pending:
                    seeker_text = pending[unit_id]["seeker_text"]
                else:
                    seeker_text = _generate_official_role(tokenizer, role_model, role_messages, args.role_device)
                    helpers._append_jsonl(ledger, {
                        "event": "role_generated", "run_identity": preflight["run_identity"],
                        "unit_id": unit_id, "screen_id": screen_id, "card_key": card_key,
                        "candidate_id": candidate["candidate_id"], "turn": turn,
                        "official_role_generation": True, "seeker_text": seeker_text,
                        "timestamp_unix": time.time(),
                    })
                supporter_messages = [
                    {"role": "system", "content": supporter_prompt},
                    *history, {"role": "user", "content": seeker_text},
                ]
                payload = chat_request_payload(
                    endpoint, supporter_messages, temperature=0.0,
                    max_tokens=cap, seed=None, response_schema=None,
                )
                if payload.get("max_tokens", payload.get("max_completion_tokens")) != 256:
                    raise RuntimeError("official Llama 256-token condition is missing")
                attempt = 0
                while True:
                    attempt += 1
                    try:
                        call, _ = client.chat(
                            supporter_messages, temperature=0.0, max_tokens=cap, retries=1
                        )
                    except RetryableProviderError as exc:
                        helpers._append_jsonl(ledger, {
                            "event": "supporter_failed", "run_identity": preflight["run_identity"],
                            "unit_id": unit_id, "card_key": card_key,
                            "candidate_id": candidate["candidate_id"], "turn": turn,
                            "physical_attempt": attempt, "failure_class": exc.last_retry_class,
                            "status_code": exc.last_status_code, "usage": exc.usage or {},
                            "timestamp_unix": time.time(),
                        })
                        transient = exc.last_retry_class in {
                            "rate_limited_429", "request_timeout_408", "http_5xx", "network_timeout"
                        }
                        if not transient:
                            raise
                        if attempt >= 2:
                            helpers._append_jsonl(ledger, {
                                "event": "trajectory_terminal_failure",
                                "run_identity": preflight["run_identity"], "screen_id": screen_id,
                                "card_key": card_key, "candidate_id": candidate["candidate_id"],
                                "terminal_turn": turn, "terminal_failure_class": exc.last_retry_class,
                                "attempts_exhausted": attempt, "timestamp_unix": time.time(),
                            })
                            close = True
                            break
                        time.sleep(min(float(exc.retry_after_seconds or 5.0), 30.0))
                        continue
                    helpers._append_jsonl(ledger, {
                        "event": "supporter_succeeded", "run_identity": preflight["run_identity"],
                        "unit_id": unit_id, "screen_id": screen_id, "card_key": card_key,
                        "source": card["source"], "candidate_id": candidate["candidate_id"],
                        "model": candidate["model"], "turn": turn,
                        "seeker_text": seeker_text, "supporter_text": call.text,
                        "supporter_prompt_sha256": helpers._sha_text(supporter_prompt),
                        "request_hash": call.request_hash, "official_max_new_tokens": 256,
                        "usage": call.usage, "latency_ms": call.latency_ms,
                        "provider_finish_reason": call.provider_finish_reason,
                        "normalized_finish_reason": call.normalized_finish_reason,
                        "raw_response": call.raw_response, "timestamp_unix": time.time(),
                    })
                    break
                if close:
                    break
    finally:
        client.close()

    events = helpers._read_jsonl(ledger)
    result = _official_result(cards, events, initial)
    (args.out / "official_result_llama31_8b_en.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=4) + "\n", encoding="utf-8"
    )
    success = [row for row in events if row.get("event") == "supporter_succeeded"]
    terminal = [row for row in events if row.get("event") == "trajectory_terminal_failure"]
    summary = {
        "protocol": "metacom-v3-rq0-llama31-8b-esc-eval-exact-run-summary-v1",
        "run_identity": preflight["run_identity"], "cards_requested": args.limit,
        "complete_official_dialogues": len(result), "successful_turns": len(success),
        "expected_turns": args.limit * 5, "terminal_trajectories": len(terminal),
        "provider_length_finishes": sum(row.get("normalized_finish_reason") == "length" for row in success),
        "official_generator_max_new_tokens": 256, "qwen_calls": 0, "observed_usd": 0.0,
        "quality_scored": False, "official_pass_line": None,
    }
    (args.out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
