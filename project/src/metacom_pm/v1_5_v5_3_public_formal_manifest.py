"""Outcome-blind materialization of the frozen 576-group public formal panel."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any, Mapping, Sequence

from .io import stable_hex
from .v1_5_typed_resource_adapter import TypedResourceCandidate
from .v1_5_v5_3_public_learnability_pilot import (
    COMPONENTS,
    PAIRED_REPLICATES,
    _greedy_select,
    _memory_stratum,
    _rs_stratum,
)
from .v1_5b_policy_runtime import compile_component_bits


PROTOCOL = "pm-v1.5-v5.3-public-formal-effect-manifest-v1"
GROUPS_PER_COMPONENT = 144
MEMORY_GROUPS_PER_USER = 8
RS_MOVE_QUOTAS = {
    "AM02_ask_one_focused_clarification": 12,
    "AM01_invite_open_expression": 27,
    "AM04_tentative_paraphrase_check": 27,
    "AM05_grounded_validation": 27,
    "AM10_offer_one_optional_micro_step": 27,
    "AM14_supportive_transition": 24,
}


def _fold_maps(outer_folds: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for row in outer_folds:
        fold = int(row["fold"])
        for user_id in row["held_out_users"]:
            if str(user_id) in mapping:
                raise ValueError("user occurs in multiple outer folds")
            mapping[str(user_id)] = fold
    return mapping


def select_formal_groups(
    *, memory_pools: Mapping[str, Sequence[dict[str, Any]]],
    rs_pool: Sequence[dict[str, Any]], development_rows: Sequence[Mapping[str, Any]],
    outer_folds: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    development_state_ids = {str(row["state_id"]) for row in development_rows}
    development_dialogues = {
        str(row["dialogue_id"])
        for row in development_rows if row["component"] == "RS"
    }
    fold_by_user = _fold_maps(outer_folds)
    users = tuple(sorted(fold_by_user))
    if len(users) != 18:
        raise ValueError("formal memory panel requires exactly 18 users")

    selected: list[dict[str, Any]] = []
    for component in ("MP", "MS", "ME"):
        eligible = [
            row for row in memory_pools[component]
            if str(row["state_id"]) not in development_state_ids
        ]
        for user_id in users:
            user_rows = [row for row in eligible if str(row["user_id"]) == user_id]
            picked = _greedy_select(
                user_rows, n=MEMORY_GROUPS_PER_USER,
                key_fn=_memory_stratum, cluster_key="user_id",
                cluster_quota={user_id: MEMORY_GROUPS_PER_USER},
            )
            for row in picked:
                copied = deepcopy(row)
                copied["outer_fold"] = fold_by_user[user_id]
                selected.append(copied)

    rs_eligible = [
        row for row in rs_pool
        if str(row["dialogue_id"]) not in development_dialogues
    ]
    # Balance the six frozen move families before outcomes exist.  Clarification
    # has only 15 eligible dialogue clusters, so its conservative quota is 12;
    # the other five absorb the remainder without changing actual Rank-1.
    rs_selected: list[dict[str, Any]] = []
    used_dialogues: set[str] = set()
    for move_id, quota in RS_MOVE_QUOTAS.items():
        move_rows = [
            row for row in rs_eligible
            if row["candidate_type"] == move_id
            and str(row["dialogue_id"]) not in used_dialogues
        ]
        picked = _greedy_select(
            move_rows, n=quota, key_fn=_rs_stratum,
            cluster_key="dialogue_id",
            cluster_quota={str(row["dialogue_id"]): 1 for row in move_rows},
        )
        rs_selected.extend(picked)
        used_dialogues.update(str(row["dialogue_id"]) for row in picked)
    # A deterministic 24-dialogue held-out block per RS fold.
    for index, row in enumerate(sorted(rs_selected, key=lambda item: stable_hex(PROTOCOL, item["dialogue_id"], n=24))):
        copied = deepcopy(row)
        copied["outer_fold"] = index // 24 + 1
        selected.append(copied)

    for row in selected:
        source_state_id = str(row["state_id"])
        component = str(row["component"])
        row["protocol"] = PROTOCOL
        row["source_state_id"] = source_state_id
        row["state_id"] = "formal_state_" + stable_hex(PROTOCOL, source_state_id, n=24)
        row["effect_group_id"] = "formal_effect_" + stable_hex(
            PROTOCOL, row["state_id"], component, n=24,
        )
        row["off_action_id"] = compile_component_bits({key: False for key in COMPONENTS})
        row["on_action_id"] = compile_component_bits({key: key == component for key in COMPONENTS})
        row["paired_generator_seeds"] = [
            int(stable_hex(PROTOCOL, row["effect_group_id"], "paired_seed", replicate, n=8), 16)
            & 0x7FFFFFFF
            for replicate in range(PAIRED_REPLICATES)
        ]
        row["development_state_excluded_before_selection"] = True
        row["outcome_or_response_read"] = False
    return selected


def audit_formal_manifest(
    rows: Sequence[Mapping[str, Any]], *, development_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    components = Counter(str(row["component"]) for row in rows)
    memory_user_counts = {
        component: Counter(str(row["user_id"]) for row in rows if row["component"] == component)
        for component in ("MP", "MS", "ME")
    }
    rs_folds = Counter(int(row["outer_fold"]) for row in rows if row["component"] == "RS")
    rs_moves = Counter(str(row["candidate_type"]) for row in rows if row["component"] == "RS")
    development_source_ids = {str(row["state_id"]) for row in development_rows}
    typed_errors = []
    for row in rows:
        try:
            TypedResourceCandidate(**row["candidate"])
        except Exception as exc:  # pragma: no cover - emitted in audit artifact
            typed_errors.append({"effect_group_id": row["effect_group_id"], "error": str(exc)})
    checks = {
        "576_groups_exactly": len(rows) == 576,
        "144_groups_per_head": all(components[key] == 144 for key in COMPONENTS),
        "memory_18_users_times_8": all(
            len(memory_user_counts[component]) == 18
            and all(count == 8 for count in memory_user_counts[component].values())
            for component in ("MP", "MS", "ME")
        ),
        "rs_144_distinct_dialogues": len({row["dialogue_id"] for row in rows if row["component"] == "RS"}) == 144,
        "rs_prefrozen_move_quotas": rs_moves == Counter(RS_MOVE_QUOTAS),
        "rs_24_dialogues_per_fold": rs_folds == Counter({fold: 24 for fold in range(1, 7)}),
        "development_states_excluded": not any(
            str(row["source_state_id"]) in development_source_ids for row in rows
        ),
        "unique_state_and_effect_ids": (
            len({row["state_id"] for row in rows}) == len(rows)
            and len({row["effect_group_id"] for row in rows}) == len(rows)
        ),
        "three_paired_seeds": all(len(row["paired_generator_seeds"]) == 3 for row in rows),
        "all_candidates_typed_executable": not typed_errors,
        "outcome_blind": all(not row["outcome_or_response_read"] for row in rows),
    }
    return {
        "protocol": PROTOCOL,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "component_counts": dict(components),
        "memory_user_counts": {key: dict(value) for key, value in memory_user_counts.items()},
        "rs_fold_counts": dict(rs_folds),
        "candidate_type_counts": {
            component: dict(Counter(str(row["candidate_type"]) for row in rows if row["component"] == component))
            for component in COMPONENTS
        },
        "typed_errors": typed_errors,
        "api_calls": 0,
    }
