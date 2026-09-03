#!/usr/bin/env python3
"""Materialize active Multi-View BGE top-8 and zero-outcome amount surfaces.

Only runtime-visible QA/Summary questions, strict-past public memory
candidates, a local pinned BGE-M3 encoder, and the hash-verified Generator
tokenizer are read.  No Generator, evaluator, paid API, effect outcome, or PM
training code is invoked.  DG remains dynamic: this artifact records its
frozen per-round query contract and outcome-blind capacity/token envelopes,
not fictitious static rankings.
"""

from __future__ import annotations

import argparse
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import read_json, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402
from metacom_pm.paper1.candidates import compile_multi_view_candidate_bundle  # noqa: E402
from metacom_pm.paper1.contracts import CandidateRecord, Head, TaskType  # noqa: E402
from metacom_pm.paper1.data.memory_source import (  # noqa: E402
    MemorySourceUser,
    Target,
    enumerate_targets,
    load_sanitized_runtime_users,
)
from metacom_pm.paper1.embeddings import (  # noqa: E402
    BgeM3Encoder,
    EmbeddingSuccessCache,
    build_materialization_report,
    materialize_embeddings,
)
from metacom_pm.paper1.execution.packing import (  # noqa: E402
    PACKING_PROTOCOL,
    RankedCandidate,
    pack_ranked_prefix,
)
from metacom_pm.paper1.execution.step2 import STEP2_RESOURCE_PROTOCOL  # noqa: E402
from metacom_pm.paper1.llama_tokenizer import (  # noqa: E402
    LLAMA_TOKENIZER_JSON_SHA256,
    LLAMA_TOKENIZER_REPO,
    LLAMA_TOKENIZER_REVISION,
    build_llama_token_counter,
)
from metacom_pm.paper1.multi_view_memory import load_accepted_multi_view_units  # noqa: E402
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config  # noqa: E402


HEADS = (Head.MP, Head.MS, Head.ME)
STATIC_TASKS = (TaskType.QA, TaskType.SUMMARY)
INITIAL_K = (0, 1, 2, 3, 4)
TOP_DEPTH = 8
DIAGNOSTIC_CAPS = (128, 192, 256, 384, 512, 768, 1024, 1536, 2048, 3072, 4096, 6144)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=PROJECT / "data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json",
    )
    parser.add_argument(
        "--session-results",
        type=Path,
        default=PROJECT / "data/paper1_public_memory/es_memeval_public_multi_view_session_results_v1.jsonl",
    )
    parser.add_argument(
        "--candidate-census-summary",
        type=Path,
        default=PROJECT / "data/paper1_public_memory/es_memeval_public_multi_view_candidate_census_summary_v1.json",
    )
    parser.add_argument("--tokenizer-json", type=Path, required=True)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=PROJECT / "outputs/paper1_multi_view_bge_m3_v1/cache",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=PROJECT / "data/paper1_public_memory",
    )
    return parser.parse_args()


def _nearest_rank(values: list[int | float], probability: float) -> int | float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(probability * len(ordered)) - 1)]


def _distribution(values: Iterable[int | float]) -> dict[str, int | float | None]:
    rows = list(values)
    return {
        "count": len(rows),
        "min": min(rows, default=None),
        "median": statistics.median(rows) if rows else None,
        "p90_nearest_rank": _nearest_rank(rows, 0.90),
        "p95_nearest_rank": _nearest_rank(rows, 0.95),
        "max": max(rows, default=None),
        "mean": statistics.fmean(rows) if rows else None,
    }


def _stable_materialization_identity(report: dict[str, Any]) -> dict[str, Any]:
    """Remove cache-state counters from a reproducible scientific artifact.

    Cache hits are an execution-performance fact: a clean first run and an
    identical resume must produce byte-identical tracked ranking/surface
    artifacts.  The cache itself remains content- and runtime-addressed.
    """

    return {
        key: value
        for key, value in report.items()
        if key not in {"cache_hits", "newly_encoded"}
    } | {"cache_hit_counts_excluded_from_frozen_identity": True}


def _build_bundles(
    *,
    users: tuple[MemorySourceUser, ...],
    targets: tuple[Target, ...],
    units: tuple[Any, ...],
    token_counter,
) -> dict[str, dict[Head, tuple[CandidateRecord, ...]]]:
    targets_by_owner: dict[str, list[Target]] = defaultdict(list)
    for target in targets:
        targets_by_owner[target.owner_id].append(target)
    units_by_owner: dict[str, list[Any]] = defaultdict(list)
    for unit in units:
        units_by_owner[unit.owner_id].append(unit)

    bundles = {}
    for user in users:
        owner_targets = targets_by_owner[user.owner_id]
        if not owner_targets or any(
            target.cutoff_rank != len(user.sessions) for target in owner_targets
        ):
            raise RuntimeError("target population does not use one official full-history cutoff")
        bundles[user.owner_id] = compile_multi_view_candidate_bundle(
            tuple(units_by_owner[user.owner_id]),
            user,
            owner_targets[0],
            token_counter=token_counter,
        )
    return bundles


def _materialize_vectors(
    *,
    bundles: dict[str, dict[Head, tuple[CandidateRecord, ...]]],
    static_targets: tuple[Target, ...],
    encoder: BgeM3Encoder,
    cache: EmbeddingSuccessCache,
) -> tuple[dict[str, tuple[float, ...]], dict[str, tuple[float, ...]], dict[str, Any]]:
    candidate_vectors: dict[str, tuple[float, ...]] = {}
    reports: dict[str, Any] = {}
    for head in HEADS:
        items = [
            (candidate.candidate_id, candidate.content)
            for owner_id in sorted(bundles)
            for candidate in bundles[owner_id][head]
        ]
        result = materialize_embeddings(
            items,
            field_source=f"active_multi_view_{head.value}_candidate_content_v1",
            encoder=encoder,
            cache=cache,
            chunk_size=128,
        )
        candidate_vectors.update(result.vectors)
        reports[head.value] = _stable_materialization_identity(
            build_materialization_report(
                field_source=f"active_multi_view_{head.value}_candidate_content_v1",
                result=result,
                encoder=encoder,
            )
        )

    query_result = materialize_embeddings(
        [(target.target_id, target.visible_query_text or "") for target in static_targets],
        field_source="active_multi_view_QA_Summary_visible_query_text_v1",
        encoder=encoder,
        cache=cache,
        chunk_size=256,
    )
    reports["static_queries"] = _stable_materialization_identity(
        build_materialization_report(
            field_source="active_multi_view_QA_Summary_visible_query_text_v1",
            result=query_result,
            encoder=encoder,
        )
    )
    return candidate_vectors, query_result.vectors, reports


def _rank_static_targets(
    *,
    static_targets: tuple[Target, ...],
    bundles: dict[str, dict[Head, tuple[CandidateRecord, ...]]],
    candidate_vectors: dict[str, tuple[float, ...]],
    query_vectors: dict[str, tuple[float, ...]],
) -> tuple[list[dict[str, Any]], dict[tuple[str, Head], tuple[RankedCandidate, ...]]]:
    rows: list[dict[str, Any]] = []
    ranked_by_target_head: dict[tuple[str, Head], tuple[RankedCandidate, ...]] = {}
    for target in static_targets:
        query = np.asarray(query_vectors[target.target_id], dtype=np.float32)
        for head in HEADS:
            candidates = bundles[target.owner_id][head]
            matrix = np.asarray(
                [candidate_vectors[candidate.candidate_id] for candidate in candidates],
                dtype=np.float32,
            )
            scores = matrix @ query
            order = sorted(
                range(len(candidates)),
                key=lambda index: (-float(scores[index]), candidates[index].candidate_id),
            )
            ranked = tuple(
                RankedCandidate(
                    candidate=candidates[index],
                    similarity=float(scores[index]),
                )
                for index in order
            )
            ranked_by_target_head[(target.target_id, head)] = ranked
            rows.append(
                {
                    "protocol": "paper1-active-multi-view-bge-top8-v1",
                    "target_id": target.target_id,
                    "task_type": target.task_type.value,
                    "owner_id": target.owner_id,
                    "head": head.value,
                    "query_sha256": sha256_text(target.visible_query_text or ""),
                    "eligible_candidate_count": len(candidates),
                    "ranked_candidates": [
                        {
                            "rank": rank,
                            "candidate_id": item.candidate.candidate_id,
                            "candidate_content_sha256": item.candidate.lineage.content_sha256,
                            "candidate_tokens": item.candidate.token_count,
                            "bge_cosine_similarity": item.similarity,
                        }
                        for rank, item in enumerate(ranked[:TOP_DEPTH], 1)
                    ],
                    "contains_query_or_candidate_text": False,
                    "formal_outcome_calls": 0,
                }
            )
    return rows, ranked_by_target_head


def _static_surface(
    *,
    task: TaskType,
    targets: tuple[Target, ...],
    ranked_by_target_head: dict[tuple[str, Head], tuple[RankedCandidate, ...]],
    token_counter,
) -> dict[str, Any]:
    task_targets = tuple(target for target in targets if target.task_type is task)
    per_head: dict[str, Any] = {}
    for head in HEADS:
        cells = []
        for k in INITIAL_K:
            realized: list[int] = []
            candidate_tokens: list[int] = []
            resource_tokens: list[int] = []
            kth_scores: list[float] = []
            boundary_margins: list[float] = []
            for target in task_targets:
                ranked = ranked_by_target_head[(target.target_id, head)]
                packed = pack_ranked_prefix(
                    head=head,
                    ranked=ranked,
                    k=k,
                    target_owner_id=target.owner_id,
                    token_counter=token_counter,
                )
                realized.append(packed.realized_k)
                resource_tokens.append(packed.rendered_resource_tokens)
                candidate_tokens.append(
                    sum(item.candidate.token_count for item in ranked[:k])
                )
                if k > 0 and len(ranked) >= k:
                    kth_scores.append(ranked[k - 1].similarity)
                if k > 0 and len(ranked) > k:
                    boundary_margins.append(ranked[k - 1].similarity - ranked[k].similarity)
            cells.append(
                {
                    "requested_k": k,
                    "targets": len(task_targets),
                    "targets_with_full_k": sum(value == k for value in realized),
                    "full_k_fraction": sum(value == k for value in realized) / len(realized),
                    "realized_k": _distribution(realized),
                    "candidate_content_tokens": _distribution(candidate_tokens),
                    "exact_step2_rendered_resource_tokens": _distribution(resource_tokens),
                    "kth_candidate_bge_cosine_similarity": _distribution(kth_scores),
                    "k_boundary_similarity_margin": _distribution(boundary_margins),
                    "diagnostic_cap_fit_not_a_cap_selection": {
                        str(cap): {
                            "targets_fit": sum(value <= cap for value in resource_tokens),
                            "fraction": sum(value <= cap for value in resource_tokens) / len(resource_tokens),
                        }
                        for cap in DIAGNOSTIC_CAPS
                    },
                }
            )
        per_head[head.value] = cells
    symmetric_cells = []
    for k in INITIAL_K:
        realized_units: list[int] = []
        combined_resource_tokens: list[int] = []
        for target in task_targets:
            blocks: list[str] = []
            delivered = 0
            for head in HEADS:
                packed = pack_ranked_prefix(
                    head=head,
                    ranked=ranked_by_target_head[(target.target_id, head)],
                    k=k,
                    target_owner_id=target.owner_id,
                    token_counter=token_counter,
                )
                delivered += packed.realized_k
                if packed.envelope.resource_block is not None:
                    blocks.append(packed.envelope.rendered_resource_block)
            realized_units.append(delivered)
            combined_resource_tokens.append(
                token_counter("\n".join(blocks)) if blocks else 0
            )
        symmetric_cells.append(
            {
                "symmetric_requested_k_per_head": k,
                "targets": len(task_targets),
                "realized_units_across_MP_ME_MS": _distribution(realized_units),
                "exact_combined_step2_resource_tokens": _distribution(
                    combined_resource_tokens
                ),
                "diagnostic_cap_fit_not_a_cap_selection": {
                    str(cap): {
                        "targets_fit": sum(
                            value <= cap for value in combined_resource_tokens
                        ),
                        "fraction": sum(
                            value <= cap for value in combined_resource_tokens
                        )
                        / len(combined_resource_tokens),
                    }
                    for cap in DIAGNOSTIC_CAPS
                },
                "interpretation": (
                    "diagnostic simultaneous-three-head request in canonical MP,ME,MS "
                    "order; the learned allocator may select a subset and amount selection "
                    "remains task/head/fold specific"
                ),
            }
        )
    return {
        "status": "STATIC_VISIBLE_QUERY_TOP8_AND_AMOUNT_SURFACE_READY",
        "targets": len(task_targets),
        "per_head": per_head,
        "all_heads_symmetric_k_diagnostic": symmetric_cells,
    }


def _dg_capacity_surface(
    *,
    dg_targets: tuple[Target, ...],
    bundles: dict[str, dict[Head, tuple[CandidateRecord, ...]]],
    token_counter,
) -> dict[str, Any]:
    owner_ids = sorted({target.owner_id for target in dg_targets})
    per_head: dict[str, Any] = {}
    for head in HEADS:
        cells = []
        for k in INITIAL_K:
            counts: list[int] = []
            shortest_candidate_tokens: list[int] = []
            longest_candidate_tokens: list[int] = []
            shortest_rendered_tokens: list[int] = []
            longest_rendered_tokens: list[int] = []
            for owner_id in owner_ids:
                candidates = bundles[owner_id][head]
                ascending = sorted(candidates, key=lambda c: (c.token_count, c.candidate_id))
                descending = sorted(candidates, key=lambda c: (-c.token_count, c.candidate_id))
                short_ranked = tuple(
                    RankedCandidate(candidate=candidate, similarity=float(-index))
                    for index, candidate in enumerate(ascending)
                )
                long_ranked = tuple(
                    RankedCandidate(candidate=candidate, similarity=float(-index))
                    for index, candidate in enumerate(descending)
                )
                short = pack_ranked_prefix(
                    head=head,
                    ranked=short_ranked,
                    k=k,
                    target_owner_id=owner_id,
                    token_counter=token_counter,
                )
                long = pack_ranked_prefix(
                    head=head,
                    ranked=long_ranked,
                    k=k,
                    target_owner_id=owner_id,
                    token_counter=token_counter,
                )
                counts.append(min(k, len(candidates)))
                shortest_candidate_tokens.append(
                    sum(candidate.token_count for candidate in ascending[:k])
                )
                longest_candidate_tokens.append(
                    sum(candidate.token_count for candidate in descending[:k])
                )
                shortest_rendered_tokens.append(short.rendered_resource_tokens)
                longest_rendered_tokens.append(long.rendered_resource_tokens)
            cells.append(
                {
                    "requested_k": k,
                    "owners": len(owner_ids),
                    "realized_k_capacity": _distribution(counts),
                    "sum_of_k_shortest_candidate_tokens": _distribution(shortest_candidate_tokens),
                    "sum_of_k_longest_candidate_tokens": _distribution(longest_candidate_tokens),
                    "exact_rendered_shortest_token_order_proxy": _distribution(shortest_rendered_tokens),
                    "exact_rendered_longest_token_order_proxy": _distribution(longest_rendered_tokens),
                    "interpretation": (
                        "outcome-blind length extremes, not a static DG ranking and not a proof "
                        "that the longest-token ordering maximizes joint tokenizer length"
                    ),
                }
            )
        per_head[head.value] = cells
    combined_cells = []
    for k in INITIAL_K:
        shortest_combined: list[int] = []
        longest_combined: list[int] = []
        for owner_id in owner_ids:
            shortest_blocks: list[str] = []
            longest_blocks: list[str] = []
            for head in HEADS:
                candidates = bundles[owner_id][head]
                ascending = sorted(candidates, key=lambda c: (c.token_count, c.candidate_id))
                descending = sorted(candidates, key=lambda c: (-c.token_count, c.candidate_id))
                for ordered_candidates, destination in (
                    (ascending, shortest_blocks),
                    (descending, longest_blocks),
                ):
                    packed = pack_ranked_prefix(
                        head=head,
                        ranked=tuple(
                            RankedCandidate(candidate=candidate, similarity=float(-index))
                            for index, candidate in enumerate(ordered_candidates)
                        ),
                        k=k,
                        target_owner_id=owner_id,
                        token_counter=token_counter,
                    )
                    if packed.envelope.resource_block is not None:
                        destination.append(packed.envelope.rendered_resource_block)
            shortest_combined.append(
                token_counter("\n".join(shortest_blocks)) if shortest_blocks else 0
            )
            longest_combined.append(
                token_counter("\n".join(longest_blocks)) if longest_blocks else 0
            )
        combined_cells.append(
            {
                "symmetric_requested_k_per_head": k,
                "owners": len(owner_ids),
                "exact_combined_shortest_token_order_proxy": _distribution(
                    shortest_combined
                ),
                "exact_combined_longest_token_order_proxy": _distribution(
                    longest_combined
                ),
                "interpretation": (
                    "three-head dynamic-query length proxy only; no static DG ranking, "
                    "effect, or final cap selection"
                ),
            }
        )
    return {
        "status": "DYNAMIC_QUERY_CONTRACT_FROZEN_STATIC_RANKING_INTENTIONALLY_ABSENT",
        "targets": len(dg_targets),
        "interaction_rounds_per_target": 10,
        "query": "exact just-appended current-round seeker utterance",
        "retrieval_schedule": "every supporter generation round",
        "per_head": per_head,
        "all_heads_symmetric_k_capacity_diagnostic": combined_cells,
    }


def main() -> int:
    args = _args()
    assert_pre_outcome_locked(
        load_public_only_config(PROJECT / "configs/paper1_public_only.yaml")
    )
    if sha256_file(args.tokenizer_json) != LLAMA_TOKENIZER_JSON_SHA256:
        raise RuntimeError("Generator tokenizer hash mismatch")
    census = read_json(args.candidate_census_summary)
    if census["status"] != "ZERO_OUTCOME_MULTI_VIEW_CANDIDATE_CENSUS_COMPLETE":
        raise RuntimeError("active Multi-View candidate census is not complete")
    if sha256_file(args.session_results) != census["source"]["promoted_session_results_sha256"]:
        raise RuntimeError("promoted 401-session result hash mismatch")

    users = load_sanitized_runtime_users(args.source)
    targets = enumerate_targets(users)
    static_targets = tuple(target for target in targets if target.task_type in STATIC_TASKS)
    dg_targets = tuple(
        target for target in targets if target.task_type is TaskType.DIALOGUE_GENERATION
    )
    if any(not target.visible_query_text for target in static_targets):
        raise RuntimeError("a static QA/Summary target lacks its official visible query")
    if any(target.visible_query_text is not None for target in dg_targets):
        raise RuntimeError("a DG target unexpectedly exposes a static query")

    token_counter = build_llama_token_counter(args.tokenizer_json)
    units = load_accepted_multi_view_units(args.session_results, users=users)
    bundles = _build_bundles(
        users=users,
        targets=targets,
        units=units,
        token_counter=token_counter,
    )
    encoder = BgeM3Encoder()
    cache = EmbeddingSuccessCache(args.cache_dir)
    candidate_vectors, query_vectors, materialization = _materialize_vectors(
        bundles=bundles,
        static_targets=static_targets,
        encoder=encoder,
        cache=cache,
    )
    top8_rows, ranked = _rank_static_targets(
        static_targets=static_targets,
        bundles=bundles,
        candidate_vectors=candidate_vectors,
        query_vectors=query_vectors,
    )

    out_dir = args.out_dir
    top8_path = out_dir / "es_memeval_public_active_multi_view_bge_top8_v1.jsonl"
    write_jsonl(top8_path, top8_rows)
    surface = {
        "protocol": "paper1-active-multi-view-resource-amount-surface-v1",
        "status": "ZERO_OUTCOME_SURFACE_READY_NOT_A_K_OR_FINAL_CAP_FREEZE",
        "source_identity": {
            "sanitized_runtime_sha256": sha256_file(args.source),
            "candidate_census_summary_sha256": sha256_file(args.candidate_census_summary),
            "promoted_session_results_sha256": sha256_file(args.session_results),
            "top8_filename": top8_path.name,
            "top8_sha256": sha256_file(top8_path),
        },
        "population": {
            "owners": len(users),
            "targets": len(targets),
            "targets_by_task": dict(sorted(Counter(t.task_type.value for t in targets).items())),
            "eligible_candidates_by_head": {
                head.value: sum(len(owner[head]) for owner in bundles.values()) for head in HEADS
            },
        },
        "retrieval": {
            "backend": "pinned local BGE-M3 dense cosine",
            "top_depth_materialized": TOP_DEPTH,
            "sort": "descending cosine; exact tie by candidate_id",
            "QA_and_Summary_query": "exact officially-visible question text",
            "DG_query": "exact just-appended current-round seeker utterance; no static proxy",
            "materialization": materialization,
        },
        "packing": {
            "protocol": PACKING_PROTOCOL,
            "step2_protocol": STEP2_RESOURCE_PROTOCOL,
            "initial_calibration_grid": list(INITIAL_K),
            "k_zero_is_true_OFF": True,
            "selection": "exact ranked prefix",
            "overflow": "fail closed before generation; never truncate, drop, rerank, or backfill",
            "diagnostic_caps_not_selected_caps": list(DIAGNOSTIC_CAPS),
            "final_k_selected": False,
            "final_resource_token_cap_selected": False,
        },
        "task_surfaces": {
            TaskType.QA.value: _static_surface(
                task=TaskType.QA,
                targets=static_targets,
                ranked_by_target_head=ranked,
                token_counter=token_counter,
            ),
            TaskType.SUMMARY.value: _static_surface(
                task=TaskType.SUMMARY,
                targets=static_targets,
                ranked_by_target_head=ranked,
                token_counter=token_counter,
            ),
            TaskType.DIALOGUE_GENERATION.value: _dg_capacity_surface(
                dg_targets=dg_targets,
                bundles=bundles,
                token_counter=token_counter,
            ),
        },
        "tokenizer": {
            "repo_id": LLAMA_TOKENIZER_REPO,
            "revision": LLAMA_TOKENIZER_REVISION,
            "tokenizer_json_sha256": LLAMA_TOKENIZER_JSON_SHA256,
            "surface": "exact rendered PAPER1_RESOURCE block; no task base prompt/chat template",
        },
        "method_boundary": {
            "formal_outcome_calls": 0,
            "paid_api_calls": 0,
            "pm_training_runs": 0,
            "calibration_outcome_lock": "CLOSED",
            "confirmatory_outcome_lock": "CLOSED",
            "task_generator_prompt_injection_point_frozen": False,
            "surface_cells_are_descriptive_not_empirical_pass_gates": True,
        },
    }
    surface_path = out_dir / "es_memeval_public_active_multi_view_resource_amount_surface_v1.json"
    write_json(surface_path, surface)
    report = {
        "protocol": "paper1-active-multi-view-bge-amount-build-report-v1",
        "status": surface["status"],
        "top8_rows": len(top8_rows),
        "top8_sha256": sha256_file(top8_path),
        "surface_sha256": sha256_file(surface_path),
        "bge_binding_identity_sha256": encoder.binding.identity_sha256,
        "bge_runtime_identity_sha256": encoder.runtime_identity.identity_sha256,
        "formal_outcome_calls": 0,
        "paid_api_calls": 0,
        "pm_training_runs": 0,
    }
    report_path = out_dir / "es_memeval_public_active_multi_view_bge_amount_build_report_v1.json"
    write_json(report_path, report)
    print(
        {
            "top8_rows": len(top8_rows),
            "surface": str(surface_path),
            "materialization": materialization,
            "locks": "CLOSED",
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
