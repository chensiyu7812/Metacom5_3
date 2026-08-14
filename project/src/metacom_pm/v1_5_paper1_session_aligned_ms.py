"""Session-aligned public MS surfaces for Paper 1 method V2.

The EvoEmo author graph relates sessions.  This module therefore exposes one
strictly-past raw session resource rather than pretending that the graph labels
one individual utterance inside that session.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any, Mapping, Sequence


PROTOCOL = "pm-v1.5-paper1-session-aligned-ms-v2"
CHECKPOINT_WORDS = 50
_SPACE = re.compile(r"\s+")
_TOKEN = re.compile(r"[a-z0-9']+")


def compact(value: Any) -> str:
    return _SPACE.sub(" ", str(value or "")).strip()


def opaque(*parts: Any) -> str:
    body = "\x1f".join(str(part) for part in parts)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:24]


def tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


def token_jaccard(left: str, right: str) -> float:
    a, b = tokens(left), tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def visible_text(dialogue: Sequence[Mapping[str, Any]]) -> str:
    return "\n".join(
        f"{str(turn['speaker']).upper()}: {compact(turn['content'])}"
        for turn in dialogue
    )


def session_resource_text(session: Mapping[str, Any]) -> str:
    lines = [
        f"SEEKER: {compact(turn.get('content'))}"
        for turn in session.get("dialogue") or []
        if str(turn.get("role") or "") == "seeker" and compact(turn.get("content"))
    ]
    return "\n".join(lines)


def checkpoint_prefix(session: Mapping[str, Any]) -> tuple[list[dict[str, Any]], int] | None:
    """Return the first prefix with 50 cumulative visible seeker words."""

    visible: list[dict[str, Any]] = []
    seeker_words = 0
    for turn in session.get("dialogue") or []:
        role = str(turn.get("role") or "")
        content = compact(turn.get("content"))
        if role not in {"seeker", "supporter"} or not content:
            continue
        raw_index = int(turn.get("idx") or 0)
        visible.append(
            {"raw_turn_index": raw_index, "speaker": role, "content": content}
        )
        if role == "seeker":
            seeker_words += len(content.split())
            if seeker_words >= CHECKPOINT_WORDS:
                return list(visible), raw_index
    return None


def build_surfaces(
    users: Sequence[Mapping[str, Any]],
    owner_assignments: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build one checkpoint state and one exact resource per raw session."""

    states: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for user in users:
        user_id = str(user["id"])
        owner = f"evo::{user_id}"
        assignment = owner_assignments[owner]
        sessions = list(user.get("dialog_history") or [])
        for session_index, session in enumerate(sessions, 1):
            session_id = str(session["id"])
            resource = session_resource_text(session)
            if not resource:
                raise ValueError(f"empty seeker session resource: {owner}/{session_id}")
            candidate_id = "mss_" + opaque(user_id, session_id, resource)
            candidates.append(
                {
                    "protocol": PROTOCOL,
                    "candidate_id": candidate_id,
                    "component": "MS",
                    "subtype": "MS_RAW_SEEKER_SESSION",
                    "runtime_owner_key": owner,
                    "split_group_key": assignment["split_group_key"],
                    "outer_fold": int(assignment["outer_fold"]),
                    "available_after_session_index": session_index,
                    "source_session_id": session_id,
                    "literal_text": resource,
                    "raw_seeker_turn_count": resource.count("SEEKER:"),
                    "raw_word_count": len(resource.split()),
                    "label": None,
                }
            )
            checkpoint = checkpoint_prefix(session)
            if checkpoint is None:
                continue
            visible, raw_turn_index = checkpoint
            states.append(
                {
                    "protocol": PROTOCOL,
                    "dataset": "EvoEmo",
                    "state_id": (
                        f"evo::{user_id}::{session_id}::ms_checkpoint::{raw_turn_index}"
                    ),
                    "runtime_owner_key": owner,
                    "split_group_key": assignment["split_group_key"],
                    "outer_fold": int(assignment["outer_fold"]),
                    "source_session_id": session_id,
                    "source_session_index": session_index,
                    "raw_current_turn_index": raw_turn_index,
                    "visible_current_session_dialogue": visible,
                    "visible_text": visible_text(visible),
                    "checkpoint_rule": "FIRST_CUMULATIVE_SEEKER_WORDS_GE_50",
                    "strict_past_session_pool_count": session_index - 1,
                    "label": None,
                }
            )
    return states, candidates


def rank1_rows(
    states: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    state_vectors: Mapping[str, Any],
    candidate_vectors: Mapping[str, Any],
) -> list[dict[str, Any]]:
    by_owner: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for candidate in candidates:
        by_owner[str(candidate["runtime_owner_key"])].append(candidate)
    result: list[dict[str, Any]] = []
    for state in states:
        eligible = [
            row
            for row in by_owner[str(state["runtime_owner_key"])]
            if int(row["available_after_session_index"])
            < int(state["source_session_index"])
        ]
        base = {
            "protocol": PROTOCOL,
            "state_id": state["state_id"],
            "component": "MS",
            "runtime_owner_key": state["runtime_owner_key"],
            "split_group_key": state["split_group_key"],
            "outer_fold": state["outer_fold"],
            "strict_past_pool_count": len(eligible),
            "label": None,
        }
        if not eligible:
            result.append(
                {
                    **base,
                    "candidate_present": False,
                    "actual_rank1_id": None,
                    "candidate_source_session_id": None,
                    "selection_score": None,
                    "top1_top2_margin": None,
                    "hard_off_reason": "no_strictly_past_session",
                }
            )
            continue
        query = state_vectors[str(state["state_id"])]
        scored = sorted(
            (
                float(query @ candidate_vectors[str(candidate["candidate_id"])]),
                int(candidate["available_after_session_index"]),
                str(candidate["candidate_id"]),
                candidate,
            )
            for candidate in eligible
        )
        scored.reverse()
        top = scored[0]
        second = scored[1][0] if len(scored) > 1 else 0.0
        result.append(
            {
                **base,
                "candidate_present": True,
                "actual_rank1_id": top[2],
                "candidate_source_session_id": top[3]["source_session_id"],
                "candidate_available_after_session_index": top[3][
                    "available_after_session_index"
                ],
                "selection_method": "bge_m3_full_visible_to_raw_session_v2",
                "selection_score": top[0],
                "top1_top2_margin": top[0] - second,
                "hard_off_reason": None,
            }
        )
    return result


def validate_public_surfaces(
    states: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    rank1: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    state_ids = [str(row["state_id"]) for row in states]
    candidate_ids = [str(row["candidate_id"]) for row in candidates]
    candidate_by_id = {str(row["candidate_id"]): row for row in candidates}
    checks = {
        "unique_state_ids": len(state_ids) == len(set(state_ids)),
        "unique_candidate_ids": len(candidate_ids) == len(set(candidate_ids)),
        "one_rank1_per_state": len(rank1) == len(states)
        and {str(row["state_id"]) for row in rank1} == set(state_ids),
        "checkpoint_exact": all(
            row["checkpoint_rule"] == "FIRST_CUMULATIVE_SEEKER_WORDS_GE_50"
            and sum(
                len(str(turn["content"]).split())
                for turn in row["visible_current_session_dialogue"]
                if turn["speaker"] == "seeker"
            )
            >= CHECKPOINT_WORDS
            for row in states
        ),
        "raw_session_resources_only": all(
            row["literal_text"].startswith("SEEKER:")
            and row["raw_seeker_turn_count"] >= 1
            and row["raw_word_count"] <= 500
            for row in candidates
        ),
        "strict_past_rank1": all(
            not row["candidate_present"]
            or int(candidate_by_id[str(row["actual_rank1_id"])]["available_after_session_index"])
            < next(
                int(state["source_session_index"])
                for state in states
                if state["state_id"] == row["state_id"]
            )
            for row in rank1
        ),
        "runtime_labels_null": all(row.get("label") is None for row in [*states, *candidates, *rank1]),
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}
