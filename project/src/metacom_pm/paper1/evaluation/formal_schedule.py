"""Outcome-blind, arm-balanced ordering for formal local DG judge requests."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any


FORMAL_MISTRAL_SCHEDULE_PROTOCOL = (
    "paper1-official-mistral24b-formal-scoring-schedule-v1"
)
CANONICAL_DG_ARMS = (
    "No_Memory",
    "Full_History",
    "Official_RAG_Top4",
    "Multi_View_Fixed_High",
    "Multi_View_Matched_Random",
    "Learned_Multi_View_PM",
)
MATCHED_UNIT_FIELDS = (
    "owner_id",
    "scenario_id",
    "turn_index",
    "observation_id",
    "judgement_kind",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_arm_balanced_schedule(
    requests: Sequence[Mapping[str, Any]],
    *,
    seed: int = 0,
    canonical_arms: Sequence[str] = CANONICAL_DG_ARMS,
) -> tuple[dict[str, Any], ...]:
    """Return a deterministic matched-unit schedule without reading outcomes.

    Every matched unit must contain exactly one request for every canonical arm.
    Units are hash-ordered, while arms use a cyclic rotation by unit rank. Across
    every complete run of six units, each arm occupies every within-unit position
    once. The scheduler records arm metadata, but callers must not place it in the
    evaluator prompt.
    """

    if not requests:
        raise ValueError("formal schedule requires at least one request")
    arms = tuple(canonical_arms)
    if not arms or len(set(arms)) != len(arms):
        raise ValueError("canonical arms must be non-empty and unique")

    request_ids: set[str] = set()
    grouped: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for row in requests:
        missing = [field for field in (*MATCHED_UNIT_FIELDS, "request_id", "arm", "request_sha256") if field not in row]
        if missing:
            raise ValueError(f"request is missing required fields: {missing}")
        request_id = str(row["request_id"])
        if request_id in request_ids:
            raise ValueError(f"duplicate request_id: {request_id}")
        request_ids.add(request_id)
        grouped[tuple(row[field] for field in MATCHED_UNIT_FIELDS)].append(row)

    ordered_units = sorted(
        grouped,
        key=lambda unit: _digest(f"{seed}\0{_canonical_json(unit)}"),
    )
    output: list[dict[str, Any]] = []
    for unit_rank, unit in enumerate(ordered_units):
        rows = grouped[unit]
        by_arm = {str(row["arm"]): row for row in rows}
        if len(by_arm) != len(rows):
            raise ValueError(f"matched unit has duplicate arm: {unit}")
        if set(by_arm) != set(arms):
            raise ValueError(f"matched unit must contain exactly the canonical arms: {unit}")

        offset = unit_rank % len(arms)
        rotated = arms[offset:] + arms[:offset]
        matched_unit_serialized = _canonical_json(dict(zip(MATCHED_UNIT_FIELDS, unit)))
        matched_unit_id = f"dgjudge_{_digest(matched_unit_serialized)[:24]}"
        for within_unit_position, arm in enumerate(rotated):
            source = dict(by_arm[arm])
            source.update(
                {
                    "schedule_protocol": FORMAL_MISTRAL_SCHEDULE_PROTOCOL,
                    "matched_unit_id": matched_unit_id,
                    "schedule_position": len(output),
                    "within_unit_position": within_unit_position,
                }
            )
            output.append(source)
    return tuple(output)
