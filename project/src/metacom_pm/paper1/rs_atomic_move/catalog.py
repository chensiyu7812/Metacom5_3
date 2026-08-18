"""Deterministic final-catalog projection for RS atomic-move units.

The source context is useful for matching a live dialogue state, while the
unit-specific rendered move keeps independently retrievable units from one
source turn from sharing the same embedding and falling through to an ID
tie-break.  This module constructs text only; BGE-M3 loading/materialization
remains separately gated by the formal embedding binding.
"""

from __future__ import annotations

import hashlib

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
    )
