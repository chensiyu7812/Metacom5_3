"""Session-only, outcome-blind projection for the active compiler."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from metacom_pm.paper1.data.memory_source import Session

from .contracts import (
    AcceptedAtomicMemoryUnit,
    AcceptedProfileViewUnit,
    MultiViewSessionInput,
    PriorCurrentProfileSlot,
    SourceTurn,
)


FORBIDDEN_INPUT_KEY_FRAGMENTS = frozenset(
    {
        "answer",
        "basic_info",
        "evidence",
        "gold",
        "more_details",
        "observation",
        "outcome_label",
        "physical_condition",
        "psychological_condition",
        "question",
        "reference",
        "related_sessions",
        "scorer",
        "subsequent_topic",
        "summary",
        "target",
        "worth",
        "utility",
    }
)
PROMPT_SOURCE_PROJECTION_VERSION = "paper1-multi-view-prompt-source-projection-v2"


def assert_input_firewall(value: Any, *, path: str = "$") -> None:
    if isinstance(value, Mapping):
        for raw_key, nested in value.items():
            key = str(raw_key).strip().casefold()
            if any(fragment in key for fragment in FORBIDDEN_INPUT_KEY_FRAGMENTS):
                raise ValueError(f"active compiler input contains forbidden key at {path}.{raw_key}")
            assert_input_firewall(nested, path=f"{path}.{raw_key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, nested in enumerate(value):
            assert_input_firewall(nested, path=f"{path}[{index}]")


def _current_profile(
    units: tuple[AcceptedAtomicMemoryUnit, ...],
    *,
    owner_id: str,
    current_rank: int,
) -> tuple[PriorCurrentProfileSlot, ...]:
    eligible = [
        unit
        for unit in units
        if isinstance(unit, AcceptedProfileViewUnit)
        and unit.owner_id == owner_id
        and unit.source_session_rank < current_rank
    ]
    if any(unit.owner_id != owner_id for unit in units):
        raise ValueError("prior compiler units cannot cross owners")
    latest: dict[str, AcceptedProfileViewUnit] = {}
    for unit in sorted(eligible, key=lambda row: (row.source_session_rank, row.memory_id)):
        latest[unit.profile_slot_key] = unit
    return tuple(
        PriorCurrentProfileSlot(
            memory_id=unit.memory_id,
            profile_field_type=unit.profile_field_type,
            profile_slot_key=unit.profile_slot_key,
            normalized_value=unit.normalized_value,
            source_session_rank=unit.source_session_rank,
        )
        for _, unit in sorted(latest.items())
    )


def build_session_input(
    *,
    owner_id: str,
    session: Session,
    strictly_past_units: tuple[AcceptedAtomicMemoryUnit, ...] = (),
) -> MultiViewSessionInput:
    projected = MultiViewSessionInput(
        owner_id=owner_id,
        session_id=session.session_id,
        timestamp=session.timestamp,
        chronological_rank=session.chronological_rank,
        turns=tuple(
            SourceTurn(
                turn_id=f"{session.session_id}:{turn.idx}",
                turn_index=turn.idx,
                role=turn.role,
                content=turn.content,
            )
            for turn in session.turns
        ),
        prior_current_profile=_current_profile(
            strictly_past_units,
            owner_id=owner_id,
            current_rank=session.chronological_rank,
        ),
    )
    assert_input_firewall(projected.model_dump(mode="json"))
    return projected


def prompt_source_projection(source: MultiViewSessionInput) -> dict[str, Any]:
    """Remove audit-only prior-slot fields from the provider transport."""

    projected = source.model_dump(mode="json")
    projected["prior_current_profile"] = [
        {
            "t": slot.profile_field_type.value,
            "k": slot.profile_slot_key,
            "v": slot.normalized_value,
        }
        for slot in source.prior_current_profile
    ]
    assert_input_firewall(projected)
    return projected


__all__ = [
    "FORBIDDEN_INPUT_KEY_FRAGMENTS",
    "PROMPT_SOURCE_PROJECTION_VERSION",
    "assert_input_firewall",
    "build_session_input",
    "prompt_source_projection",
]
