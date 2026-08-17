"""B29.3: high-precision cross-turn action->outcome proposal audit for ME.

Diagnostic only -- never wired into ``memory/me.py``, never changes what the
primary ME compiler extracts (still 3 unique same-turn candidates / 2
owners, unchanged, recomputed directly in this module's report for
contrast). This module exists to answer, mechanically and honestly: if a
cross-turn action->outcome pattern were reintroduced with a REAL
coreference-linkage requirement -- the exact gap B11 identified when it
removed the old, unlinked ``supporter_suggestion_then_reported_result``
pattern -- what would it find?

Every proposed candidate must pass ALL of the following, each checked
mechanically (no LLM judgment, no pure temporal-proximity pairing):

1. **Antecedent action**: a supporter turn matching an explicit suggestion
   pattern ("you could/might/may/should try ...", "have you tried/
   considered ..."). Narrower than B11's retired ``is_action_cue`` on
   purpose -- precision first, not recall first (this is the opposite
   trade-off from B29.2's MP proposal audit).
2. **Explicit anaphora/reference**: the candidate result turn must contain
   an explicit back-reference marker ("that"/"it"/"this"/"what you said/
   suggested/mentioned/told me") -- a bare later turn with no such marker
   is never a candidate, no matter how topically similar. The marker must
   sit within ``MAX_ANAPHORA_TO_RESULT_GAP`` characters immediately before
   the matched result-relation clause -- an anaphora word appearing
   elsewhere in the turn, unconnected to the actual result clause, does
   not qualify (a real precision gap found and closed during construction:
   an earlier draft accepted any anaphora anywhere in the turn and matched
   cases where the anaphora's real antecedent was plainly a different
   clause than the one containing the result-relation match).
3. **Action lexical/coreference linkage**: the result turn must share at
   least one non-trigger, non-stopword content word (length >= 4) with the
   antecedent suggestion turn -- a purely anaphoric reference with zero
   lexical overlap to the specific suggestion is rejected (too weak a
   coreference proxy on its own).
4. **Explicit result clause**: the same ``_RESULT_RELATION_PATTERNS`` the
   same-turn primary ME construct already uses (memory/me.py) must match
   somewhere in the result turn, outside any question context.
5. **Bounded temporal window**: the result turn's ``idx`` must be within
   ``MAX_TURN_IDX_WINDOW`` of the antecedent's ``idx``, same session
   (never cross-session -- see the real esc1024/esc1172 mispairing B11
   already found and this audit does not want to reproduce).
6. **No competing antecedent**: if more than one qualifying supporter-
   suggestion turn appears between the antecedent and the result turn,
   the pair is excluded from the "clean" proposal list (reported
   separately as ``competing_antecedent_excluded``, not silently dropped
   and not silently kept).

No item here becomes primary, no per-candidate ID blacklist is used, and no
candidate is filtered by whether it looks "useful" -- only the six
mechanical gates above decide inclusion.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from metacom_pm.paper1.data.memory_source import MemorySourceUser, Session, Turn
from metacom_pm.paper1.memory.me import (
    _RESULT_RELATION_PATTERNS,
    _first_result_relation_match,
    _is_question_context,
    extract_action_result_episodes,
)

MAX_TURN_IDX_WINDOW = 8
MAX_ANAPHORA_TO_RESULT_GAP = 15

_SUGGESTION_PATTERN = re.compile(
    r"\byou\s+(?:could|might|may|should)\s+try\b|\bhave\s+you\s+(?:tried|considered)\b",
    re.IGNORECASE,
)
_ANAPHORA_PATTERN = re.compile(
    r"\bthat\b|\bit\b|\bthis\b|\bwhat\s+you\s+(?:said|suggested|mentioned|told\s+me)\b",
    re.IGNORECASE,
)
_CONTENT_WORD_PATTERN = re.compile(r"[a-z]{4,}")
_OVERLAP_STOPWORDS = frozenset(
    {
        "that",
        "this",
        "what",
        "said",
        "told",
        "have",
        "tried",
        "trying",
        "could",
        "might",
        "should",
        "considered",
        "suggested",
        "mentioned",
        "will",
        "with",
        "your",
        "about",
        # B29.3 precision fix: "help"-family words are part of both the
        # suggestion-turn register ("...might help") and the result-clause
        # pattern vocabulary itself (_RESULT_RELATION_PATTERNS literally
        # matches on helped/helps/helpful) -- co-occurrence is close to
        # tautological, not meaningful evidence of coreference to the
        # specific suggested action. "really" is a common register
        # intensifier in supportive dialogue, not a substantive content
        # word -- excluded for the same reason (found to produce
        # coincidental, non-substantive matches during construction).
        "help",
        "helps",
        "helped",
        "helpful",
        "really",
        # Common conversational fillers/minimizers -- coincidentally likely
        # to co-occur across any two turns in this supportive-dialogue
        # register regardless of topic, so not substantive content.
        "just",
        "also",
        "some",
        "sometimes",
    }
)


def _content_words(text: str) -> frozenset[str]:
    return frozenset(w for w in _CONTENT_WORD_PATTERN.findall(text.lower()) if w not in _OVERLAP_STOPWORDS)


def _closest_anaphora_before(text: str, limit: int, max_gap: int) -> "re.Match[str] | None":
    """The anaphora match nearest to (and ending at or before) ``limit``,
    or ``None`` if the closest one is farther than ``max_gap`` characters
    away -- structurally ties the anaphora to the result clause it must
    immediately precede, rather than accepting any anaphora anywhere in
    the turn."""

    best: "re.Match[str] | None" = None
    for match in _ANAPHORA_PATTERN.finditer(text, 0, limit):
        if best is None or match.start() > best.start():
            best = match
    if best is None:
        return None
    if limit - best.end() > max_gap:
        return None
    return best


def _anaphora_for_result_match(text: str, result_match: "re.Match[str]", max_gap: int) -> "re.Match[str] | None":
    """Two ways a result-relation match can carry an explicit anaphoric
    subject: (1) several ``_RESULT_RELATION_PATTERNS`` already require the
    subject pronoun as PART of the match itself (e.g. 'it really helped'),
    so the match starts exactly at the anaphora word -- checked first via
    an anchored ``.match()``, not ``.search()``, since it must begin at
    that exact position, not merely contain it somewhere. (2) other
    patterns have no built-in subject (e.g. 'didn't help', 'ended in'), so
    a separate anaphora word must appear within ``max_gap`` characters
    immediately before the match."""

    self_contained = _ANAPHORA_PATTERN.match(text, result_match.start())
    if self_contained is not None:
        return self_contained
    return _closest_anaphora_before(text, result_match.start(), max_gap)


@dataclass(frozen=True)
class MeCrossTurnCandidate:
    owner_id: str
    session_id: str
    action_turn_idx: int
    action_span: tuple[int, int]
    action_text: str
    result_turn_idx: int
    result_span: tuple[int, int]
    result_text: str
    anaphora_span: tuple[int, int]
    anaphora_text: str
    shared_content_words: tuple[str, ...]
    linkage_rule: str
    competing_antecedent_turn_indices: tuple[int, ...]
    excluded_for_competing_antecedent: bool

    def to_manifest_row(self) -> dict[str, Any]:
        return {
            "protocol": "pm-paper1-me-cross-turn-proposal-row-v1",
            "owner_id": self.owner_id,
            "session_id": self.session_id,
            "action_turn_idx": self.action_turn_idx,
            "action_span": list(self.action_span),
            "action_text": self.action_text,
            "result_turn_idx": self.result_turn_idx,
            "result_span": list(self.result_span),
            "result_text": self.result_text,
            "anaphora_span": list(self.anaphora_span),
            "anaphora_text": self.anaphora_text,
            "shared_content_words": list(self.shared_content_words),
            "linkage_rule": self.linkage_rule,
            "competing_antecedent_turn_indices": list(self.competing_antecedent_turn_indices),
            "excluded_for_competing_antecedent": self.excluded_for_competing_antecedent,
        }


_LINKAGE_RULE_DESCRIPTION = (
    "cross-turn: a supporter suggestion turn ('you could/might/may/should "
    "try ...' or 'have you tried/considered ...') followed, within "
    f"{MAX_TURN_IDX_WINDOW} turn-idx and the same session, by a seeker turn "
    "containing an explicit anaphoric reference (that/it/this/what you "
    "said/suggested/mentioned/told me), at least one shared non-stopword "
    "content word (length >= 4) with the suggestion turn, and an explicit "
    "result-relation clause (memory/me.py's _RESULT_RELATION_PATTERNS) "
    "outside any question context. Excluded if more than one qualifying "
    "suggestion turn exists between the antecedent and the result turn "
    "(competing antecedent)."
)


def _find_suggestion_turns(session: Session) -> list[Turn]:
    return [t for t in session.supporter_turns() if _SUGGESTION_PATTERN.search(t.content)]


def _find_result_candidates_for_owner_session(
    owner_id: str, session: Session
) -> tuple[MeCrossTurnCandidate, ...]:
    suggestion_turns = _find_suggestion_turns(session)
    if not suggestion_turns:
        return ()

    candidates: list[MeCrossTurnCandidate] = []
    for seeker_turn in session.seeker_turns():
        result_match = _first_result_relation_match(seeker_turn.content, 0, len(seeker_turn.content))
        if result_match is None:
            continue
        if _is_question_context(seeker_turn.content, result_match.start()):
            continue

        anaphora_match = _anaphora_for_result_match(
            seeker_turn.content, result_match, MAX_ANAPHORA_TO_RESULT_GAP
        )
        if anaphora_match is None:
            continue

        # every suggestion turn strictly before this seeker turn, within window
        in_window = [
            s
            for s in suggestion_turns
            if s.idx < seeker_turn.idx and (seeker_turn.idx - s.idx) <= MAX_TURN_IDX_WINDOW
        ]
        if not in_window:
            continue

        result_words = _content_words(seeker_turn.content)
        linked = [s for s in in_window if _content_words(s.content) & result_words]
        if not linked:
            continue

        # nearest linked antecedent is the primary candidate pairing
        antecedent = max(linked, key=lambda s: s.idx)
        shared = tuple(sorted(_content_words(antecedent.content) & result_words))
        competing = tuple(sorted(s.idx for s in linked if s.idx != antecedent.idx))

        candidates.append(
            MeCrossTurnCandidate(
                owner_id=owner_id,
                session_id=session.session_id,
                action_turn_idx=antecedent.idx,
                action_span=(0, len(antecedent.content)),
                action_text=antecedent.content,
                result_turn_idx=seeker_turn.idx,
                result_span=(result_match.start(), len(seeker_turn.content)),
                result_text=seeker_turn.content[result_match.start() :],
                anaphora_span=(anaphora_match.start(), anaphora_match.end()),
                anaphora_text=seeker_turn.content[anaphora_match.start() : anaphora_match.end()],
                shared_content_words=shared,
                linkage_rule=_LINKAGE_RULE_DESCRIPTION,
                competing_antecedent_turn_indices=competing,
                excluded_for_competing_antecedent=len(competing) > 0,
            )
        )
    return tuple(candidates)


def build_me_cross_turn_proposal_rows(
    users: tuple[MemorySourceUser, ...],
) -> tuple[MeCrossTurnCandidate, ...]:
    rows: list[MeCrossTurnCandidate] = []
    for user in users:
        for session in user.sessions:
            rows.extend(_find_result_candidates_for_owner_session(user.owner_id, session))
    return tuple(rows)


def build_me_cross_turn_proposal_report(users: tuple[MemorySourceUser, ...]) -> dict[str, Any]:
    rows = build_me_cross_turn_proposal_rows(users)
    clean = [r for r in rows if not r.excluded_for_competing_antecedent]
    excluded = [r for r in rows if r.excluded_for_competing_antecedent]

    primary_unique = len(
        {
            f"{ep.owner_id}:{ep.action_session_id}:{ep.action_turn.idx}:{ep.action_span}"
            for u in users
            for ep in extract_action_result_episodes(u)
        }
    )
    primary_owners = len({u.owner_id for u in users if extract_action_result_episodes(u)})

    return {
        "protocol": "pm-paper1-me-cross-turn-proposal-report-v1",
        "status": "B29_3_DIAGNOSTIC_PROPOSAL_ONLY_NOT_ADOPTED",
        "outcome_calls": 0,
        "primary_me_unchanged": {
            "unique_candidate_count": primary_unique,
            "owners_with_candidates": primary_owners,
            "note": (
                "The primary ME compiler (memory/me.py, same-turn "
                "self-reported pattern only) is not modified by this audit "
                "-- recomputed here directly for contrast, not hardcoded."
            ),
        },
        "max_turn_idx_window": MAX_TURN_IDX_WINDOW,
        "clean_proposal_count": len(clean),
        "competing_antecedent_excluded_count": len(excluded),
        "total_proposal_count": len(rows),
        "no_llm_judgment_note": (
            "No LLM 'is this useful' judgment and no pure temporal-"
            "proximity pairing are used anywhere in this audit -- every "
            "inclusion/exclusion decision is one of the six mechanical "
            "gates in this module's docstring."
        ),
        "researcher_decision_required": True,
    }


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_me_cross_turn_proposal_manifest(
    rows: tuple[MeCrossTurnCandidate, ...], report: dict[str, Any], out_dir: Path
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows_path = out_dir / "es_memeval_public_me_cross_turn_proposal_rows_v1.jsonl"
    rendered_rows = "".join(_canonical(r.to_manifest_row()) + "\n" for r in rows)
    rows_path.write_text(rendered_rows, encoding="utf-8")

    report_path = out_dir / "es_memeval_public_me_cross_turn_proposal_audit_v1.json"
    report_path.write_text(_canonical(report) + "\n", encoding="utf-8")

    return {"rows": rows_path, "report": report_path}
