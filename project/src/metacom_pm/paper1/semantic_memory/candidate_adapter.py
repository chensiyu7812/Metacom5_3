"""Materialize formal memory candidates from verified semantic units."""

from __future__ import annotations

from collections.abc import Callable

from metacom_pm.io import sha256_text
from metacom_pm.paper1.contracts import CandidateLineage, CandidateRecord, Head

from .contracts import AcceptedSemanticMemoryUnit, MemoryClass
from .versioning import resolve_memory_versions

CANDIDATE_ADAPTER_VERSION = "paper1-semantic-memory-candidate-adapter-v1"


def _raw_descriptors(unit: AcceptedSemanticMemoryUnit) -> dict[str, str | int]:
    structural = {"session_chronological_rank": unit.source_session_rank}
    if unit.memory_class is MemoryClass.MP:
        assert unit.profile_field_type is not None
        return {**structural, "mp_profile_field_type": unit.profile_field_type.value}
    if unit.memory_class is MemoryClass.MS:
        assert unit.continuity_type is not None
        return {
            **structural,
            "ms_continuity_type": unit.continuity_type.value,
            "ms_source_status": unit.timestamp_status.value,
        }
    assert unit.historical_outcome_type is not None
    return {**structural, "me_historical_outcome_type": unit.historical_outcome_type.value}


def materialize_memory_candidates(
    units: tuple[AcceptedSemanticMemoryUnit, ...],
    *,
    target_owner_id: str,
    target_session_rank: int,
    token_counter: Callable[[str], int],
) -> dict[Head, tuple[CandidateRecord, ...]]:
    """Build strict-past candidates; never infer usefulness or relevance."""

    resolved = resolve_memory_versions(
        units,
        target_owner_id=target_owner_id,
        target_session_rank=target_session_rank,
    )
    active_ids = {state.memory_id for state in resolved if state.active_for_candidate}
    by_head: dict[Head, list[CandidateRecord]] = {
        Head.MP: [],
        Head.MS: [],
        Head.ME: [],
    }
    for unit in sorted(
        (unit for unit in units if unit.memory_id in active_ids),
        key=lambda item: (item.source_session_rank, item.source_session_id, item.memory_id),
    ):
        content = unit.rendered_candidate_content
        token_count = int(token_counter(content))
        if token_count < 1:
            raise ValueError("token_counter must return a positive count")
        head = Head(unit.memory_class.value)
        by_head[head].append(
            CandidateRecord(
                candidate_id=f"semantic_{unit.memory_id}",
                head=head,
                content=content,
                token_count=token_count,
                lineage=CandidateLineage(
                    source=CANDIDATE_ADAPTER_VERSION,
                    owner_id=unit.owner_id,
                    source_record_ids=(
                        unit.memory_id,
                        unit.source_session_id,
                        *unit.source_turn_ids,
                    ),
                    strict_past=True,
                    observed_at=unit.timestamp,
                    content_sha256=sha256_text(content),
                ),
                raw_descriptors=_raw_descriptors(unit),
            )
        )
    return {head: tuple(rows) for head, rows in by_head.items()}
