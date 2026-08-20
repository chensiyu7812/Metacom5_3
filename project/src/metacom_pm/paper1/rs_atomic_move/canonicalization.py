"""Exact-only treatment identity for RS calibration.

Canonicalization happens before ranking.  Each exact rendered treatment has
one deterministic representative retrieval document and therefore exactly
one BGE score per query.  Additional source occurrences expand provenance;
they never create additional ranking tickets or a frequency prior.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Mapping, Sequence

from pydantic import Field

from ..contracts import StrictContract
from .catalog import AtomicMoveRetrievalDocument
from .contracts import AcceptedAtomicMoveUnit


class ExactTreatmentAlias(StrictContract):
    treatment_id: str = Field(pattern=r"^rs_treatment_[0-9a-f]{24}$")
    rendered_card_text: str = Field(min_length=1)
    rendered_card_text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    representative_atomic_card_id: str = Field(pattern=r"^rs_atomic_[0-9a-f]{24}$")
    representative_source_card_id: str = Field(pattern=r"^rs_src_[0-9a-f]{24}$")
    representative_retrieval_text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    atomic_card_ids: tuple[str, ...] = Field(min_length=1)
    source_card_ids: tuple[str, ...] = Field(min_length=1)
    source_dialogue_ids: tuple[str, ...] = Field(min_length=1)
    atomic_move_families: tuple[str, ...] = Field(min_length=1)


def canonicalize_exact_treatments(
    documents: Sequence[AtomicMoveRetrievalDocument],
    *,
    units_by_id: Mapping[str, AcceptedAtomicMoveUnit],
) -> tuple[ExactTreatmentAlias, ...]:
    """Collapse byte-identical injected treatments, and nothing else.

    The representative is the lexicographically smallest
    ``(source_card_id, atomic_card_id)``.  Ranking must embed/score only this
    representative document; max/mean pooling over duplicate occurrences is
    forbidden because occurrence count would become an unintended retrieval
    prior.  Full lineage remains on the alias for conservative
    leave-current-dialogue-out exclusion.
    """

    if not documents:
        raise ValueError("exact treatment canonicalization requires documents")
    atomic_ids = [document.atomic_card_id for document in documents]
    if len(atomic_ids) != len(set(atomic_ids)):
        raise ValueError("atomic retrieval documents must have unique IDs")

    groups: dict[str, list[AtomicMoveRetrievalDocument]] = defaultdict(list)
    for document in documents:
        unit = units_by_id.get(document.atomic_card_id)
        if unit is None:
            raise ValueError(f"missing accepted unit for {document.atomic_card_id}")
        if unit.rendered_card_text != document.rendered_card_text:
            raise ValueError("accepted unit and retrieval document treatment text disagree")
        if tuple(unit.source_dialogue_ids) != tuple(document.source_dialogue_ids):
            raise ValueError("accepted unit and retrieval document provenance disagree")
        treatment_sha = hashlib.sha256(document.rendered_card_text.encode("utf-8")).hexdigest()
        if treatment_sha != unit.rendered_card_text_sha256:
            raise ValueError("rendered treatment hash mismatch")
        groups[treatment_sha].append(document)

    aliases: list[ExactTreatmentAlias] = []
    for treatment_sha, members in sorted(groups.items()):
        members = sorted(members, key=lambda row: (row.source_card_id, row.atomic_card_id))
        representative = members[0]
        member_units = [units_by_id[row.atomic_card_id] for row in members]
        aliases.append(
            ExactTreatmentAlias(
                treatment_id=f"rs_treatment_{treatment_sha[:24]}",
                rendered_card_text=representative.rendered_card_text,
                rendered_card_text_sha256=treatment_sha,
                representative_atomic_card_id=representative.atomic_card_id,
                representative_source_card_id=representative.source_card_id,
                representative_retrieval_text_sha256=representative.text_sha256,
                atomic_card_ids=tuple(sorted(row.atomic_card_id for row in members)),
                source_card_ids=tuple(sorted({row.source_card_id for row in members})),
                source_dialogue_ids=tuple(
                    sorted({dialogue for row in members for dialogue in row.source_dialogue_ids})
                ),
                atomic_move_families=tuple(
                    sorted({unit.atomic_move_family.value for unit in member_units})
                ),
            )
        )

    if sum(len(alias.atomic_card_ids) for alias in aliases) != len(documents):
        raise RuntimeError("exact treatment provenance union is incomplete")
    return tuple(aliases)
