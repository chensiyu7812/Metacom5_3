#!/usr/bin/env python3
"""Measure the pinned local Mistral-24B DG judge without formal outcomes.

The pilot uses public historical dialogue text and the exact official
observation-score/usage message contracts.  It records only schema validity,
hashes, token counts, latency, throughput and hardware identity; generated
score values are deliberately omitted from the tracked authority artifact.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import subprocess
import sys
import time
from importlib.metadata import version
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import (  # noqa: E402
    canonical_json,
    read_json,
    sha256_file,
    sha256_text,
    utc_now,
    write_json,
)
from metacom_pm.paper1.execution.dg_observation_official import (  # noqa: E402
    SCORE_JSON_SCHEMA,
    USAGE_JSON_SCHEMA,
    build_observation_score_messages,
    build_observation_usage_messages,
)
from metacom_pm.paper1.outcome_lock import (  # noqa: E402
    assert_pre_outcome_locked,
    load_public_only_config,
)

MODEL = "mistralai/Mistral-Small-3.1-24B-Instruct-2503"
MODEL_REVISION = "68faf511d618ef198fef186659617cfd2eb8e33a"
UPSTREAM_COMMIT = "692624208acc077b8867698c1d6fcd998dee641a"
UPSTREAM_SOURCE_SHA256 = (
    "aad049c2408042947a63ff75c6aebbb43c489340ad5809347ecac102e60c61bc"
)
PROTOCOL = "paper1-official-mistral24b-zero-outcome-backend-pilot-v2"
MAX_COMPLETION_TOKENS = 30
FORMAL_CALL_SURFACE = 102_720
GREEDY_DIAGNOSTIC = (
    PROJECT
    / "data/paper1_authority/"
    "paper1_official_mistral24b_backend_pilot_20260904_v1.json"
)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8911/v1")
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--determinism-repeats", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--gpu-index", type=int, default=1)
    parser.add_argument(
        "--model-snapshot",
        type=Path,
        default=Path(
            "/opt/tokkio-data0/tokkio_models/huggingface/"
            "models--mistralai--Mistral-Small-3.1-24B-Instruct-2503/"
            f"snapshots/{MODEL_REVISION}"
        ),
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=PROJECT / "data/external/evo_emo.json",
    )
    parser.add_argument(
        "--upstream-source",
        type=Path,
        default=PROJECT / "outputs/vendor_es_memeval/src/lib/dg/dg_experiment.py",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT
        / "data/paper1_authority/"
        "paper1_official_mistral24b_backend_pilot_20260904_v2.json",
    )
    return parser.parse_args()


def _nearest_rank(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(probability * len(ordered)) - 1)]


def _distribution(values: list[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "min": ordered[0],
        "median": (
            ordered[(len(ordered) - 1) // 2] + ordered[len(ordered) // 2]
        )
        / 2,
        "p95_nearest_rank": _nearest_rank(ordered, 0.95),
        "max": ordered[-1],
        "mean": sum(ordered) / len(ordered),
    }


def _gpu_snapshot(index: int) -> dict[str, Any]:
    fields = [
        "index",
        "uuid",
        "name",
        "driver_version",
        "memory.used",
        "memory.total",
        "utilization.gpu",
    ]
    result = subprocess.run(
        [
            "nvidia-smi",
            f"--id={index}",
            f"--query-gpu={','.join(fields)}",
            "--format=csv,noheader,nounits",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    values = [value.strip() for value in result.stdout.strip().split(",")]
    return dict(zip(fields, values, strict=True))


def _model_artifact_identity(snapshot: Path) -> dict[str, Any]:
    weights = []
    for path in sorted(snapshot.glob("model-*-of-*.safetensors")):
        target = path.resolve()
        weights.append(
            {
                "name": path.name,
                "blob": target.name,
                "bytes": target.stat().st_size,
            }
        )
    if len(weights) != 10:
        raise RuntimeError("expected ten pinned Mistral weight shards")
    identity = {
        "repo": MODEL,
        "revision": MODEL_REVISION,
        "config_sha256": sha256_file(snapshot / "config.json"),
        "index_sha256": sha256_file(snapshot / "model.safetensors.index.json"),
        "weight_shards": weights,
    }
    return {
        **identity,
        "identity_sha256": sha256_text(canonical_json(identity)),
        "total_weight_bytes": sum(row["bytes"] for row in weights),
    }


def _paired_public_messages(session: dict[str, Any]) -> tuple[str, str]:
    dialogue = session["dialogue"]
    for index, message in enumerate(dialogue):
        if message["role"] != "seeker":
            continue
        supporter = next(
            (
                later["content"]
                for later in dialogue[index + 1 :]
                if later["role"] == "supporter"
            ),
            None,
        )
        if supporter is not None:
            return str(message["content"]), str(supporter)
    raise RuntimeError(f"session {session['id']} has no seeker/supporter pair")


def _candidate_requests(users: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = []
    for user in users:
        sessions = {str(row["id"]): row for row in user["dialog_history"]}
        for topic in user["subsequent_topics"]:
            for session_id in topic["related_sessions"]:
                session = sessions[str(session_id)]
                seeker, supporter = _paired_public_messages(session)
                for observation in session["observation"]:
                    shared = {
                        "case_id": (
                            f"{user['id']}:{topic['idx']}:{session_id}:"
                            f"{observation['idx']}"
                        ),
                        "user": user,
                        "topic": topic,
                        "seeker_message": seeker,
                        "supporter_message": supporter,
                        "observation": str(observation["content"]),
                    }
                    candidates.append({**shared, "kind": "score"})
                    candidates.append({**shared, "kind": "usage"})
    return candidates


def _select_evenly(candidates: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    if count < 2 or count > len(candidates):
        raise ValueError(f"count must be between 2 and {len(candidates)}")
    return [
        candidates[round(index * (len(candidates) - 1) / (count - 1))]
        for index in range(count)
    ]


def _payload(case: dict[str, Any]) -> dict[str, Any]:
    if case["kind"] == "score":
        messages = build_observation_score_messages(
            user=case["user"],
            topic=case["topic"],
            seeker_message=case["seeker_message"],
            observation=case["observation"],
        )
        schema = SCORE_JSON_SCHEMA
    else:
        messages = build_observation_usage_messages(
            user=case["user"],
            topic=case["topic"],
            seeker_message=case["seeker_message"],
            supporter_message=case["supporter_message"],
            observation=case["observation"],
        )
        schema = USAGE_JSON_SCHEMA
    return {
        "model": MODEL,
        "messages": messages,
        "max_completion_tokens": MAX_COMPLETION_TOKENS,
        "response_format": {"type": "json_schema", "json_schema": schema},
    }


def _valid(kind: str, content: str) -> bool:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return False
    if kind == "score":
        return (
            set(parsed) == {"score"}
            and type(parsed["score"]) is int
            and 1 <= parsed["score"] <= 3
        )
    return set(parsed) == {"judgement"} and type(parsed["judgement"]) is bool


async def _post_one(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    case: dict[str, Any],
) -> dict[str, Any]:
    payload = _payload(case)
    async with semaphore:
        started = time.perf_counter()
        response = await client.post("/chat/completions", json=payload)
        elapsed = time.perf_counter() - started
    response.raise_for_status()
    body = response.json()
    content = body["choices"][0]["message"]["content"]
    return {
        "case_id": case["case_id"],
        "kind": case["kind"],
        "request_sha256": sha256_text(canonical_json(payload)),
        "response_sha256": sha256_text(content),
        "schema_valid": _valid(case["kind"], content),
        "finish_reason": body["choices"][0]["finish_reason"],
        "prompt_tokens": int(body["usage"]["prompt_tokens"]),
        "completion_tokens": int(body["usage"]["completion_tokens"]),
        "latency_seconds": elapsed,
        "response_value_retained": False,
    }


async def _run_batch(
    client: httpx.AsyncClient,
    cases: list[dict[str, Any]],
    concurrency: int,
) -> tuple[list[dict[str, Any]], float]:
    semaphore = asyncio.Semaphore(concurrency)
    started = time.perf_counter()
    results = await asyncio.gather(
        *(_post_one(client, semaphore, case) for case in cases)
    )
    return results, time.perf_counter() - started


async def _main(args: argparse.Namespace) -> dict[str, Any]:
    parsed_url = urlparse(args.base_url)
    if parsed_url.hostname not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("this zero-cost pilot may only call a local backend")
    if args.concurrency < 1:
        raise ValueError("concurrency must be positive")
    config = load_public_only_config(PROJECT / "configs/paper1_public_only.yaml")
    assert_pre_outcome_locked(config)
    if sha256_file(args.upstream_source) != UPSTREAM_SOURCE_SHA256:
        raise RuntimeError("pinned upstream DG source identity changed")

    users = read_json(args.data)
    candidates = _candidate_requests(users)
    selected = _select_evenly(candidates, args.count)
    payloads = [_payload(case) for case in selected]
    request_surface_sha256 = sha256_text(canonical_json(payloads))
    gpu_before = _gpu_snapshot(args.gpu_index)

    async with httpx.AsyncClient(base_url=args.base_url, timeout=300) as client:
        health = await client.get("/models")
        health.raise_for_status()
        served_models = [row["id"] for row in health.json()["data"]]
        if MODEL not in served_models:
            raise RuntimeError("pinned model name is not served")
        first_results, first_wall = await _run_batch(
            client, selected, args.concurrency
        )
        repeat_cases = selected[: args.determinism_repeats]
        repeat_results, repeat_wall = await _run_batch(
            client, repeat_cases, args.concurrency
        )

    gpu_after = _gpu_snapshot(args.gpu_index)
    comparisons = [
        first_results[index]["response_sha256"]
        == repeat_results[index]["response_sha256"]
        for index in range(len(repeat_results))
    ]
    schema_valid = sum(row["schema_valid"] for row in first_results)
    repeated_schema_valid = sum(row["schema_valid"] for row in repeat_results)
    throughput = len(first_results) / first_wall
    identity = {
        "protocol": PROTOCOL,
        "upstream_repo": "slptongji/ES-MemEval",
        "upstream_commit": UPSTREAM_COMMIT,
        "upstream_dg_source_sha256": UPSTREAM_SOURCE_SHA256,
        "raw_data_sha256": sha256_file(args.data),
        "model_artifact": _model_artifact_identity(args.model_snapshot),
        "server": {
            "vllm": version("vllm"),
            "torch": version("torch"),
            "transformers": version("transformers"),
            "mistral_common": version("mistral-common"),
            "langchain_openai_official_requirement": "0.3.32",
            "base_url": args.base_url,
            "dtype": "bfloat16",
            "max_model_len": 4096,
            "max_num_seqs": 16,
            "cpu_offload_gb": 5,
            "gpu_memory_utilization": 0.98,
            "text_only": True,
            "structured_backend": "xgrammar",
            "disable_any_json_whitespace": True,
        },
        "request_surface_sha256": request_surface_sha256,
        "max_completion_tokens": MAX_COMPLETION_TOKENS,
        "temperature": "official_provider_default_omitted",
        "concurrency": args.concurrency,
        "projected_formal_call_surface": FORMAL_CALL_SURFACE,
        "formal_outcome_calls": 0,
        "pm_training_runs": 0,
        "paid_api_calls": 0,
    }
    return {
        "identity": identity,
        "execution_identity_sha256": sha256_text(canonical_json(identity)),
        "date": "2026-09-04",
        "status": (
            "OFFICIAL_BACKEND_COMPATIBILITY_OBSERVED"
            if schema_valid == len(first_results)
            and repeated_schema_valid == len(repeat_results)
            else "OFFICIAL_BACKEND_COMPATIBILITY_PROBLEM_OBSERVED"
        ),
        "not_a_research_outcome_or_self_defined_scientific_gate": True,
        "purpose": (
            "local official-backend interface, resource and throughput evidence; "
            "not model-quality evaluation"
        ),
        "response_values_retained_in_authority": False,
        "response_quality_inspected_or_scored": False,
        "locks": {
            name: config[name]["status"]
            for name in (
                "RQ1_RS_CALIBRATION_OUTCOME_LOCK",
                "RQ2_MEMORY_CALIBRATION_OUTCOME_LOCK",
                "RQ1_CONFIRMATORY_OUTCOME_LOCK",
                "RQ2_CONFIRMATORY_OUTCOME_LOCK",
            )
        },
        "sample": {
            "candidate_requests": len(candidates),
            "selected_unique_requests": len(selected),
            "score_requests": sum(case["kind"] == "score" for case in selected),
            "usage_requests": sum(case["kind"] == "usage" for case in selected),
            "selection": "evenly_spaced_over_public_owner_topic_session_observation_surface",
            "uses_generated_formal_system_responses": False,
        },
        "compatibility": {
            "schema_valid": schema_valid,
            "schema_total": len(first_results),
            "finish_reason_counts": {
                reason: sum(row["finish_reason"] == reason for row in first_results)
                for reason in sorted({row["finish_reason"] for row in first_results})
            },
            "repeat_schema_valid": repeated_schema_valid,
            "repeat_total": len(repeat_results),
            "byte_identical_repeats": sum(comparisons),
            "repeat_agreement_is_reported_not_used_as_a_gate": True,
        },
        "performance": {
            "first_pass_wall_seconds": first_wall,
            "first_pass_requests_per_second": throughput,
            "projected_102720_call_gpu_hours_at_observed_rate": (
                FORMAL_CALL_SURFACE / throughput / 3600
            ),
            "repeat_wall_seconds": repeat_wall,
            "latency_seconds": _distribution(
                [row["latency_seconds"] for row in first_results]
            ),
            "prompt_tokens": _distribution(
                [float(row["prompt_tokens"]) for row in first_results]
            ),
            "completion_tokens": _distribution(
                [float(row["completion_tokens"]) for row in first_results]
            ),
            "total_prompt_tokens": sum(
                row["prompt_tokens"] for row in first_results
            ),
            "total_completion_tokens": sum(
                row["completion_tokens"] for row in first_results
            ),
        },
        "hardware": {"before": gpu_before, "after": gpu_after},
        "configuration_note": (
            "The server-side no-arbitrary-whitespace structured-decoding option "
            "prevents a measured Mistral/xgrammar loop that otherwise consumes "
            "the official 30-token ceiling with '{' plus newlines. It does not "
            "change the official score or boolean schemas."
        ),
        "prior_greedy_diagnostic": {
            "path": str(GREEDY_DIAGNOSTIC.relative_to(PROJECT)),
            "sha256": sha256_file(GREEDY_DIAGNOSTIC),
            "temperature": 0,
            "purpose": (
                "separate structured-decoding and batch-context diagnostic; "
                "not the official temperature-omitted call contract"
            ),
        },
        "case_evidence": first_results,
        "repeat_evidence": repeat_results,
        "completed_at": utc_now(),
    }


def main() -> int:
    args = _args()
    result = asyncio.run(_main(args))
    write_json(args.output, result)
    print(json.dumps({
        "status": result["status"],
        "output": str(args.output),
        "compatibility": result["compatibility"],
        "performance": result["performance"],
    }, indent=2))
    return (
        0
        if result["status"] == "OFFICIAL_BACKEND_COMPATIBILITY_OBSERVED"
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
