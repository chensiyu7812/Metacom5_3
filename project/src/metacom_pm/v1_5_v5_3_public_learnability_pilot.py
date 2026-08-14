"""Outcome-blind materialization for the V5.3 public-data learnability pilot.

The pilot freezes 24 same-state ON/OFF groups for each of MP/MS/ME/RS.
Memory groups come from EvoEmo users p12/p13/p18; RS groups come from
quarantined-clean ESConv train dialogues.  Selection sees only runtime
features and candidate lineage, never a generated response or effect label.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import json
from typing import Any, Mapping, Sequence

from .contracts import MemoryItem, MemorySource, StrategyCard
from .io import canonical_json, sha256_file, stable_hex
from .text import estimate_tokens
from .v1_5_candidate_discovery import discover_final_typed_memory_candidates
from .v1_5_v5_2_atomic_memory import compile_atomic_reusable_outcome, me_subtype_hints
from .v1_5_v5_3_candidate_layer_responsibility import (
    rs_mechanical_candidate_pool,
    rs_shared_candidate_top1,
)
from .v1_5_v5_3_contribution_slot_features import (
    me_contribution_slots,
    mp_contribution_slots,
    ms_contribution_slots,
    rs_contribution_slots,
)
from .v1_5_v5_3_public_backbone import (
    _chronological_users,
    _event_items_by_session,
    _exact_me_items,
    _memory_id,
    _official_ms_items,
    _relationship_items_by_session,
)
from .v1_5b_policy_runtime import compile_component_bits


PROTOCOL = "pm-v1.5-v5.3-public-learnability-pilot-v1"
PILOT_USERS = ("p12", "p13", "p18")
COMPONENTS = ("MP", "MS", "ME", "RS")
GROUPS_PER_COMPONENT = 24
PAIRED_REPLICATES = 3


def _clean(value: object) -> str:
    return " ".join(str(value or "").split())


def _bucket(value: float, boundaries: Sequence[float]) -> int:
    for index, boundary in enumerate(boundaries):
        if value <= boundary:
            return index
    return len(boundaries)


def _state_id(*parts: object) -> str:
    return "state_" + stable_hex(PROTOCOL, *parts, n=24)


def _group_id(*parts: object) -> str:
    return "effect_" + stable_hex(PROTOCOL, *parts, n=24)


def _slots_dict(value: object) -> dict[str, Any]:
    return dict(vars(value))


def _memory_candidate_payload(
    *, component: str, item: MemoryItem, subtype: str, user_id: str,
    current_session_index: int,
) -> dict[str, Any]:
    base = {
        "component": component,
        "resource_id": item.memory_id,
        "candidate_version": "v1",
        "owner_id": user_id,
        "strictly_prior": item.created_session < current_session_index,
        "age_sessions": current_session_index - item.created_session,
    }
    if component == "MP":
        return {
            **base,
            "subtype": "MP_PROFILE",
            "source_kind": "profile",
            "profile_fact": item.text,
        }
    if component == "MS":
        return {
            **base,
            "subtype": "MS_SESSION_OBSERVATION",
            "source_kind": "session",
            "prior_observation": item.text,
        }
    compiled = compile_atomic_reusable_outcome(item.text)
    if subtype == "reusable_action_result" and compiled is not None:
        return {
            **base,
            "subtype": "ME_REUSABLE_OUTCOME",
            "source_kind": "event",
            "past_action": compiled.past_action_span,
            "observed_outcome": compiled.observed_outcome_span,
        }
    return {
        **base,
        "subtype": "ME_CONTEXT_EVENT",
        "source_kind": "event",
        "past_event": item.text,
    }


def materialize_memory_pool(
    evoemo_path: Path, *, user_ids: Sequence[str] = PILOT_USERS,
) -> dict[str, list[dict[str, Any]]]:
    """Return every executable actual-Rank1 state for the requested users."""

    raw = json.loads(evoemo_path.read_text(encoding="utf-8"))
    requested_users = tuple(str(user_id) for user_id in user_ids)
    users = {
        str(user["id"]): user
        for user in _chronological_users(raw)
        if str(user["id"]) in requested_users
    }
    if set(users) != set(requested_users):
        raise ValueError("requested user set is incomplete")
    pools: dict[str, list[dict[str, Any]]] = {key: [] for key in ("MP", "MS", "ME")}

    for user_id in requested_users:
        user = users[user_id]
        prior: list[MemoryItem] = []
        item_types: dict[str, str] = {}
        for field, value in (user.get("basic_info") or {}).items():
            if field == "name":
                continue
            item = MemoryItem(
                memory_id=_memory_id(user_id, "MP_BASIC", field),
                source=MemorySource.MP,
                created_session=0,
                text=f"{field.replace('_', ' ').title()}: {value}",
            )
            prior.append(item)
            item_types[item.memory_id] = "onboarding_profile"

        sessions = list(user["dialog_history"])
        session_index_by_id = {
            str(session["id"]): index
            for index, session in enumerate(sessions, start=1)
        }
        relationships = _relationship_items_by_session(user, session_index_by_id)
        events = _event_items_by_session(user, session_index_by_id)
        for session_index, session in enumerate(sessions, start=1):
            visible: list[dict[str, str]] = []
            seeker_ordinal = 0
            for turn in session.get("dialogue") or []:
                role = "user" if turn.get("role") == "seeker" else "assistant"
                text = _clean(turn.get("content"))
                if not text:
                    continue
                visible.append({"role": role, "content": text})
                if role != "user":
                    continue
                seeker_ordinal += 1
                discoveries = discover_final_typed_memory_candidates(
                    queries={source: text for source in MemorySource},
                    items=prior,
                    source_metadata=me_subtype_hints(prior),
                    session_index=session_index,
                )
                for source in MemorySource:
                    discovery = discoveries[source]
                    if not discovery.selected_items:
                        continue
                    item = discovery.selected_items[0]
                    subtype = item_types[item.memory_id]
                    component = source.value
                    source_items = [candidate for candidate in prior if candidate.source is source]
                    if component == "MP":
                        slots = mp_contribution_slots(
                            current_user_text=text,
                            candidate_text=item.text,
                            candidate_is_preference=False,
                            source_items=source_items,
                            selected_items=discovery.selected_items,
                            session_index=session_index,
                        )
                    elif component == "MS":
                        slots = ms_contribution_slots(
                            current_user_text=text,
                            candidate_text=item.text,
                            source_items=source_items,
                            selected_items=discovery.selected_items,
                            session_index=session_index,
                        )
                    else:
                        slots = me_contribution_slots(
                            current_user_text=text,
                            candidate_text=item.text,
                            source_items=source_items,
                            selected_items=discovery.selected_items,
                            session_index=session_index,
                        )
                    slot_payload = _slots_dict(slots)
                    slot_payload["candidate_subtype"] = subtype
                    state_id = _state_id(user_id, session["id"], turn.get("idx"), component)
                    row = {
                        "protocol": PROTOCOL,
                        "state_id": state_id,
                        "component": component,
                        "source_dataset": "EvoEmo",
                        "user_id": user_id,
                        "session_id": str(session["id"]),
                        "session_index": session_index,
                        "turn_id": turn.get("idx"),
                        "seeker_ordinal": seeker_ordinal,
                        "visible_dialogue": list(visible),
                        "current_user_text": text,
                        "candidate_type": subtype,
                        "candidate_text": item.text,
                        "candidate": _memory_candidate_payload(
                            component=component,
                            item=item,
                            subtype=subtype,
                            user_id=user_id,
                            current_session_index=session_index,
                        ),
                        "candidate_descriptor": discovery.descriptor,
                        "model_features": slot_payload,
                        "outcome_or_response_read": False,
                    }
                    pools[component].append(row)

            session_id = str(session["id"])
            for item, subtype in _official_ms_items(session, session_index, user_id):
                prior.append(item)
                item_types[item.memory_id] = subtype
            for item, subtype in relationships.get(session_id, []):
                prior.append(item)
                item_types[item.memory_id] = subtype
            for item, subtype in events.get(session_id, []):
                prior.append(item)
                item_types[item.memory_id] = subtype
            for item in _exact_me_items(session, session_index, user_id):
                prior.append(item)
                item_types[item.memory_id] = "reusable_action_result"
    return pools


def materialize_rs_pool(
    *, esconv_path: Path, manifest_path: Path, cards_path: Path,
) -> list[dict[str, Any]]:
    esconv = json.loads(esconv_path.read_text(encoding="utf-8"))
    manifest = [
        json.loads(line)
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    cards = [
        StrategyCard.model_validate(json.loads(line))
        for line in cards_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    rows: list[dict[str, Any]] = []
    for manifest_row in manifest:
        if manifest_row["excluded_for_evoemo_overlap"] or manifest_row["split"] != "train":
            continue
        dialogue_id = str(manifest_row["dialogue_id"])
        visible: list[dict[str, str]] = []
        seeker_ordinal = 0
        turns = esconv[int(manifest_row["index"])].get("dialog") or []
        for turn_index, turn in enumerate(turns):
            role = "user" if turn.get("speaker") == "seeker" else "assistant"
            content = _clean(turn.get("content"))
            if not content:
                continue
            visible.append({"role": role, "content": content})
            if role != "user":
                continue
            seeker_ordinal += 1
            pool = rs_mechanical_candidate_pool(recent_dialogue=visible, cards=cards)
            shared = rs_shared_candidate_top1(pool)
            if shared is None:
                continue
            obs = shared.observation
            slots = _slots_dict(
                rs_contribution_slots(
                    current_user_text=content,
                    recent_dialogue=visible,
                    move_id=obs.move_id,
                    already_executed_last_turn=False,
                )
            )
            slots.update({f"observable_{key}": value for key, value in pool.observable_flags.items()})
            phase = float(turn_index + 1) / max(1.0, float(len(turns)))
            slots["candidate_subtype"] = obs.move_id
            slots["dialogue_phase_bucket"] = _bucket(phase, (0.33, 0.67))
            slots["selection_mode"] = shared.selection_mode
            rows.append(
                {
                    "protocol": PROTOCOL,
                    "state_id": _state_id(dialogue_id, turn_index, "RS"),
                    "component": "RS",
                    "source_dataset": "ESConv",
                    "dialogue_id": dialogue_id,
                    "esconv_index": int(manifest_row["index"]),
                    "split": "train",
                    "turn_index": turn_index,
                    "seeker_ordinal": seeker_ordinal,
                    "dialogue_turn_count": len(turns),
                    "visible_dialogue": list(visible),
                    "current_user_text": content,
                    "candidate_type": obs.move_id,
                    "candidate_text": obs.strategy_card.guidance_text,
                    "candidate": {
                        "component": "RS",
                        "subtype": "RS_ATOMIC_MOVE",
                        "resource_id": obs.strategy_card.strategy_id,
                        "candidate_version": "v1",
                        "source_kind": "strategy",
                        "support_move": obs.strategy_card.guidance_text,
                        "when_to_use": obs.strategy_card.retrieval_text,
                        "when_not_to_use": "Follow the boundaries in the frozen card.",
                    },
                    "selection_mode": shared.selection_mode,
                    "transparent_rule_on": shared.transparent_rule_on,
                    "lexical_relevance": obs.lexical_relevance,
                    "model_features": slots,
                    "outcome_or_response_read": False,
                }
            )
    return rows


def _memory_stratum(row: Mapping[str, Any]) -> tuple[Any, ...]:
    features = row["model_features"]
    return (
        row["candidate_type"],
        _bucket(float(features.get("topk_top1_lexical_relevance") or 0.0), (0.08, 0.18, 0.35)),
        _bucket(float(features.get("rank1_relative_age") or 0.0), (0.15, 0.35, 0.65)),
        bool(features.get("current_redundant")),
        str(features.get("current_action_readiness") or ""),
        bool(features.get("continuity_request")),
        bool(features.get("profile_goal_needs_advice_or_arrangement")),
    )


def _rs_stratum(row: Mapping[str, Any]) -> tuple[Any, ...]:
    flags = row["model_features"]
    phase = float(row["turn_index"] + 1) / max(1.0, float(row["dialogue_turn_count"]))
    return (
        row["candidate_type"],
        row["selection_mode"],
        _bucket(phase, (0.33, 0.67)),
        bool(flags.get("observable_explicit_advice_welcome")),
        bool(flags.get("observable_question_repetition_block")),
    )


def _greedy_select(
    rows: Sequence[dict[str, Any]], *, n: int, key_fn, cluster_key: str,
    cluster_quota: Mapping[str, int] | None = None,
) -> list[dict[str, Any]]:
    remaining = sorted(rows, key=lambda row: stable_hex(PROTOCOL, row["state_id"], n=24))
    selected: list[dict[str, Any]] = []
    used_values: list[set[Any]] = []
    cluster_counts: Counter[str] = Counter()
    used_sessions: set[tuple[str, str]] = set()
    while remaining and len(selected) < n:
        best_index = -1
        best_score: tuple[float, str] | None = None
        for index, row in enumerate(remaining):
            cluster = str(row[cluster_key])
            if cluster_quota is not None and cluster_counts[cluster] >= cluster_quota[cluster]:
                continue
            key = key_fn(row)
            while len(used_values) < len(key):
                used_values.append(set())
            novelty = sum(8.0 / (1.0 + len(values)) for value, values in zip(key, used_values) if value not in values)
            session_key = (cluster, str(row.get("session_id") or row.get("dialogue_id")))
            novelty += 4.0 if session_key not in used_sessions else 0.0
            score = (novelty, stable_hex(row["state_id"], n=24))
            if best_score is None or score > best_score:
                best_score, best_index = score, index
        if best_index < 0:
            break
        row = remaining.pop(best_index)
        selected.append(row)
        cluster = str(row[cluster_key])
        cluster_counts[cluster] += 1
        used_sessions.add((cluster, str(row.get("session_id") or row.get("dialogue_id"))))
        for value, values in zip(key_fn(row), used_values):
            values.add(value)
    if len(selected) != n:
        raise ValueError(f"could only select {len(selected)} of {n} required states")
    return selected


def select_pilot_groups(
    memory_pools: Mapping[str, Sequence[dict[str, Any]]],
    rs_pool: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    quota = {user: GROUPS_PER_COMPONENT // len(PILOT_USERS) for user in PILOT_USERS}
    for component in ("MP", "MS", "ME"):
        selected.extend(
            _greedy_select(
                memory_pools[component], n=GROUPS_PER_COMPONENT,
                key_fn=_memory_stratum, cluster_key="user_id", cluster_quota=quota,
            )
        )
    # One state per independent ESConv dialogue for the RS pilot.
    selected.extend(
        _greedy_select(
            rs_pool, n=GROUPS_PER_COMPONENT, key_fn=_rs_stratum,
            cluster_key="dialogue_id",
            cluster_quota={str(row["dialogue_id"]): 1 for row in rs_pool},
        )
    )
    for row in selected:
        component = str(row["component"])
        group_id = _group_id(row["state_id"], component)
        row["effect_group_id"] = group_id
        row["off_action_id"] = compile_component_bits({key: False for key in COMPONENTS})
        row["on_action_id"] = compile_component_bits(
            {key: key == component for key in COMPONENTS}
        )
        row["paired_generator_seeds"] = [
            int(stable_hex(PROTOCOL, group_id, "paired_seed", replicate, n=8), 16)
            & 0x7FFFFFFF
            for replicate in range(PAIRED_REPLICATES)
        ]
    return selected


def add_frozen_semantic_similarity(
    rows: Sequence[dict[str, Any]], *, encoder: Any,
) -> None:
    """Attach one frozen BGE candidate-state cosine feature per group."""
    import numpy as np

    texts: list[str] = []
    for row in rows:
        texts.extend((str(row["current_user_text"]), str(row["candidate_text"])))
    vectors = encoder.encode(texts)
    if len(vectors) != len(texts):
        raise ValueError("semantic encoder returned the wrong row count")
    for index, row in enumerate(rows):
        left, right = vectors[2 * index], vectors[2 * index + 1]
        score = float(np.dot(left, right))
        row["model_features"]["candidate_state_bge_m3_cosine"] = round(score, 8)


def estimate_call_budget(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    groups = len(rows)
    generator_calls = groups * PAIRED_REPLICATES * 2
    # Three replicate pairs are judged together: AB and BA contribution,
    # one absolute-arm risk call, and one functional-use call.
    judge_calls = groups * 4
    base_generation_tokens = 700
    output_tokens_per_generation = 512
    generator_input = 0
    for row in rows:
        context_tokens = estimate_tokens(canonical_json(row["visible_dialogue"]))
        candidate_tokens = estimate_tokens(str(row["candidate_text"]))
        generator_input += PAIRED_REPLICATES * (
            2 * (base_generation_tokens + context_tokens) + candidate_tokens
        )
    generator_output = generator_calls * output_tokens_per_generation
    # Conservative grouped-judge ceilings, not an invoice.
    judge_input = groups * (2 * 2700 + 3000 + 2200)
    judge_output = groups * (2 * 700 + 1200 + 700)
    return {
        "effect_groups": groups,
        "paired_replicates_per_group": PAIRED_REPLICATES,
        "generator_calls": generator_calls,
        "judge_calls": judge_calls,
        "base_calls": generator_calls + judge_calls,
        "maximum_retry_calls_10_percent": (generator_calls + judge_calls + 9) // 10,
        "hard_call_cap": generator_calls + judge_calls + (generator_calls + judge_calls + 9) // 10,
        "estimated_generator_input_tokens": generator_input,
        "maximum_generator_output_tokens": generator_output,
        "maximum_judge_input_tokens": judge_input,
        "maximum_judge_output_tokens": judge_output,
        "usd_not_frozen": False,
    }


def audit_pilot(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    component_counts = Counter(str(row["component"]) for row in rows)
    seed_count_ok = all(len(row["paired_generator_seeds"]) == 3 for row in rows)
    semantic = [
        float(row["model_features"].get("candidate_state_bge_m3_cosine", 0.0))
        for row in rows
    ]
    user_counts = {
        component: Counter(
            str(row["user_id"])
            for row in rows
            if row["component"] == component
        )
        for component in ("MP", "MS", "ME")
    }
    duplicate_ids = len(rows) - len({str(row["state_id"]) for row in rows})
    chronology_errors = sum(
        row["component"] != "RS"
        and not bool(row["candidate"].get("strictly_prior"))
        and row["candidate"]["subtype"] not in {"MP_PROFILE", "MP_PREFERENCE"}
        for row in rows
    )
    checks = {
        "96_groups_exactly": len(rows) == 96,
        "24_groups_per_head": all(component_counts[key] == 24 for key in COMPONENTS),
        "memory_heads_8_groups_per_pilot_user": all(
            user_counts[component][user] == 8
            for component in ("MP", "MS", "ME") for user in PILOT_USERS
        ),
        "rs_24_independent_dialogues": len({row.get("dialogue_id") for row in rows if row["component"] == "RS"}) == 24,
        "no_duplicate_state_ids": duplicate_ids == 0,
        "strict_chronology": chronology_errors == 0,
        "three_frozen_paired_seeds": seed_count_ok,
        "semantic_feature_present_and_variable": len(set(semantic)) >= 8,
        "outcome_blind": all(not row["outcome_or_response_read"] for row in rows),
    }
    return {
        "protocol": PROTOCOL,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "component_counts": dict(component_counts),
        "memory_user_counts": {key: dict(value) for key, value in user_counts.items()},
        "candidate_type_counts": {
            component: dict(Counter(str(row["candidate_type"]) for row in rows if row["component"] == component))
            for component in COMPONENTS
        },
        "semantic_similarity": {
            "minimum": min(semantic) if semantic else None,
            "maximum": max(semantic) if semantic else None,
            "distinct_rounded_values": len(set(semantic)),
        },
        "api_calls": 0,
    }


def source_hashes(paths: Mapping[str, Path]) -> dict[str, str]:
    return {name: sha256_file(path) for name, path in paths.items()}
