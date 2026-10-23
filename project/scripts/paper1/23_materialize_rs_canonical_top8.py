#!/usr/bin/env python3
"""Materialize direct canonical-ticket BGE Top-8 without any outcome call.

The script reuses hash-bound vectors from the completed RS embedding cache.
It does not load BGE-M3, call a Generator/evaluator, or read an outcome.  A
local CUDA matrix multiply may be used only to rank already-frozen vectors.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.paper1.embeddings.cache import EmbeddingCallIdentity, EmbeddingSuccessCache  # noqa: E402
from metacom_pm.paper1.llama_tokenizer import build_llama_token_counter  # noqa: E402
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config  # noqa: E402
from metacom_pm.paper1.rs.strategy_bank import build_strategy_source_catalog  # noqa: E402
from metacom_pm.paper1.rs.zero_outcome_census import build_rs_decision_states  # noqa: E402
from metacom_pm.paper1.rs_atomic_move.canonical_topk import (  # noqa: E402
    build_dialogue_exclusion_index,
    select_top_indices,
)
from metacom_pm.paper1.rs_atomic_move.canonicalization import canonicalize_exact_treatments  # noqa: E402
from metacom_pm.paper1.rs_atomic_move.catalog import load_atomic_move_retrieval_documents  # noqa: E402
from metacom_pm.paper1.rs_atomic_move.contracts import AcceptedAtomicMoveUnit  # noqa: E402

PROTOCOL = "pm-paper1-rs-canonical-bge-top8-zero-outcome-v1"
ROW_PROTOCOL = "pm-paper1-rs-canonical-bge-top8-row-v1"
K_REPORT = (1, 2, 3, 4, 6, 8)
TOP_K = 8
INTERNAL_TOP_K = 9
CAP = 384
DOCUMENT_FIELD = "rs.document_text"
QUERY_FIELD = "rs.query_text"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _distribution(values: list[float | int]) -> dict[str, float | int]:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("empty distribution")
    at = lambda q: ordered[round((len(ordered) - 1) * q)]
    return {
        "min": ordered[0],
        "p25": at(0.25),
        "median": at(0.5),
        "p75": at(0.75),
        "p90": at(0.9),
        "p95": at(0.95),
        "max": ordered[-1],
        "mean": statistics.fmean(values),
    }


def _load_units(path: Path) -> dict[str, AcceptedAtomicMoveUnit]:
    units: dict[str, AcceptedAtomicMoveUnit] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            for raw in json.loads(line).get("accepted_units") or ():
                unit = AcceptedAtomicMoveUnit.model_validate(raw)
                if unit.card_id in units:
                    raise RuntimeError(f"duplicate unit {unit.card_id}")
                units[unit.card_id] = unit
    return units


def _cache_vector(
    cache: EmbeddingSuccessCache,
    *,
    binding_sha: str,
    runtime_sha: str,
    field: str,
    text: str,
) -> tuple[float, ...]:
    identity = EmbeddingCallIdentity(
        binding_identity_sha256=binding_sha,
        runtime_identity_sha256=runtime_sha,
        field_source=field,
        text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )
    vector = cache.load(identity)
    if vector is None:
        raise RuntimeError(f"required frozen embedding cache miss: {identity.cache_key}")
    return vector


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> str:
    rendered = "".join(_canonical(row) + "\n" for row in rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-results", type=Path, required=True)
    parser.add_argument("--embedding-cache", type=Path, required=True)
    parser.add_argument("--old-census-summary", type=Path, required=True)
    parser.add_argument("--old-census", type=Path, required=True)
    parser.add_argument("--tokenizer-json", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=PROJECT / "data/paper1_public_rs")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--compute-backend", choices=("auto", "cpu", "cuda"), default="auto")
    args = parser.parse_args()

    config = load_public_only_config(PROJECT / "configs/paper1_public_only.yaml")
    assert_pre_outcome_locked(config)
    old_summary = json.loads(args.old_census_summary.read_text(encoding="utf-8"))
    if _sha_file(args.old_census) != old_summary["artifacts"]["census_sha256"]:
        raise RuntimeError("old census hash mismatch")
    if _sha_file(args.session_results) != old_summary["source"]["session_results_sha256"]:
        raise RuntimeError("session-results hash mismatch")
    binding_sha = old_summary["bge_materialization"]["documents"]["binding_identity_sha256"]
    runtime_sha = old_summary["bge_materialization"]["documents"]["runtime_identity_sha256"]
    if runtime_sha != old_summary["bge_materialization"]["queries"]["runtime_identity_sha256"]:
        raise RuntimeError("document/query runtime identities differ")

    esconv = PROJECT / "data/external/ESConv.json"
    split_manifest = PROJECT / "data/strategy/esconv_split_manifest_v1_5.jsonl"
    cards = build_strategy_source_catalog(esconv_path=esconv, split_manifest_path=split_manifest)
    cards_by_id = {card.card_id: card for card in cards}
    documents = load_atomic_move_retrieval_documents(args.session_results, cards_by_id=cards_by_id)
    documents_by_id = {doc.atomic_card_id: doc for doc in documents}
    units = _load_units(args.session_results)
    aliases = canonicalize_exact_treatments(documents, units_by_id=units)
    if len(documents) != 15061 or len(aliases) != 13172:
        raise RuntimeError(f"unexpected RS counts documents={len(documents)} aliases={len(aliases)}")
    states = build_rs_decision_states(
        esconv_path=esconv,
        split_manifest_path=split_manifest,
        source_splits=("train", "validation"),
        exclude_evoemo_overlap=True,
        query_preceding_turns=6,
    )
    if len(states) != 11883:
        raise RuntimeError(f"unexpected RS decision-state count {len(states)}")

    token_counter = build_llama_token_counter(args.tokenizer_json)
    cache = EmbeddingSuccessCache(args.embedding_cache)
    treatment_ids = tuple(alias.treatment_id for alias in aliases)
    representative_docs = tuple(
        documents_by_id[alias.representative_atomic_card_id] for alias in aliases
    )
    document_vectors = np.asarray(
        [
            _cache_vector(
                cache,
                binding_sha=binding_sha,
                runtime_sha=runtime_sha,
                field=DOCUMENT_FIELD,
                text=doc.text,
            )
            for doc in representative_docs
        ],
        dtype=np.float32,
    )
    query_vectors = np.asarray(
        [
            _cache_vector(
                cache,
                binding_sha=binding_sha,
                runtime_sha=runtime_sha,
                field=QUERY_FIELD,
                text=state.query_text,
            )
            for state in states
        ],
        dtype=np.float32,
    )
    if document_vectors.shape != (13172, 1024) or query_vectors.shape != (11883, 1024):
        raise RuntimeError("cached vector matrix shape mismatch")

    exclusions = build_dialogue_exclusion_index(aliases)
    use_cuda = False
    torch = None
    if args.compute_backend != "cpu":
        try:
            import torch as imported_torch

            torch = imported_torch
            use_cuda = bool(torch.cuda.is_available())
        except ImportError:
            use_cuda = False
    if args.compute_backend == "cuda" and not use_cuda:
        raise RuntimeError("--compute-backend=cuda requested but CUDA is unavailable")
    if args.compute_backend == "cpu":
        use_cuda = False

    alias_tokens = [token_counter(alias.rendered_card_text) for alias in aliases]
    alias_families = [set(alias.atomic_move_families) for alias in aliases]
    alias_source_cards = [set(alias.source_card_ids) for alias in aliases]
    treatment_index = {treatment_id: index for index, treatment_id in enumerate(treatment_ids)}
    rows: list[dict[str, Any]] = []
    start = time.perf_counter()
    document_tensor = None
    if use_cuda and torch is not None:
        document_tensor = torch.from_numpy(document_vectors).to("cuda")

    for batch_start in range(0, len(states), args.batch_size):
        batch_end = min(batch_start + args.batch_size, len(states))
        if use_cuda and torch is not None and document_tensor is not None:
            query_tensor = torch.from_numpy(query_vectors[batch_start:batch_end]).to("cuda")
            batch_scores = (query_tensor @ document_tensor.T).cpu().numpy()
        else:
            batch_scores = query_vectors[batch_start:batch_end] @ document_vectors.T
        for offset, state in enumerate(states[batch_start:batch_end]):
            scores = batch_scores[offset]
            mask = np.ones(len(aliases), dtype=bool)
            excluded = exclusions.get(state.source_dialogue_id, ())
            if excluded:
                mask[list(excluded)] = False
            selected = select_top_indices(
                scores,
                treatment_ids=treatment_ids,
                eligible_mask=mask,
                top_k=INTERNAL_TOP_K,
            )
            top8 = selected[:TOP_K]
            rows.append(
                {
                    "protocol": ROW_PROTOCOL,
                    "state_id": state.state_id,
                    "source_dialogue_id": state.source_dialogue_id,
                    "source_split": state.source_split,
                    "decision_turn_index": state.decision_turn_index,
                    "query_sha256": hashlib.sha256(state.query_text.encode("utf-8")).hexdigest(),
                    "eligible_canonical_treatment_count": int(mask.sum()),
                    "ranked_treatments": [
                        {
                            "rank": rank,
                            "treatment_id": treatment_ids[index],
                            "cosine_similarity": float(scores[index]),
                            "injected_tokens": alias_tokens[index],
                            "families": sorted(alias_families[index]),
                            "representative_atomic_card_id": aliases[index].representative_atomic_card_id,
                            "representative_source_card_id": aliases[index].representative_source_card_id,
                        }
                        for rank, index in enumerate(top8, start=1)
                    ],
                    "rank9_similarity_for_boundary_audit": float(scores[selected[8]]),
                }
            )

    elapsed = time.perf_counter() - start
    alias_path = args.out_dir / "esconv_rs_exact_canonical_treatments_v1.jsonl"
    ranking_path = args.out_dir / "esconv_rs_canonical_bge_top8_v1.jsonl"
    report_path = args.out_dir / "esconv_rs_canonical_bge_top8_report_v1.json"
    alias_sha = _write_jsonl(alias_path, [alias.model_dump(mode="json") for alias in aliases])
    ranking_sha = _write_jsonl(ranking_path, rows)

    old_rows = []
    with args.old_census.open("r", encoding="utf-8") as handle:
        old_rows = [json.loads(line) for line in handle if line.strip()]
    atomic_to_treatment = {
        atomic_id: alias.treatment_id for alias in aliases for atomic_id in alias.atomic_card_ids
    }
    old_underfill = {str(k): 0 for k in (1, 2, 3, 4)}
    old_missing_slots = {str(k): 0 for k in (1, 2, 3, 4)}
    for old in old_rows:
        seen: set[str] = set()
        delivered: list[str] = []
        for atomic_id in old["diagnostic_candidate_ids"]:
            treatment_id = atomic_to_treatment[atomic_id]
            if treatment_id not in seen:
                seen.add(treatment_id)
                delivered.append(treatment_id)
        for k in (1, 2, 3, 4):
            got = min(k, len(delivered))
            old_underfill[str(k)] += int(got < k)
            old_missing_slots[str(k)] += k - got

    k_stats: dict[str, Any] = {}
    for k in K_REPORT:
        token_totals = [sum(item["injected_tokens"] for item in row["ranked_treatments"][:k]) for row in rows]
        family_counts = [
            len({family for item in row["ranked_treatments"][:k] for family in item["families"]})
            for row in rows
        ]
        same_source = 0
        margins = []
        for row in rows:
            chosen = row["ranked_treatments"][:k]
            cards_for_treatments = [
                alias_source_cards[treatment_index[item["treatment_id"]]] for item in chosen
            ]
            if any(
                cards_for_treatments[i] & cards_for_treatments[j]
                for i in range(len(cards_for_treatments))
                for j in range(i + 1, len(cards_for_treatments))
            ):
                same_source += 1
            next_similarity = (
                row["ranked_treatments"][k]["cosine_similarity"]
                if k < TOP_K
                else row["rank9_similarity_for_boundary_audit"]
            )
            margins.append(chosen[-1]["cosine_similarity"] - next_similarity)
        k_stats[str(k)] = {
            "states": len(rows),
            "states_with_full_k": len(rows),
            "coverage": 1.0,
            "rank1_similarity": _distribution([row["ranked_treatments"][0]["cosine_similarity"] for row in rows]),
            "rank_k_similarity": _distribution([row["ranked_treatments"][k - 1]["cosine_similarity"] for row in rows]),
            "k_vs_next_margin": _distribution(margins),
            "injected_tokens": _distribution(token_totals),
            "truncated_by_common_cap384": sum(total > CAP for total in token_totals),
            "truncation_rate_common_cap384": sum(total > CAP for total in token_totals) / len(rows),
            "distinct_family_count": _distribution(family_counts),
            "states_with_same_source_card_among_selected": same_source,
            "same_source_card_fraction": same_source / len(rows),
        }

    report = {
        "protocol": PROTOCOL,
        "status": "READY",
        "scope": "ZERO_OUTCOME_CANONICAL_RETRIEVAL_MATERIALIZATION_ONLY",
        "counts": {
            "raw_atomic_units": len(documents),
            "exact_canonical_treatments": len(aliases),
            "exact_alias_instances_beyond_first": len(documents) - len(aliases),
            "decision_states": len(states),
        },
        "mechanical_rule": {
            "identity": "sha256(byte_exact_rendered_card_text)",
            "representative": "lexicographically_minimum(source_card_id,atomic_card_id)",
            "full_provenance_union": True,
            "occurrence_prior": False,
            "near_duplicate_deletion": False,
            "leave_dialogue_out_on_union": True,
            "ranking": "direct_BGE_cosine_over_13172_representative_documents",
            "tie_break": "descending_similarity_then_treatment_id",
        },
        "k_surface": k_stats,
        "alias_and_backfill": {
            "old_raw_top4_postcollapse_states_underfilled": old_underfill,
            "old_raw_top4_postcollapse_missing_slots": old_missing_slots,
            "direct_canonical_top8_states_underfilled": 0,
            "top6_top8_not_derived_from_old_top4": True,
        },
        "identities": {
            "esconv_sha256": _sha_file(esconv),
            "split_manifest_sha256": _sha_file(split_manifest),
            "session_results_sha256": _sha_file(args.session_results),
            "old_census_sha256": _sha_file(args.old_census),
            "bge_binding_identity_sha256": binding_sha,
            "bge_runtime_identity_sha256": runtime_sha,
            "embedding_cache_role": "read_only_hash_bound_success_cache",
            "tokenizer_json_sha256": _sha_file(args.tokenizer_json),
            "script_sha256": _sha_file(Path(__file__)),
            "canonical_catalog_sha256": alias_sha,
            "canonical_top8_sha256": ranking_sha,
        },
        "compute": {
            "backend": "cuda_cached_vector_matrix_multiply" if use_cuda else "cpu_cached_vector_matrix_multiply",
            "batch_size": args.batch_size,
            "elapsed_seconds": elapsed,
            "BGE_model_calls": 0,
            "Generator_calls": 0,
            "evaluator_calls": 0,
            "outcome_calls": 0,
        },
        "pure_k_protocol": {
            "initial_k": [0, 1, 2, 3, 4],
            "common_nonbinding_cap": CAP,
            "expansion_k": [6, 8],
            "expansion_rule": "only_if_calibration_best_is_k4_boundary_and_not_plateaued",
        },
        "locks": {
            key: config[key]["status"]
            for key in (
                "RQ1_RS_CALIBRATION_OUTCOME_LOCK",
                "RQ2_MEMORY_CALIBRATION_OUTCOME_LOCK",
                "RQ1_CONFIRMATORY_OUTCOME_LOCK",
                "RQ2_CONFIRMATORY_OUTCOME_LOCK",
            )
        },
        "artifacts": {
            "canonical_catalog": str(alias_path.relative_to(PROJECT)),
            "canonical_top8": str(ranking_path.relative_to(PROJECT)),
        },
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
