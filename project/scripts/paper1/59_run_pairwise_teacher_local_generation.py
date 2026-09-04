#!/usr/bin/env python3
"""Generate the 142 frozen local ON/OFF responses for teacher reference.

The runner is deterministic, single-request, cache-resumable, and evaluator
free.  Full request/response text remains under ignored ``outputs/``.  The
tracked result contains only hashes, usage, latency, finish reasons, and the
80-base-pair response mapping needed to materialize blinded rating sheets.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import httpx

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import (  # noqa: E402
    canonical_json,
    iter_jsonl,
    read_json,
    sha256_file,
    sha256_text,
    utc_now,
    write_json,
)
from metacom_pm.paper1.execution.dg_official import trim_to_last_complete_sentence  # noqa: E402
from metacom_pm.paper1.execution.rq2_prompts import (  # noqa: E402
    LOCAL_GENERATOR_ARTIFACT_IDENTITY_SHA256,
    LOCAL_GENERATOR_CHAT_TEMPLATE_SHA256,
    LOCAL_GENERATOR_MODEL_REVISION,
    LOCAL_GENERATOR_SERVER_PROTOCOL,
)
from metacom_pm.paper1.outcome_lock import (  # noqa: E402
    assert_pre_outcome_locked,
    load_public_only_config,
)


PROTOCOL = "paper1-pairwise-teacher-local-generation-result-v1"
LOCAL_MODEL = "meta/llama-3.1-8b-instruct"
EXPECTED_GPU = "NVIDIA RTX A6000"


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8011")
    parser.add_argument(
        "--binding",
        type=Path,
        default=PROJECT
        / "data/paper1_authority/paper1_pairwise_teacher_generator_request_binding_20260904_v1.json",
    )
    parser.add_argument(
        "--private-requests",
        type=Path,
        default=PROJECT
        / "outputs/paper1_pairwise_teacher/private_generator_requests_20260904_v1.jsonl",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=PROJECT
        / "outputs/paper1_pairwise_teacher/local_generator_success_cache_v1",
    )
    parser.add_argument(
        "--authority-out",
        type=Path,
        default=PROJECT
        / "data/paper1_authority/paper1_pairwise_teacher_local_generation_result_20260904_v1.json",
    )
    return parser.parse_args()


def _health(base_url: str) -> dict[str, Any]:
    response = httpx.get(f"{base_url.rstrip('/')}/health", timeout=15.0)
    response.raise_for_status()
    health = response.json()
    expected = {
        "status": "ready",
        "protocol": LOCAL_GENERATOR_SERVER_PROTOCOL,
        "model": LOCAL_MODEL,
        "revision": LOCAL_GENERATOR_MODEL_REVISION,
        "model_artifact_identity_sha256": LOCAL_GENERATOR_ARTIFACT_IDENTITY_SHA256,
        "chat_template_sha256": LOCAL_GENERATOR_CHAT_TEMPLATE_SHA256,
        "gpu": EXPECTED_GPU,
        "dtype": "bfloat16",
    }
    if any(health.get(key) != value for key, value in expected.items()):
        raise RuntimeError("local Generator health identity mismatch")
    return {key: health[key] for key in expected}


def _provider_payload(request: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": LOCAL_MODEL,
        "messages": request["messages"],
        "temperature": 0,
        "max_tokens": int(request["max_output_tokens"]),
        "stream": True,
        "stream_options": {"include_usage": True},
    }


def _call(client: httpx.Client, base_url: str, row: dict[str, Any]) -> dict[str, Any]:
    request = row["request"]
    if sha256_text(canonical_json(request)) != row["request_sha256"]:
        raise RuntimeError("private Generator request hash mismatch")
    payload = _provider_payload(request)
    started = time.monotonic_ns()
    first_visible_ns: int | None = None
    pieces: list[str] = []
    usage: dict[str, int] = {}
    finish_reason = "unknown"
    returned_models: set[str] = set()
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
                raise RuntimeError(f"local Generator failed: {chunk['error']}")
            if chunk.get("model"):
                returned_models.add(str(chunk["model"]))
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
            content = (choice.get("delta") or {}).get("content")
            if isinstance(content, str) and content:
                if first_visible_ns is None:
                    first_visible_ns = time.monotonic_ns()
                pieces.append(content)
    completed = time.monotonic_ns()
    raw_text = "".join(pieces)
    if not raw_text:
        raise RuntimeError("local Generator returned terminal empty output")
    accepted_text = (
        trim_to_last_complete_sentence(raw_text)
        if row["task"] == "DG" and finish_reason != "stop"
        else raw_text
    )
    if not accepted_text:
        raise RuntimeError("DG complete-sentence prefix is terminal empty")
    if returned_models != {LOCAL_MODEL}:
        raise RuntimeError("local Generator returned-model identity mismatch")
    return {
        "protocol": PROTOCOL,
        "request_id": row["request_id"],
        "request_sha256": row["request_sha256"],
        "provider_payload_sha256": sha256_text(canonical_json(payload)),
        "task": row["task"],
        "target_id": row["target_id"],
        "arm": row["arm"],
        "head": row["head"],
        "base_pair_ids": row["base_pair_ids"],
        "raw_text": raw_text,
        "accepted_text": accepted_text,
        "raw_response_sha256": sha256_text(raw_text),
        "accepted_response_sha256": sha256_text(accepted_text),
        "finish_reason": finish_reason,
        "complete_sentence_prefix_applied": accepted_text != raw_text,
        "usage": usage,
        "ttft_ms": (
            None if first_visible_ns is None else (first_visible_ns - started) / 1_000_000
        ),
        "completion_ms": (completed - started) / 1_000_000,
        "returned_models": sorted(returned_models),
        "response_quality_inspected_or_scored": False,
    }


def _cache_path(cache_dir: Path, request_id: str) -> Path:
    return cache_dir / f"{request_id}.json"


def main() -> int:
    args = _args()
    config = load_public_only_config(PROJECT / "configs/paper1_public_only.yaml")
    assert_pre_outcome_locked(config)
    binding = read_json(args.binding)
    if (
        binding.get("status") != "ACTIVE_ZERO_OUTCOME_142_LOCAL_REQUESTS_BOUND"
        or binding["counts"]["unique_generator_requests"] != 142
        or binding["private_request_manifest"]["sha256"]
        != sha256_file(args.private_requests)
    ):
        raise RuntimeError("local Generator request binding is not ready")
    rows = list(iter_jsonl(args.private_requests))
    if len(rows) != 142 or len({row["request_id"] for row in rows}) != 142:
        raise RuntimeError("private Generator request set is not exactly 142 unique rows")
    tracked_by_id = {
        row["request_id"]: row for row in binding["request_identities"]
    }
    if len(tracked_by_id) != 142:
        raise RuntimeError("tracked Generator request identity count mismatch")
    for row in rows:
        tracked = tracked_by_id.get(row["request_id"])
        if (
            tracked is None
            or tracked["request_sha256"] != row["request_sha256"]
            or tracked["base_pair_ids"] != row["base_pair_ids"]
        ):
            raise RuntimeError("private/tracked Generator request identity mismatch")
    health = _health(args.base_url)
    client = httpx.Client(timeout=httpx.Timeout(300.0), http2=False)
    successes: list[dict[str, Any]] = []
    new_calls = 0
    cache_hits = 0
    try:
        for index, row in enumerate(rows, 1):
            cache_path = _cache_path(args.cache_dir, row["request_id"])
            if cache_path.exists():
                result = read_json(cache_path)
                if (
                    result.get("protocol") != PROTOCOL
                    or result.get("request_id") != row["request_id"]
                    or result.get("request_sha256") != row["request_sha256"]
                    or result.get("response_quality_inspected_or_scored") is not False
                ):
                    raise RuntimeError(f"local Generator cache identity mismatch: {cache_path}")
                cache_hits += 1
            else:
                result = _call(client, args.base_url, row)
                write_json(cache_path, result)
                new_calls += 1
            successes.append(result)
            if index % 10 == 0 or index == len(rows):
                print(
                    canonical_json(
                        {
                            "progress": f"{index}/{len(rows)}",
                            "new_calls": new_calls,
                            "cache_hits": cache_hits,
                        }
                    ),
                    flush=True,
                )
    finally:
        client.close()

    if len(successes) != 142:
        raise RuntimeError("local Generator response set is incomplete")
    pair_map: dict[str, dict[str, Any]] = {}
    for result in successes:
        for base_pair_id in result["base_pair_ids"]:
            cell = pair_map.setdefault(base_pair_id, {})
            arm = result["arm"]
            if arm in cell:
                raise RuntimeError(f"duplicate {arm} response for {base_pair_id}")
            cell[arm] = {
                "request_id": result["request_id"],
                "response_sha256": result["accepted_response_sha256"],
            }
    if len(pair_map) != 80 or any(set(cell) != {"OFF", "ON"} for cell in pair_map.values()):
        raise RuntimeError("80-base-pair local response map is incomplete")
    finish = Counter(
        f"{row['task']}:{row['arm']}:{row['finish_reason']}" for row in successes
    )
    result = {
        "protocol": PROTOCOL,
        "date": "2026-09-04",
        "status": "PASS_142_LOCAL_RESPONSES_READY_FOR_BLINDED_SHEETS",
        "completed_at": utc_now(),
        "request_binding_sha256": sha256_file(args.binding),
        "private_request_manifest_sha256": sha256_file(args.private_requests),
        "local_health": health,
        "execution": {
            "unique_requests": 142,
            "new_calls_this_run": new_calls,
            "cache_hits_this_run": cache_hits,
            "temperature": 0,
            "concurrency": 1,
            "physical_attempts_per_request": 1,
            "finish_reason_counts": dict(sorted(finish.items())),
            "terminal_empty_outputs": 0,
            "response_quality_inspected_or_scored": False,
            "tracked_response_text_retained": False,
        },
        "usage": {
            "prompt_tokens": sum(int(row["usage"].get("prompt_tokens", 0)) for row in successes),
            "completion_tokens": sum(
                int(row["usage"].get("completion_tokens", 0)) for row in successes
            ),
            "total_tokens": sum(int(row["usage"].get("total_tokens", 0)) for row in successes),
        },
        "latency_ms": {
            "sum_completion": sum(float(row["completion_ms"]) for row in successes),
            "maximum_completion": max(float(row["completion_ms"]) for row in successes),
        },
        "private_success_cache": {
            "path": "outputs/paper1_pairwise_teacher/local_generator_success_cache_v1",
            "files": 142,
            "contains_generated_response_text": True,
            "git_tracking_forbidden": True,
        },
        "base_pair_response_map": [
            {"base_pair_id": base_pair_id, **pair_map[base_pair_id]}
            for base_pair_id in sorted(pair_map)
        ],
        "paid_api_calls": 0,
        "formal_outcome_calls": 0,
        "evaluator_calls": 0,
        "pm_training_runs": 0,
        "locks": {
            name: config[name]["status"]
            for name in (
                "RQ1_RS_CALIBRATION_OUTCOME_LOCK",
                "RQ2_MEMORY_CALIBRATION_OUTCOME_LOCK",
                "RQ1_CONFIRMATORY_OUTCOME_LOCK",
                "RQ2_CONFIRMATORY_OUTCOME_LOCK",
            )
        },
    }
    write_json(args.authority_out, result)
    print(canonical_json({
        "status": result["status"],
        "execution": result["execution"],
        "usage": result["usage"],
        "latency_ms": result["latency_ms"],
        "base_pairs": len(result["base_pair_response_map"]),
        "paid_api_calls": 0,
        "formal_outcome_calls": 0,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
