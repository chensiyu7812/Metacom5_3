"""Materialize active MP/ME/MS candidates without changing their meanings."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable

from metacom_pm.io import sha256_text
from metacom_pm.paper1.contracts import CandidateLineage, CandidateRecord, Head
from metacom_pm.paper1.data.memory_source import MemorySourceUser, Target
from metacom_pm.paper1.memory.ms import extract_session_documents

from .contracts import (
    AcceptedAtomicMemoryUnit,
    AcceptedEventExperienceUnit,
    AcceptedProfileViewUnit,
)


MULTI_VIEW_CANDIDATE_ADAPTER_VERSION = "paper1-multi-view-candidate-adapter-v1"


def _validate_unit_source(
    unit: AcceptedAtomicMemoryUnit,
    user: MemorySourceUser,
) -> None:
    try:
        session = user.session_by_id(unit.source_session_id)
    except KeyError:
        raise ValueError("multi-view unit source session is not owned by the target user") from None
    if (
        session.chronological_rank != unit.source_session_rank
        or session.timestamp != unit.timestamp
    ):
        raise ValueError("multi-view unit source session rank/timestamp mismatch")
    turns = {turn.idx: turn for turn in session.turns}
    for span in unit.supporting_spans:
        turn = turns.get(span.turn_index)
        if turn is None or turn.role != "seeker":
            raise ValueError("multi-view source span must bind a seeker-authored turn")
        if span.turn_id != f"{unit.source_session_id}:{span.turn_index}":
            raise ValueError("multi-view source span turn identity mismatch")
        if turn.content[span.start_char : span.end_char] != span.exact_text:
            raise ValueError("multi-view source span text/offset mismatch")


def _candidate(
    *,
    candidate_id: str,
    head: Head,
    content: str,
    owner_id: str,
    source_record_ids: tuple[str, ...],
    observed_at: str,
    token_counter: Callable[[str], int],
    descriptors: dict[str, str | int | float | bool | None],
) -> CandidateRecord:
    tokens = int(token_counter(content))
    if tokens < 1:
        raise ValueError("token_counter must return a positive count")
    return CandidateRecord(
        candidate_id=candidate_id,
        head=head,
        content=content,
        token_count=tokens,
        lineage=CandidateLineage(
            source=MULTI_VIEW_CANDIDATE_ADAPTER_VERSION,
            owner_id=owner_id,
            source_record_ids=source_record_ids,
            strict_past=True,
            observed_at=observed_at,
            content_sha256=sha256_text(content),
        ),
        raw_descriptors=descriptors,
    )


def materialize_multi_view_candidates(
    units: tuple[AcceptedAtomicMemoryUnit, ...],
    *,
    user: MemorySourceUser,
    target: Target,
    token_counter: Callable[[str], int],
) -> dict[Head, tuple[CandidateRecord, ...]]:
    """Build target-time MP, strict-past ME, and full-session MS views.

    Historical MP versions remain in ``units`` for provenance but only the
    latest strict-past value(s) per slot enter the target-time current MP view.
    ME never disappears merely because a later event occurred. MS is compiled
    mechanically from each complete raw session transcript and never from the
    semantic atom stream.
    """

    if user.owner_id != target.owner_id:
        raise ValueError("multi-view candidate target/user owner mismatch")
    eligible = [
        unit
        for unit in units
        if unit.owner_id == target.owner_id and unit.source_session_rank < target.cutoff_rank
    ]
    if any(unit.owner_id != target.owner_id for unit in units):
        raise ValueError("multi-view units cannot cross owners")
    for unit in eligible:
        _validate_unit_source(unit, user)

    profiles: dict[str, list[AcceptedProfileViewUnit]] = defaultdict(list)
    events: list[AcceptedEventExperienceUnit] = []
    for unit in eligible:
        if isinstance(unit, AcceptedProfileViewUnit):
            profiles[unit.profile_slot_key].append(unit)
        else:
            events.append(unit)

    mp: list[CandidateRecord] = []
    for slot_key, slot_units in sorted(profiles.items()):
        latest_rank = max(unit.source_session_rank for unit in slot_units)
        current_units = sorted(
            (unit for unit in slot_units if unit.source_session_rank == latest_rank),
            key=lambda unit: unit.memory_id,
        )
        collision = len({unit.normalized_value for unit in current_units}) > 1
        for unit in current_units:
            mp.append(
                _candidate(
                    candidate_id=f"mp::{unit.memory_id}",
                    head=Head.MP,
                    content=unit.rendered_candidate_content,
                    owner_id=unit.owner_id,
                    source_record_ids=(
                        unit.memory_id,
                        unit.source_session_id,
                        *(span.span_id for span in unit.supporting_spans),
                    ),
                    observed_at=unit.timestamp,
                    token_counter=token_counter,
                    descriptors={
                        "session_chronological_rank": unit.source_session_rank,
                        "mp_profile_field_type": unit.profile_field_type.value,
                        "mp_profile_slot_key": slot_key,
                        "target_time_current_view": True,
                        "same_rank_slot_collision": collision,
                    },
                )
            )

    me = [
        _candidate(
            candidate_id=f"me::{unit.memory_id}",
            head=Head.ME,
            content=unit.rendered_candidate_content,
            owner_id=unit.owner_id,
            source_record_ids=(
                unit.memory_id,
                unit.source_session_id,
                *(span.span_id for span in unit.supporting_spans),
            ),
            observed_at=unit.timestamp,
            token_counter=token_counter,
            descriptors={
                "session_chronological_rank": unit.source_session_rank,
                "me_event_experience_type": unit.event_experience_type.value,
                "me_temporal_status": unit.temporal_status.value,
                "action_observed_outcome_subtype": (
                    unit.event_experience_type.value == "action_observed_outcome"
                ),
            },
        )
        for unit in sorted(
            events,
            key=lambda unit: (
                unit.source_session_rank,
                unit.source_session_id,
                unit.memory_id,
            ),
        )
    ]

    ms = [
        _candidate(
            candidate_id=f"ms::{document.owner_id}::{document.session_id}",
            head=Head.MS,
            content=document.transcript,
            owner_id=document.owner_id,
            source_record_ids=document.source_record_ids,
            observed_at=document.observed_at,
            token_counter=token_counter,
            descriptors={
                "session_id": document.session_id,
                "session_chronological_rank": document.session_chronological_rank,
                "turn_count": document.turn_count,
                "complete_raw_session_transcript": True,
            },
        )
        for document in extract_session_documents(user)
        if document.session_chronological_rank < target.cutoff_rank
    ]
    return {Head.MP: tuple(mp), Head.ME: tuple(me), Head.MS: tuple(ms)}


__all__ = ["MULTI_VIEW_CANDIDATE_ADAPTER_VERSION", "materialize_multi_view_candidates"]
