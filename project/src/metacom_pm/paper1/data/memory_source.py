"""Sanitized runtime types for ES-MemEval-Public-v1.0.0-1427 (B12/B17/B18/B23).

This module never reads ``data/external/evo_emo.json`` and never imports
``metacom_pm.paper1.data.es_memeval`` (the evaluator/split-only, raw-JSON,
evidence-bearing module) or ``metacom_pm.paper1.data.materializer`` (the raw
JSON -> sanitized artifact builder). It only knows how to (a) hold the
sanitized types and (b) deserialize them from an *already-materialized*
JSON artifact file on disk (``load_sanitized_runtime_users``). Candidates,
memory extraction, and features import exclusively from here -- see
``metacom_pm.paper1.data.materializer`` module docstring for the one-way
dependency this enforces (materializer -> memory_source, never the reverse,
and runtime code -> memory_source only).

B17 runtime-visibility correction (verified directly against the pinned
official ES-MemEval source, commit ``692624208acc077b8867698c1d6fcd998
dee641a``, not assumed):

- QA (``src/lib/qa/qa_experiment.py``) and Summary
  (``src/lib/sum/sum_experiment.py``) both call
  ``ChatRoomBuilder.fill_chat_room(room, data)``, which iterates the
  seeker's *entire* ``dialog_history`` (every session, unconditionally) and
  records each one into the room's memory/document store *before* the
  question is asked -- the "full" experiment variants use
  ``SessionWiseMemoryInplaceStrategy(AlwaysAllDocumentStore(), False)``
  (literally "always all sessions"); the "rag" variants retrieve from the
  same all-sessions store. There is no per-question restriction to "sessions
  up to this question's own session" anywhere in the official harness --
  every question in a seeker's file sees the same full-history universe.
- DG's "full" supporter room builder (``src/exe/dg/dg_gpt4o_full.py``,
  identical pattern in the other model variants) does
  ``for history in parameters.data["dialog_history"]: ...
  ChatRoomBuilder.fill_session(room, history)`` -- the complete
  ``dialog_history``, verbatim, injected as real chat messages -- followed
  by a literal ``"The following dialogue happens now."`` marker. The
  supporter (what our PM stands in for) never receives
  ``subsequent_topics[].related_sessions``/``topic``/``psychological_
  condition``/``physical_condition``/``more_details`` at all; those fields
  are used exclusively to build the *seeker simulator's* system prompt
  (``src/lib/dg/dg_experiment.py``) -- genuinely simulator/evaluator-only
  hidden background, confirmed by reading the actual construction code, not
  inferred from field naming.

B23 runtime-visibility correction (same verification method, one layer
deeper): the room-construction code itself
(``src/lib/shared/chat_rooms/chat_room_builder.py``,
``ChatRoomBuilder.fill_chat_room``/``fill_session``, shared by QA, Summary,
and DG's "full" supporter room) builds every session/turn from only
``history["timestamp"]`` (the session boundary marker passed to
``room.begin_session``) and each ``dialogue["role"]``/``dialogue["content"]``
-- it never reads ``history["emotion"]`` or ``history["topic"]`` at all, for
any task type. Those two per-session dataset-author labels were still being
carried into ``Session``/the sanitized artifact/MS ``raw_descriptors`` before
this fix -- a runtime-visibility leak in the same family as B17's
group/related-session identity leak, just for annotation content rather than
identity. ``Session`` now carries only ``session_id``/``timestamp``/
``chronological_rank``/``turns`` -- no ``owner_id`` field either (it never
needed one: every ``Session`` only ever exists inside its owning
``MemorySourceUser.sessions``, and every consumer already reads owner
identity from that containing ``MemorySourceUser.owner_id``, never from the
session itself).

Consequently: ``Target.cutoff_rank`` is always the full session count for
its owner (every session is strict-past for every target of every task
type), and ``Target`` carries no ``context_session_ids`` field at all
(removed -- B17.2: question group / Summary group / DG related_sessions/
topic must never enter the runtime ``Target``, a feature, a retrieval query,
or a candidate-pool exclusion). The one legitimately runtime-visible piece
of "current state" is the QA/Summary ``question`` text itself -- not gold
(it is literally the input the officially-tested system receives), so it is
carried as ``Target.visible_query_text``. DG has no such text pre-generation
(``visible_query_text=None``): the real seeker utterance only exists once a
(currently unauthorized) generation runner actually simulates a turn.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

from metacom_pm.paper1.contracts import TaskType

TIMELINE_QUESTION_GROUP_ID = "timeline"


def _parse_date(raw: str) -> date:
    return date.fromisoformat(raw)


@dataclass(frozen=True)
class Turn:
    idx: int
    role: Literal["seeker", "supporter"]
    content: str


@dataclass(frozen=True)
class Session:
    """A single strictly-ordered dialog_history session, runtime-visible fields only.

    Deliberately does not carry the raw ``summary``/``observation`` fields:
    those are evaluator-authored annotations, not text the seeker or
    supporter produced, and must never be compiled into MS/ME candidate
    content (see the historical ESConv ``situation``-field privileged-input
    leak this project already found and fixed once).

    B23: also does not carry ``emotion``/``topic``. These are per-session
    dataset-author labels, not something the tested system (or anyone
    playing the supporter role) is ever shown. Verified directly against the
    pinned official harness (commit
    ``692624208acc077b8867698c1d6fcd998dee641a``,
    ``src/lib/shared/chat_rooms/chat_room_builder.py``):
    ``ChatRoomBuilder.fill_chat_room``/``fill_session`` construct every room
    turn from only ``history["timestamp"]`` (the session boundary marker)
    and each ``dialogue["role"]``/``dialogue["content"]`` -- ``emotion`` and
    ``topic`` are never read by the builder at all, for QA, Summary, or DG.
    Carrying them into ``Session`` and onward into MS ``raw_descriptors``
    was itself a runtime-visibility leak in the same family B17 already
    fixed for group/related-session identity, just for annotation content
    instead of identity.
    """

    session_id: str
    timestamp: str
    chronological_rank: int
    turns: tuple[Turn, ...]

    @property
    def date(self) -> date:
        return _parse_date(self.timestamp)

    def seeker_turns(self) -> tuple[Turn, ...]:
        return tuple(t for t in self.turns if t.role == "seeker")

    def supporter_turns(self) -> tuple[Turn, ...]:
        return tuple(t for t in self.turns if t.role == "supporter")


@dataclass(frozen=True)
class MemorySourceQuestionItem:
    """No ``evidence``. ``question`` is the officially-asked query text --
    not gold, the actual runtime input (see module docstring)."""

    idx: str
    question: str


@dataclass(frozen=True)
class MemorySourceQuestionGroup:
    question_group_id: str
    items: tuple[MemorySourceQuestionItem, ...]


@dataclass(frozen=True)
class MemorySourceSummaryItem:
    """No ``evidence``, no ``group`` (B18: Summary group is explicitly
    forbidden from the sanitized artifact), no ``answer``/``theme``.
    ``question`` is the officially-asked query text, same rationale as
    ``MemorySourceQuestionItem``."""

    idx: int
    question: str


@dataclass(frozen=True)
class MemorySourceSubsequentTopic:
    """Identity only. No ``related_sessions``, ``topic``, ``psychological_
    condition``, ``physical_condition``, or ``more_details`` -- B17/B18:
    confirmed simulator/evaluator-only hidden background, never visible to
    the system under test."""

    idx: int


@dataclass(frozen=True)
class MemorySourceUser:
    """Sanitized runtime user: public dialog_history + opaque target identity only.

    No QA/Summary ``evidence``, no ``answer``, no session ``summary``/
    ``observation``, no Summary ``group``, no DG ``related_sessions``/
    ``topic``/background, no ``basic_info``, no evaluator-authored hints of
    any kind.
    """

    owner_id: str
    sessions: tuple[Session, ...]
    question_groups: tuple[MemorySourceQuestionGroup, ...]
    summaries: tuple[MemorySourceSummaryItem, ...]
    subsequent_topics: tuple[MemorySourceSubsequentTopic, ...]

    def session_by_id(self, session_id: str) -> Session:
        for session in self.sessions:
            if session.session_id == session_id:
                return session
        raise KeyError(session_id)


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


@dataclass(frozen=True)
class Target:
    """One QA / Summary / Dialogue-Generation evaluation unit.

    ``cutoff_rank`` is always ``len(user.sessions)`` for this target's
    owner: the full ``dialog_history`` is strict-past for every target of
    every task type (B17, verified against the official evaluation harness
    -- see module docstring). There is no per-target restriction any more;
    a session is never excluded from any target's candidate pool.

    ``visible_query_text`` is the officially-asked QA/Summary ``question``
    text (not gold) for QA/Summary targets, and always ``None`` for DG (no
    static current-dialogue state exists pre-generation -- B17.4).

    No exact-evidence fingerprint, ``fold_id``/``group_component_id``, or
    other gold-derived/split-only field lives here; those are built
    exclusively in ``metacom_pm.paper1.splits`` from the evaluator/split-only
    ``metacom_pm.paper1.data.es_memeval`` module.

    ``identity_anomaly`` is set when the raw ``question_group_id`` does not
    resolve to any session owned by this ``owner_id`` (a real, rare data
    quirk in the public artifact: owner ``p6`` has a question group literally
    named ``p7_conv_17``, another owner's session-id shape). B17.5: this is
    audit-only -- it no longer gates ``cutoff_rank`` or empties the candidate
    pool, since cutoff/eligibility no longer depend on resolving the group id
    to any particular session at all.
    """

    target_id: str
    task_type: TaskType
    owner_id: str
    primary_group_key: str
    cutoff_rank: int
    visible_query_text: str | None
    identity_anomaly: str | None = None


def enumerate_targets(users: tuple[MemorySourceUser, ...]) -> tuple[Target, ...]:
    """Enumerate every QA / Summary / DG target.

    Every target's ``cutoff_rank`` is its owner's full session count (B17).
    ``identity_anomaly`` is still detected and reported (a real data-quality
    finding worth disclosing) but never changes ``cutoff_rank`` or empties a
    candidate pool -- see ``Target`` docstring.
    """

    targets: list[Target] = []
    for user in users:
        known_session_ids = {s.session_id for s in user.sessions}
        n_sessions = len(user.sessions)

        for group in user.question_groups:
            identity_anomaly: str | None = None
            if (
                group.question_group_id != TIMELINE_QUESTION_GROUP_ID
                and group.question_group_id not in known_session_ids
            ):
                identity_anomaly = (
                    "question_group_id "
                    f"{group.question_group_id!r} does not resolve to any session "
                    f"owned by {user.owner_id!r}"
                )
            for item in group.items:
                targets.append(
                    Target(
                        target_id=qa_target_id(user.owner_id, group.question_group_id, item.idx),
                        task_type=TaskType.QA,
                        owner_id=user.owner_id,
                        primary_group_key=qa_primary_group_key(
                            user.owner_id, group.question_group_id
                        ),
                        cutoff_rank=n_sessions,
                        visible_query_text=item.question,
                        identity_anomaly=identity_anomaly,
                    )
                )

        for summary in user.summaries:
            targets.append(
                Target(
                    target_id=summary_target_id(user.owner_id, summary.idx),
                    task_type=TaskType.SUMMARY,
                    owner_id=user.owner_id,
                    primary_group_key=summary_primary_group_key(user.owner_id, summary.idx),
                    cutoff_rank=n_sessions,
                    visible_query_text=summary.question,
                )
            )

        for topic in user.subsequent_topics:
            targets.append(
                Target(
                    target_id=dg_target_id(user.owner_id, topic.idx),
                    task_type=TaskType.DIALOGUE_GENERATION,
                    owner_id=user.owner_id,
                    primary_group_key=dg_primary_group_key(user.owner_id, topic.idx),
                    cutoff_rank=n_sessions,
                    visible_query_text=None,
                )
            )

    return tuple(targets)


# --- sanitized artifact (de)serialization -----------------------------------
#
# Pure data-shape functions: no file I/O, no raw-JSON knowledge. The
# materializer (metacom_pm.paper1.data.materializer) is the only module that
# calls `user_to_dict` while building the artifact; `load_sanitized_runtime_
# users` is what candidates/memory/features actually call.


def user_to_dict(user: MemorySourceUser) -> dict[str, Any]:
    return {
        "owner_id": user.owner_id,
        "sessions": [
            {
                "session_id": s.session_id,
                "timestamp": s.timestamp,
                "chronological_rank": s.chronological_rank,
                "turns": [{"idx": t.idx, "role": t.role, "content": t.content} for t in s.turns],
            }
            for s in user.sessions
        ],
        "question_groups": [
            {
                "question_group_id": g.question_group_id,
                "items": [{"idx": i.idx, "question": i.question} for i in g.items],
            }
            for g in user.question_groups
        ],
        "summaries": [{"idx": sm.idx, "question": sm.question} for sm in user.summaries],
        "subsequent_topics": [{"idx": t.idx} for t in user.subsequent_topics],
    }


def user_from_dict(payload: dict[str, Any]) -> MemorySourceUser:
    owner_id = payload["owner_id"]
    sessions = tuple(
        Session(
            session_id=s["session_id"],
            timestamp=s["timestamp"],
            chronological_rank=s["chronological_rank"],
            turns=tuple(Turn(idx=t["idx"], role=t["role"], content=t["content"]) for t in s["turns"]),
        )
        for s in payload["sessions"]
    )
    question_groups = tuple(
        MemorySourceQuestionGroup(
            question_group_id=g["question_group_id"],
            items=tuple(
                MemorySourceQuestionItem(idx=i["idx"], question=i["question"]) for i in g["items"]
            ),
        )
        for g in payload["question_groups"]
    )
    summaries = tuple(
        MemorySourceSummaryItem(idx=sm["idx"], question=sm["question"]) for sm in payload["summaries"]
    )
    subsequent_topics = tuple(MemorySourceSubsequentTopic(idx=t["idx"]) for t in payload["subsequent_topics"])
    return MemorySourceUser(
        owner_id=owner_id,
        sessions=sessions,
        question_groups=question_groups,
        summaries=summaries,
        subsequent_topics=subsequent_topics,
    )


def load_sanitized_runtime_users(artifact_path: Path) -> tuple[MemorySourceUser, ...]:
    """Read the already-materialized sanitized runtime artifact from disk.

    This is the *only* way candidates/memory/features should obtain
    ``MemorySourceUser`` data -- never ``data/external/evo_emo.json``
    directly, and never through ``metacom_pm.paper1.data.materializer``.
    """

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    return tuple(user_from_dict(u) for u in payload["users"])
