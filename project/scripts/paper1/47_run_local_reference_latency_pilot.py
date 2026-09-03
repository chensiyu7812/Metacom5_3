#!/usr/bin/env python3
"""Run a zero-outcome local reference-client latency instrumentation pilot.

The pilot uses exact official-aligned QA/Summary requests and exact active
Multi-View ranked-prefix resource envelopes.  Selection is outcome-blind:
one median combined-top4-length target per task, five fixed resource
configurations, and two randomized adjacent repeats.  Generated text is
never written or scored; only its SHA-256, usage and client timing survive.

This small N is an instrumentation and deployment-stack pilot.  Its lookup
rows are explicitly not eligible for the runtime allocator or paper claims.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any

import httpx

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import (  # noqa: E402
    canonical_json,
    iter_jsonl,
    sha256_file,
    sha256_text,
    utc_now,
    write_json,
    write_jsonl,
)
from metacom_pm.paper1.candidates import compile_multi_view_candidate_bundle  # noqa: E402
from metacom_pm.paper1.contracts import (  # noqa: E402
    EndToEndLatencyRecord,
    ExperimentArm,
    Head,
    LatencyMeasurementSurface,
    TaskType,
    WarmState,
)
from metacom_pm.paper1.data.memory_source import (  # noqa: E402
    enumerate_targets,
    load_sanitized_runtime_users,
)
from metacom_pm.paper1.execution.packing import RankedCandidate, pack_ranked_prefix  # noqa: E402
from metacom_pm.paper1.execution.rq2_prompts import (  # noqa: E402
    LOCAL_GENERATOR_ARTIFACT_IDENTITY_SHA256,
    LOCAL_GENERATOR_CHAT_TEMPLATE_SHA256,
    LOCAL_GENERATOR_MODEL_REVISION,
    LOCAL_GENERATOR_SERVER_PROTOCOL,
    build_static_rq2_request,
)
from metacom_pm.paper1.llama_tokenizer import build_llama_token_counter  # noqa: E402
from metacom_pm.paper1.multi_view_memory import load_accepted_multi_view_units  # noqa: E402
from metacom_pm.paper1.outcome_lock import (  # noqa: E402
    assert_pre_outcome_locked,
    load_public_only_config,
)


PROTOCOL = "paper1-local-reference-client-latency-pilot-v1"
MODEL = "meta/llama-3.1-8b-instruct"
MODEL_REVISION = LOCAL_GENERATOR_MODEL_REVISION
SERVER_PROTOCOL = LOCAL_GENERATOR_SERVER_PROTOCOL
HEAD_ORDER = (Head.MP, Head.ME, Head.MS)
CONFIGURATIONS: dict[str, tuple[tuple[Head, int], ...]] = {
    "OFF": (),
    "MP_k4": ((Head.MP, 4),),
    "ME_k4": ((Head.ME, 4),),
    "MS_k1": ((Head.MS, 1),),
    "ALL_k4": ((Head.MP, 4), (Head.ME, 4), (Head.MS, 4)),
}
SEED = 20260903
REPEATS = 2


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:8011")
    parser.add_argument("--tokenizer-json", type=Path, required=True)
    parser.add_argument(
        "--source",
        type=Path,
        default=PROJECT
        / "data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json",
    )
    parser.add_argument(
        "--session-results",
        type=Path,
        default=PROJECT
        / "data/paper1_public_memory/es_memeval_public_multi_view_session_results_v1.jsonl",
    )
    parser.add_argument(
        "--top8",
        type=Path,
        default=PROJECT
        / "data/paper1_public_memory/es_memeval_public_active_multi_view_bge_top8_v1.jsonl",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=PROJECT / "outputs/paper1_reference_client_latency_pilot_v1/local",
    )
    return parser.parse_args()


def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(probability * len(ordered)) - 1)]


def _ranked_lookup(path: Path) -> dict[tuple[str, Head], list[tuple[str, float]]]:
    rows: dict[tuple[str, Head], list[tuple[str, float]]] = {}
    for row in iter_jsonl(path):
        rows[(str(row["target_id"]), Head(row["head"]))] = [
            (str(item["candidate_id"]), float(item["bge_cosine_similarity"]))
            for item in row["ranked_candidates"]
        ]
    return rows


def _prepare(args: argparse.Namespace) -> dict[str, Any]:
    config = load_public_only_config(PROJECT / "configs/paper1_public_only.yaml")
    assert_pre_outcome_locked(config)
    users = load_sanitized_runtime_users(args.source)
    targets = enumerate_targets(users)
    units = load_accepted_multi_view_units(args.session_results, users=users)
    token_counter = build_llama_token_counter(args.tokenizer_json)
    targets_by_owner: dict[str, list[Any]] = defaultdict(list)
    units_by_owner: dict[str, list[Any]] = defaultdict(list)
    for target in targets:
        targets_by_owner[target.owner_id].append(target)
    for unit in units:
        units_by_owner[unit.owner_id].append(unit)
    bundles = {
        user.owner_id: compile_multi_view_candidate_bundle(
            tuple(units_by_owner[user.owner_id]),
            user,
            targets_by_owner[user.owner_id][0],
            token_counter=token_counter,
        )
        for user in users
    }
    by_id = {
        (owner_id, head, candidate.candidate_id): candidate
        for owner_id, bundle in bundles.items()
        for head, candidates in bundle.items()
        for candidate in candidates
    }
    ranking_ids = _ranked_lookup(args.top8)

    def ranked(target: Any, head: Head) -> tuple[RankedCandidate, ...]:
        return tuple(
            RankedCandidate(
                candidate=by_id[(target.owner_id, head, candidate_id)],
                similarity=similarity,
            )
            for candidate_id, similarity in ranking_ids[(target.target_id, head)]
        )

    selected_targets: list[Any] = []
    selection_audit: list[dict[str, Any]] = []
    for task in (TaskType.QA, TaskType.SUMMARY):
        candidates = []
        for target in targets:
            if target.task_type is not task:
                continue
            resources = tuple(
                pack_ranked_prefix(
                    head=head,
                    ranked=ranked(target, head),
                    k=4,
                    target_owner_id=target.owner_id,
                    token_counter=token_counter,
                ).envelope
                for head in HEAD_ORDER
            )
            combined = token_counter(
                "\n".join(resource.rendered_resource_block for resource in resources)
            )
            candidates.append((combined, target.target_id, target))
        candidates.sort(key=lambda item: (item[0], item[1]))
        chosen = candidates[(len(candidates) - 1) // 2]
        selected_targets.append(chosen[2])
        selection_audit.append(
            {
                "task_type": task.value,
                "rule": "lower_nearest_median_exact_ALL_k4_resource_tokens_then_target_id",
                "population_n": len(candidates),
                "selected_target_id": chosen[1],
                "selected_all_k4_resource_tokens": chosen[0],
                "population_median_resource_tokens": median(x[0] for x in candidates),
            }
        )

    requests: dict[tuple[str, str], dict[str, Any]] = {}
    request_audit: list[dict[str, Any]] = []
    for target in selected_targets:
        for configuration_id, head_ks in CONFIGURATIONS.items():
            resources = tuple(
                pack_ranked_prefix(
                    head=head,
                    ranked=ranked(target, head),
                    k=k,
                    target_owner_id=target.owner_id,
                    token_counter=token_counter,
                ).envelope
                for head, k in head_ks
            )
            request = build_static_rq2_request(
                task_type=target.task_type,
                question=target.visible_query_text or "",
                resources=resources,
            )
            messages = [message.model_dump(mode="json") for message in request.messages]
            payload = {
                "model": MODEL,
                "messages": messages,
                "temperature": 0,
                "max_tokens": request.max_output_tokens,
                "stream": True,
                "stream_options": {"include_usage": True},
            }
            resource_tokens = token_counter(
                "\n".join(resource.rendered_resource_block for resource in resources)
            ) if resources else 0
            input_tokens = token_counter(
                "\n".join(f"{message['role']}: {message['content']}" for message in messages)
            )
            requests[(target.target_id, configuration_id)] = {
                "payload": payload,
                "resource_tokens": resource_tokens,
                "estimated_visible_message_tokens": input_tokens,
                "heads": [head.value for head, _ in head_ks],
                "requested_k": {head.value: k for head, k in head_ks},
            }
            request_audit.append(
                {
                    "target_id": target.target_id,
                    "task_type": target.task_type.value,
                    "configuration_id": configuration_id,
                    "request_sha256": sha256_text(canonical_json(payload)),
                    "request_messages_sha256": request.request_messages_hash,
                    "resource_heads": [head.value for head, _ in head_ks],
                    "requested_k": {head.value: k for head, k in head_ks},
                    "resource_tokens": resource_tokens,
                    "estimated_visible_message_tokens": input_tokens,
                    "response_text_retained": False,
                }
            )

    rng = random.Random(SEED)
    schedule: list[dict[str, Any]] = []
    position = 0
    for repeat in range(REPEATS):
        target_order = list(selected_targets)
        rng.shuffle(target_order)
        for target_position, target in enumerate(target_order):
            configurations = list(CONFIGURATIONS)
            rng.shuffle(configurations)
            microblock = f"{target.task_type.value}-r{repeat:02d}-m{target_position:02d}"
            for within, configuration_id in enumerate(configurations):
                schedule.append(
                    {
                        "target_id": target.target_id,
                        "task_type": target.task_type.value,
                        "configuration_id": configuration_id,
                        "repeat_index": repeat,
                        "time_block_id": f"local-warm-repeat-{repeat:02d}",
                        "target_microblock_id": microblock,
                        "randomized_sequence_position": position,
                        "position_within_target_microblock": within,
                    }
                )
                position += 1
    manifest = {
        "protocol": PROTOCOL,
        "created_at": utc_now(),
        "status": "LIVE_READY" if args.live else "DRY_RUN_READY",
        "purpose": "zero-outcome instrumentation and local deployment-stack pilot only",
        "measurement_scope": (
            "Generator-path client request only; PM, retrieval, embedding and resource "
            "packing are precomputed and therefore excluded"
        ),
        "eligible_for_runtime_allocator": False,
        "eligible_for_paper_latency_claim": False,
        "insufficiency_reason": "two warm repeats per task/configuration cannot estimate a stable p95",
        "formal_outcome_calls": 0,
        "pm_training_runs": 0,
        "response_quality_inspected_or_scored": False,
        "model": MODEL,
        "model_revision": MODEL_REVISION,
        "model_artifact_identity_sha256": LOCAL_GENERATOR_ARTIFACT_IDENTITY_SHA256,
        "chat_template_sha256": LOCAL_GENERATOR_CHAT_TEMPLATE_SHA256,
        "server_protocol": SERVER_PROTOCOL,
        "base_url": args.base_url,
        "temperature": 0,
        "max_output_tokens": {"qa": 256, "summary": 256},
        "seed": SEED,
        "warm_repeats": REPEATS,
        "cold_calls": 1,
        "warm_calls": len(schedule),
        "concurrency": 1,
        "selection_audit": selection_audit,
        "requests": request_audit,
        "schedule": schedule,
        "inputs": {
            "source_sha256": sha256_file(args.source),
            "session_results_sha256": sha256_file(args.session_results),
            "top8_sha256": sha256_file(args.top8),
            "tokenizer_json_sha256": sha256_file(args.tokenizer_json),
        },
    }
    return {
        "manifest": manifest,
        "requests": requests,
        "targets": {target.target_id: target for target in selected_targets},
    }


def _call(client: httpx.Client, base_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    send_ns = time.monotonic_ns()
    first_ns: int | None = None
    final_ns: int | None = None
    parts: list[str] = []
    usage: dict[str, int] = {}
    finish_reason = "unknown"
    with client.stream(
        "POST", f"{base_url}/v1/chat/completions", json=payload
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith("data:"):
                continue
            body = line[5:].strip()
            if not body or body == "[DONE]":
                continue
            chunk = json.loads(body)
            if chunk.get("error"):
                raise RuntimeError(f"local generation failed: {chunk['error']}")
            if isinstance(chunk.get("usage"), dict):
                usage = {key: int(value) for key, value in chunk["usage"].items()}
            choices = chunk.get("choices") or []
            if not choices:
                continue
            choice = choices[0]
            if choice.get("finish_reason") is not None:
                finish_reason = str(choice["finish_reason"])
            content = (choice.get("delta") or {}).get("content")
            if isinstance(content, str) and content:
                if first_ns is None:
                    first_ns = time.monotonic_ns()
                parts.append(content)
        final_ns = time.monotonic_ns()
    if first_ns is None or not parts:
        raise RuntimeError("stream completed without visible text")
    return {
        "provider_ttft_ms": (first_ns - send_ns) / 1_000_000,
        "provider_completion_ms": (final_ns - send_ns) / 1_000_000,
        "response_sha256": sha256_text("".join(parts)),
        "visible_characters": sum(len(part) for part in parts),
        "usage": usage,
        "finish_reason": finish_reason,
    }


def _record(
    *,
    row: dict[str, Any],
    request_info: dict[str, Any],
    call: dict[str, Any],
    warm_state: WarmState,
    connection_reuse: bool,
    trace_id: str,
) -> dict[str, Any]:
    usage = call["usage"]
    record = EndToEndLatencyRecord(
        trace_id=trace_id,
        measurement_surface=LatencyMeasurementSurface.REFERENCE_CLIENT,
        time_block_id=row["time_block_id"],
        target_microblock_id=row["target_microblock_id"],
        randomized_sequence_position=int(row["randomized_sequence_position"]),
        client_region="loopback-localhost-on-premise-reference-client",
        warm_state=warm_state,
        concurrency=1,
        connection_reuse=connection_reuse,
        policy_decision_ms=0.0,
        retrieval_embedding_ms=0.0,
        resource_render_pack_ms=0.0,
        provider_request_to_first_content_ms=call["provider_ttft_ms"],
        provider_request_to_completion_ms=call["provider_completion_ms"],
        client_send_to_first_visible_text_ms=call["provider_ttft_ms"],
        client_send_to_final_visible_text_ms=call["provider_completion_ms"],
        streaming_observed=True,
        input_tokens=int(usage.get("prompt_tokens", 0)),
        output_tokens=int(usage.get("completion_tokens", 0)),
        retry_count=0,
        finish_reason=call["finish_reason"],
        metadata={
            "protocol": PROTOCOL,
            "configuration_id": row["configuration_id"],
            "resource_heads": request_info["heads"],
            "requested_k": request_info["requested_k"],
            "resource_tokens": request_info["resource_tokens"],
            "response_sha256": call["response_sha256"],
            "response_text_retained": False,
            "visible_character_count": call["visible_characters"],
            "server_protocol": SERVER_PROTOCOL,
            "precomputed_request_excludes_policy_retrieval_and_pack": True,
        },
    )
    return {
        "protocol": PROTOCOL,
        "target_id": row["target_id"],
        "task_type": row["task_type"],
        "arm": (
            ExperimentArm.NO_MEMORY.value
            if row["configuration_id"] == "OFF"
            else ExperimentArm.TYPED_FIXED_HIGH.value
        ),
        "configuration_id": row["configuration_id"],
        "repeat_index": row.get("repeat_index"),
        "record": record.model_dump(mode="json"),
    }


def main() -> int:
    args = _args()
    prepared = _prepare(args)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out_dir / "call_manifest.json"
    write_json(manifest_path, prepared["manifest"])
    if not args.live:
        print(canonical_json(prepared["manifest"]))
        return 0

    with httpx.Client(timeout=httpx.Timeout(180.0)) as health_client:
        health = health_client.get(f"{args.base_url}/health")
        health.raise_for_status()
        health_json = health.json()
    expected = {
        "status": "ready",
        "protocol": SERVER_PROTOCOL,
        "model": MODEL,
        "revision": MODEL_REVISION,
        "model_artifact_identity_sha256": LOCAL_GENERATOR_ARTIFACT_IDENTITY_SHA256,
        "chat_template_sha256": LOCAL_GENERATOR_CHAT_TEMPLATE_SHA256,
        "gpu": "NVIDIA RTX A6000",
        "concurrency": 1,
    }
    if any(health_json.get(key) != value for key, value in expected.items()):
        raise RuntimeError(f"local server identity mismatch: {health_json}")

    traces: list[dict[str, Any]] = []
    cold_target_id = prepared["manifest"]["selection_audit"][0]["selected_target_id"]
    cold_info = prepared["requests"][(cold_target_id, "OFF")]
    cold_row = {
        "target_id": cold_target_id,
        "task_type": "qa",
        "configuration_id": "OFF",
        "repeat_index": None,
        "time_block_id": "local-cold-start-00",
        "target_microblock_id": "local-cold-start-qa-off",
        "randomized_sequence_position": 0,
    }
    with httpx.Client(timeout=httpx.Timeout(180.0)) as cold_client:
        cold_call = _call(cold_client, args.base_url, cold_info["payload"])
    traces.append(
        _record(
            row=cold_row,
            request_info=cold_info,
            call=cold_call,
            warm_state=WarmState.COLD,
            connection_reuse=False,
            trace_id="local-cold-qa-off-000",
        )
    )

    with httpx.Client(timeout=httpx.Timeout(180.0)) as client:
        warm_health = client.get(f"{args.base_url}/health")
        warm_health.raise_for_status()
        for row in prepared["manifest"]["schedule"]:
            info = prepared["requests"][(row["target_id"], row["configuration_id"])]
            call = _call(client, args.base_url, info["payload"])
            traces.append(
                _record(
                    row=row,
                    request_info=info,
                    call=call,
                    warm_state=WarmState.WARM,
                    connection_reuse=True,
                    trace_id=f"local-warm-{row['randomized_sequence_position']:04d}",
                )
            )
    write_jsonl(args.out_dir / "raw_traces.jsonl", traces)

    strata: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for trace in traces:
        record = trace["record"]
        strata[(trace["task_type"], trace["configuration_id"], record["warm_state"])].append(trace)
    summaries = []
    for (task, configuration, warm_state), rows in sorted(strata.items()):
        ttft = [row["record"]["client_send_to_first_visible_text_ms"] for row in rows]
        completion = [row["record"]["client_send_to_final_visible_text_ms"] for row in rows]
        summaries.append(
            {
                "task_type": task,
                "configuration_id": configuration,
                "warm_state": warm_state,
                "calls": len(rows),
                "p50_ttft_ms": _percentile(ttft, 0.50),
                "p95_ttft_ms": _percentile(ttft, 0.95),
                "p50_completion_ms": _percentile(completion, 0.50),
                "p95_completion_ms": _percentile(completion, 0.95),
                "mean_input_tokens": sum(row["record"]["input_tokens"] for row in rows) / len(rows),
                "mean_output_tokens": sum(row["record"]["output_tokens"] for row in rows) / len(rows),
                "allocator_eligible": False,
            }
        )
    report = {
        "protocol": PROTOCOL,
        "completed_at": utc_now(),
        "status": "PILOT_COMPLETE_NOT_ALLOCATOR_ELIGIBLE",
        "health": health_json,
        "manifest_sha256": sha256_file(manifest_path),
        "raw_traces_sha256": sha256_file(args.out_dir / "raw_traces.jsonl"),
        "raw_trace_count": len(traces),
        "cold_trace_count": 1,
        "warm_trace_count": len(traces) - 1,
        "response_text_retained": False,
        "response_quality_inspected_or_scored": False,
        "formal_outcome_calls": 0,
        "pm_training_runs": 0,
        "paid_api_cost_usd": 0.0,
        "lookup_status": "SPARSE_PILOT_ONLY_MORE_REPEATS_AND_RS_DG_COVERAGE_REQUIRED",
        "summaries": summaries,
    }
    write_json(args.out_dir / "pilot_report.json", report)
    print(canonical_json(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
