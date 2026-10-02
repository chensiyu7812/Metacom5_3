#!/usr/bin/env python3
"""Promote the redacted full retrieval+Generator latency pilot."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import (  # noqa: E402
    canonical_json,
    iter_jsonl,
    read_json,
    sha256_file,
    write_json,
    write_jsonl,
)
from metacom_pm.paper1.outcome_lock import (  # noqa: E402
    assert_pre_outcome_locked,
    load_public_only_config,
)

PROTOCOL = "paper1-local-reference-client-retrieval-generator-pilot-v2"


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pilot-dir",
        type=Path,
        default=PROJECT / "outputs/paper1_reference_client_latency_pilot_v2/full_pipeline",
    )
    parser.add_argument(
        "--out-dir", type=Path, default=PROJECT / "data/paper1_authority"
    )
    return parser.parse_args()


def _component_summary(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
    values = [float(row["record"][key]) for row in rows]
    return {
        "median_ms": statistics.median(values),
        "min_ms": min(values),
        "max_ms": max(values),
    }


def main() -> int:
    args = _args()
    config = load_public_only_config(PROJECT / "configs/paper1_public_only.yaml")
    assert_pre_outcome_locked(config)
    manifest = read_json(args.pilot_dir / "call_manifest.json")
    report = read_json(args.pilot_dir / "pilot_report.json")
    traces = list(iter_jsonl(args.pilot_dir / "raw_traces.jsonl"))
    if manifest.get("protocol") != PROTOCOL or report.get("protocol") != PROTOCOL:
        raise RuntimeError("full-pipeline pilot protocol mismatch")
    if len(traces) != 21 or report.get("raw_trace_count") != 21:
        raise RuntimeError("full-pipeline pilot requires the exact 21-call trace set")
    if report.get("status") != "FULL_RETRIEVAL_GENERATOR_PILOT_COMPLETE_NOT_ALLOCATOR_ELIGIBLE":
        raise RuntimeError("full-pipeline pilot is not complete")
    if report.get("paid_api_cost_usd") != 0.0:
        raise RuntimeError("local full-pipeline pilot unexpectedly reports API cost")
    if report.get("trained_pm_coefficients_profiled") is not False:
        raise RuntimeError("pilot must not claim untrained PM coefficients")
    if report.get("live_query_embedding_and_all_head_ranking_profiled") is not True:
        raise RuntimeError("pilot omitted live BGE query/ranking")
    for row in traces:
        if "response" in row or "text" in row:
            raise RuntimeError("redacted trace contains response text")
        metadata = row["record"]["metadata"]
        if metadata.get("response_text_retained") is not False:
            raise RuntimeError("trace does not attest response-text deletion")
        if metadata.get("query_embedding_and_all_head_ranking_inside_client_clock") is not True:
            raise RuntimeError("trace omits live query/ranking from the E2E clock")
        if metadata.get("trained_pm_coefficients_inside_client_clock") is not False:
            raise RuntimeError("trace falsely claims trained PM inference")
        record = row["record"]
        if record["provider_request_to_completion_ms"] > record[
            "client_send_to_final_visible_text_ms"
        ]:
            raise RuntimeError("provider completion exceeds end-to-end completion")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out_dir / "paper1_full_pipeline_latency_pilot_manifest_20260904_v1.json"
    traces_path = args.out_dir / "paper1_full_pipeline_latency_pilot_traces_20260904_v1.jsonl"
    report_path = args.out_dir / "paper1_full_pipeline_latency_pilot_report_20260904_v1.json"
    authority_path = args.out_dir / "paper1_full_pipeline_latency_pilot_20260904_v1.json"
    write_json(manifest_path, manifest)
    write_jsonl(traces_path, traces)
    promoted_report = report | {
        "tracked_manifest_sha256": sha256_file(manifest_path),
        "tracked_traces_sha256": sha256_file(traces_path),
    }
    write_json(report_path, promoted_report)
    authority = {
        "protocol": "paper1-full-pipeline-latency-pilot-freeze-v1",
        "date": "2026-09-04",
        "status": "ZERO_OUTCOME_PILOT_COMPLETE_NOT_ALLOCATOR_ELIGIBLE",
        "not_an_empirical_pass_gate": True,
        "scope": (
            "preloaded candidate vectors; fresh BGE query encoding and all-head ranking, "
            "fixed pilot action, packing, request construction, and streaming local Generator "
            "inside one client monotonic clock"
        ),
        "hardware": {
            "query_embedding_and_ranking_gpu": manifest["embedding_runtime"]["gpu"],
            "streaming_generator_gpu": report["health"]["gpu"],
            "deployment_shape": "dual_local_GPU_concurrency_1",
        },
        "coverage": {
            "tasks": ["qa", "summary"],
            "configurations": ["OFF", "MP_k4", "ME_k4", "MS_k1", "ALL_k4"],
            "cold_calls": 1,
            "warm_calls": 20,
            "warm_repeats_per_task_configuration": 2,
            "RS": False,
            "dynamic_DG": False,
            "trained_PM_coefficients": False,
        },
        "component_latency": {
            "live_query_embedding_plus_all_head_ranking": _component_summary(
                traces, "retrieval_embedding_ms"
            ),
            "fixed_action_branch": _component_summary(traces, "policy_decision_ms"),
            "resource_pack_plus_request_construction": _component_summary(
                traces, "resource_render_pack_ms"
            ),
        },
        "interpretation": (
            "The full client clock works and adds real pre-provider work. N=2/cell, one target/task, "
            "and missing RS/DG/trained PM make these samples ineligible for allocator lookup or a paper p95 claim."
        ),
        "artifacts": {
            "manifest": manifest_path.name,
            "manifest_sha256": sha256_file(manifest_path),
            "traces": traces_path.name,
            "traces_sha256": sha256_file(traces_path),
            "report": report_path.name,
            "report_sha256": sha256_file(report_path),
        },
        "formal_outcome_calls": 0,
        "pm_training_runs": 0,
        "paid_api_cost_usd": 0.0,
        "locks": {
            "RQ1_RS_CALIBRATION_OUTCOME_LOCK": "CLOSED",
            "RQ2_MEMORY_CALIBRATION_OUTCOME_LOCK": "CLOSED",
            "RQ1_CONFIRMATORY_OUTCOME_LOCK": "CLOSED",
            "RQ2_CONFIRMATORY_OUTCOME_LOCK": "CLOSED",
        },
    }
    write_json(authority_path, authority)
    print(
        canonical_json(
            {
                "authority": str(authority_path),
                "authority_sha256": sha256_file(authority_path),
                "traces": len(traces),
                "formal_outcome_calls": 0,
                "paid_api_cost_usd": 0.0,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
