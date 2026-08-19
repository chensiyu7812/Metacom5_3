"""Deterministic final-catalog projection for RS atomic-move units.

The source context is useful for matching a live dialogue state, while the
unit-specific rendered move keeps independently retrievable units from one
source turn from sharing the same embedding and falling through to an ID
tie-break.  This module constructs text only; BGE-M3 loading/materialization
remains separately gated by the formal embedding binding.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import Field

from ..contracts import StrictContract
from ..rs.strategy_bank import StrategySourceCard
from .contracts import AcceptedAtomicMoveUnit


class AtomicMoveRetrievalDocument(StrictContract):
    source_card_id: str = Field(pattern=r"^rs_src_[0-9a-f]{24}$")
    atomic_card_id: str = Field(pattern=r"^rs_atomic_[0-9a-f]{24}$")
    source_dialogue_ids: tuple[str, ...] = Field(min_length=1)
    text: str = Field(min_length=1)
    text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    # The unit's own rendered move, separate from `text` (retrieval_text +
    # rendered_card_text combined, what gets embedded for matching). This is
    # what would actually be injected into the Generator if this unit is
    # selected -- a cost/length diagnostic must measure this, not the full
    # retrieval document (which includes source dialogue context used only
    # for matching, never injected).
    rendered_card_text: str = Field(min_length=1)


def build_atomic_move_retrieval_document(
    source_card: StrategySourceCard,
    unit: AcceptedAtomicMoveUnit,
) -> AtomicMoveRetrievalDocument:
    """Bind one source context to exactly one rendered atomic-move unit."""

    if unit.source_turn_index != source_card.source_turn_index:
        raise ValueError("atomic unit/source card turn identity mismatch")
    if unit.source_dialogue_ids != source_card.source_dialogue_ids:
        raise ValueError("atomic unit/source card dialogue lineage mismatch")
    text = f"{source_card.retrieval_text}\n{unit.rendered_card_text}"
    return AtomicMoveRetrievalDocument(
        source_card_id=source_card.card_id,
        atomic_card_id=unit.card_id,
        source_dialogue_ids=unit.source_dialogue_ids,
        text=text,
        text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        rendered_card_text=unit.rendered_card_text,
    )


def load_atomic_move_retrieval_documents(
    results_path: str | Path,
    *,
    cards_by_id: dict[str, StrategySourceCard],
) -> tuple[AtomicMoveRetrievalDocument, ...]:
    """Load every accepted atomic-move unit from a completed compiler run's
    ``session_results.jsonl`` (one row per source card, each carrying its own
    ``accepted_units`` list -- see ``rs_atomic_move.batch``) and bind each to
    its source card's retrieval document. Rows with no accepted units (a
    fully-rejected or permanently call-failed source card) contribute
    nothing, not a placeholder."""

    documents: list[AtomicMoveRetrievalDocument] = []
    with Path(results_path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            source_card_id = row["source_card_id"]
            card = cards_by_id.get(source_card_id)
            if card is None:
                raise ValueError(
                    f"session results reference a source card not in the live catalog: {source_card_id}"
                )
            for unit_row in row.get("accepted_units") or ():
                unit = AcceptedAtomicMoveUnit.model_validate(unit_row)
                documents.append(build_atomic_move_retrieval_document(card, unit))
    if len({doc.atomic_card_id for doc in documents}) != len(documents):
        raise RuntimeError("loaded atomic-move retrieval documents are not uniquely identified")
    return tuple(documents)
