#!/usr/bin/env python3
"""Materialize the Paper-1 ESC-Eval English source-overlap slices."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


EXPECTED_SOURCES = {"ESconv": 158, "ExTES": 70, "MHP": 73, "Psych": 25, "EPITOME": 5}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def materialize(cards_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    cards = json.loads(cards_path.read_text(encoding="utf-8"))
    if len(cards) != 331:
        raise ValueError("expected the official 331-card English file")
    rows: list[dict[str, Any]] = []
    source_counts: dict[str, int] = {}
    for index, card in enumerate(cards):
        source = card["source"]
        source_counts[source] = source_counts.get(source, 0) + 1
        is_esconv = source == "ESconv"
        rows.append(
            {
                "protocol": "pm-paper1-esc-eval-source-overlap-v1",
                "official_file_index": index,
                "card_key": f"{card['language']}::{source}::{card['id']}",
                "source": source,
                "role_card_sha256": _sha_text(card["base"]),
                "analysis_slice": "esconv_source_overlap" if is_esconv else "primary_non_esconv_transfer",
            }
        )
    if source_counts != EXPECTED_SOURCES:
        raise ValueError(f"official English source counts drifted: {source_counts}")
    rendered = "".join(_canonical(row) + "\n" for row in rows)
    summary = {
        "protocol": "pm-paper1-esc-eval-source-overlap-summary-v1",
        "status": "OUTCOME_BLIND_SOURCE_SLICES_FROZEN",
        "official_cards_sha256": hashlib.sha256(cards_path.read_bytes()).hexdigest(),
        "manifest_sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
        "english_cards": 331,
        "primary_non_esconv_transfer_cards": 173,
        "esconv_source_overlap_cards": 158,
        "source_counts": source_counts,
        "primary_rule": "source != ESconv",
        "secondary": "all_331_English_cards",
        "sensitivity": "ESconv_source_158_cards",
        "contains_outcomes": False,
    }
    return rows, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cards", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    args = parser.parse_args()
    if args.manifest.exists() or args.summary.exists():
        raise RuntimeError("overlap artifacts already exist; refusing overwrite")
    rows, summary = materialize(args.cards)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text("".join(_canonical(row) + "\n" for row in rows), encoding="utf-8")
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
