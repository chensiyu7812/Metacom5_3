"""Evaluator/split-only raw loader for ES-MemEval-Public-v1.0.0-1427.

B12: this module is the *only* place in the paper1 namespace allowed to
carry QA/Summary ``evidence`` (the answer-justifying session-reference set --
gold-adjacent, since it encodes which sessions the correct answer actually
depends on). ``UserRecord``/``QuestionItem``/``SummaryItem``/``parse_users``
defined here must only ever be imported by
``metacom_pm.paper1.splits.evidence`` (the sole legitimate consumer, for
exact-evidence fold-fingerprint construction).

Everything candidates/memory/features/census actually run on --
``MemorySourceUser``, ``Target``, ``enumerate_targets``,
``validate_es_memeval_identity`` -- lives in the sibling module
``metacom_pm.paper1.data.memory_source``, which parses the same raw JSON
completely independently (never constructing a ``UserRecord`` at any point)
so there is no code path where gold-adjacent evidence is loaded and then
merely *not used* -- it is structurally unreachable from that module.

Neither module ever reads a question ``answer``, a summary ``answer``/
``question``/``theme``, a session ``observation``/``summary``, or any DG
``subsequent_topics`` narrative field (``topic``/``more_details``/
``physical_condition``/``psychological_condition``) -- those are all
evaluator-authored gold/premise-adjacent text and were never parsed into any
type in this package, full or sanitized.

Paper vs. public boundary: the WWW-2026 paper reports evaluating on 1209 QA
rows, but the exact 1209-row subset was never published (row IDs, filter
criteria, and selection script are all absent from the paper, the public
repository history, and its issue tracker). The pinned public repository
artifact (tag ``v1.0.0``, commit
``692624208acc077b8867698c1d6fcd998dee641a``) ships 1427 QA rows. Paper-1
evaluates on the complete public artifact and names it
``ES-MemEval-Public-v1.0.0-1427``; it does not claim row-identical
reproduction of the paper's 1209-question set. See
``data/v3_authority/es_memeval_public_v1_0_0_1427_identity_decision_v1.json``
for the prior formal decision this module's sibling cross-checks itself
against.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

PAPER_QA_COUNT = 1209
PUBLIC_QA_COUNT = 1427
PUBLIC_ARTIFACT_NAME = "ES-MemEval-Public-v1.0.0-1427"
EXPECTED_USER_COUNT = 18
EXPECTED_SESSION_COUNT = 401
EXPECTED_SUMMARY_COUNT = 125
EXPECTED_DG_COUNT = 34

TIMELINE_QUESTION_GROUP_ID = "timeline"


def _parse_date(raw: str) -> date:
    return date.fromisoformat(raw)


def _normalize_text_field(value: Any) -> str:
    """Raw ``topic``/``emotion`` are sometimes a string, sometimes a list of strings."""

    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


@dataclass(frozen=True)
class Turn:
    idx: int
    role: Literal["seeker", "supporter"]
    content: str


@dataclass(frozen=True)
class Session:
    """A single strictly-ordered past/current session, gold fields excluded.

    Deliberately does not carry the raw ``summary``/``observation`` fields:
    those are evaluator-authored annotations, not text the seeker or
    supporter produced, and must never be compiled into MS/ME candidate
    content (see the historical ESConv ``situation``-field privileged-input
    leak this project already found and fixed once).
    """

    owner_id: str
    session_id: str
    timestamp: str
    chronological_rank: int
    emotion: str
    topic: str
    turns: tuple[Turn, ...]

    @property
    def date(self) -> date:
        return _parse_date(self.timestamp)

    def seeker_turns(self) -> tuple[Turn, ...]:
        return tuple(t for t in self.turns if t.role == "seeker")

    def supporter_turns(self) -> tuple[Turn, ...]:
        return tuple(t for t in self.turns if t.role == "supporter")


def qa_target_id(owner_id: str, question_group_id: str, idx: str) -> str:
    return f"{owner_id}::{question_group_id}::{idx}"


def summary_target_id(owner_id: str, idx: int) -> str:
    return f"{owner_id}::summary::{idx}"


def dg_target_id(owner_id: str, idx: int) -> str:
    return f"{owner_id}::dg::{idx}"


def qa_primary_group_key(owner_id: str, question_group_id: str) -> str:
    return f"{owner_id}::qa::{question_group_id}"


def summary_primary_group_key(owner_id: str, idx: int) -> str:
    return f"{owner_id}::summary::{idx}"


def dg_primary_group_key(owner_id: str, idx: int) -> str:
    return f"{owner_id}::dg::{idx}"


def load_users(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("ES-MemEval/EvoEmo source must be a JSON array of user records")
    return raw


@dataclass(frozen=True)
class QuestionItem:
    """Evaluator/split-only: carries the answer-justifying ``evidence`` set."""

    owner_id: str
    question_group_id: str
    idx: str
    capability: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class QuestionGroup:
    owner_id: str
    question_group_id: str
    items: tuple[QuestionItem, ...]


@dataclass(frozen=True)
class SummaryItem:
    """Evaluator/split-only: carries the answer-justifying ``evidence`` set."""

    owner_id: str
    idx: int
    capability: str
    evidence: tuple[str, ...]
    group: tuple[str, ...]


@dataclass(frozen=True)
class SubsequentTopic:
    owner_id: str
    idx: int
    related_sessions: tuple[str, ...]


@dataclass(frozen=True)
class UserRecord:
    """Evaluator/split-only full parse. Do not import outside ``splits/evidence.py``.

    Candidates/memory/features/census must use
    ``metacom_pm.paper1.data.memory_source.MemorySourceUser`` instead, which
    is parsed independently from the same raw JSON and never constructs
    this type or its evidence-bearing ``QuestionItem``/``SummaryItem``
    members at any point.
    """

    owner_id: str
    sessions: tuple[Session, ...]
    question_groups: tuple[QuestionGroup, ...]
    summaries: tuple[SummaryItem, ...]
    subsequent_topics: tuple[SubsequentTopic, ...]

    def session_by_id(self, session_id: str) -> Session:
        for session in self.sessions:
            if session.session_id == session_id:
                return session
        raise KeyError(session_id)


def parse_users(raw: list[dict[str, Any]]) -> tuple[UserRecord, ...]:
    """Parse raw EvoEmo user records, resolving true chronological session order.

    Evaluator/split-only (see module docstring): the returned records carry
    QA/Summary ``evidence``. Session list order in the raw file is not
    reliably chronological (several users have out-of-order
    ``dialog_history`` entries); sessions are re-sorted by parsed
    ``timestamp`` with original list position as a stable tie-break, since
    no user in the corpus has two sessions sharing a date.
    """

    users: list[UserRecord] = []
    for raw_user in raw:
        owner_id = raw_user["id"]
        indexed = list(enumerate(raw_user["dialog_history"]))
        indexed.sort(key=lambda pair: (_parse_date(pair[1]["timestamp"]), pair[0]))

        sessions: list[Session] = []
        for rank, (_, raw_session) in enumerate(indexed):
            turns = tuple(
                Turn(idx=t["idx"], role=t["role"], content=t["content"])
                for t in raw_session["dialogue"]
            )
            sessions.append(
                Session(
                    owner_id=owner_id,
                    session_id=raw_session["id"],
                    timestamp=raw_session["timestamp"],
                    chronological_rank=rank,
                    emotion=_normalize_text_field(raw_session["emotion"]),
                    topic=_normalize_text_field(raw_session["topic"]),
                    turns=turns,
                )
            )

        question_groups = tuple(
            QuestionGroup(
                owner_id=owner_id,
                question_group_id=group["id"],
                items=tuple(
                    QuestionItem(
                        owner_id=owner_id,
                        question_group_id=group["id"],
                        idx=str(item["idx"]),
                        capability=item["capability"],
                        evidence=tuple(item.get("evidence", ())),
                    )
                    for item in group["questions"]
                ),
            )
            for group in raw_user["questions"]
        )
        summaries = tuple(
            SummaryItem(
                owner_id=owner_id,
                idx=item["idx"],
                capability=item["capability"],
                evidence=tuple(item.get("evidence", ())),
                group=tuple(item.get("group", ())),
            )
            for item in raw_user["summaries"]
        )
        subsequent_topics = tuple(
            SubsequentTopic(
                owner_id=owner_id,
                idx=item["idx"],
                related_sessions=tuple(item.get("related_sessions", ())),
            )
            for item in raw_user["subsequent_topics"]
        )

        users.append(
            UserRecord(
                owner_id=owner_id,
                sessions=tuple(sessions),
                question_groups=question_groups,
                summaries=summaries,
                subsequent_topics=subsequent_topics,
            )
        )
    return tuple(users)
