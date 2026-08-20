#!/usr/bin/env python3
"""Materialize outcome-blind RS and typed-memory resource-amount surfaces.

This script deliberately consumes the already-materialized BGE census
prefixes.  It never invokes an embedding model, Generator, evaluator, or
outcome endpoint.  RS exact treatment aliases are canonicalized by exact
``rendered_card_text`` hash and retain the union of their source provenance;
near duplicates are only counted, never threshold-deleted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

PROJECT = Path(__file__).resolve().parents[2]
REPO = PROJECT.parent
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.paper1.llama_tokenizer import build_llama_token_counter  # noqa: E402
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config  # noqa: E402
from metacom_pm.paper1.rs.strategy_bank import build_strategy_source_catalog  # noqa: E402
from metacom_pm.paper1.rs_atomic_move.catalog import load_atomic_move_retrieval_documents  # noqa: E402
from metacom_pm.paper1.rs_atomic_move.canonicalization import canonicalize_exact_treatments  # noqa: E402
from metacom_pm.paper1.rs_atomic_move.contracts import AcceptedAtomicMoveUnit  # noqa: E402

RS_K_VALUES = (0, 1, 2, 3, 4)
RS_FIXED_NONBINDING_TOKEN_CAP = 384
MEMORY_K_VALUES = (1, 2, 3, 4)
RS_TOKEN_CAPS = (16, 24, 32, 48, 64, 96, 128)
MEMORY_TOKEN_CAPS = (64, 96, 128, 192, 256, 384, 512)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _percentile(values: list[float | int], fraction: float) -> float | int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * fraction)]


def _distribution(values: Iterable[float | int]) -> dict[str, float | int | None]:
    materialized = list(values)
    if not materialized:
        return {key: None for key in ("min", "p25", "median", "p75", "p90", "p95", "max", "mean")}
    return {
        "min": min(materialized),
        "p25": _percentile(materialized, 0.25),
        "median": _percentile(materialized, 0.50),
        "p75": _percentile(materialized, 0.75),
        "p90": _percentile(materialized, 0.90),
        "p95": _percentile(materialized, 0.95),
        "max": max(materialized),
        "mean": statistics.fmean(materialized),
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_atomic_units(results_path: Path) -> dict[str, AcceptedAtomicMoveUnit]:
    units: dict[str, AcceptedAtomicMoveUnit] = {}
    for row in _read_jsonl(results_path):
        for raw in row.get("accepted_units") or ():
            unit = AcceptedAtomicMoveUnit.model_validate(raw)
            if unit.card_id in units:
                raise RuntimeError(f"duplicate accepted atomic unit: {unit.card_id}")
            units[unit.card_id] = unit
    return units


def build_rs_surface(
    *,
    census_path: Path,
    census_summary_path: Path,
    session_results_path: Path,
    tokenizer_json: Path,
) -> dict[str, Any]:
    summary = json.loads(census_summary_path.read_text(encoding="utf-8"))
    rows = _read_jsonl(census_path)
    if _sha_file(census_path) != summary["artifacts"]["census_sha256"]:
        raise RuntimeError("RS census hash does not match its summary")
    if _sha_file(session_results_path) != summary["source"]["session_results_sha256"]:
        raise RuntimeError("RS session-results hash does not match its census summary")
    if len(rows) != summary["counts"]["decision_states"]:
        raise RuntimeError("RS census row count does not match summary")

    cards = build_strategy_source_catalog(
        esconv_path=PROJECT / "data" / "external" / "ESConv.json",
        split_manifest_path=PROJECT / "data" / "strategy" / "esconv_split_manifest_v1_5.jsonl",
    )
    cards_by_id = {card.card_id: card for card in cards}
    documents = load_atomic_move_retrieval_documents(session_results_path, cards_by_id=cards_by_id)
    units = _load_atomic_units(session_results_path)
    if len(documents) != summary["counts"]["atomic_move_retrieval_documents"]:
        raise RuntimeError("RS retrieval document count does not match census summary")

    token_counter = build_llama_token_counter(tokenizer_json)
    canonical_aliases = canonicalize_exact_treatments(documents, units_by_id=units)
    aliases: dict[str, dict[str, Any]] = {
        alias.treatment_id: {
            "rendered_card_text_sha256": alias.rendered_card_text_sha256,
            "atomic_card_ids": set(alias.atomic_card_ids),
            "source_card_ids": set(alias.source_card_ids),
            "source_dialogue_ids": set(alias.source_dialogue_ids),
            "families": set(alias.atomic_move_families),
            "representative_atomic_card_id": alias.representative_atomic_card_id,
            "representative_source_card_id": alias.representative_source_card_id,
            "representative_retrieval_text_sha256": alias.representative_retrieval_text_sha256,
            "token_count": token_counter(alias.rendered_card_text),
        }
        for alias in canonical_aliases
    }
    atomic_to_alias = {
        atomic_card_id: alias.treatment_id
        for alias in canonical_aliases
        for atomic_card_id in alias.atomic_card_ids
    }

    raw_text_counts = Counter(doc.rendered_card_text for doc in documents)
    exact_duplicate_instances = sum(count - 1 for count in raw_text_counts.values())
    canonical_prefixes: list[dict[str, Any]] = []
    for row in rows:
        selected: list[tuple[str, float]] = []
        seen: set[str] = set()
        alias_collapses = 0
        lineage_drops = 0
        for atomic_id, similarity in zip(
            row["diagnostic_candidate_ids"],
            row["diagnostic_bge_cosine_similarities"],
            strict=True,
        ):
            alias_id = atomic_to_alias[atomic_id]
            if alias_id in seen:
                alias_collapses += 1
                continue
            seen.add(alias_id)
            # Exact-alias provenance is unioned catalog-wide.  Applying
            # leave-dialogue-out to that union is conservative and
            # prevents an alias from laundering current-dialogue lineage.
            if row["source_dialogue_id"] in aliases[alias_id]["source_dialogue_ids"]:
                lineage_drops += 1
                continue
            selected.append((alias_id, float(similarity)))
        canonical_prefixes.append(
            {
                "selected": selected,
                "alias_collapses": alias_collapses,
                "lineage_drops": lineage_drops,
            }
        )

    cells: list[dict[str, Any]] = []
    for k in RS_K_VALUES:
        delivered_counts: list[int] = []
        token_counts: list[int] = []
        distinct_family_counts: list[int] = []
        margins: list[float] = []
        alias_collapses = sum(item["alias_collapses"] for item in canonical_prefixes)
        conservative_lineage_drops = sum(item["lineage_drops"] for item in canonical_prefixes)
        states_with_shared_source_card = 0
        states_with_full_k = 0
        boundary_margins: list[float] = []
        for prefix in canonical_prefixes:
            available = prefix["selected"]
            selected = available[:k]

            delivered_counts.append(len(selected))
            if len(selected) == k:
                states_with_full_k += 1
            token_counts.append(sum(aliases[alias_id]["token_count"] for alias_id, _ in selected))
            distinct_family_counts.append(
                len(set().union(*(aliases[alias_id]["families"] for alias_id, _ in selected)))
                if selected
                else 0
            )
            provenance_sets = [aliases[alias_id]["source_card_ids"] for alias_id, _ in selected]
            if any(
                provenance_sets[i] & provenance_sets[j]
                for i in range(len(provenance_sets))
                for j in range(i + 1, len(provenance_sets))
            ):
                states_with_shared_source_card += 1
            if len(selected) >= 2:
                margins.append(selected[0][1] - selected[1][1])
            if k > 0 and len(available) > k:
                boundary_margins.append(available[k - 1][1] - available[k][1])

        cells.append(
            {
                "requested_k": k,
                "observed_rank_prefix": k,
                "states": len(rows),
                "states_with_full_k_after_exact_alias_and_lineage_rules": states_with_full_k,
                "full_k_fraction": states_with_full_k / len(rows),
                "delivered_canonical_treatments": _distribution(delivered_counts),
                "generator_input_tokens": _distribution(token_counts),
                "distinct_family_count": _distribution(distinct_family_counts),
                "top1_minus_top2_similarity_margin": _distribution(margins),
                "k_boundary_similarity_margin": _distribution(boundary_margins),
                "exact_alias_collapses_in_available_top4_prefix": alias_collapses,
                "conservative_union_lineage_drops_in_available_top4_prefix": conservative_lineage_drops,
                "states_with_selected_treatments_sharing_a_source_card": states_with_shared_source_card,
                "states_with_selected_treatments_sharing_a_source_card_fraction": (
                    states_with_shared_source_card / len(rows)
                ),
                "token_cap_fit": {
                    str(cap): {
                        "states": sum(total <= cap for total in token_counts),
                        "fraction": sum(total <= cap for total in token_counts) / len(rows),
                    }
                    for cap in RS_TOKEN_CAPS
                },
            }
        )

    return {
        "protocol": "pm-paper1-rs-resource-amount-surface-v1",
        "status": "ZERO_OUTCOME_AMOUNT_SURFACE_NOT_A_K_FREEZE",
        "outcome_calls": 0,
        "calibration_outcome_lock": "CLOSED",
        "confirmatory_outcome_lock": "CLOSED",
        "source_identity": {
            "census_path": census_path.relative_to(PROJECT).as_posix(),
            "census_sha256": _sha_file(census_path),
            "census_summary_sha256": _sha_file(census_summary_path),
            "session_results_filename": session_results_path.name,
            "session_results_sha256": _sha_file(session_results_path),
            "bge_binding_identity_sha256": summary["bge_materialization"]["documents"][
                "binding_identity_sha256"
            ],
            "bge_runtime_identity_sha256": summary["bge_materialization"]["documents"][
                "runtime_identity_sha256"
            ],
            "tokenizer_json_sha256": _sha_file(tokenizer_json),
        },
        "catalog": {
            "raw_atomic_move_units": len(documents),
            "exact_canonical_treatments": len(aliases),
            "exact_duplicate_instances": exact_duplicate_instances,
            "exact_duplicate_fraction_of_raw_units": exact_duplicate_instances / len(documents),
            "canonicalization": (
                "exact rendered_card_text SHA-256 only; treatment identity retains union of "
                "atomic_card_ids/source_card_ids/source_dialogue_ids/families"
            ),
            "representative_rule": (
                "one BGE ranking ticket per exact treatment; representative retrieval document "
                "is the lexicographically smallest (source_card_id, atomic_card_id); duplicate "
                "occurrences never contribute max/mean score pooling or a frequency prior"
            ),
            "near_duplicate_policy": "REPORT_ONLY_NO_SEMANTIC_THRESHOLD_DELETION",
        },
        "ranking": {
            "backend": "existing real BGE-M3 census ranking",
            "leave_dialogue_out": True,
            "available_prefix_depth": max(RS_K_VALUES),
            "surface_k_values": list(RS_K_VALUES),
            "limitation": (
                "Exact aliases are collapsed inside the already-materialized top-4 prefix; "
                "this audit does not backfill a collapsed slot from rank >4. A formal "
                "canonical-catalog retriever must be materialized before calibration calls."
            ),
        },
        "cells": cells,
        "pure_k_calibration_protocol": {
            "status": "PRE_REGISTERED_PROTOCOL_CALIBRATION_LOCK_REMAINS_CLOSED",
            "initial_k_values": [0, 1, 2, 3, 4],
            "fixed_nonbinding_generator_input_token_cap": RS_FIXED_NONBINDING_TOKEN_CAP,
            "zero_outcome_truncation": {
                str(cell["requested_k"]): {
                    "states_truncated": 0,
                    "fraction": 0.0,
                    "observed_max_injected_tokens": cell["generator_input_tokens"]["max"],
                }
                for cell in cells
            },
            "actual_injected_tokens": "record the realized tokenizer count separately per trajectory",
            "expansion_rule": (
                "Expand once to k={6,8} only if k=4 has the highest calibration mean and "
                "k=3 is outside the one-standard-error admissible set relative to k=4. "
                "Before expanded calls, materialize canonical top-8 and re-audit one fixed "
                "nonbinding cap shared by every k; do not inspect confirmatory outcomes."
            ),
            "reason": (
                "all initial arms vary k only; k=0 preserves the no-injection control, and "
                "the shared cap is deliberately nonbinding rather than a second treatment axis"
            ),
            "step2_utility_filter": "FORBIDDEN",
        },
    }


def _ranked_candidates(row: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = row["candidates"]
    if not row["has_visible_query"]:
        return []
    if any(candidate["bge_retrieval_rank"] is None for candidate in candidates):
        raise RuntimeError("visible-query memory row is missing a BGE retrieval rank")
    return sorted(candidates, key=lambda c: (c["bge_retrieval_rank"], c["candidate_id"]))


def _memory_head_cell(rows: list[dict[str, Any]], k: int) -> dict[str, Any]:
    delivered: list[int] = []
    tokens: list[int] = []
    kth_similarities: list[float] = []
    for row in rows:
        ranked = _ranked_candidates(row)
        selected = ranked[:k]
        delivered.append(len(selected))
        tokens.append(sum(candidate["token_count"] for candidate in selected))
        if len(selected) == k:
            kth_similarities.append(float(selected[-1]["bge_cosine_similarity"]))
    return {
        "requested_k": k,
        "targets": len(rows),
        "targets_with_full_k": sum(value == k for value in delivered),
        "full_k_fraction": sum(value == k for value in delivered) / len(rows),
        "delivered_units": _distribution(delivered),
        "generator_input_tokens": _distribution(tokens),
        "kth_candidate_bge_cosine_similarity": _distribution(kth_similarities),
        "token_cap_fit": {
            str(cap): {
                "targets": sum(total <= cap for total in tokens),
                "fraction": sum(total <= cap for total in tokens) / len(rows),
            }
            for cap in MEMORY_TOKEN_CAPS
        },
    }


def build_memory_surface(*, census_path: Path, census_summary_path: Path) -> dict[str, Any]:
    summary = json.loads(census_summary_path.read_text(encoding="utf-8"))
    rows = _read_jsonl(census_path)
    if _sha_file(census_path) != summary["manifest_sha256"]:
        raise RuntimeError("memory census hash does not match summary")
    if len(rows) != summary["manifest_rows"]:
        raise RuntimeError("memory census row count does not match summary")

    by_task_head: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    by_target: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in rows:
        by_task_head[(row["task_type"], row["head"])].append(row)
        by_target[(row["task_type"], row["target_id"])][row["head"]] = row

    task_surfaces: dict[str, Any] = {}
    for task in ("qa", "summary"):
        per_head = {
            head: [_memory_head_cell(by_task_head[(task, head)], k) for k in MEMORY_K_VALUES]
            for head in ("MP", "MS", "ME")
        }
        bundles: list[dict[str, Any]] = []
        targets = [item for (task_name, _), item in by_target.items() if task_name == task]
        for k in MEMORY_K_VALUES:
            token_totals: list[int] = []
            delivered_totals: list[int] = []
            all_heads_full = 0
            for head_rows in targets:
                selected_by_head = {
                    head: _ranked_candidates(head_rows[head])[:k] for head in ("MP", "MS", "ME")
                }
                delivered_totals.append(sum(len(value) for value in selected_by_head.values()))
                token_totals.append(
                    sum(candidate["token_count"] for value in selected_by_head.values() for candidate in value)
                )
                if all(len(selected_by_head[head]) == k for head in ("MP", "MS", "ME")):
                    all_heads_full += 1
            bundles.append(
                {
                    "symmetric_k_per_head": k,
                    "targets": len(targets),
                    "targets_with_all_three_heads_full_k": all_heads_full,
                    "all_three_heads_full_k_fraction": all_heads_full / len(targets),
                    "delivered_typed_units": _distribution(delivered_totals),
                    "generator_input_tokens": _distribution(token_totals),
                    "token_cap_fit": {
                        str(cap): {
                            "targets": sum(total <= cap for total in token_totals),
                            "fraction": sum(total <= cap for total in token_totals) / len(targets),
                        }
                        for cap in MEMORY_TOKEN_CAPS
                    },
                }
            )
        task_surfaces[task] = {
            "status": "STATIC_VISIBLE_QUERY_BGE_SURFACE_READY_NOT_FROZEN",
            "targets": len(targets),
            "per_head": per_head,
            "typed_bundle_surface": bundles,
        }

    dg_head_availability: dict[str, Any] = {}
    for head in ("MP", "MS", "ME"):
        head_rows = by_task_head[("dialogue_generation", head)]
        cells = []
        for k in MEMORY_K_VALUES:
            lower_bounds: list[int] = []
            upper_bounds: list[int] = []
            delivered: list[int] = []
            for row in head_rows:
                token_counts = sorted(candidate["token_count"] for candidate in row["candidates"])
                take = min(k, len(token_counts))
                delivered.append(take)
                lower_bounds.append(sum(token_counts[:take]))
                upper_bounds.append(sum(token_counts[-take:]) if take else 0)
            cells.append(
                {
                    "requested_k": k,
                    "targets": len(head_rows),
                    "full_k_fraction": sum(value == k for value in delivered) / len(head_rows),
                    "delivered_units": _distribution(delivered),
                    "unranked_token_lower_bound": _distribution(lower_bounds),
                    "unranked_token_upper_bound": _distribution(upper_bounds),
                }
            )
        dg_head_availability[head] = cells
    task_surfaces["dialogue_generation"] = {
        "status": "IMPLEMENTATION_BLOCKER_RESEARCHER_DECISION_REQUIRED_DYNAMIC_QUERY_NOT_FROZEN",
        "targets": summary["targets_by_task"]["dialogue_generation"],
        "official_harness_requirement": (
            "audit the official 10-round DG harness and mechanically freeze the exact dynamic "
            "query window, turn timing, and re-retrieval schedule before any calibration outcome"
        ),
        "selection_surface": None,
        "outcome_blind_unranked_availability_and_token_envelope": dg_head_availability,
    }

    current_counts = {
        head: {
            "unique_candidates": summary["per_head"][head]["unique_candidate_count"],
            "owners_with_any_candidate": summary["per_head"][head]["owners_with_any_candidate"],
            "targets_total": summary["per_head"][head]["targets_total"],
            "targets_with_coverage": summary["per_head"][head]["targets_with_coverage"],
            "coverage_fraction": summary["per_head"][head]["coverage_fraction"],
        }
        for head in ("MP", "MS", "ME")
    }
    return {
        "protocol": "pm-paper1-typed-memory-resource-amount-surface-v1",
        "status": "ZERO_OUTCOME_TASK_LEVEL_SURFACES_NOT_A_BUNDLE_FREEZE",
        "outcome_calls": 0,
        "calibration_outcome_lock": "CLOSED",
        "confirmatory_outcome_lock": "CLOSED",
        "source_identity": {
            "census_path": census_path.relative_to(PROJECT).as_posix(),
            "census_sha256": _sha_file(census_path),
            "census_summary_sha256": _sha_file(census_summary_path),
            "semantic_compiler_source": summary["semantic_compiler_source"],
            "token_counter": summary["token_counter"],
        },
        "current_local_counts": current_counts,
        "old_remote_artifact_check": {
            "old_counts": {"MP": 3, "MS": 401, "ME": 3},
            "matches_current_local": False,
            "instruction": "do not cite the old remote counts as current local evidence",
        },
        "sparsity_interpretation": {
            "MP": "not the old 3-unit artifact, but owner-level pool size is uneven; wide ordinary top-k is not assumed",
            "MS": "supports the broadest amount surface",
            "ME": "80 unique units total and owner mean 4.44; k>4 loses full-k coverage and no synthetic rescue is allowed",
            "synthetic_rescue": "FORBIDDEN",
        },
        "surface_k_values": list(MEMORY_K_VALUES),
        "token_caps": list(MEMORY_TOKEN_CAPS),
        "task_surfaces": task_surfaces,
        "selection_rule": (
            "task-specific official primary anchor, quality-first one-standard-error, then minimum "
            "Generator input-token cost; never a QA/Summary/DG composite"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rs-session-results", type=Path, required=True)
    parser.add_argument("--llama-tokenizer-json", type=Path, required=True)
    parser.add_argument(
        "--rs-census",
        type=Path,
        default=PROJECT / "data" / "paper1_public_rs" / "esconv_rs_atomic_move_zero_outcome_census_v1.jsonl",
    )
    parser.add_argument(
        "--rs-census-summary",
        type=Path,
        default=PROJECT / "data" / "paper1_public_rs" / "esconv_rs_atomic_move_zero_outcome_census_summary_v1.json",
    )
    parser.add_argument(
        "--memory-census",
        type=Path,
        default=PROJECT / "data" / "paper1_public_memory" / "es_memeval_public_candidate_census_v1.jsonl",
    )
    parser.add_argument(
        "--memory-census-summary",
        type=Path,
        default=PROJECT / "data" / "paper1_public_memory" / "es_memeval_public_candidate_census_summary_v1.json",
    )
    parser.add_argument(
        "--rs-out",
        type=Path,
        default=PROJECT / "data" / "paper1_public_rs" / "esconv_rs_resource_amount_surface_20260820_v1.json",
    )
    parser.add_argument(
        "--memory-out",
        type=Path,
        default=PROJECT / "data" / "paper1_public_memory" / "es_memeval_typed_memory_resource_amount_surface_20260820_v1.json",
    )
    args = parser.parse_args()

    config = load_public_only_config(PROJECT / "configs" / "paper1_public_only.yaml")
    assert_pre_outcome_locked(config)
    rs_surface = build_rs_surface(
        census_path=args.rs_census,
        census_summary_path=args.rs_census_summary,
        session_results_path=args.rs_session_results,
        tokenizer_json=args.llama_tokenizer_json,
    )
    memory_surface = build_memory_surface(
        census_path=args.memory_census,
        census_summary_path=args.memory_census_summary,
    )
    _write_json(args.rs_out, rs_surface)
    _write_json(args.memory_out, memory_surface)
    print(
        json.dumps(
            {
                "rs_out": args.rs_out.relative_to(REPO).as_posix(),
                "memory_out": args.memory_out.relative_to(REPO).as_posix(),
                "outcome_calls": 0,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
