"""Adapts ``rs/strategy_bank.py`` source cards into structured, turn-indexed
compiler input.

``StrategySourceCard.retrieval_text`` is a pre-flattened "speaker: text"
string -- adequate for the existing lexical/embedding retriever, but not for
this compiler's exact-span grounding, which must look up
``(source_dialogue_id, turn_index) -> exact text`` per turn. Rather than
duplicate ``build_strategy_source_catalog``'s selection logic (train-only,
EvoEmo-overlap exclusion, dedup), this module re-derives individual turns for
an *already-selected* card by re-reading the same raw ESConv dialogue at the
card's own ``(source_dialogue_id, source_turn_index)`` -- the card list
itself remains the single source of truth for which cards exist.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from metacom_pm.io import sha256_file

from .contracts import SourceCardCompileInput, SourceTurnInput
from ..rs.strategy_bank import (
    EXPECTED_ESCONV_SHA256,
    StrategySourceCard,
    _file_sha256,
    _normalize,
)

SOURCE_ADAPTER_CODE_SHA256 = sha256_file(Path(__file__))


def _dialogue_index_by_id(data: list[dict[str, Any]], dialogue_id: str) -> int:
    # ESConv dialogue_id in the project split manifest is derived from list
    # position as f"esconv_{index:04d}" (see strategy_bank._read_split_manifest).
    if not dialogue_id.startswith("esconv_"):
        raise ValueError(f"unexpected dialogue_id format: {dialogue_id}")
    index = int(dialogue_id[len("esconv_") :])
    if not (0 <= index < len(data)):
        raise ValueError(f"dialogue_id {dialogue_id} out of range for ESConv data")
    return index


def build_source_card_compile_input(
    card: StrategySourceCard,
    *,
    esconv_data: list[dict[str, Any]],
    preceding_turns: int = 6,
) -> SourceCardCompileInput:
    """Re-derive individual, turn-indexed input for one already-selected
    source card. ``esconv_data`` is the parsed ESConv.json list, loaded once
    by the caller (batch.py) and shared across all cards -- this function
    does not re-read the file per card."""

    dialogue_index = _dialogue_index_by_id(esconv_data, card.source_dialogue_id)
    dialogue = esconv_data[dialogue_index].get("dialog")
    if not isinstance(dialogue, list):
        raise ValueError(f"invalid dialogue for {card.source_dialogue_id}")
    if not (0 <= card.source_turn_index < len(dialogue)):
        raise ValueError(
            f"source_turn_index {card.source_turn_index} out of range for {card.source_dialogue_id}"
        )

    target_raw = dialogue[card.source_turn_index]
    target_role = "supporter" if target_raw.get("speaker") == "supporter" else "seeker"
    target_text = _normalize(target_raw.get("content"))
    if target_text != card.example_response:
        raise ValueError(
            f"re-derived target turn text does not match the source card's "
            f"example_response for {card.card_id} -- ESConv data or card is stale"
        )

    window_start = max(0, card.source_turn_index - preceding_turns)
    preceding: list[SourceTurnInput] = []
    for turn_index in range(window_start, card.source_turn_index):
        raw = dialogue[turn_index]
        text = _normalize(raw.get("content"))
        if not text:
            continue
        role = "supporter" if raw.get("speaker") == "supporter" else "seeker"
        preceding.append(
            SourceTurnInput(
                source_dialogue_id=card.source_dialogue_id,
                turn_index=turn_index,
                role=role,
                text=text,
            )
        )

    return SourceCardCompileInput(
        source_card_id=card.card_id,
        target_dialogue_id=card.source_dialogue_id,
        target_turn_index=card.source_turn_index,
        preceding_turns=tuple(preceding),
        target_turn=SourceTurnInput(
            source_dialogue_id=card.source_dialogue_id,
            turn_index=card.source_turn_index,
            role=target_role,
            text=target_text,
        ),
        equivalent_dialogue_ids=tuple(
            sorted(dialogue_id for dialogue_id in card.source_dialogue_ids if dialogue_id != card.source_dialogue_id)
        ),
    )


def load_esconv_data(esconv_path: str | Path) -> list[dict[str, Any]]:
    path = Path(esconv_path)
    if _file_sha256(path) != EXPECTED_ESCONV_SHA256:
        raise ValueError("ESConv artifact SHA256 mismatch")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("ESConv must be a list of dialogues")
    return data
