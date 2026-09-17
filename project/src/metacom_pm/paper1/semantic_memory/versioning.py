"""Outcome-blind resolution of strictly-past semantic-memory versions."""

from __future__ import annotations

from pydantic import Field

from metacom_pm.paper1.contracts import StrictContract

from .contracts import (
    AcceptedSemanticMemoryUnit,
    CandidateSourceUse,
    PriorMemoryRelationType,
)

VERSION_RESOLVER_VERSION = "paper1-semantic-memory-version-resolver-v1"


class ResolvedMemoryState(StrictContract):
    memory_id: str = Field(min_length=1)
    active_for_candidate: bool
    invalidated_by_memory_id: str | None = None
    mechanical_reasons: tuple[str, ...] = ()


def resolve_memory_versions(
    units: tuple[AcceptedSemanticMemoryUnit, ...],
    *,
    target_owner_id: str,
    target_session_rank: int,
) -> tuple[ResolvedMemoryState, ...]:
    """Resolve current versions without using relevance, utility, or outcomes.

    Reaffirm/update/supersede/conflict relations select the newer grounded unit
    as the current version and mechanically deactivate the referenced older
    unit. Coreference alone never changes candidate activity. These semantic
    relations are forbidden from primary fold grouping.
    """

    if target_session_rank < 0:
        raise ValueError("target_session_rank must be non-negative")
    owner_units = tuple(unit for unit in units if unit.owner_id == target_owner_id)
    if len(owner_units) != len(units):
        raise ValueError("version resolver received a wrong-owner memory")
    memory_ids = [unit.memory_id for unit in owner_units]
    if len(memory_ids) != len(set(memory_ids)):
        raise ValueError("version resolver received duplicate memory IDs")

    history = tuple(
        sorted(
            (unit for unit in owner_units if unit.source_session_rank < target_session_rank),
            key=lambda unit: (
                unit.source_session_rank,
                unit.source_session_id,
                unit.memory_id,
            ),
        )
    )
    by_id = {unit.memory_id: unit for unit in history}
    active = {
        unit.memory_id: unit.candidate_source_use is CandidateSourceUse.CANDIDATE_SOURCE
        for unit in history
    }
    invalidated_by: dict[str, str | None] = {unit.memory_id: None for unit in history}
    reasons: dict[str, list[str]] = {unit.memory_id: [] for unit in history}

    seen: set[str] = set()
    invalidating_relations = {
        PriorMemoryRelationType.REAFFIRMS,
        PriorMemoryRelationType.UPDATES,
        PriorMemoryRelationType.SUPERSEDES,
        PriorMemoryRelationType.CONFLICTS_WITH,
    }
    for unit in history:
        for link in unit.linked_prior_relations:
            prior = by_id.get(link.memory_id)
            if prior is None:
                raise ValueError(f"version relation points outside target history: {link.memory_id}")
            if link.memory_id not in seen:
                raise ValueError(f"version relation is not strictly earlier: {link.memory_id}")
            if (
                link.relation is not PriorMemoryRelationType.COREFERS_WITH
                and prior.memory_class is not unit.memory_class
            ):
                raise ValueError(f"cross-class version relation is forbidden: {link.memory_id}")
            if link.relation in invalidating_relations:
                active[link.memory_id] = False
                invalidated_by[link.memory_id] = unit.memory_id
                reasons[link.memory_id].append(f"newer_{link.relation.value}")
        seen.add(unit.memory_id)

    return tuple(
        ResolvedMemoryState(
            memory_id=unit.memory_id,
            active_for_candidate=active[unit.memory_id],
            invalidated_by_memory_id=invalidated_by[unit.memory_id],
            mechanical_reasons=tuple(reasons[unit.memory_id]),
        )
        for unit in history
    )
