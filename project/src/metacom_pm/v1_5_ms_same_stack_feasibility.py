"""Deterministic planning primitives for frozen MS same-stack feasibility."""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
from typing import Any, Mapping, Sequence

from pydantic import Field

from .contracts import StrictModel


PROTOCOL = "pm-v1.5-paper1-ms-same-stack-feasibility-v1"
SELECTION_PROTOCOL = "pm-v1.5-paper1-borderline-ms-same-stack-feasibility-candidate-v1"
POLICIES = ("always_off", "fixed_high_MS", "cross_fitted_learned_MS")


class SameStackGeneratorOutput(StrictModel):
    reply: str = Field(min_length=1)
    used_evidence_ids: list[str]
    realized_response_act: str = Field(min_length=1)


def stable_hex(*parts: object, length: int = 24) -> str:
    body = "\x1f".join(str(part) for part in parts).encode()
    return hashlib.sha256(body).hexdigest()[:length]


def select_fixed_states(
    rows: Sequence[Mapping[str, Any]], *, per_group: int = 4
) -> list[Mapping[str, Any]]:
    by_group: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_group[str(row["split_group_key"])].append(row)
    selected: list[Mapping[str, Any]] = []
    for _, group_rows in sorted(by_group.items()):
        ordered = sorted(
            group_rows,
            key=lambda row: (
                stable_hex(SELECTION_PROTOCOL, row["state_id"], length=64),
                str(row["state_id"]),
            ),
        )
        if len(ordered) < per_group:
            raise ValueError("each connected owner group must provide four states")
        selected.extend(ordered[:per_group])
    return selected


def paired_seed(state_id: str) -> int:
    return 20260811 + int(stable_hex(PROTOCOL, state_id, "seed", length=8), 16) % 1_000_000


def arm_order(state_id: str) -> tuple[str, str]:
    return ("ON", "OFF") if int(stable_hex(PROTOCOL, state_id, "order", length=2), 16) % 2 else ("OFF", "ON")


def validate_frozen_plan(
    physical: Sequence[Mapping[str, Any]], aliases: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    physical_ids = [str(row["physical_call_id"]) for row in physical]
    alias_ids = [str(row["logical_observation_id"]) for row in aliases]
    by_policy = Counter(str(row["policy"]) for row in aliases)
    state_ids = {str(row["state_id"]) for row in physical}
    checks = {
        "68_states": len(state_ids) == 68,
        "136_physical_calls": len(physical) == 136,
        "204_logical_aliases": len(aliases) == 204,
        "unique_physical_ids": len(physical_ids) == len(set(physical_ids)),
        "unique_logical_ids": len(alias_ids) == len(set(alias_ids)),
        "two_physical_actions_per_state": all(
            {str(row["feasible_action_id"]) for row in physical if row["state_id"] == state_id}
            == {"M0+R0", "MS+R0"}
            for state_id in state_ids
        ),
        "68_aliases_each_policy": by_policy == Counter({policy: 68 for policy in POLICIES}),
        "every_alias_resolves": all(
            str(row["physical_call_id"]) in set(physical_ids) for row in aliases
        ),
        "same_seed_within_state": all(
            len({int(row["seed"]) for row in physical if row["state_id"] == state_id}) == 1
            for state_id in state_ids
        ),
        "labels_and_outcomes_absent": all(
            not ({"label", "quality", "risk", "function", "outcome"} & set(row))
            for row in [*physical, *aliases]
        ),
    }
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "policy_alias_counts": dict(by_policy),
    }
