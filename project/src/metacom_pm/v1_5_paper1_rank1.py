"""Outcome-blind actual Rank-1 materialization for Paper 1 P1B.

The selectors in this module may read only the completed P1 structural state,
the strictly-past same-owner candidate catalog, and the frozen six-card RS
bank.  They never read suitability labels, response outcomes, QA gold, or a
future session.  A missing candidate is an observed retrieval condition, not
a negative suitability label.
"""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .contracts import StrategyCard
from .text import lexical_score
from .v1_5_candidate_discovery import final_typed_content_match_level
from .v1_5_v5_2_atomic_memory import compile_atomic_reusable_outcome
from .v1_5_v5_3_candidate_layer_responsibility import (
    rs_mechanical_candidate_pool,
    rs_shared_candidate_top1,
)


PAPER1_RANK1_PROTOCOL = "pm-v1.5-paper1-p1b-actual-rank1-v1"

# Applicability scopes name situations in which a stored profile field could
# change a response.  They intentionally exclude each user's field value: a
# user need not repeat "office worker" for the job profile to become eligible.
# These six fields are exactly the six non-name EvoEmo basic_info fields.
MP_PROFILE_SCOPE_V1: dict[str, str] = {
    "age": (
        "age ages aged birthday birthdays older younger youth adult adulthood "
        "teenager retirement retired generation"
    ),
    "education": (
        "education school study studies studying student college university "
        "degree class classes academic campus graduate graduation"
    ),
    "gender": "gender identity woman women man men female male nonbinary",
    "job": (
        "job jobs work works working workplace office employer employment "
        "career careers colleague colleagues coworker coworkers boss manager "
        "shift profession professional occupation"
    ),
    "location": (
        "location city local locally neighborhood travel commute commuting "
        "timezone town state country home moved moving relocate relocation"
    ),
    "nationality": (
        "nationality country culture cultural language languages immigration "
        "immigrant visa homeland abroad"
    ),
}


def _compact(value: Any) -> str:
    return " ".join(str(value or "").split())


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _candidate_base(
    *,
    state: Mapping[str, Any],
    component: str,
    pool_count: int,
) -> dict[str, Any]:
    return {
        "protocol": PAPER1_RANK1_PROTOCOL,
        "dataset": str(state["dataset"]),
        "state_id": str(state["state_id"]),
        "component": component,
        "runtime_owner_key": str(state["runtime_owner_key"]),
        "split_group_key": str(state["split_group_key"]),
        "split": state.get("split"),
        "outer_fold": state.get("outer_fold"),
        "strict_past_pool_count": int(pool_count),
        "candidate_present": False,
        "actual_rank1_id": None,
        "actual_rank1_increment_sha256": None,
        "candidate_source_session_id": None,
        "candidate_source_turn_index": None,
        "candidate_available_after_session_index": None,
        "selection_method": None,
        "selection_score": None,
        "top1_top2_margin": None,
        "hard_off_reason": None,
        "retrieval_observations": {},
        "suitability_label": None,
    }


def _selected_memory_row(
    *,
    state: Mapping[str, Any],
    component: str,
    pool_count: int,
    candidate: Mapping[str, Any],
    method: str,
    score: float,
    margin: float,
    observations: Mapping[str, Any],
) -> dict[str, Any]:
    row = _candidate_base(state=state, component=component, pool_count=pool_count)
    row.update(
        {
            "candidate_present": True,
            "actual_rank1_id": str(candidate["candidate_id"]),
            "actual_rank1_increment_sha256": _sha_text(
                _compact(candidate["literal_text"])
            ),
            "candidate_source_session_id": candidate.get("source_session_id"),
            "candidate_source_turn_index": candidate.get("source_turn_index"),
            "candidate_available_after_session_index": int(
                candidate["available_after_session_index"]
            ),
            "selection_method": method,
            "selection_score": float(score),
            "top1_top2_margin": float(margin),
            "retrieval_observations": dict(observations),
        }
    )
    return row


def eligible_strict_past_candidates(
    state: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    component: str,
) -> list[Mapping[str, Any]]:
    """Return only same-owner candidates opened before the current session."""

    if str(state["dataset"]) != "EvoEmo":
        return []
    session_index = int(state["source_session_index"])
    owner = str(state["runtime_owner_key"])
    return [
        row
        for row in candidates
        if str(row["runtime_owner_key"]) == owner
        and str(row["component"]) == component
        and int(row["available_after_session_index"]) < session_index
    ]


def rank_mp(
    state: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    eligible = eligible_strict_past_candidates(state, candidates, "MP")
    query = _compact(state["current_user_text"])
    ranked: list[tuple[float, float, int, str, Mapping[str, Any]]] = []
    for candidate in eligible:
        field = str(candidate.get("profile_field") or "")
        if field not in MP_PROFILE_SCOPE_V1:
            raise ValueError(f"unfrozen MP profile field: {field!r}")
        scope_score = final_typed_content_match_level(
            query, MP_PROFILE_SCOPE_V1[field]
        )
        if scope_score <= 0.0:
            continue
        surface_score = lexical_score(query, str(candidate["literal_text"]))
        ranked.append(
            (
                float(scope_score),
                float(surface_score),
                int(candidate["available_after_session_index"]),
                str(candidate["candidate_id"]),
                candidate,
            )
        )
    ranked.sort(key=lambda row: row[:4], reverse=True)
    if not ranked:
        row = _candidate_base(state=state, component="MP", pool_count=len(eligible))
        row["hard_off_reason"] = "no_profile_scope_match"
        row["selection_method"] = "frozen_profile_scope_v1"
        return row
    top = ranked[0]
    second_scope = ranked[1][0] if len(ranked) > 1 else 0.0
    return _selected_memory_row(
        state=state,
        component="MP",
        pool_count=len(eligible),
        candidate=top[4],
        method="frozen_profile_scope_v1",
        score=top[0],
        margin=top[0] - second_scope,
        observations={
            "profile_field": str(top[4]["profile_field"]),
            "scope_match_level": top[0],
            "literal_surface_lexical_score": top[1],
        },
    )


def rank_ms_from_vectors(
    state: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
    *,
    query_vector: Any,
    candidate_vectors: Mapping[str, Any],
) -> dict[str, Any]:
    """BGE-M3 cosine Rank-1 over the full strictly-past MS pool."""

    eligible = eligible_strict_past_candidates(state, candidates, "MS")
    if not eligible:
        row = _candidate_base(state=state, component="MS", pool_count=0)
        row["hard_off_reason"] = "no_strictly_past_ms"
        row["selection_method"] = "bge_m3_full_ms_pool_v1"
        return row
    ranked: list[tuple[float, int, str, Mapping[str, Any]]] = []
    for candidate in eligible:
        candidate_id = str(candidate["candidate_id"])
        if candidate_id not in candidate_vectors:
            raise ValueError(f"missing MS vector: {candidate_id}")
        score = float(query_vector @ candidate_vectors[candidate_id])
        ranked.append(
            (
                score,
                int(candidate["available_after_session_index"]),
                candidate_id,
                candidate,
            )
        )
    ranked.sort(key=lambda row: row[:3], reverse=True)
    top = ranked[0]
    second = ranked[1][0] if len(ranked) > 1 else 0.0
    return _selected_memory_row(
        state=state,
        component="MS",
        pool_count=len(eligible),
        candidate=top[3],
        method="bge_m3_full_ms_pool_v1",
        score=top[0],
        margin=top[0] - second,
        observations={"semantic_encoder_scope": "MS_only"},
    )


def rank_me(
    state: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Typed lexical ME Rank-1; an invalid Rank-1 is OFF, never Rank-2."""

    eligible = eligible_strict_past_candidates(state, candidates, "ME")
    query = _compact(state["current_user_text"])
    ranked: list[tuple[float, float, int, str, Mapping[str, Any]]] = []
    for candidate in eligible:
        match = final_typed_content_match_level(query, str(candidate["literal_text"]))
        if match <= 0.0:
            continue
        ranked.append(
            (
                float(match),
                float(lexical_score(query, str(candidate["literal_text"]))),
                int(candidate["available_after_session_index"]),
                str(candidate["candidate_id"]),
                candidate,
            )
        )
    ranked.sort(key=lambda row: row[:4], reverse=True)
    if not ranked:
        row = _candidate_base(state=state, component="ME", pool_count=len(eligible))
        row["hard_off_reason"] = (
            "no_strictly_past_me" if not eligible else "no_me_content_overlap"
        )
        row["selection_method"] = "typed_content_lexical_rank1_v1"
        return row
    top = ranked[0]
    compiler_valid = compile_atomic_reusable_outcome(
        str(top[4]["literal_text"])
    ) is not None
    if not compiler_valid:
        row = _candidate_base(state=state, component="ME", pool_count=len(eligible))
        row["hard_off_reason"] = "actual_rank1_compiler_invalid_no_rank2"
        row["selection_method"] = "typed_content_lexical_rank1_v1"
        row["selection_score"] = top[0]
        row["retrieval_observations"] = {
            "actual_rank1_compiler_valid": False,
            "rank2_promoted": False,
        }
        return row
    second = ranked[1][0] if len(ranked) > 1 else 0.0
    return _selected_memory_row(
        state=state,
        component="ME",
        pool_count=len(eligible),
        candidate=top[4],
        method="typed_content_lexical_rank1_v1",
        score=top[0],
        margin=top[0] - second,
        observations={
            "actual_rank1_compiler_valid": True,
            "rank2_promoted": False,
            "literal_surface_lexical_score": top[1],
        },
    )


def rank_rs(
    state: Mapping[str, Any],
    cards: Sequence[StrategyCard],
) -> dict[str, Any]:
    visible = (
        state["visible_dialogue"]
        if str(state["dataset"]) == "ESConv"
        else state["visible_current_session_dialogue"]
    )
    pool = rs_mechanical_candidate_pool(recent_dialogue=visible, cards=cards)
    row = _candidate_base(
        state=state,
        component="RS",
        pool_count=len(pool.candidates),
    )
    row["selection_method"] = "six_card_shared_rank1_v1"
    row["retrieval_observations"] = {
        "observable_flags": pool.observable_flags,
        "already_executed_move_ids_observed": False,
    }
    shared = rs_shared_candidate_top1(pool)
    if shared is None:
        row["hard_off_reason"] = pool.hard_off_reason or "empty_rs_pool"
        return row
    observation = shared.observation
    card = observation.strategy_card
    ranked_scores = sorted(
        (float(item.lexical_relevance) for item in pool.candidates), reverse=True
    )
    row.update(
        {
            "candidate_present": True,
            "actual_rank1_id": card.strategy_id,
            "actual_rank1_increment_sha256": _sha_text(
                _compact(card.guidance_text)
            ),
            "selection_method": (
                "six_card_transparent_priority_v1"
                if shared.selection_mode == "transparent_priority"
                else "six_card_lexical_fallback_v1"
            ),
            "selection_score": float(observation.lexical_relevance),
            "top1_top2_margin": (
                ranked_scores[0] - ranked_scores[1]
                if len(ranked_scores) > 1
                else ranked_scores[0]
                if ranked_scores
                else 0.0
            ),
            "retrieval_observations": {
                **row["retrieval_observations"],
                "move_id": observation.move_id,
                "transparent_rule_on": shared.transparent_rule_on,
                "selection_mode": shared.selection_mode,
            },
        }
    )
    return row


def group_candidates_by_owner(
    candidates: Iterable[Mapping[str, Any]],
) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        grouped[str(candidate["runtime_owner_key"])].append(candidate)
    return dict(grouped)


def validate_rank1_rows(
    *,
    esconv_states: Sequence[Mapping[str, Any]],
    evo_states: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    state_by_id = {
        str(row["state_id"]): row for row in [*esconv_states, *evo_states]
    }
    candidate_by_id = {str(row["candidate_id"]): row for row in candidates}
    expected_keys = {
        (str(state["state_id"]), "RS") for state in esconv_states
    } | {
        (str(state["state_id"]), component)
        for state in evo_states
        for component in ("MP", "MS", "ME", "RS")
    }
    observed_keys = {
        (str(row["state_id"]), str(row["component"])) for row in rows
    }
    strict_past = True
    same_owner = True
    hashes_match = True
    for row in rows:
        if not row["candidate_present"]:
            continue
        state = state_by_id[str(row["state_id"])]
        if row["component"] == "RS":
            continue
        candidate = candidate_by_id.get(str(row["actual_rank1_id"]))
        if candidate is None:
            strict_past = same_owner = hashes_match = False
            continue
        strict_past = strict_past and int(
            candidate["available_after_session_index"]
        ) < int(state["source_session_index"])
        same_owner = same_owner and (
            candidate["runtime_owner_key"] == state["runtime_owner_key"]
        )
        hashes_match = hashes_match and row[
            "actual_rank1_increment_sha256"
        ] == _sha_text(_compact(candidate["literal_text"]))
    checks = {
        "one_row_per_required_state_component": observed_keys == expected_keys
        and len(rows) == len(expected_keys),
        "all_labels_null": all(row["suitability_label"] is None for row in rows),
        "present_memory_candidates_are_strictly_past": strict_past,
        "present_memory_candidates_have_same_owner": same_owner,
        "present_memory_candidate_hashes_match": hashes_match,
        "absent_candidates_have_no_id": all(
            row["candidate_present"] or row["actual_rank1_id"] is None
            for row in rows
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {"checks": checks, "failed_checks": failed}


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(_canonical(dict(row)) + "\n")
            count += 1
    return count
