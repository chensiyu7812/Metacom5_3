"""Deterministic evaluator-only label primitives for the Paper 1 pivot."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Mapping, Sequence


RS_STRATEGY_TO_MOVES = {
    "Question": frozenset(
        {"AM01_invite_open_expression", "AM02_ask_one_focused_clarification"}
    ),
    "Restatement or Paraphrasing": frozenset(
        {"AM04_tentative_paraphrase_check"}
    ),
    "Reflection of feelings": frozenset({"AM05_grounded_validation"}),
    "Affirmation and Reassurance": frozenset({"AM05_grounded_validation"}),
    "Providing Suggestions": frozenset({"AM10_offer_one_optional_micro_step"}),
}
_CURRENT_CLOSE = re.compile(
    r"\b(?:bye|goodbye|stop here|end here|done for (?:today|now)|talk later|"
    r"need to go|have to go|thanks for listening|thank you for listening)\b",
    re.IGNORECASE,
)
_SUPPORTER_CLOSE = re.compile(
    r"\b(?:bye|goodbye|take care|talk (?:again|later)|here if you need|"
    r"glad (?:we|you)|rest|wish you|hope you)\b",
    re.IGNORECASE,
)


def first_future_supporter(
    dialogue: Sequence[Mapping[str, Any]], current_turn_index: int
) -> Mapping[str, Any] | None:
    for turn in dialogue[current_turn_index + 1 :]:
        if str(turn.get("speaker") or "") == "supporter" and str(
            turn.get("content") or ""
        ).strip():
            return turn
    return None


def rs_source_annotated_label(
    *,
    move_id: str,
    current_user_text: str,
    next_supporter_turn: Mapping[str, Any],
) -> bool:
    strategy = str((next_supporter_turn.get("annotation") or {}).get("strategy") or "")
    if move_id in RS_STRATEGY_TO_MOVES.get(strategy, frozenset()):
        return True
    if move_id == "AM14_supportive_transition":
        return bool(
            _CURRENT_CLOSE.search(current_user_text)
            and _SUPPORTER_CLOSE.search(str(next_supporter_turn.get("content") or ""))
        )
    return False


def event_ancestor_source_sessions(user: Mapping[str, Any]) -> dict[str, set[str]]:
    """Map each current session to recursive strict-past ancestor conv IDs."""

    events = {str(row["id"]): row for row in user.get("event_experience") or []}
    event_ids_by_conv: dict[str, list[str]] = defaultdict(list)
    for event_id, event in events.items():
        event_ids_by_conv[str(event["conv_id"])].append(event_id)
    result: dict[str, set[str]] = {}
    for session in user.get("dialog_history") or []:
        current_session = str(session["id"])
        stack = [
            str(parent)
            for event_id in event_ids_by_conv.get(current_session, [])
            for parent in events[event_id].get("influenced_by") or []
        ]
        visited: set[str] = set()
        while stack:
            event_id = stack.pop()
            if event_id in visited or event_id not in events:
                continue
            visited.add(event_id)
            stack.extend(str(parent) for parent in events[event_id].get("influenced_by") or [])
        result[current_session] = {str(events[event_id]["conv_id"]) for event_id in visited}
    return result


def memory_source_annotated_label(
    *, source_session_id: str, current_session_id: str, ancestors: Mapping[str, set[str]]
) -> bool:
    return source_session_id in ancestors.get(current_session_id, set())

