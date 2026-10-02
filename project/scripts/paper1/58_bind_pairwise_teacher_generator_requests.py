#!/usr/bin/env python3
"""Bind the 142 unique local Generator requests for teacher reference.

Static ESC/QA/Summary requests come directly from the outcome-blind base-pair
preflight.  DG uses the nine already-frozen first seeker turns as the exact
live retrieval query, then applies the pinned BGE-M3 ranking and typed Step2
packing.  Generated seeker text and full provider requests remain under
ignored ``outputs/``; tracked authority stores identities and hashes only.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import (  # noqa: E402
    canonical_json,
    iter_jsonl,
    read_json,
    sha256_file,
    sha256_text,
    stable_hex,
    write_json,
    write_jsonl,
)
from metacom_pm.paper1.candidates import compile_multi_view_candidate_bundle  # noqa: E402
from metacom_pm.paper1.contracts import Head, TaskType  # noqa: E402
from metacom_pm.paper1.data.memory_source import (  # noqa: E402
    enumerate_targets,
    load_sanitized_runtime_users,
)
from metacom_pm.paper1.embeddings import (  # noqa: E402
    BgeM3Encoder,
    EmbeddingSuccessCache,
    materialize_embeddings,
)
from metacom_pm.paper1.execution import GeneratorMessage, build_dg_supporter_request  # noqa: E402
from metacom_pm.paper1.execution.packing import RankedCandidate, pack_ranked_prefix  # noqa: E402
from metacom_pm.paper1.llama_tokenizer import (  # noqa: E402
    LLAMA_TOKENIZER_JSON_SHA256,
    build_llama_token_counter,
)
from metacom_pm.paper1.multi_view_memory import load_accepted_multi_view_units  # noqa: E402
from metacom_pm.paper1.outcome_lock import (  # noqa: E402
    assert_pre_outcome_locked,
    load_public_only_config,
)


PROTOCOL = "paper1-pairwise-teacher-generator-request-binding-v1"
HEADS = (Head.MP, Head.ME, Head.MS)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tokenizer-json", type=Path, required=True)
    parser.add_argument(
        "--base-pairs",
        type=Path,
        default=PROJECT
        / "data/paper1_authority/paper1_pairwise_teacher_base_pair_preflight_20260904_v1.jsonl",
    )
    parser.add_argument(
        "--dg-result",
        type=Path,
        default=PROJECT
        / "data/paper1_authority/paper1_pairwise_teacher_dg_first_turn_result_20260904_v1.json",
    )
    parser.add_argument(
        "--dg-private",
        type=Path,
        default=PROJECT
        / "outputs/paper1_pairwise_teacher/private_dg_first_turns_20260904_v1.json",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=PROJECT
        / "data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json",
    )
    parser.add_argument(
        "--raw-data", type=Path, default=PROJECT / "data/external/evo_emo.json"
    )
    parser.add_argument(
        "--session-results",
        type=Path,
        default=PROJECT
        / "data/paper1_public_memory/es_memeval_public_multi_view_session_results_v1.jsonl",
    )
    parser.add_argument(
        "--embedding-cache",
        type=Path,
        default=PROJECT / "outputs/paper1_multi_view_bge_m3_v1/cache",
    )
    parser.add_argument(
        "--private-out",
        type=Path,
        default=PROJECT
        / "outputs/paper1_pairwise_teacher/private_generator_requests_20260904_v1.jsonl",
    )
    parser.add_argument(
        "--authority-out",
        type=Path,
        default=PROJECT
        / "data/paper1_authority/paper1_pairwise_teacher_generator_request_binding_20260904_v1.json",
    )
    return parser.parse_args()


def _build_selected_owner_bundles(
    *, users, targets_by_id, units, owner_ids: set[str], token_counter
):
    users_by_owner = {user.owner_id: user for user in users}
    units_by_owner: dict[str, list[Any]] = defaultdict(list)
    for unit in units:
        if unit.owner_id in owner_ids:
            units_by_owner[unit.owner_id].append(unit)
    bundles = {}
    for owner_id in sorted(owner_ids):
        target = next(
            target
            for target in targets_by_id.values()
            if target.owner_id == owner_id
            and target.task_type is TaskType.DIALOGUE_GENERATION
        )
        bundles[owner_id] = compile_multi_view_candidate_bundle(
            tuple(units_by_owner[owner_id]),
            users_by_owner[owner_id],
            target,
            token_counter=token_counter,
        )
    return bundles


def _rank_dg(
    *, dg_text: dict[str, str], targets_by_id, bundles, encoder, cache
) -> tuple[dict[tuple[str, Head], tuple[RankedCandidate, ...]], dict[str, Any]]:
    candidate_vectors: dict[str, tuple[float, ...]] = {}
    for head in HEADS:
        items = [
            (candidate.candidate_id, candidate.content)
            for owner_id in sorted(bundles)
            for candidate in bundles[owner_id][head]
        ]
        materialized = materialize_embeddings(
            items,
            field_source=f"active_multi_view_{head.value}_candidate_content_v1",
            encoder=encoder,
            cache=cache,
            chunk_size=128,
        )
        candidate_vectors.update(materialized.vectors)
    queries = materialize_embeddings(
        sorted(dg_text.items()),
        field_source="pairwise_teacher_DG_first_seeker_turn_v1",
        encoder=encoder,
        cache=cache,
        chunk_size=9,
    )
    ranked: dict[tuple[str, Head], tuple[RankedCandidate, ...]] = {}
    for target_id in sorted(dg_text):
        target = targets_by_id[target_id]
        query = np.asarray(queries.vectors[target_id], dtype=np.float32)
        for head in HEADS:
            candidates = bundles[target.owner_id][head]
            matrix = np.asarray(
                [candidate_vectors[candidate.candidate_id] for candidate in candidates],
                dtype=np.float32,
            )
            scores = matrix @ query
            order = sorted(
                range(len(candidates)),
                key=lambda index: (
                    -float(scores[index]),
                    candidates[index].candidate_id,
                ),
            )
            ranked[(target_id, head)] = tuple(
                RankedCandidate(
                    candidate=candidates[index], similarity=float(scores[index])
                )
                for index in order
            )
    identity = {
        "binding_identity_sha256": encoder.binding.identity_sha256,
        "runtime_identity_sha256": encoder.runtime_identity.identity_sha256,
        "query_field_source": "pairwise_teacher_DG_first_seeker_turn_v1",
        "query_count": len(queries.vectors),
    }
    return ranked, identity


def main() -> int:
    args = _args()
    assert_pre_outcome_locked(
        load_public_only_config(PROJECT / "configs/paper1_public_only.yaml")
    )
    if sha256_file(args.tokenizer_json) != LLAMA_TOKENIZER_JSON_SHA256:
        raise RuntimeError("Generator tokenizer hash mismatch")
    dg_result = read_json(args.dg_result)
    dg_private = read_json(args.dg_private)
    if (
        dg_result.get("status") != "PASS"
        or dg_result["execution"]["new_calls_succeeded"] != 8
        or dg_private.get("status") != "PASS"
        or dg_private.get("response_quality_inspected_or_scored") is not False
    ):
        raise RuntimeError("nine frozen DG seeker turns are not ready")
    dg_text: dict[str, str] = {}
    for row in dg_private["responses"]:
        text = str(row.get("accepted_text") or row.get("text") or "")
        if not text:
            raise RuntimeError("DG private response text is empty")
        dg_text[str(row["target_id"])] = text
    if len(dg_text) != 9:
        raise RuntimeError("DG private response set is not exactly nine scenarios")

    base_rows = list(iter_jsonl(args.base_pairs))
    users = load_sanitized_runtime_users(args.source)
    raw_users = {
        str(user["id"]): user
        for user in json.loads(args.raw_data.read_text(encoding="utf-8"))
    }
    targets = enumerate_targets(users)
    targets_by_id = {target.target_id: target for target in targets}
    units = load_accepted_multi_view_units(args.session_results, users=users)
    token_counter = build_llama_token_counter(args.tokenizer_json)
    owner_ids = {targets_by_id[target_id].owner_id for target_id in dg_text}
    bundles = _build_selected_owner_bundles(
        users=users,
        targets_by_id=targets_by_id,
        units=units,
        owner_ids=owner_ids,
        token_counter=token_counter,
    )
    encoder = BgeM3Encoder()
    ranked, embedding_identity = _rank_dg(
        dg_text=dg_text,
        targets_by_id=targets_by_id,
        bundles=bundles,
        encoder=encoder,
        cache=EmbeddingSuccessCache(args.embedding_cache),
    )

    private_requests: list[dict[str, Any]] = []
    tracked_requests: list[dict[str, Any]] = []

    def add_request(
        *, task: str, target_id: str, arm: str, head: str | None,
        base_pair_ids: list[str], request: dict[str, Any]
    ) -> None:
        request_hash = sha256_text(canonical_json(request))
        request_id = "teacher_gen_" + stable_hex(
            PROTOCOL, task, target_id, arm, head or "shared", request_hash, n=24
        )
        private_requests.append(
            {
                "protocol": PROTOCOL,
                "request_id": request_id,
                "task": task,
                "target_id": target_id,
                "arm": arm,
                "head": head,
                "base_pair_ids": sorted(base_pair_ids),
                "request_sha256": request_hash,
                "request": request,
            }
        )
        tracked_requests.append(
            {
                "request_id": request_id,
                "task": task,
                "target_id": target_id,
                "arm": arm,
                "head": head,
                "base_pair_ids": sorted(base_pair_ids),
                "request_sha256": request_hash,
            }
        )

    for row in base_rows:
        if row["task"] == "DG":
            continue
        add_request(
            task=row["task"],
            target_id=row["target_id"],
            arm="OFF",
            head=row["head"],
            base_pair_ids=[row["base_pair_id"]],
            request=row["off_request"],
        )
        add_request(
            task=row["task"],
            target_id=row["target_id"],
            arm="ON",
            head=row["head"],
            base_pair_ids=[row["base_pair_id"]],
            request=row["on_request"],
        )

    dg_rows_by_target: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in base_rows:
        if row["task"] == "DG":
            dg_rows_by_target[row["target_id"]].append(row)
    dg_retrieval: list[dict[str, Any]] = []
    for target_id in sorted(dg_rows_by_target):
        rows = dg_rows_by_target[target_id]
        target = targets_by_id[target_id]
        display_name = str(raw_users[target.owner_id]["basic_info"]["name"])
        opening = GeneratorMessage(
            role="assistant",
            content=f"Hi {display_name}! How are you these days?",
        )
        seeker = GeneratorMessage(role="user", content=dg_text[target_id])
        off = build_dg_supporter_request(
            display_name=display_name, current_dialogue=(opening, seeker)
        )
        add_request(
            task="DG",
            target_id=target_id,
            arm="OFF",
            head=None,
            base_pair_ids=[row["base_pair_id"] for row in rows],
            request=off.model_dump(mode="json"),
        )
        for row in rows:
            head = Head(row["head"])
            k = int(row["qualification_probe_k"])
            packed = pack_ranked_prefix(
                head=head,
                ranked=ranked[(target_id, head)],
                k=k,
                target_owner_id=target.owner_id,
                token_counter=token_counter,
            )
            on = build_dg_supporter_request(
                display_name=display_name,
                current_dialogue=(opening, seeker),
                resources=(packed.envelope,),
            )
            add_request(
                task="DG",
                target_id=target_id,
                arm="ON",
                head=head.value,
                base_pair_ids=[row["base_pair_id"]],
                request=on.model_dump(mode="json"),
            )
            dg_retrieval.append(
                {
                    "target_id": target_id,
                    "seeker_text_sha256": sha256_text(dg_text[target_id]),
                    "head": head.value,
                    "requested_k": k,
                    "realized_k": packed.realized_k,
                    "candidate_ids": [
                        item.candidate.candidate_id
                        for item in ranked[(target_id, head)][:k]
                    ],
                    "candidate_similarities": [
                        item.similarity for item in ranked[(target_id, head)][:k]
                    ],
                    "resource_sha256": (
                        packed.envelope.resource_block.resource_sha256
                        if packed.envelope.resource_block is not None
                        else None
                    ),
                    "rendered_resource_tokens": packed.rendered_resource_tokens,
                }
            )

    if len(private_requests) != 142:
        raise RuntimeError(f"expected 142 unique Generator requests, got {len(private_requests)}")
    if len({row["request_id"] for row in private_requests}) != 142:
        raise RuntimeError("Generator request IDs are not unique")
    if Counter(row["task"] for row in private_requests) != Counter(
        {"ESC": 54, "QA": 26, "Summary": 26, "DG": 36}
    ):
        raise RuntimeError("Generator request task accounting drifted")
    write_jsonl(args.private_out, private_requests)
    authority = {
        "protocol": PROTOCOL,
        "date": "2026-09-04",
        "status": "ACTIVE_ZERO_OUTCOME_142_LOCAL_REQUESTS_BOUND",
        "source": {
            "base_pair_manifest_sha256": sha256_file(args.base_pairs),
            "dg_first_turn_result_sha256": sha256_file(args.dg_result),
            "dg_private_response_manifest_sha256": sha256_file(args.dg_private),
            "memory_source_sha256": sha256_file(args.source),
            "raw_data_sha256": sha256_file(args.raw_data),
            "multi_view_session_results_sha256": sha256_file(args.session_results),
            "tokenizer_sha256": sha256_file(args.tokenizer_json),
        },
        "embedding_identity": embedding_identity,
        "counts": {
            "base_pairs": 80,
            "unique_generator_requests": 142,
            "by_task": dict(sorted(Counter(row["task"] for row in private_requests).items())),
            "dg_scenario_clusters": 9,
            "dg_shared_off_requests": 9,
            "dg_head_specific_on_requests": 27,
        },
        "private_request_manifest": {
            "path": "outputs/paper1_pairwise_teacher/private_generator_requests_20260904_v1.jsonl",
            "sha256": sha256_file(args.private_out),
            "contains_private_generated_seeker_text": True,
            "git_tracking_forbidden": True,
        },
        "request_identities": tracked_requests,
        "dg_dynamic_retrieval": dg_retrieval,
        "selection_read_response_quality": False,
        "paid_api_calls": 0,
        "formal_outcome_calls": 0,
        "evaluator_calls": 0,
        "pm_training_runs": 0,
        "locks": {
            name: load_public_only_config(PROJECT / "configs/paper1_public_only.yaml")[name][
                "status"
            ]
            for name in (
                "RQ1_RS_CALIBRATION_OUTCOME_LOCK",
                "RQ2_MEMORY_CALIBRATION_OUTCOME_LOCK",
                "RQ1_CONFIRMATORY_OUTCOME_LOCK",
                "RQ2_CONFIRMATORY_OUTCOME_LOCK",
            )
        },
    }
    write_json(args.authority_out, authority)
    print(canonical_json({
        "status": authority["status"],
        "counts": authority["counts"],
        "embedding_identity": embedding_identity,
        "private_request_manifest_sha256": authority["private_request_manifest"]["sha256"],
        "paid_api_calls": 0,
        "formal_outcome_calls": 0,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
