#!/usr/bin/env python3
"""Freeze the pre-outcome Generator-backend incident and local pilot artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import (  # noqa: E402
    canonical_json,
    iter_jsonl,
    read_json,
    sha256_file,
    sha256_text,
    write_json,
    write_jsonl,
)
from metacom_pm.paper1.execution.rq2_prompts import (  # noqa: E402
    LOCAL_GENERATOR_ARTIFACT_IDENTITY_SHA256,
    LOCAL_GENERATOR_CHAT_TEMPLATE_SHA256,
    LOCAL_GENERATOR_MODEL_REVISION,
    LOCAL_GENERATOR_SERVER_PROTOCOL,
    LOCAL_GENERATOR_TOKENIZER_CONFIG_SHA256,
    RQ2_PROMPT_PROTOCOL,
)
from metacom_pm.paper1.outcome_lock import (  # noqa: E402
    assert_pre_outcome_locked,
    load_public_only_config,
)


EXPECTED_FILES = {
    "config.json": "29e4c210b0d6ac178b16b2a255a568bdb23b581e50ca1ef6a6d071dd85704e6e",
    "generation_config.json": "189fb0c0d7fd8a527db217c0a60a0e013f0394cd8800f9697a666a9e75e5f7fd",
    "model-00001-of-00004.safetensors": "2b1879f356aed350030bb40eb45ad362c89d9891096f79a3ab323d3ba5607668",
    "model-00002-of-00004.safetensors": "09d433f650646834a83c580877bd60c6d1f88f7755305c12576b5c7058f9af15",
    "model-00003-of-00004.safetensors": "fc1cdddd6bfa91128d6e94ee73d0ce62bfcdb7af29e978ddcab30c66ae9ea7fa",
    "model-00004-of-00004.safetensors": "92ecfe1a2414458b4821ac8c13cf8cb70aed66b5eea8dc5ad9eeb4ff309d6d7b",
    "model.safetensors.index.json": "146776fce3f6db1103aa6f249e65ee5544c5923ce6f971b092eee79aa6e5d37b",
    "original/params.json": "b15b6b31b2043c0400b028ecc25c8946e21d76ac260e9ac6a357ed8727c8865f",
    "special_tokens_map.json": "6f38c73729248f6c127296386e3cdde96e254636cc58b4169d3fd32328d9a8ec",
    "tokenizer.json": "79e3e522635f3171300913bb421464a87de6222182a0570b9b2ccba2a964b2b4",
    "tokenizer_config.json": LOCAL_GENERATOR_TOKENIZER_CONFIG_SHA256,
}


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument(
        "--hosted-probe",
        type=Path,
        default=PROJECT
        / "outputs/paper1_reference_client_latency_pilot_v1/frozen_generator_probe.json",
    )
    parser.add_argument(
        "--local-pilot-dir",
        type=Path,
        default=PROJECT / "outputs/paper1_reference_client_latency_pilot_v1/local",
    )
    parser.add_argument("--nvidia-catalog", type=Path, default=Path("/tmp/paper1_nim_models.json"))
    parser.add_argument("--mirror-metadata", type=Path, default=Path("/tmp/paper1_llama_model_info.json"))
    parser.add_argument("--official-metadata", type=Path, default=Path("/tmp/paper1_meta_official_llama_info.json"))
    parser.add_argument(
        "--out-dir", type=Path, default=PROJECT / "data/paper1_authority"
    )
    return parser.parse_args()


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _weight_metadata(data: dict) -> dict[str, str]:
    return {
        str(row["rfilename"]): str(row["lfs"]["sha256"])
        for row in data["siblings"]
        if str(row.get("rfilename", "")).endswith(".safetensors")
        and row.get("lfs", {}).get("sha256")
    }


def main() -> int:
    args = _args()
    config = load_public_only_config(PROJECT / "configs/paper1_public_only.yaml")
    assert_pre_outcome_locked(config)
    probe = read_json(args.hosted_probe)
    pilot_manifest = read_json(args.local_pilot_dir / "call_manifest.json")
    pilot_report = read_json(args.local_pilot_dir / "pilot_report.json")
    traces = list(iter_jsonl(args.local_pilot_dir / "raw_traces.jsonl"))
    nvidia_catalog = read_json(args.nvidia_catalog)
    mirror = read_json(args.mirror_metadata)
    official = read_json(args.official_metadata)

    if probe.get("status") != "HTTP_REJECTED" or probe.get("result", {}).get("status_code") != 410:
        raise RuntimeError("hosted Generator retirement is not bound to one HTTP 410")
    catalog_models = {
        str(row.get("id")) for row in nvidia_catalog.get("data", []) if isinstance(row, dict)
    }
    if "meta/llama-3.1-8b-instruct" in catalog_models:
        raise RuntimeError("frozen hosted model unexpectedly remains in the bound catalog")
    if len(traces) != 21 or pilot_report.get("raw_trace_count") != 21:
        raise RuntimeError("local pilot must contain the exact 21-call trace set")
    if any("response" in row or "text" in row for row in traces):
        raise RuntimeError("tracked latency traces must not contain generated text")
    if any(row["record"]["metadata"].get("response_text_retained") is not False for row in traces):
        raise RuntimeError("every trace must attest that response text was not retained")
    warm_hashes: dict[tuple[str, str], set[str]] = {}
    for row in traces:
        if row["record"]["warm_state"] != "warm":
            continue
        key = (row["task_type"], row["configuration_id"])
        warm_hashes.setdefault(key, set()).add(row["record"]["metadata"]["response_sha256"])
    if len(warm_hashes) != 10 or any(len(values) != 1 for values in warm_hashes.values()):
        raise RuntimeError("warm greedy duplicate responses are not deterministic")

    file_rows = []
    for relative, expected in sorted(EXPECTED_FILES.items()):
        path = args.model_dir / relative
        actual = _file_sha(path)
        if actual != expected:
            raise RuntimeError(f"local model file hash mismatch: {relative}")
        file_rows.append({"path": relative, "size": path.stat().st_size, "sha256": actual})
    artifact_identity = sha256_text(canonical_json(file_rows))
    if artifact_identity != LOCAL_GENERATOR_ARTIFACT_IDENTITY_SHA256:
        raise RuntimeError("local model artifact aggregate identity mismatch")

    mirror_weights = _weight_metadata(mirror)
    official_weights = _weight_metadata(official)
    shard_names = [name for name in EXPECTED_FILES if name.endswith(".safetensors")]
    if any(
        EXPECTED_FILES[name] != mirror_weights.get(name)
        or EXPECTED_FILES[name] != official_weights.get(name)
        for name in shard_names
    ):
        raise RuntimeError("local/mirror/official weight identities do not match")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = args.out_dir / "paper1_local_llama31_model_artifact_20260903_v1.json"
    tracked_manifest_path = args.out_dir / "paper1_local_reference_latency_pilot_manifest_20260903_v1.json"
    tracked_traces_path = args.out_dir / "paper1_local_reference_latency_pilot_traces_20260903_v1.jsonl"
    tracked_report_path = args.out_dir / "paper1_local_reference_latency_pilot_report_20260903_v1.json"

    artifact = {
        "protocol": "paper1-local-llama31-model-artifact-v1",
        "status": "HASH_VERIFIED_EXACT_OFFICIAL_WEIGHT_BYTES",
        "model_runtime_id": "meta/llama-3.1-8b-instruct",
        "download_source": "NousResearch/Meta-Llama-3.1-8B-Instruct",
        "download_revision": LOCAL_GENERATOR_MODEL_REVISION,
        "meta_official_comparison_repo": "meta-llama/Llama-3.1-8B-Instruct",
        "meta_official_comparison_revision": official["sha"],
        "all_four_weight_shards_match_meta_official_lfs_sha256": True,
        "non_weight_note": (
            "weights/config/generation/index/tokenizer blobs match the official repository; "
            "the pinned mirror tokenizer_config predates Meta's later tokenizer_config update, "
            "so the actual local chat template is independently hash-frozen"
        ),
        "artifact_identity_sha256": artifact_identity,
        "chat_template_sha256": LOCAL_GENERATOR_CHAT_TEMPLATE_SHA256,
        "files": file_rows,
        "mirror_metadata_snapshot_sha256": sha256_file(args.mirror_metadata),
        "official_metadata_snapshot_sha256": sha256_file(args.official_metadata),
        "safetensors_shards_opened_successfully": 4,
        "paid_api_cost_usd": 0.0,
    }
    write_json(artifact_path, artifact)
    write_json(tracked_manifest_path, pilot_manifest)
    write_jsonl(tracked_traces_path, traces)
    report = pilot_report | {
        "tracked_manifest_sha256": sha256_file(tracked_manifest_path),
        "tracked_traces_sha256": sha256_file(tracked_traces_path),
        "supersedes_untracked_output_hashes": True,
    }
    write_json(tracked_report_path, report)

    authority = {
        "protocol": "paper1-generator-backend-retirement-local-amendment-v1",
        "date": "2026-09-03",
        "status": "ACTIVE_PRE_OUTCOME_LOCAL_GENERATOR_BACKEND",
        "not_an_empirical_pass_gate": True,
        "incident": {
            "previous_provider": "NVIDIA hosted NIM",
            "previous_model": "meta/llama-3.1-8b-instruct",
            "nvidia_catalog_sha256": sha256_file(args.nvidia_catalog),
            "nvidia_catalog_model_count": len(catalog_models),
            "previous_model_listed": False,
            "exact_model_call_http_status": 410,
            "retry_performed": False,
            "probe_artifact_sha256": sha256_file(args.hosted_probe),
            "probe_unknown_cost_conservatively_accounted_usd": 0.01,
            "dg_seeker_catalog_note_superseded_2026_09_04": {
                "incorrect_old_inference": (
                    "the historical Mixtral/Qwen fixed-seeker endpoints were treated as "
                    "the official Paper-1 ES-MemEval DG seeker dependency"
                ),
                "correction": (
                    "pinned ES-MemEval binds every DG executable's seeker to gpt-4o; "
                    "Mixtral/Qwen belong to an older controlled fixed-seeker extension"
                ),
                "authoritative_followup": (
                    "paper1_official_dg_simulator_call_cost_surface_20260904_v1.json"
                ),
                "seeker_calls_made": 0,
            },
        },
        "decision": {
            "action": "replace retired hosted backend with local exact-weight A6000 backend",
            "timing": "before any formal outcome or PM training",
            "model_architecture_and_weight_bytes_changed": False,
            "serving_backend_changed": True,
            "old_hosted_internal_chat_template_equivalence_claimed": False,
            "old_hosted_latency_combined_with_local_latency": False,
            "local_provider": "single-node local A6000 Transformers reference server",
            "local_base_url": "http://127.0.0.1:8011",
            "local_server_protocol": LOCAL_GENERATOR_SERVER_PROTOCOL,
            "local_model_artifact": artifact_path.name,
            "local_model_artifact_sha256": sha256_file(artifact_path),
            "temperature": 0,
            "decoding": "greedy_do_sample_false",
            "concurrency": 1,
            "streaming": True,
        },
        "pilot": {
            "purpose": "instrumentation and deployment-stack feasibility only",
            "scope": "precomputed QA/Summary Generator path, not full PM+BGE+pack E2E",
            "raw_calls": 21,
            "cold_calls": 1,
            "warm_calls": 20,
            "warm_repeats_per_task_configuration": 2,
            "all_calls_completed": True,
            "all_warm_duplicate_response_hashes_deterministic": True,
            "generated_text_retained_or_scored": False,
            "formal_outcome_calls": 0,
            "pm_training_runs": 0,
            "paid_api_cost_usd": 0.0,
            "allocator_eligible": False,
            "paper_latency_claim_eligible": False,
            "reason": "N=2 per warm cell and no RS/DG/full-pipeline coverage",
            "manifest": tracked_manifest_path.name,
            "manifest_sha256": sha256_file(tracked_manifest_path),
            "traces": tracked_traces_path.name,
            "traces_sha256": sha256_file(tracked_traces_path),
            "report": tracked_report_path.name,
            "report_sha256": sha256_file(tracked_report_path),
            "important_observation": (
                "realized completion latency depends on both prompt prefill and response stopping "
                "length; current-request realized output length remains forbidden as a pre-action feature"
            ),
        },
        "budget": {
            "researcher_authorized_token_call_latency_pilot_cap_usd": 1.0,
            "conservatively_accounted_this_stage_usd": 0.01,
            "remaining_stage_authorization_usd": 0.99,
            "paper1_cumulative_accounted_usd": 1.16721901,
            "new_valid_local_pilot_api_cost_usd": 0.0,
        },
        "remaining_before_allocator_use": [
            "add RS and dynamic DG coverage",
            "measure multiple targets in each frozen context/resource-token bin",
            "select repeat count before allocator-eligible timing data",
            "measure warm primary and cold separately",
            "include real PM, query embedding, retrieval and packing inside one client clock",
            "retain task output caps and learn stopping-length variation only from zero-outcome timing data",
        "freeze the official GPT-4o seeker execution/cost policy after the separate 2026-09-04 source audit",
        ],
        "locks": {
            key: config[key]["status"] for key in config if key.endswith("OUTCOME_LOCK")
        },
        "formal_outcome_calls": 0,
        "pm_training_runs": 0,
    }
    authority_path = args.out_dir / "paper1_generator_backend_retirement_local_amendment_20260903_v1.json"
    write_json(authority_path, authority)

    previous_multi_view = read_json(
        args.out_dir / "paper1_active_multi_view_bge_packing_binding_20260903_v1.json"
    )
    multi_view_v2 = previous_multi_view | {
        "protocol": "pm-paper1-active-multi-view-bge-packing-binding-v2",
        "status": (
            "ACTIVE_ZERO_OUTCOME_RETRIEVAL_PACKING_PROMPT_LOCAL_BACKEND_BINDING_"
            "NO_K_OR_FINAL_CAP_SELECTED"
        ),
        "supersedes": "paper1_active_multi_view_bge_packing_binding_20260903_v1.json",
        "supersession_scope": (
            "Generator backend/request identity only; candidate, BGE, top8, amount, "
            "packing and official prompt bytes are unchanged"
        ),
        "rq2_generator_prompt_binding": previous_multi_view["rq2_generator_prompt_binding"]
        | {
            "protocol": RQ2_PROMPT_PROTOCOL,
            "implementation": {
                "path": "src/metacom_pm/paper1/execution/rq2_prompts.py",
                "sha256": sha256_file(
                    PROJECT / "src/metacom_pm/paper1/execution/rq2_prompts.py"
                ),
            },
            "provider_request": {
                "provider": "local A6000 Transformers reference server",
                "base_url": "http://127.0.0.1:8011",
                "model": "meta/llama-3.1-8b-instruct",
                "model_revision": LOCAL_GENERATOR_MODEL_REVISION,
                "model_artifact_identity_sha256": LOCAL_GENERATOR_ARTIFACT_IDENTITY_SHA256,
                "serving_protocol": LOCAL_GENERATOR_SERVER_PROTOCOL,
                "chat_template_sha256": LOCAL_GENERATOR_CHAT_TEMPLATE_SHA256,
                "temperature": 0,
                "decoding": "greedy_do_sample_false",
                "max_output_tokens": {
                    "QA": 256,
                    "Summary": 256,
                    "DialogueGeneration": 60,
                },
                "client_role_content_message_bytes_hash_bound_per_request": True,
                "provider_internal_chat_template_hash_available": True,
                "old_hosted_template_or_latency_equivalence_claimed": False,
            },
        },
    }
    multi_view_v2_path = (
        args.out_dir / "paper1_active_multi_view_bge_packing_binding_20260903_v2.json"
    )
    write_json(multi_view_v2_path, multi_view_v2)
    print(
        canonical_json(
            {
                "authority": str(authority_path),
                "authority_sha256": sha256_file(authority_path),
                "model_artifact_sha256": sha256_file(artifact_path),
                "pilot_traces": len(traces),
                "multi_view_v2_sha256": sha256_file(multi_view_v2_path),
                "formal_outcome_calls": 0,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
