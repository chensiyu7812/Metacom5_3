"""Session-only projection and pre-request leakage firewall."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from metacom_pm.paper1.data.memory_source import Session

from .contracts import (
    AcceptedSemanticMemoryUnit,
    PriorAcceptedMemory,
    SessionCompileInput,
    SessionTurnInput,
)

FORBIDDEN_INPUT_KEY_FRAGMENTS = frozenset(
    {
        "answer",
        "basic_info",
        "evidence",
        "gold",
        "more_details",
        "observation",
        "official_annotation",
        "outcome_label",
        "physical_condition",
        "psychological_condition",
        "question",
        "reference",
        "related_sessions",
        "scorer",
        "social_relationship",
        "subsequent_topic",
        "summary",
        "target",
    }
)


def assert_compiler_input_firewall(value: Any, *, path: str = "$") -> None:
    """Reject evaluator/gold/future-bearing keys before request serialization."""

    if isinstance(value, Mapping):
        for raw_key, nested in value.items():
            key = str(raw_key).strip().lower()
            if any(fragment in key for fragment in FORBIDDEN_INPUT_KEY_FRAGMENTS):
                raise ValueError(f"semantic compiler input contains forbidden key at {path}.{raw_key}")
            assert_compiler_input_firewall(nested, path=f"{path}.{raw_key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, nested in enumerate(value):
            assert_compiler_input_firewall(nested, path=f"{path}[{index}]")


def build_session_compile_input(
    *,
    owner_id: str,
    session: Session,
    strictly_past_accepted_units: tuple[AcceptedSemanticMemoryUnit, ...] = (),
) -> SessionCompileInput:
    """Project one sanitized Session, never the enclosing MemorySourceUser."""

    strictly_past_memory_table = tuple(
        PriorAcceptedMemory(
            memory_id=unit.memory_id,
            owner_id=unit.owner_id,
            source_session_id=unit.source_session_id,
            source_session_rank=unit.source_session_rank,
            memory_class=unit.memory_class,
            memory_subtype=unit.memory_subtype,
            normalized_memory=unit.normalized_memory,
            entities=unit.entities,
            timestamp_status=unit.timestamp_status,
            candidate_source_use=unit.candidate_source_use,
            profile_field_type=unit.profile_field_type,
            continuity_type=unit.continuity_type,
            historical_outcome_type=unit.historical_outcome_type,
        )
        for unit in strictly_past_accepted_units
    )

    projected = SessionCompileInput(
        owner_id=owner_id,
        session_id=session.session_id,
        timestamp=session.timestamp,
        chronological_rank=session.chronological_rank,
        turns=tuple(
            SessionTurnInput(
                turn_id=f"{session.session_id}:turn:{turn.idx}",
                turn_index=turn.idx,
                role=turn.role,
                content=turn.content,
            )
            for turn in session.turns
        ),
        strictly_past_memory_table=strictly_past_memory_table,
    )
    assert_compiler_input_firewall(projected.model_dump(mode="json"))
    return projected
