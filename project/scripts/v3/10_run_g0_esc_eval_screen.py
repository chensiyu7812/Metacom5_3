#!/usr/bin/env python3
"""Run the frozen G0 ESC-Eval screen with a local official ESC-Role model.

All generated dialogue and provider payloads are private run artifacts under
project/outputs.  The script is resumable at the (card, candidate, turn) unit.
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
AUTHORITY_DIR = PROJECT_ROOT / "data" / "v3_authority"
CONTRACT_PATH = AUTHORITY_DIR / "g0_generator_bakeoff_contract_v1.json"
PREFLIGHT_PATH = AUTHORITY_DIR / "g0_generator_bakeoff_preflight_v1.json"
MANIFEST_PATH = AUTHORITY_DIR / "g0_esc_eval_screening_manifest_v1.jsonl"


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


def _require_ledger_identity(events: list[dict[str, Any]], run_identity: str, label: str) -> None:
    mismatched = [row for row in events if row.get("run_identity") != run_identity]
    if mismatched:
        raise RuntimeError(f"{label} contains {len(mismatched)} event(s) from another run identity")


def _git_head(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _load_selected_cards(esc_eval: Path) -> list[dict[str, Any]]:
    contract = _load_json(CONTRACT_PATH)
    if _git_head(esc_eval) != contract["esc_eval_screen"]["exam_commit"]:
        raise RuntimeError("ESC-Eval checkout is not at the frozen commit")
    raw = json.loads((esc_eval / "data" / "card_high_en.json").read_text(encoding="utf-8"))
    by_key = {f"{row['language']}::{row['source']}::{row['id']}": row for row in raw}
    manifest = _read_jsonl(MANIFEST_PATH)
    selected = []
    for identity in manifest:
        card = by_key.get(identity["card_key"])
        if card is None:
            raise RuntimeError(f"frozen card not found: {identity['card_key']}")
        if _sha_text(card["base"]) != identity["role_card_sha256"]:
            raise RuntimeError(f"role-card hash drift: {identity['card_key']}")
        selected.append({"identity": identity, "card": card})
    return selected


def _role_prompt(card_text: str) -> str:
    return (
        "I hope you can role-play as a person with worries and communicate with an AI assistant. "
        "Here is your character card:'"
        + card_text
        + "\n' Please simulate a natural human conversation as much as possible. "
        "Avoid behaving like a machine and refrain from mentioning that you are an AI assistant. "
        "Gradually reveal your worries throughout our multiple conversations."
    )


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


def _role_seed(card_key: str, turn: int) -> int:
    return int(_sha_text(f"metacom-v3-g0-role-seed|{card_key}|{turn}")[:8], 16)


def _load_role_model(path: Path, device: str):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    expected = "2e2a4733d2e71da242f348aad165fe171acd5df7"
    if path.resolve().name != expected:
        raise RuntimeError("ESC-Role local path does not end in the frozen revision")
    tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        path,
        local_files_only=True,
        torch_dtype=torch.bfloat16,
        device_map={"": device},
    ).eval()
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
    new_tokens = generated[0][inputs["input_ids"].shape[-1] :]
    text = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()
    if not text:
        raise RuntimeError("ESC-Role produced an empty turn")
    return text


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


def _completed_by_unit(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {row["unit_id"]: row for row in events if row.get("event") == "supporter_succeeded"}


def _pending_role_by_unit(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    pending: dict[str, dict[str, Any]] = {}
    for row in events:
        if row.get("event") == "role_generated":
            pending[row["unit_id"]] = row
    return pending


def _terminal_trajectories(events: list[dict[str, Any]]) -> set[tuple[str, str]]:
    return {
        (row["card_key"], row["candidate_id"])
        for row in events
        if row.get("event") == "trajectory_terminal_failure"
    }


def _history_for(events: list[dict[str, Any]], card_key: str, candidate_id: str) -> list[dict[str, str]]:
    rows = [
        row
        for row in events
        if row.get("event") == "supporter_succeeded"
        and row.get("card_key") == card_key
        and row.get("candidate_id") == candidate_id
    ]
    rows.sort(key=lambda row: row["turn"])
    history: list[dict[str, str]] = []
    for row in rows:
        history.extend(
            [
                {"role": "user", "content": row["seeker_text"]},
                {"role": "assistant", "content": row["supporter_text"]},
            ]
        )
    return history


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--esc-eval", required=True, type=Path)
    parser.add_argument("--role-model", required=True, type=Path)
    parser.add_argument("--role-device", default="cuda:0")
    parser.add_argument("--approved-identity", required=True)
    parser.add_argument("--max-usd", required=True, type=float)
    parser.add_argument("--limit", type=int, default=24)
    parser.add_argument(
        "--out",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "v3_g0_generator_screen_20260813",
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
    if not 1 <= args.limit <= 24:
        raise ValueError("limit must be between 1 and 24")
    for candidate in contract["candidates"]:
        if not os.environ.get(candidate["api_key_env"]):
            raise RuntimeError(f"missing {candidate['api_key_env']}")

    selected = _load_selected_cards(args.esc_eval)[: args.limit]
    args.out.mkdir(parents=True, exist_ok=True)
    ledger = args.out / "private_turn_ledger.jsonl"
    events = _read_jsonl(ledger)
    _require_ledger_identity(events, preflight["run_identity"], "dialogue ledger")
    budget_events = _read_jsonl(args.qwen_budget_ledger)
    _require_ledger_identity(budget_events, preflight["run_identity"], "Qwen budget ledger")
    if _qwen_cost_usd(budget_events) > args.max_usd:
        raise RuntimeError("existing Qwen usage already exceeds approved max-usd")

    torch, tokenizer, role_model = _load_role_model(args.role_model, args.role_device)
    from metacom_pm.api import OpenAICompatibleClient, RetryableProviderError

    clients = {
        row["candidate_id"]: OpenAICompatibleClient(_candidate_endpoint(row))
        for row in contract["candidates"]
    }
    try:
        for card_index, item in enumerate(selected):
            identity, card = item["identity"], item["card"]
            candidates = list(contract["candidates"])
            rotation = card_index % len(candidates)
            candidates = candidates[rotation:] + candidates[:rotation]
            for candidate in candidates:
                cid = candidate["candidate_id"]
                card_key = identity["card_key"]
                if (card_key, cid) in _terminal_trajectories(_read_jsonl(ledger)):
                    continue
                trajectory_closed = False
                for turn in range(1, 6):
                    events = _read_jsonl(ledger)
                    completed = _completed_by_unit(events)
                    pending = _pending_role_by_unit(events)
                    unit_id = f"{identity['screen_id']}::{cid}::turn{turn}"
                    if unit_id in completed:
                        continue
                    history = _history_for(events, card_key, cid)
                    if len(history) != (turn - 1) * 2:
                        raise RuntimeError(f"non-contiguous history before {unit_id}")
                    seeker_messages = [
                        {"role": "system", "content": _role_prompt(card["base"])},
                        {"role": "user", "content": "Hello, I'm your personal assistant. You can confide in me about any worries or concerns you may have!"},
                    ]
                    for prior in history:
                        seeker_messages.append(
                            {"role": "assistant" if prior["role"] == "user" else "user", "content": prior["content"]}
                        )
                    if unit_id in pending:
                        seeker_text = pending[unit_id]["seeker_text"]
                    else:
                        seeker_text = _generate_role(
                            torch,
                            tokenizer,
                            role_model,
                            seeker_messages,
                            device=args.role_device,
                            seed=_role_seed(card_key, turn),
                        )
                        _append_jsonl(
                            ledger,
                            {
                                "event": "role_generated",
                                "run_identity": preflight["run_identity"],
                                "unit_id": unit_id,
                                "screen_id": identity["screen_id"],
                                "card_key": card_key,
                                "candidate_id": cid,
                                "turn": turn,
                                "role_seed": _role_seed(card_key, turn),
                                "seeker_text": seeker_text,
                                "timestamp_unix": time.time(),
                            },
                        )
                    supporter_messages = [{"role": "system", "content": "You are a helpful assistant!"}, *history, {"role": "user", "content": seeker_text}]
                    attempt = 0
                    while True:
                        attempt += 1
                        if cid == "qwen37_plus_primary_challenger" and _qwen_cost_usd(_read_jsonl(args.qwen_budget_ledger)) + _qwen_max_call_usd() > args.max_usd:
                            raise RuntimeError("approved Qwen cost ceiling reached")
                        try:
                            call, _ = clients[cid].chat(
                                supporter_messages,
                                temperature=0.0,
                                max_tokens=256,
                                retries=1,
                            )
                        except RetryableProviderError as exc:
                            if cid == "qwen37_plus_primary_challenger":
                                _append_jsonl(
                                    args.qwen_budget_ledger,
                                    {
                                        "event": "qwen_physical_attempt",
                                        "run_identity": preflight["run_identity"],
                                        "surface": "esc_eval",
                                        "unit_id": unit_id,
                                        "candidate_id": cid,
                                        "physical_attempt": attempt,
                                        "usage": exc.usage or {},
                                        "timestamp_unix": time.time(),
                                    },
                                )
                            _append_jsonl(
                                ledger,
                                {
                                    "event": "supporter_failed",
                                    "run_identity": preflight["run_identity"],
                                    "unit_id": unit_id,
                                    "card_key": card_key,
                                    "candidate_id": cid,
                                    "turn": turn,
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
                                        "event": "trajectory_terminal_failure",
                                        "run_identity": preflight["run_identity"],
                                        "screen_id": identity["screen_id"],
                                        "card_key": card_key,
                                        "candidate_id": cid,
                                        "terminal_turn": turn,
                                        "terminal_failure_class": exc.last_retry_class,
                                        "attempts_exhausted": attempt,
                                        "timestamp_unix": time.time(),
                                    },
                                )
                                trajectory_closed = True
                                break
                            time.sleep(min(float(exc.retry_after_seconds or 5.0), 30.0))
                            continue
                        usage = call.usage
                        if cid == "qwen37_plus_primary_challenger":
                            _append_jsonl(
                                args.qwen_budget_ledger,
                                {
                                    "event": "qwen_physical_attempt",
                                    "run_identity": preflight["run_identity"],
                                    "surface": "esc_eval",
                                    "unit_id": unit_id,
                                    "candidate_id": cid,
                                    "physical_attempt": attempt,
                                    "usage": usage,
                                    "timestamp_unix": time.time(),
                                },
                            )
                        if int(usage.get("prompt_tokens", 0)) > 8192 or int(usage.get("completion_tokens", 0)) > 256:
                            raise RuntimeError(f"token budget contract exceeded at {unit_id}: {usage}")
                        _append_jsonl(
                            ledger,
                            {
                                "event": "supporter_succeeded",
                                "run_identity": preflight["run_identity"],
                                "unit_id": unit_id,
                                "screen_id": identity["screen_id"],
                                "card_key": card_key,
                                "candidate_id": cid,
                                "model": candidate["model"],
                                "turn": turn,
                                "physical_attempt": attempt,
                                "seeker_text": seeker_text,
                                "supporter_text": call.text,
                                "request_hash": call.request_hash,
                                "usage": usage,
                                "latency_ms": call.latency_ms,
                                "provider_finish_reason": call.provider_finish_reason,
                                "raw_response": call.raw_response,
                                "timestamp_unix": time.time(),
                            },
                        )
                        break
                    if trajectory_closed:
                        break
    finally:
        for client in clients.values():
            client.close()

    events = _read_jsonl(ledger)
    success = [row for row in events if row.get("event") == "supporter_succeeded"]
    terminal = [row for row in events if row.get("event") == "trajectory_terminal_failure"]
    expected = len(selected) * len(contract["candidates"]) * 5
    expected_trajectories = len(selected) * len(contract["candidates"])
    completed_trajectories = len(
        {
            (row["card_key"], row["candidate_id"])
            for row in success
            if row["turn"] == 5
        }
    )
    summary = {
        "protocol": "metacom-v3-g0-esc-eval-screen-run-summary-v1",
        "run_identity": preflight["run_identity"],
        "cards_requested": len(selected),
        "successful_supporter_turns": len(success),
        "expected_supporter_turns": expected,
        "complete": len(success) == expected,
        "execution_closed": completed_trajectories + len(terminal) == expected_trajectories,
        "completed_trajectories": completed_trajectories,
        "terminal_failed_trajectories": len(terminal),
        "qwen_estimated_usd_across_g0_surfaces": _qwen_cost_usd(_read_jsonl(args.qwen_budget_ledger)),
        "formal_qualification": False,
        "next": "Run local repaired ESC-RANK and the separately frozen executor screen; do not select from unscored dialogue text.",
    }
    (args.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["execution_closed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
