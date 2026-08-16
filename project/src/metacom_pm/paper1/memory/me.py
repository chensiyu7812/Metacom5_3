"""ME (Episodic memory): a strictly-past action + the user's own observed result.

An "action" is a supporter turn containing a deterministic actionable-
suggestion cue (``try``, ``you could``, ``why don't you``, ``I suggest``,
...). The paired "result" is the *next* seeker turn appearing anywhere later
in the same session -- the user's own subsequent words, not an evaluator's
characterization of them. Both turns are same-session and same-owner by
construction, so every episode is inherently text-traceable and strictly
past relative to any later session.

This is deliberately a syntactic cue match, not a judgment about whether the
suggestion was good advice or whether the user's reply shows the suggestion
"worked" -- semantic adoption/usefulness is out of scope for candidate
construction (AGENTS.md: semantic adoption is diagnostic only).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from metacom_pm.paper1.data.es_memeval import Turn, UserRecord

_ACTION_CUE_PATTERNS = (
    re.compile(r"\btry\b", re.IGNORECASE),
    re.compile(r"\byou\s+could\b", re.IGNORECASE),
    re.compile(r"\byou\s+should\b", re.IGNORECASE),
    re.compile(r"why\s+don'?t\s+you\b", re.IGNORECASE),
    re.compile(r"\bwhy\s+not\b", re.IGNORECASE),
    re.compile(r"\byou\s+might\b", re.IGNORECASE),
    re.compile(r"\byou\s+may\s+want\s+to\b", re.IGNORECASE),
    re.compile(r"\bconsider\b", re.IGNORECASE),
    re.compile(r"\bi\s+suggest\b", re.IGNORECASE),
    re.compile(r"\bi\s+recommend\b", re.IGNORECASE),
    re.compile(r"\bmaybe\s+you\b", re.IGNORECASE),
    re.compile(r"\bhow\s+about\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+if\s+you\b", re.IGNORECASE),
)


def is_action_cue(text: str) -> bool:
    return any(pattern.search(text) for pattern in _ACTION_CUE_PATTERNS)


@dataclass(frozen=True)
class ActionResultEpisode:
    owner_id: str
    session_id: str
    session_chronological_rank: int
    observed_at: str
    action_turn: Turn
    result_turn: Turn

    @property
    def content(self) -> str:
        return f"action: {self.action_turn.content}\nresult: {self.result_turn.content}"

    @property
    def source_record_ids(self) -> tuple[str, ...]:
        return (
            f"{self.session_id}:{self.action_turn.idx}",
            f"{self.session_id}:{self.result_turn.idx}",
        )


def extract_action_result_episodes(user: UserRecord) -> tuple[ActionResultEpisode, ...]:
    """Every (supporter action cue -> next seeker turn) pair, per session."""

    episodes: list[ActionResultEpisode] = []
    for session in user.sessions:
        turns = session.turns
        for position, turn in enumerate(turns):
            if turn.role != "supporter" or not is_action_cue(turn.content):
                continue
            for later in turns[position + 1 :]:
                if later.role == "seeker":
                    episodes.append(
                        ActionResultEpisode(
                            owner_id=user.owner_id,
                            session_id=session.session_id,
                            session_chronological_rank=session.chronological_rank,
                            observed_at=session.timestamp,
                            action_turn=turn,
                            result_turn=later,
                        )
                    )
                    break
    return tuple(episodes)
