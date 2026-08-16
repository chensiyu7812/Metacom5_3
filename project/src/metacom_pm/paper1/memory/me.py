"""ME (Episodic memory): a strictly-past action + an actual user-observed result.

B7 repair note: an earlier version paired any supporter "action cue" turn
(``try``, ``you might``, ...) with whatever seeker turn happened to come
next in the same session, and called that pairing "the observed result".
That is wrong -- a real false positive found in the corpus (p1, session
``p1_conv_27``): supporter turn 15 "Have you already thought about what you
might write next?" (matched the ``you might`` cue) paired with turn 16 "I'm
thinking about exploring the theme of resilience...", which reports neither
an executed action nor an observed outcome. This module now requires an
explicit, deterministic signal of *both* execution and outcome before any
pairing is made; a bare "next turn" is never sufcient.

Two grounded extraction patterns (grounded in real corpus text, not
invented -- see the regex construction notes below):

1. ``self_reported_same_turn`` (preferred, per AGENTS.md's general
   preference for the seeker's own first-person account): a single seeker
   turn that both self-reports a past action ("I tried ...", "I've tried
   ...") *and* states an explicit help/work-family outcome, positive or
   negative ("... which helped", "... but it didn't work"). The turn is
   split into two exact char spans: the action clause and the outcome
   clause. Grounded in 10 real occurrences found by scanning every seeker
   turn in the corpus for this pattern, e.g. (p12, p12_conv_2, turn 14):
   "I tried meditation and some breathing exercises which were somewhat
   helpful before."

2. ``supporter_suggestion_then_reported_result``: a supporter turn matching
   the existing action-cue patterns, paired with the *nearest* later seeker
   turn (same session first, else the nearest strictly-later session) that
   itself matches the pattern-1 self-report-with-outcome test. Acknowledgment
   turns ("okay", "thanks", "I'll try that") and stated-intention turns
   ("I'm thinking about ...") never match this test, so they can no longer
   be mistaken for an observed result.

Neither pattern reads a session's ``summary``/``observation`` field or any
evaluator annotation -- both operate purely on seeker/supporter turn text.
"""

from __future__ import annotations

import hashlib
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


# Past-tense self-report of having already taken an action ("I tried ...",
# "I've tried ...", "we tried ..."). Deliberately requires the past-tense
# "tried"/"tries" form, not "I'll try"/"I will try" (a stated *intention*,
# not an executed action, and not evidence of any outcome).
_TRIED_SELF_REPORT_PATTERN = re.compile(
    r"\b(?:i(?:'ve|'d|\s+have)?|we(?:'ve)?(?:\s+have)?)\s+tri(?:ed|es)\b", re.IGNORECASE
)

# An explicit help/work-family outcome statement, positive or negative. Both
# directions are valid observed results (AGENTS.md: a worse/negative effect
# is still a valid realized outcome, not something to exclude).
_OUTCOME_STATEMENT_PATTERN = re.compile(
    r"\b(?:"
    r"did(?:n'?t|\s+not)\s+(?:really\s+)?(?:help|work)(?:ed)?"
    r"|has(?:n'?t|\s+not)\s+(?:really\s+)?help(?:ed)?"
    r"|help(?:ed|s|ful)?"
    r"|work(?:ed|s)?"
    r")\b",
    re.IGNORECASE,
)


def find_self_reported_action_result_spans(
    text: str,
) -> tuple[tuple[int, int], tuple[int, int]] | None:
    """Split a seeker turn into (action_span, outcome_span) char offsets, or None.

    Requires a past-tense "tried" self-report followed later in the same
    turn by an explicit help/work-family outcome statement. Acknowledgment-
    only text ("okay", "thanks"), stated intentions ("I'll try", "I'm
    thinking about ..."), and "tried" without any stated outcome (e.g. "I
    tried to just sit ... but the words still didn't come") all correctly
    return None.
    """

    tried_match = _TRIED_SELF_REPORT_PATTERN.search(text)
    if tried_match is None:
        return None
    outcome_match = _OUTCOME_STATEMENT_PATTERN.search(text, tried_match.end())
    if outcome_match is None:
        return None
    action_span = (tried_match.start(), outcome_match.start())
    outcome_span = (outcome_match.start(), len(text))
    if action_span[0] >= action_span[1]:
        return None
    return action_span, outcome_span


def find_executed_result_span(text: str) -> tuple[int, int] | None:
    """A seeker turn's full "I tried X and it helped/didn't help"-shaped span, or None.

    Reuses ``find_self_reported_action_result_spans``: a turn only counts as
    an observed *result* of some earlier suggestion if it itself clears the
    same bar -- explicit execution and an explicit stated outcome. The
    returned span covers the whole qualifying clause (from "tried" onward),
    since the executed-ness and the outcome are both part of what the reader
    needs to see.
    """

    spans = find_self_reported_action_result_spans(text)
    if spans is None:
        return None
    action_span, _outcome_span = spans
    return (action_span[0], len(text))


def _span_hash(text: str, span: tuple[int, int]) -> str:
    return hashlib.sha256(text[span[0] : span[1]].encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ActionResultEpisode:
    pattern: str  # "self_reported_same_turn" | "supporter_suggestion_then_reported_result"
    owner_id: str
    action_session_id: str
    action_session_chronological_rank: int
    action_observed_at: str
    action_turn: Turn
    action_span: tuple[int, int]
    result_session_id: str
    result_session_chronological_rank: int
    result_observed_at: str
    result_turn: Turn
    result_span: tuple[int, int]

    @property
    def action_text(self) -> str:
        return self.action_turn.content[self.action_span[0] : self.action_span[1]]

    @property
    def result_text(self) -> str:
        return self.result_turn.content[self.result_span[0] : self.result_span[1]]

    @property
    def content(self) -> str:
        return f"action: {self.action_text}\nresult: {self.result_text}"

    @property
    def source_record_ids(self) -> tuple[str, ...]:
        return (
            f"{self.action_session_id}:{self.action_turn.idx}:"
            f"{self.action_span[0]}-{self.action_span[1]}",
            f"{self.result_session_id}:{self.result_turn.idx}:"
            f"{self.result_span[0]}-{self.result_span[1]}",
        )

    @property
    def action_span_sha256(self) -> str:
        return _span_hash(self.action_turn.content, self.action_span)

    @property
    def result_span_sha256(self) -> str:
        return _span_hash(self.result_turn.content, self.result_span)


def _self_reported_episodes(user: UserRecord) -> list[ActionResultEpisode]:
    episodes: list[ActionResultEpisode] = []
    for session in user.sessions:
        for turn in session.seeker_turns():
            spans = find_self_reported_action_result_spans(turn.content)
            if spans is None:
                continue
            action_span, result_span = spans
            episodes.append(
                ActionResultEpisode(
                    pattern="self_reported_same_turn",
                    owner_id=user.owner_id,
                    action_session_id=session.session_id,
                    action_session_chronological_rank=session.chronological_rank,
                    action_observed_at=session.timestamp,
                    action_turn=turn,
                    action_span=action_span,
                    result_session_id=session.session_id,
                    result_session_chronological_rank=session.chronological_rank,
                    result_observed_at=session.timestamp,
                    result_turn=turn,
                    result_span=result_span,
                )
            )
    return episodes


def _nearest_qualifying_result(
    sessions: tuple, session_index: int, turn_position: int
):
    """The nearest later seeker turn (same session, else nearest later session)
    that itself passes ``find_executed_result_span``; None if none exists."""

    action_session = sessions[session_index]
    for later in action_session.turns[turn_position + 1 :]:
        if later.role == "seeker":
            span = find_executed_result_span(later.content)
            if span is not None:
                return action_session, later, span
    for later_session in sessions[session_index + 1 :]:
        for later_turn in later_session.seeker_turns():
            span = find_executed_result_span(later_turn.content)
            if span is not None:
                return later_session, later_turn, span
    return None


def _suggestion_result_episodes(user: UserRecord) -> list[ActionResultEpisode]:
    episodes: list[ActionResultEpisode] = []
    sessions = user.sessions
    for session_index, action_session in enumerate(sessions):
        for turn_position, turn in enumerate(action_session.turns):
            if turn.role != "supporter" or not is_action_cue(turn.content):
                continue
            found = _nearest_qualifying_result(sessions, session_index, turn_position)
            if found is None:
                continue
            result_session, result_turn, result_span = found
            episodes.append(
                ActionResultEpisode(
                    pattern="supporter_suggestion_then_reported_result",
                    owner_id=user.owner_id,
                    action_session_id=action_session.session_id,
                    action_session_chronological_rank=action_session.chronological_rank,
                    action_observed_at=action_session.timestamp,
                    action_turn=turn,
                    action_span=(0, len(turn.content)),
                    result_session_id=result_session.session_id,
                    result_session_chronological_rank=result_session.chronological_rank,
                    result_observed_at=result_session.timestamp,
                    result_turn=result_turn,
                    result_span=result_span,
                )
            )
    return episodes


def extract_action_result_episodes(user: UserRecord) -> tuple[ActionResultEpisode, ...]:
    """Every deterministically-qualifying (action span, observed-result span) pair.

    Both extraction patterns require an explicit outcome statement; there is
    no "next turn counts as the result" fallback. Coverage is expected to be
    much sparser than a naive next-turn rule -- see AGENTS.md's "no synthetic
    rescue for a sparse ... head": this module keeps that sparsity honest
    rather than loosening the qualifying condition.
    """

    return tuple(_self_reported_episodes(user) + _suggestion_result_episodes(user))
