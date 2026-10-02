#!/usr/bin/env python3
"""Materialize the dialogue-only, text-free ESConv Strategy source identity."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from statistics import median

from metacom_pm.paper1.rs.strategy_bank import build_strategy_source_catalog


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--esconv", type=Path, default=Path("data/external/ESConv.json"))
    parser.add_argument(
        "--split-manifest",
        type=Path,
        default=Path("data/strategy/esconv_split_manifest_v1_5.jsonl"),
    )
    parser.add_argument(
        "--identity-out",
        type=Path,
        default=Path(
            "data/paper1_public_rs/esconv_strategy_source_identity_dialogue_only_v2.jsonl"
        ),
    )
    parser.add_argument(
        "--summary-out",
        type=Path,
        default=Path(
            "data/paper1_public_rs/esconv_strategy_source_summary_dialogue_only_v2.json"
        ),
    )
    args = parser.parse_args()

    cards = build_strategy_source_catalog(
        esconv_path=args.esconv,
        split_manifest_path=args.split_manifest,
    )
    args.identity_out.parent.mkdir(parents=True, exist_ok=True)
    with args.identity_out.open("w", encoding="utf-8") as handle:
        for card in cards:
            handle.write(
                json.dumps(
                    {
                        "protocol": "pm-paper1-esconv-strategy-source-dialogue-only-v2",
                        "card_id": card.card_id,
                        "source_dialogue_id": card.source_dialogue_id,
                        "source_turn_index": card.source_turn_index,
                        "source_split": card.source_split,
                        "source_strategy_annotation": card.strategy_label,
                        "retrieval_text_sha256": card.retrieval_text_sha256,
                        "example_response_sha256": card.example_response_sha256,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
            )

    source_dialogues = {card.source_dialogue_id for card in cards}
    retrieval_words = [len(card.retrieval_text.split()) for card in cards]
    response_words = [len(card.example_response.split()) for card in cards]
    summary = {
        "protocol": "pm-paper1-esconv-strategy-source-summary-dialogue-only-v2",
        "status": "ZERO_OUTCOME_SOURCE_CATALOG_ONLY_NOT_CANDIDATE_BUNDLE_FREEZE",
        "source": {
            "artifact": str(args.esconv),
            "artifact_sha256": _sha256(args.esconv),
            "project_defined_split_manifest": str(args.split_manifest),
            "project_defined_split_manifest_sha256": _sha256(args.split_manifest),
            "split_is_official": False,
            "source_split": "train",
            "evoemo_overlap_dialogues_excluded": True,
            "retrieval_text_source": "preceding_visible_dialogue_turns_only",
            "esconv_situation_excluded": True,
        },
        "counts": {
            "cards": len(cards),
            "source_dialogues": len(source_dialogues),
            "strategy_labels": dict(sorted(Counter(card.strategy_label for card in cards).items())),
        },
        "outcome_blind_lengths": {
            "retrieval_words_min": min(retrieval_words),
            "retrieval_words_median": median(retrieval_words),
            "retrieval_words_max": max(retrieval_words),
            "response_words_min": min(response_words),
            "response_words_median": median(response_words),
            "response_words_max": max(response_words),
        },
        "identity_manifest": str(args.identity_out),
        "identity_manifest_sha256": _sha256(args.identity_out),
        "contains_raw_dialogue_or_response_text": False,
        "formal_outcome_calls": 0,
        "pending_m2_freeze": [
            "final_card_rendering",
            "retrieval_backend",
            "top_k",
            "token_cap",
            "fold_manifest",
        ],
    }
    _write_json(args.summary_out, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
