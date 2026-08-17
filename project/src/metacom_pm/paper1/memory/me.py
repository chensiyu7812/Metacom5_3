"""ME (Episodic memory): a strictly-past, seeker-self-reported action + observed result.

B11 repair note: B7 replaced the original "next seeker turn = result" bug
with two patterns, one of which (``supporter_suggestion_then_reported_
result``) paired an earlier supporter action-cue turn with whatever later
qualifying seeker turn happened to occur next -- purely on temporal order,
with no actual identity/coreference link between the specific suggestion and
the specific later turn. Audited: 53 of the resulting 63 candidates were
this pattern, and manual inspection found real, non-topical pairings (e.g.
four sleep/relationship suggestions from session ``esc1024`` all mechanically
paired to an unrelated HR-workplace turn in a later session, ``esc1172``,
purely because it was the nearest later turn that happened to match the
outcome test). There is no reliable deterministic way to verify that a given
later seeker turn is actually reporting on a given earlier suggestion
(that requires coreference/topic linkage this project does not have a
mechanical method for), so per AGENTS.md's "no synthetic rescue for a sparse
head", that pattern is deleted rather than patched. ``is_action_cue`` and
the supporter-suggestion pairing are gone; if a future round adds a real
mechanical coreference check, that pattern can be reintroduced, gated on
that check actually existing.

The one remaining pattern, ``self_reported_same_turn``, is also tightened
this round. The old outcome test (bare ``help``/``work`` word presence
anywhere after "tried") produced real false positives found by inspection:

- p1, session ``esc1172``, turn 4: "...Will that help, or just get me in
  trouble?" -- a *question*, not a stated outcome.
- p9, session ``p9_conv_13``, turn 7: "I tried to help, gave first aid..."
  -- "help" is the object of "tried to", i.e. part of the *action*, not an
  outcome.
- p14, session ``p14_conv_6``, turn 7: "...he seems so wrapped up in his
  work." -- "work" is a possessed noun (his job), not a verb describing an
  effect.
- p16, session ``p16_conv_7``, turn 5: "...affecting my motivation at
  work." -- "at work" is a location noun phrase, not an outcome.

The fix: an outcome must be an explicit *result-relation* clause -- a
help/work-family verb with a back-referring subject ("it/that/this/which/
they/these helped/worked/helps/works", "which were helpful"), an explicit
negation ("didn't help", "doesn't work", "hasn't helped", "wasn't
helpful"), or one of the other explicit result connectives named in scope
("ended in/up ...", "made me/them/it ..."). Requiring a subject pronoun
mechanically rules out "tried to help" (no subject immediately before
"help") and "his/at work" (the token before "work" is not a qualifying
subject) without any hand-written blacklist for those specific phrases.
Any candidate match falling inside a question (the containing sentence
ends in "?") is discarded regardless of wording.

Both fixes are purely syntactic pattern changes, not semantic/LLM judgment,
and grounded by scanning the whole corpus before and after the change (see
project memory / commit message for the before/after counts).

B20 repair note: two more real counter-examples survived B11's fix, both
found by per-candidate audit:

- p3, session ``p3_conv_10``, turn 9: "I tried, but it just ended up
  becoming another argument." -- "tried" has no action complement at all
  (the sentence never says *what* was tried), so "ended up becoming another
  argument" cannot be a result of a specific action.
- p14, session ``p14_conv_9``, turn 9: "We've tried talking, but sometimes
  it just ends in arguments. I think we both feel overwhelmed. He's been a
  bit better about his work hours, which helps, but there's still a lot to
  mend between us." -- "which helps" grammatically refers back to "his work
  hours" (the subject of the immediately preceding clause), not to "tried
  talking" two sentences earlier. A subject/topic shift, not a real
  action-result link.

Two more mechanical requirements fix both without any per-candidate
blacklist: (1) the "tried" match must be followed by a non-empty action
complement before the next comma -- "tried," with nothing between "tried"
and the comma is rejected outright (fixes the first case); (2) the
result-relation search is now bounded to the *same sentence* as the "tried"
clause (never crosses a ``.``/``!``/``?``) -- a result-relation match in a
later, independent sentence is exactly the shape a subject/topic shift takes
(fixes the second case, and is the more general, more defensible mechanical
proxy for "no intermediate subject shift" than trying to detect the shift
directly). This also correctly retires one previously-accepted case
(p8, ``p8_conv_11`` turn 15: "...from meditation apps. They help in
stressful moments...") whose result clause was in a separate sentence too --
losing it is the intended, honest effect of the stricter same-sentence rule,
not a new bug.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from metacom_pm.paper1.data.memory_source import MemorySourceUser, Turn

# Past-tense self-report of having already taken an action ("I tried ...",
# "I've tried ...", "we tried ..."). Deliberately requires the past-tense
# "tried"/"tries" form, not "I'll try"/"I will try" (a stated *intention*,
# not an executed action, and not evidence of any outcome).
_TRIED_SELF_REPORT_PATTERN = re.compile(
    r"\b(?:i(?:'ve|'d|\s+have)?|we(?:'ve)?(?:\s+have)?)\s+tri(?:ed|es)\b", re.IGNORECASE
)

# An explicit result-relation clause, positive or negative -- both
# directions are valid observed results (AGENTS.md: a worse/negative effect
# is still a valid realized outcome, not something to exclude). Each pattern
# requires a back-referring subject or an explicit negation/connective, so a
# bare occupational/infinitival/interrogative use of "help"/"work" never
# qualifies on its own.
_RESULT_RELATION_PATTERNS = (
    # "it/that/this/which/they/these (really/actually/...) helped/worked/help(s)/work(s)"
    re.compile(
        r"\b(?:it|that|this|which|they|these)\s+"
        r"(?:really\s+|actually\s+|definitely\s+|also\s+|somewhat\s+)?"
        r"(?:helped|worked|helps?\b|works?\b)",
        re.IGNORECASE,
    ),
    # "it/that/this/which/they/these was/were/is/are ... helpful"
    re.compile(
        r"\b(?:it|that|this|which|they|these)\s+(?:was|were|is|are)\s+(?:\w+\s+)?helpful\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bdid(?:n'?t|\s+not)\s+(?:really\s+)?(?:help|work)(?:ed)?\b", re.IGNORECASE),
    re.compile(r"\bdoes(?:n'?t|\s+not)\s+(?:really\s+)?(?:help|work)\b", re.IGNORECASE),
    re.compile(r"\bhas(?:n'?t|\s+not)\s+(?:really\s+)?help(?:ed)?\b", re.IGNORECASE),
    re.compile(r"\bwas(?:n'?t|\s+not)\s+(?:very\s+|really\s+)?helpful\b", re.IGNORECASE),
    re.compile(r"\bended\s+(?:in|up)\b", re.IGNORECASE),
    re.compile(r"\bmade\s+(?:me|things|it|him|her|us)\s+\w+", re.IGNORECASE),
)

_SENTENCE_TERMINATOR_PATTERN = re.compile(r"[.!?]")


def _first_result_relation_match(text: str, start: int, limit: int) -> re.Match[str] | None:
    best: re.Match[str] | None = None
    for pattern in _RESULT_RELATION_PATTERNS:
        candidate = pattern.search(text, start, limit)
        if candidate is not None and (best is None or candidate.start() < best.start()):
            best = candidate
    return best


def _is_question_context(text: str, position: int) -> bool:
    """True if the sentence containing ``position`` ends in "?"."""

    terminator = _SENTENCE_TERMINATOR_PATTERN.search(text, position)
    return terminator is not None and terminator.group(0) == "?"


def _has_action_complement(text: str, tried_end: int) -> bool:
    """False for a bare "tried," with nothing between "tried" and the comma.

    B20: "I tried, but ..." never states what was tried, so it can never be
    a valid action span no matter what follows.
    """

    remainder = text[tried_end:].lstrip()
    return not remainder.startswith(",")


def find_self_reported_action_result_spans(
    text: str,
) -> tuple[tuple[int, int], tuple[int, int]] | None:
    """Split a seeker turn into (action_span, outcome_span) char offsets, or None.

    Requires: a past-tense "tried" self-report; a non-empty action
    complement immediately after it (not bare "tried,"); and an explicit
    result-relation clause found *within the same sentence* as the "tried"
    clause (search never crosses a ``.``/``!``/``?`` -- B20: a result-relation
    match in a later, independent sentence is exactly the shape a subject/
    topic shift takes, e.g. "we've tried talking ... his work hours, which
    helps" -- "which helps" refers to "his work hours", not the tried
    action). Returns None for: no "tried" at all; "tried" with no action
    complement; no qualifying result clause in the same sentence; a
    candidate result clause that is actually an infinitival/possessive/
    locational use of "help"/"work" (excluded by requiring a back-referring
    subject); or a candidate result clause inside a question.
    """

    tried_match = _TRIED_SELF_REPORT_PATTERN.search(text)
    if tried_match is None:
        return None
    if not _has_action_complement(text, tried_match.end()):
        return None
    boundary_match = _SENTENCE_TERMINATOR_PATTERN.search(text, tried_match.end())
    sentence_boundary = boundary_match.start() if boundary_match is not None else len(text)
    outcome_match = _first_result_relation_match(text, tried_match.end(), sentence_boundary)
    if outcome_match is None:
        return None
    if _is_question_context(text, outcome_match.start()):
        return None
    action_span = (tried_match.start(), outcome_match.start())
    outcome_span = (outcome_match.start(), len(text))
    if action_span[0] >= action_span[1]:
        return None
    return action_span, outcome_span


def _span_hash(text: str, span: tuple[int, int]) -> str:
    return hashlib.sha256(text[span[0] : span[1]].encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ActionResultEpisode:
    """One (action span, observed-result span) pair.

    ``pattern`` is currently always ``"self_reported_same_turn"`` (B11: the
    supporter-suggestion cross-turn pattern was removed for lacking a
    mechanical action-identity link -- see module docstring). The action/
    result session/turn fields are kept separate rather than collapsed to a
    single session/turn, so a future properly-linked cross-turn pattern
    could be reintroduced without changing this contract or the compiler's
    strict-past check in ``candidates/compilers.py``.
    """

    pattern: str
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


def extract_action_result_episodes(user: MemorySourceUser) -> tuple[ActionResultEpisode, ...]:
    """Every deterministically-qualifying same-turn (action span, result span) pair.

    Coverage is expected to be much sparser than either the original next-
    turn rule or B7's cross-turn pattern -- see AGENTS.md's "no synthetic
    rescue for a sparse ... head": this module keeps that sparsity honest
    rather than loosening the qualifying condition or resurrecting a
    temporal-only cross-turn pairing.
    """

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
    return tuple(episodes)
