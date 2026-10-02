#!/usr/bin/env python3
"""Materialize the public-only, text-free RS Phase-1 census."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from statistics import median, pvariance
from typing import Any

from metacom_pm.paper1.rs.strategy_bank import build_strategy_source_catalog
from metacom_pm.paper1.rs.zero_outcome_census import (
    build_rs_decision_states,
    build_rs_zero_outcome_census,
)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(_canonical(row) + "\n" for row in rows), encoding="utf-8")


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


def _situation_visibility_audit(esconv_path: Path) -> dict[str, int | str]:
    data = json.loads(esconv_path.read_text(encoding="utf-8"))
    nonempty = 0
    verbatim_visible = 0
    for row in data:
        situation = " ".join(str(row.get("situation") or "").split()).casefold()
        dialogue = " ".join(
            " ".join(str(turn.get("content") or "").split())
            for turn in row.get("dialog", [])
        ).casefold()
        if situation:
            nonempty += 1
            verbatim_visible += int(situation in dialogue)
    return {
        "status": "DIAGNOSTIC_ONLY_FIELD_EXCLUDED_FROM_ACTIVE_CATALOG_AND_STATE",
        "dialogues_with_nonempty_situation": nonempty,
        "situation_verbatim_contained_anywhere_in_dialogue": verbatim_visible,
        "situation_not_verbatim_contained_anywhere_in_dialogue": nonempty - verbatim_visible,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--esconv", type=Path, default=Path("data/external/ESConv.json"))
    parser.add_argument(
        "--split-manifest",
        type=Path,
        default=Path("data/strategy/esconv_split_manifest_v1_5.jsonl"),
    )
    parser.add_argument(
        "--out-dir", type=Path, default=Path("data/paper1_public_rs")
    )
    parser.add_argument("--query-preceding-turns", type=int, default=6)
    parser.add_argument("--diagnostic-top-k", type=int, default=4)
    parser.add_argument("--diagnostic-max-document-frequency", type=float, default=0.2)
    args = parser.parse_args()

    cards = build_strategy_source_catalog(
        esconv_path=args.esconv,
        split_manifest_path=args.split_manifest,
        preceding_turns=args.query_preceding_turns,
    )
    all_train_cards = build_strategy_source_catalog(
        esconv_path=args.esconv,
        split_manifest_path=args.split_manifest,
        preceding_turns=args.query_preceding_turns,
        exclude_evoemo_overlap=False,
    )
    states = build_rs_decision_states(
        esconv_path=args.esconv,
        split_manifest_path=args.split_manifest,
        source_splits=("train", "validation"),
        exclude_evoemo_overlap=True,
        query_preceding_turns=args.query_preceding_turns,
    )
    all_train_dev_states = build_rs_decision_states(
        esconv_path=args.esconv,
        split_manifest_path=args.split_manifest,
        source_splits=("train", "validation"),
        exclude_evoemo_overlap=False,
        query_preceding_turns=args.query_preceding_turns,
    )
    census = build_rs_zero_outcome_census(
        states=states,
        cards=cards,
        diagnostic_top_k=args.diagnostic_top_k,
        diagnostic_max_document_frequency=args.diagnostic_max_document_frequency,
    )

    card_path = args.out_dir / "esconv_strategy_source_identity_dialogue_only_v2.jsonl"
    state_path = args.out_dir / "esconv_rs_decision_state_identity_v1.jsonl"
    census_path = args.out_dir / "esconv_rs_zero_outcome_census_v1.jsonl"
    summary_path = args.out_dir / "esconv_rs_zero_outcome_census_summary_v1.json"

    _write_jsonl(
        card_path,
        [
            {
                "protocol": "pm-paper1-esconv-strategy-source-dialogue-only-v2",
                "card_id": card.card_id,
                "source_dialogue_id": card.source_dialogue_id,
                "source_turn_index": card.source_turn_index,
                "source_split": card.source_split,
                "source_strategy_annotation": card.strategy_label,
                "retrieval_text_sha256": card.retrieval_text_sha256,
                "example_response_sha256": card.example_response_sha256,
            }
            for card in cards
        ],
    )
    _write_jsonl(
        state_path,
        [
            {
                "protocol": "pm-paper1-esconv-rs-decision-state-identity-v1",
                "state_id": state.state_id,
                "source_dialogue_id": state.source_dialogue_id,
                "source_split": state.source_split,
                "decision_turn_index": state.decision_turn_index,
                "visible_dialogue_sha256": hashlib.sha256(
                    state.visible_dialogue_text.encode("utf-8")
                ).hexdigest(),
                "query_text_sha256": hashlib.sha256(
                    state.query_text.encode("utf-8")
                ).hexdigest(),
                "current_user_text_sha256": hashlib.sha256(
                    state.current_user_text.encode("utf-8")
                ).hexdigest(),
                "visible_turn_count": state.visible_turn_count,
                "query_turn_count": state.query_turn_count,
                "current_user_turn_count": state.current_user_turn_count,
            }
            for state in states
        ],
    )
    _write_jsonl(
        census_path,
        [
            {
                "protocol": "pm-paper1-esconv-rs-zero-outcome-census-v1",
                **row.model_dump(mode="json"),
            }
            for row in census
        ],
    )

    similarities = [row.diagnostic_lexical_jaccards[0] for row in census]
    candidate_counts = [row.candidate_count_after_leave_dialogue_out for row in census]
    nonzero_counts = [row.nonzero_lexical_overlap_candidate_count for row in census]
    query_words = [row.query_word_count for row in census]
    card_retrieval_words = [len(card.retrieval_text.split()) for card in cards]
    card_injected_words = [
        len(card.guidance_text.split()) + len(card.example_response.split()) for card in cards
    ]
    bundle_words = {
        str(k): [sum(row.diagnostic_injected_word_counts[:k]) for row in census]
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
    source_dialogues = {state.source_dialogue_id for state in states}
    old_identity = Path("data/paper1_authority/esconv_strategy_source_identity_v1.jsonl")
    summary = {
        "protocol": "pm-paper1-esconv-rs-zero-outcome-summary-v1",
        "status": "ZERO_OUTCOME_AUDIT_ONLY_AWAITING_M2_FREEZE",
        "intended_grain": "one row per supporter-response opportunity after a visible seeker turn",
        "source": {
            "esconv_artifact": str(args.esconv),
            "esconv_sha256": _sha256(args.esconv),
            "project_defined_split_manifest": str(args.split_manifest),
            "project_defined_split_manifest_sha256": _sha256(args.split_manifest),
            "effect_state_splits": ["train", "validation"],
            "evoemo_overlap_dialogues_excluded": True,
            "strategy_bank_split": "train",
            "strategy_bank_leave_current_dialogue_out_required": True,
        },
        "privileged_field_audit": {
            "situation": _situation_visibility_audit(args.esconv),
            "excluded_everywhere": [
                "survey_score",
                "turn.feedback",
                "seeker_question1",
                "seeker_question2",
                "supporter_question1",
                "supporter_question2",
            ],
            "target_supporter_response_used_as_state_or_query": False,
            "future_turns_used_as_state_or_query": False,
        },
        "superseded_artifact": {
            "path": str(old_identity),
            "sha256": _sha256(old_identity) if old_identity.exists() else None,
            "reason": "v1 retrieval hashes were conditioned on ESConv situation text",
        },
        "counts": {
            "strategy_source_cards": len(cards),
            "strategy_source_dialogues": len({card.source_dialogue_id for card in cards}),
            "decision_states": len(states),
            "decision_state_dialogues": len(source_dialogues),
            "decision_states_by_split": dict(
                sorted(Counter(state.source_split for state in states).items())
            ),
            "states_with_leave_dialogue_out_candidates": sum(
                row.candidate_count_after_leave_dialogue_out > 0 for row in census
            ),
            "states_with_nonzero_lexical_overlap": sum(
                row.nonzero_lexical_overlap_candidate_count > 0 for row in census
            ),
        },
        "overlap_policy_sensitivity": {
            "status": "M2_RESEARCHER_DECISION_REQUIRED",
            "conservative_existing_project_flag": {
                "strategy_source_cards": len(cards),
                "strategy_source_dialogues": len(
                    {card.source_dialogue_id for card in cards}
                ),
                "decision_states": len(states),
                "decision_state_dialogues": len(source_dialogues),
            },
            "authority_literal_esconv_train_bank_train_dev_states": {
                "strategy_source_cards": len(all_train_cards),
                "strategy_source_dialogues": len(
                    {card.source_dialogue_id for card in all_train_cards}
                ),
                "decision_states": len(all_train_dev_states),
                "decision_state_dialogues": len(
                    {state.source_dialogue_id for state in all_train_dev_states}
                ),
            },
            "note": (
                "The highest research program says ESConv train for the Bank and "
                "train/dev for effects; it does not itself require the legacy "
                "EvoEmo-overlap exclusion. No final policy is selected here."
            ),
        },
        "outcome_blind_distributions": {
            "candidate_count_after_leave_dialogue_out": _distribution(candidate_counts),
            "nonzero_lexical_overlap_candidate_count": _distribution(nonzero_counts),
            "query_words": _distribution(query_words),
            "source_card_retrieval_words": _distribution(card_retrieval_words),
            "source_card_diagnostic_injected_words": _distribution(card_injected_words),
            "diagnostic_top1_lexical_jaccard": _distribution(similarities),
            "diagnostic_top1_lexical_jaccard_population_variance": pvariance(similarities),
            "diagnostic_bundle_injected_words": {
                key: _distribution(value) for key, value in bundle_words.items()
            },
        },
        "diagnostic_lexical_method": {
            "status": "PHASE1_AUDIT_ONLY_NOT_FINAL_RETRIEVER",
            "similarity": "token_set_jaccard",
            "max_card_document_frequency": args.diagnostic_max_document_frequency,
            "query_preceding_turns": args.query_preceding_turns,
            "top_k": args.diagnostic_top_k,
        },
        "diagnostic_word_cap_grid": {
            "status": "AUDIT_GRID_ONLY_WORD_COUNTS_NOT_MODEL_TOKENS_NOT_M2_FREEZE",
            "cells": word_cap_grid,
        },
        "draft_visible_request_flags": {
            "status": "DETERMINISTIC_DIAGNOSTIC_NOT_M2_FEATURE_FREEZE",
            "advice_request": sum(row.advice_request_visible for row in census),
            "listen_only": sum(row.listen_only_visible for row in census),
            "no_probing": sum(row.no_probing_visible for row in census),
        },
        "feature_readiness": {
            "state_candidate_similarity": "diagnostic lexical variance measured; final backend pending",
            "atomic_move_type": "source-card property available; exact mapping/rendering pending",
            "recent_same_move": "pending runtime-observable text classifier; source gold not used",
            "explicit_request_flags": "draft deterministic parser audited; exact parser pending",
            "candidate_token_cost": "word proxy audited; frozen Generator tokenizer pending",
            "forbidden_shortcuts_present": False,
        },
        "artifacts": {
            "strategy_source_identity": str(card_path),
            "strategy_source_identity_sha256": _sha256(card_path),
            "decision_state_identity": str(state_path),
            "decision_state_identity_sha256": _sha256(state_path),
            "census": str(census_path),
            "census_sha256": _sha256(census_path),
        },
        "formal_outcome_calls": 0,
        "pending_m2_freeze": [
            "final_card_rendering",
            "retrieval_backend_and_query_window",
            "candidate_bundle_top_k",
            "generator_token_cap",
            "exact_rs_feature_schema",
            "effect_state_overlap_policy",
            "fold_manifest",
        ],
    }
    _write_json(summary_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
