#!/usr/bin/env python3
"""Replay the private DG supporter path on the intended A6000, with no API calls."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import canonical_json, read_json, sha256_text, utc_now, write_json  # noqa: E402
from metacom_pm.paper1.execution.dg_official import (  # noqa: E402
    DG_OFFICIAL_MAX_GENERATION_ATTEMPTS,
    DG_OFFICIAL_MAX_OUTPUT_TOKENS,
    build_official_dg_supporter_system_prompt,
    official_dg_supporter_messages,
    trim_to_last_complete_sentence,
)
from metacom_pm.paper1.execution.rq2_prompts import (  # noqa: E402
    LOCAL_GENERATOR_ARTIFACT_IDENTITY_SHA256,
    LOCAL_GENERATOR_CHAT_TEMPLATE_SHA256,
    LOCAL_GENERATOR_MODEL_REVISION,
    LOCAL_GENERATOR_SERVER_PROTOCOL,
)


PROTOCOL = "paper1-dg-supporter-a6000-local-replay-v1"
MODEL = "meta/llama-3.1-8b-instruct"
EXPECTED_GPU = "NVIDIA RTX A6000"


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8011")
    parser.add_argument(
        "--private-trajectory",
        type=Path,
        default=PROJECT
        / "outputs/paper1_dg_compatibility_pilot_v1/private_trajectory.json",
    )
    parser.add_argument(
        "--raw-data", type=Path, default=PROJECT / "data/external/evo_emo.json"
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=PROJECT
        / "data/paper1_authority/paper1_dg_supporter_a6000_replay_20260904_v1.json",
    )
    return parser.parse_args()


def _call(
    client: httpx.Client, base_url: str, messages: tuple[dict[str, str], ...]
) -> dict[str, Any]:
    payload = {
        "model": MODEL,
        "messages": list(messages),
        "temperature": 0,
        "max_tokens": DG_OFFICIAL_MAX_OUTPUT_TOKENS,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    started = time.monotonic_ns()
    parts: list[str] = []
    usage: dict[str, int] = {}
    finish = "unknown"
    with client.stream(
        "POST", f"{base_url.rstrip('/')}/v1/chat/completions", json=payload
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if not raw or raw == "[DONE]":
                continue
            chunk = json.loads(raw)
            if chunk.get("error"):
                raise RuntimeError(f"local generation failed: {chunk['error']}")
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
                finish = str(choice["finish_reason"])
            content = (choice.get("delta") or {}).get("content")
            if isinstance(content, str) and content:
                parts.append(content)
    text = "".join(parts)
    if not text:
        raise RuntimeError("A6000 replay returned no visible text")
    return {
        "text": text,
        "request_sha256": sha256_text(canonical_json(payload)),
        "response_sha256": sha256_text(text),
        "finish_reason": finish,
        "usage": usage,
        "latency_ms": (time.monotonic_ns() - started) / 1_000_000,
    }


def main() -> int:
    args = _args()
    private = read_json(args.private_trajectory)
    users = read_json(args.raw_data)
    user = next(row for row in users if str(row["id"]) == "p7")
    name = str(user["basic_info"]["name"])
    system_prompt = build_official_dg_supporter_system_prompt(seeker_name=name)
    opening = f"Hi {name}! How are you these days?"

    health_response = httpx.get(f"{args.base_url.rstrip('/')}/health", timeout=15.0)
    health_response.raise_for_status()
    health = health_response.json()
    expected_health = {
        "protocol": LOCAL_GENERATOR_SERVER_PROTOCOL,
        "model": MODEL,
        "revision": LOCAL_GENERATOR_MODEL_REVISION,
        "model_artifact_identity_sha256": LOCAL_GENERATOR_ARTIFACT_IDENTITY_SHA256,
        "chat_template_sha256": LOCAL_GENERATOR_CHAT_TEMPLATE_SHA256,
        "gpu": EXPECTED_GPU,
        "dtype": "bfloat16",
    }
    if any(health.get(key) != value for key, value in expected_health.items()):
        raise RuntimeError("replay server is not the frozen A6000 backend")

    prior: list[tuple[str, str]] = []
    attempts: list[dict[str, Any]] = []
    comparisons: list[dict[str, Any]] = []
    with httpx.Client(timeout=httpx.Timeout(180.0), http2=False) as client:
        for source_turn in private["turns"]:
            turn = int(source_turn["turn"])
            messages = official_dg_supporter_messages(
                system_prompt=system_prompt,
                first_supporter_message=opening,
                prior_turns=prior,
                current_seeker_message=str(source_turn["seeker"]),
            )
            final_text = ""
            for attempt in range(1, DG_OFFICIAL_MAX_GENERATION_ATTEMPTS + 1):
                result = _call(client, args.base_url, messages)
                attempts.append(
                    {
                        "turn": turn,
                        "attempt": attempt,
                        "request_sha256": result["request_sha256"],
                        "response_sha256": result["response_sha256"],
                        "finish_reason": result["finish_reason"],
                        "usage": result["usage"],
                        "latency_ms": result["latency_ms"],
                        "contains_response_text": False,
                    }
                )
                final_text = str(result["text"])
                if str(result["finish_reason"]).casefold() == "stop":
                    break
            else:
                final_text = trim_to_last_complete_sentence(final_text)
                attempts[-1]["third_non_stop_prefix_trim_applied"] = True
                attempts[-1]["trimmed_response_sha256"] = sha256_text(final_text)
            expected_hash = sha256_text(str(source_turn["supporter"]))
            actual_hash = sha256_text(final_text)
            comparisons.append(
                {
                    "turn": turn,
                    "source_a4500_supporter_sha256": expected_hash,
                    "a6000_replay_supporter_sha256": actual_hash,
                    "byte_exact_match": expected_hash == actual_hash,
                }
            )
            prior.append((str(source_turn["seeker"]), final_text))

    all_match = all(row["byte_exact_match"] for row in comparisons)
    output = {
        "protocol": PROTOCOL,
        "created_at": utc_now(),
        "status": "PASS_BYTE_EXACT" if all_match else "HARDWARE_REPLAY_MISMATCH",
        "purpose": (
            "zero-API replay after CUDA ordinal ambiguity placed the original local "
            "supporter on A4500; determine whether intended A6000 changes any dialogue byte"
        ),
        "original_paid_seeker_calls_repeated": 0,
        "paid_api_calls": 0,
        "formal_outcome_calls": 0,
        "quality_inspected_or_scored": False,
        "health": expected_health,
        "original_execution_identity_sha256": private["execution_identity_sha256"],
        "rounds": len(comparisons),
        "byte_exact_matches": sum(row["byte_exact_match"] for row in comparisons),
        "comparisons": comparisons,
        "attempts": attempts,
        "contains_response_text": False,
        "interpretation": (
            "The A4500 device-label deviation did not alter the deterministic supporter "
            "trajectory, so no paid seeker rerun is necessary."
            if all_match
            else "The original trajectory cannot be represented as an A6000 execution."
        ),
        "required_launch_binding": (
            "CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES=1 on this host; "
            "health.gpu must equal NVIDIA RTX A6000 before execution"
        ),
    }
    write_json(args.out, output)
    print(canonical_json(output))
    return 0 if all_match else 2


if __name__ == "__main__":
    raise SystemExit(main())
