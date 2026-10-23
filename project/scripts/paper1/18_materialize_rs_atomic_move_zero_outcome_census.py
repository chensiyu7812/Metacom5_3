#!/usr/bin/env python3
"""Materialize the RS zero-outcome census over the real atomic-move catalog.

Supersedes ``06_materialize_esconv_rs_zero_outcome_census.py`` as the
authoritative RS retrieval diagnostic: that script still ranks the
pre-atomic-move ``StrategySourceCard`` catalog (12169 source turns) with a
token-Jaccard index, never updated after the real atomic-move compile
produced the actually-approved catalog granularity (RS M2 freeze decision
10: one entry per accepted unit). This script ranks the real
``AtomicMoveRetrievalDocument`` catalog with real BGE-M3 cosine similarity,
materialized on local GPU hardware, with leave-dialogue-out exclusion over
each unit's full ``source_dialogue_ids`` lineage.

06's output is left untouched -- both artifacts exist side by side, with
this one's summary explicitly noting which it supersedes and why.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from statistics import median, pvariance
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.paper1.embeddings import (  # noqa: E402
    BgeM3Encoder,
    EmbeddingSuccessCache,
    build_materialization_report,
    materialize_embeddings,
)
from metacom_pm.paper1.llama_tokenizer import build_llama_token_counter  # noqa: E402
from metacom_pm.paper1.rs.strategy_bank import build_strategy_source_catalog  # noqa: E402
from metacom_pm.paper1.rs.zero_outcome_census import build_rs_decision_states  # noqa: E402
from metacom_pm.paper1.rs_atomic_move.catalog import load_atomic_move_retrieval_documents  # noqa: E402
from metacom_pm.paper1.rs_atomic_move.zero_outcome_census import (  # noqa: E402
    build_rs_atomic_move_zero_outcome_census,
)

RS_DOCUMENT_FIELD_SOURCE = "rs.document_text"
RS_QUERY_FIELD_SOURCE = "rs.query_text"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = "".join(_canonical(row) + "\n" for row in rows)
    path.write_text(rendered, encoding="utf-8")
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _distribution(values: list[int | float]) -> dict[str, int | float]:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("distribution requires values")

    def percentile(fraction: float) -> int | float:
        return ordered[round((len(ordered) - 1) * fraction)]

    return {
        "min": ordered[0],
        "p25": percentile(0.25),
        "median": median(ordered),
        "p75": percentile(0.75),
        "p90": percentile(0.90),
        "p95": percentile(0.95),
        "max": ordered[-1],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--esconv", type=Path, default=Path("data/external/ESConv.json"))
    parser.add_argument(
        "--split-manifest", type=Path, default=Path("data/strategy/esconv_split_manifest_v1_5.jsonl")
    )
    parser.add_argument("--session-results", type=Path, required=True)
    parser.add_argument("--bge-embedding-cache-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=Path("data/paper1_public_rs"))
    parser.add_argument("--query-preceding-turns", type=int, default=6)
    parser.add_argument("--diagnostic-top-k", type=int, default=4)
    parser.add_argument(
        "--llama-tokenizer-json",
        type=Path,
        help=(
            "Path to the hash-verified frozen Llama-3.1-8B-Instruct tokenizer.json "
            "(metacom_pm.paper1.llama_tokenizer.LLAMA_TOKENIZER_JSON_SHA256). Required "
            "unless --allow-whitespace-proxy-diagnostic-only is also passed."
        ),
    )
    parser.add_argument(
        "--allow-whitespace-proxy-diagnostic-only",
        action="store_true",
        help=(
            "Explicitly permit falling back to the whitespace-split token-count proxy "
            "for diagnostic_injected_token_counts when --llama-tokenizer-json is omitted."
        ),
    )
    args = parser.parse_args()
    if args.llama_tokenizer_json is None and not args.allow_whitespace_proxy_diagnostic_only:
        raise RuntimeError(
            "no --llama-tokenizer-json given -- a real census build must use the real "
            "Generator token counter for diagnostic_injected_token_counts, not the "
            "whitespace-split proxy. Pass --allow-whitespace-proxy-diagnostic-only "
            "explicitly if this is a throwaway diagnostic run."
        )
    token_counter = (
        build_llama_token_counter(args.llama_tokenizer_json) if args.llama_tokenizer_json else None
    )

    cards = build_strategy_source_catalog(esconv_path=args.esconv, split_manifest_path=args.split_manifest)
    cards_by_id = {card.card_id: card for card in cards}
    documents = load_atomic_move_retrieval_documents(args.session_results, cards_by_id=cards_by_id)
    if not documents:
        raise RuntimeError(f"{args.session_results} produced zero atomic-move retrieval documents")

    states = build_rs_decision_states(
        esconv_path=args.esconv,
        split_manifest_path=args.split_manifest,
        source_splits=("train", "validation"),
        exclude_evoemo_overlap=True,
        query_preceding_turns=args.query_preceding_turns,
    )

    encoder = BgeM3Encoder()
    cache = EmbeddingSuccessCache(args.bge_embedding_cache_dir)

    document_result = materialize_embeddings(
        [(doc.atomic_card_id, doc.text) for doc in documents],
        field_source=RS_DOCUMENT_FIELD_SOURCE,
        encoder=encoder,
        cache=cache,
    )
    query_result = materialize_embeddings(
        [(state.state_id, state.query_text) for state in states],
        field_source=RS_QUERY_FIELD_SOURCE,
        encoder=encoder,
        cache=cache,
    )

    census = build_rs_atomic_move_zero_outcome_census(
        states=states,
        documents=documents,
        document_vectors=document_result.vectors,
        query_vectors=query_result.vectors,
        diagnostic_top_k=args.diagnostic_top_k,
        token_counter=token_counter,
    )

    census_path = args.out_dir / "esconv_rs_atomic_move_zero_outcome_census_v1.jsonl"
    summary_path = args.out_dir / "esconv_rs_atomic_move_zero_outcome_census_summary_v1.json"
    census_sha256 = _write_jsonl(census_path, [row.model_dump(mode="json") for row in census])

    top1_similarities = [row.diagnostic_bge_cosine_similarities[0] for row in census]
    candidate_counts = [row.candidate_count_after_leave_dialogue_out for row in census]
    nonzero_counts = [row.nonzero_bge_similarity_candidate_count for row in census]
    bundle_words = {
        str(k): [sum(row.diagnostic_document_word_counts[:k]) for row in census]
        for k in (1, 2, args.diagnostic_top_k)
        if k <= args.diagnostic_top_k
    }
    word_cap_grid = {
        f"k{k}_cap{cap}": {
            "states_within_cap": sum(total <= cap for total in totals),
            "rate": sum(total <= cap for total in totals) / len(totals),
        }
        for k, totals in ((int(key), value) for key, value in bundle_words.items())
        for cap in (64, 128, 256, 512)
    }

    # Concentration/redundancy diagnostics -- "every state got a nonzero
    # candidate" is a weak claim on its own (dense embeddings almost always
    # give a nonzero cosine similarity for any pair); these numbers say
    # something sharper about the actual catalog structure and how
    # concentrated top-1 selection is.
    top1_ids = [row.diagnostic_candidate_ids[0] for row in census]
    exact_top1_top2_ties = sum(
        1
        for row in census
        if len(row.diagnostic_bge_cosine_similarities) >= 2
        and row.diagnostic_bge_cosine_similarities[0] == row.diagnostic_bge_cosine_similarities[1]
    )
    top1_reuse_counts = Counter(top1_ids)
    text_sha256_counts = Counter(doc.text_sha256 for doc in documents)
    duplicate_retrieval_document_instances = sum(
        count - 1 for count in text_sha256_counts.values() if count > 1
    )
    atomic_to_source_card = {doc.atomic_card_id: doc.source_card_id for doc in documents}
    states_with_same_source_card_in_top_k = sum(
        1
        for row in census
        if len(
            {atomic_to_source_card[candidate_id] for candidate_id in row.diagnostic_candidate_ids}
        )
        < len(row.diagnostic_candidate_ids)
    )
    concentration_diagnostics = {
        "note": (
            "states_with_nonzero_bge_similarity above is a weak claim on its own -- "
            "dense embeddings almost always produce a nonzero cosine similarity for "
            "any pair, so it mainly says every state had a legal candidate, not that "
            "every candidate is semantically relevant. These numbers characterize "
            "actual retrieval structure instead."
        ),
        "exact_top1_top2_bge_cosine_similarity_ties": exact_top1_top2_ties,
        "distinct_documents_ever_selected_as_top1": len(top1_reuse_counts),
        "atomic_move_retrieval_documents": len(documents),
        "most_reused_top1_document": {
            "atomic_card_id": top1_reuse_counts.most_common(1)[0][0],
            "times_selected_as_top1": top1_reuse_counts.most_common(1)[0][1],
        },
        "duplicate_retrieval_document_instances": duplicate_retrieval_document_instances,
        "duplicate_retrieval_document_instances_note": (
            "count of documents whose retrieval text (source context + rendered "
            "move) is byte-identical to another document already counted -- i.e. "
            "extra instances beyond the first in each duplicate-content group, not "
            "the number of groups."
        ),
        f"states_with_multiple_top_{args.diagnostic_top_k}_candidates_sharing_a_source_card": (
            states_with_same_source_card_in_top_k
        ),
        f"states_with_multiple_top_{args.diagnostic_top_k}_candidates_sharing_a_source_card_fraction": (
            states_with_same_source_card_in_top_k / len(census)
        ),
    }

    old_census = Path("data/paper1_public_rs/esconv_rs_zero_outcome_census_summary_v1.json")
    summary = {
        "protocol": "pm-paper1-rs-atomic-move-zero-outcome-summary-v1",
        "status": "ZERO_OUTCOME_AUDIT_ONLY_AWAITING_M2_FREEZE",
        "supersedes": {
            "path": str(old_census),
            "sha256": _sha256_file(old_census) if old_census.exists() else None,
            "reason": (
                "06_materialize_esconv_rs_zero_outcome_census.py ranks the "
                "pre-atomic-move 12169-card StrategySourceCard catalog with a "
                "token-Jaccard index; this script ranks the real 15061-unit "
                "atomic-move catalog (RS M2 freeze decision 10's approved "
                "granularity) with real BGE-M3 cosine similarity. The old "
                "artifact is left in place, not deleted -- both exist side "
                "by side as distinct, dated diagnostics."
            ),
        },
        "source": {
            "esconv_sha256": _sha256_file(args.esconv),
            "split_manifest_sha256": _sha256_file(args.split_manifest),
            # B10: filename + hash only, never an absolute/worktree-specific
            # path -- session_results normally lives outside the repo
            # (e.g. /home/.../paper1_runs/...), which would not exist after
            # a fresh clone on another machine.
            "session_results_filename": args.session_results.name,
            "session_results_sha256": _sha256_file(args.session_results),
        },
        "counts": {
            "strategy_source_cards": len(cards),
            "atomic_move_retrieval_documents": len(documents),
            "decision_states": len(states),
            "decision_state_dialogues": len({state.source_dialogue_id for state in states}),
            "states_with_leave_dialogue_out_candidates": sum(
                row.candidate_count_after_leave_dialogue_out > 0 for row in census
            ),
            "states_with_nonzero_bge_similarity": sum(
                row.nonzero_bge_similarity_candidate_count > 0 for row in census
            ),
        },
        "bge_materialization": {
            "documents": build_materialization_report(
                field_source=RS_DOCUMENT_FIELD_SOURCE, result=document_result, encoder=encoder
            ),
            "queries": build_materialization_report(
                field_source=RS_QUERY_FIELD_SOURCE, result=query_result, encoder=encoder
            ),
        },
        "outcome_blind_distributions": {
            "candidate_count_after_leave_dialogue_out": _distribution(candidate_counts),
            "nonzero_bge_similarity_candidate_count": _distribution(nonzero_counts),
            "diagnostic_top1_bge_cosine_similarity": _distribution(top1_similarities),
            "diagnostic_top1_bge_cosine_similarity_population_variance": pvariance(top1_similarities),
            "diagnostic_bundle_document_words": {
                key: _distribution(value) for key, value in bundle_words.items()
            },
        },
        "concentration_diagnostics": concentration_diagnostics,
        "diagnostic_word_cap_grid": {
            "status": "AUDIT_GRID_ONLY_WORD_COUNTS_NOT_MODEL_TOKENS_NOT_M2_FREEZE",
            "cells": word_cap_grid,
        },
        "diagnostic_similarity_method": {
            "status": "REAL_BGE_M3_NOT_A_LEXICAL_PROXY_STILL_PHASE1_AUDIT_ONLY_NOT_FINAL_RETRIEVER",
            "similarity": "cosine (L2-normalized BGE-M3 dot product)",
            "query_preceding_turns": args.query_preceding_turns,
            "top_k": args.diagnostic_top_k,
        },
        "primary_retrieval_unit_decision": {
            "status": "M2_RESEARCHER_DECISION_REQUIRED_NOT_ENACTED_HERE",
            "recommendation": (
                "Since the research definition is 'inject or don't inject one RS "
                "atomic move,' the formal primary retrieval unit should probably "
                "freeze to top-1 alone. top_k>1 is kept as a diagnostic surface "
                "(concentration/redundancy auditing above) and must not be "
                "silently reassembled into a multi-move bundle at freeze time -- "
                "that would quietly break the atomic-unit treatment definition. "
                "This is a pre-outcome researcher decision, not something this "
                "script or its default top_k picks on its own."
            ),
        },
        "artifacts": {
            "census": str(census_path),
            "census_sha256": census_sha256,
        },
        "outcome_calls": 0,
        "outcome_lock": "LOCKED_PRE_ZERO_OUTCOME_FREEZE",
        "pending_m2_freeze": [
            "final_card_rendering",
            "retrieval_backend_and_query_window",
            "candidate_bundle_top_k_vs_top1_primary_unit",
            "generator_token_cap",
            "exact_rs_feature_schema",
            "effect_state_overlap_policy",
            "fold_manifest",
            "cross_source_card_duplicate_policy",
        ],
    }
    _write_json(summary_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
