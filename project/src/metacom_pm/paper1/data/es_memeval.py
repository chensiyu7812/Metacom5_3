"""Public-only loader and identity validation for ES-MemEval-Public-v1.0.0-1427.

Zero-outcome scope: this module reads only the raw dialogue/question/summary/
subsequent-topic structure needed to enumerate evaluation targets and locate
strict-past memory source material. It never reads a question `answer`, a
summary `answer`, or a session `observation`/`summary` field -- those are
evaluator-authored gold content and stay untouched until the outcome lock is
lifted. See ``metacom_pm.paper1.memory`` for the compilers built on top of the
types defined here.

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
for the prior formal decision this module cross-checks itself against.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml

from metacom_pm.paper1.contracts import TaskType

PAPER_QA_COUNT = 1209
PUBLIC_QA_COUNT = 1427
PUBLIC_ARTIFACT_NAME = "ES-MemEval-Public-v1.0.0-1427"
EXPECTED_USER_COUNT = 18
EXPECTED_SESSION_COUNT = 401
EXPECTED_SUMMARY_COUNT = 125
EXPECTED_DG_COUNT = 34

TIMELINE_QUESTION_GROUP_ID = "timeline"


def _sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


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


@dataclass(frozen=True)
class QuestionItem:
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


@dataclass(frozen=True)
class Target:
    """One QA / Summary / Dialogue-Generation evaluation unit.

    ``cutoff_rank`` is the first session ``chronological_rank`` that is *not*
    strict-past for this target: candidate compilers must only draw on
    sessions with ``chronological_rank < cutoff_rank``. Gold answer/summary
    text is never stored on this record.

    ``context_session_ids`` is the task's own *premise* sessions (QA: the
    session the question is anchored to; DG: ``related_sessions``; Summary:
    ``group``). Legitimately known at decision time, safe to use for
    outcome-blind current-context features (e.g. lexical overlap).

    This type deliberately carries no gold-adjacent evidence field (B8: no
    ``evidence_refs``, ``answer``, ``gold``, ``reference``, or ``observation``
    data). QA/Summary's answer-justifying ``evidence`` sets are gold-adjacent
    -- they encode which sessions the correct answer actually depends on --
    and are physically isolated in ``metacom_pm.paper1.splits.evidence``,
    the only module allowed to read them. Any module importing ``Target``
    (``candidates/``, ``features/``) structurally cannot access that data at
    all, rather than merely being asked not to use it.

    ``cutoff_rank`` is ``None`` and ``identity_anomaly`` is set when the raw
    ``question_group_id`` does not resolve to any session owned by this
    ``owner_id`` (a real, rare data quirk in the public artifact: e.g. owner
    ``p6`` has a question group literally named ``p7_conv_17``, another
    owner's session-id shape). This is a mechanical owner/identity mismatch,
    not something to silently repair by guessing the intended session, so
    such targets are kept (to preserve the total public row count) but
    compile zero candidates and are flagged, never silently resolved.
    """

    target_id: str
    task_type: TaskType
    owner_id: str
    primary_group_key: str
    cutoff_rank: int | None
    context_session_ids: tuple[str, ...]
    identity_anomaly: str | None = None


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


def parse_users(raw: list[dict[str, Any]]) -> tuple[UserRecord, ...]:
    """Parse raw EvoEmo user records, resolving true chronological session order.

    Session list order in the raw file is not reliably chronological (several
    users have out-of-order ``dialog_history`` entries). Sessions are
    re-sorted by parsed ``timestamp`` with original list position as a stable
    tie-break, since no user in the corpus has two sessions sharing a date.
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


def enumerate_targets(users: tuple[UserRecord, ...]) -> tuple[Target, ...]:
    """Enumerate every QA / Summary / DG target with its strict-past cutoff.

    Grouping keys follow the frozen mechanical rule (AGENTS.md / execution
    reconciliation): QA groups by ``owner::question_group_id`` (the whole
    session's question set, or the per-owner ``timeline`` group, is one
    primary group); Summary and DG are one target per item, left for the
    splits layer to union across exact evidence fingerprints rather than
    folding evidence into the primary key here.
    """

    targets: list[Target] = []
    for user in users:
        rank_by_session = {s.session_id: s.chronological_rank for s in user.sessions}
        n_sessions = len(user.sessions)

        for group in user.question_groups:
            identity_anomaly: str | None = None
            context_session_ids: tuple[str, ...]
            if group.question_group_id == TIMELINE_QUESTION_GROUP_ID:
                cutoff_rank = n_sessions
                context_session_ids = ()
            elif group.question_group_id in rank_by_session:
                cutoff_rank = rank_by_session[group.question_group_id] + 1
                context_session_ids = (group.question_group_id,)
            else:
                cutoff_rank = None
                context_session_ids = ()
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
                        cutoff_rank=cutoff_rank,
                        context_session_ids=context_session_ids,
                        identity_anomaly=identity_anomaly,
                    )
                )

        for summary in user.summaries:
            # Cutoff/context anchoring uses only `group` (the dataset's session
            # cluster premise for this summary target), never `evidence` (the
            # exact answer-justifying session set). `evidence` is never read in
            # this module at all -- see metacom_pm.paper1.splits.evidence,
            # the only place allowed to read it, for the fold fingerprint.
            group_sessions = tuple(sorted(set(summary.group)))
            referenced_ranks = [rank_by_session[s] for s in group_sessions]
            cutoff_rank = (max(referenced_ranks) + 1) if referenced_ranks else 0
            targets.append(
                Target(
                    target_id=summary_target_id(user.owner_id, summary.idx),
                    task_type=TaskType.SUMMARY,
                    owner_id=user.owner_id,
                    primary_group_key=summary_primary_group_key(user.owner_id, summary.idx),
                    cutoff_rank=cutoff_rank,
                    context_session_ids=group_sessions,
                )
            )

        for topic in user.subsequent_topics:
            referenced_ranks = [rank_by_session[s] for s in topic.related_sessions]
            cutoff_rank = (max(referenced_ranks) + 1) if referenced_ranks else 0
            targets.append(
                Target(
                    target_id=dg_target_id(user.owner_id, topic.idx),
                    task_type=TaskType.DIALOGUE_GENERATION,
                    owner_id=user.owner_id,
                    primary_group_key=dg_primary_group_key(user.owner_id, topic.idx),
                    cutoff_rank=cutoff_rank,
                    context_session_ids=topic.related_sessions,
                )
            )

    return tuple(targets)


def validate_es_memeval_identity(project_root: Path) -> dict[str, Any]:
    """Recompute the ES-MemEval-Public-v1.0.0-1427 identity from raw data.

    Independently re-derives user/session/QA/Summary/DG counts and QA
    ``row_id`` values from ``data/external/evo_emo.json`` and cross-checks
    them against the already-frozen ``data/v3_authority`` row identity
    manifest, without depending on that manifest for parsing. Zero outcome
    reads; raises on any pinned-hash or count drift instead of silently
    tolerating it.
    """

    evo_path = project_root / "data" / "external" / "evo_emo.json"
    config = yaml.safe_load(
        (project_root / "configs" / "paper1_public_only.yaml").read_text(encoding="utf-8")
    )
    expected_sha256 = config["public_sources"]["es_memeval"]["artifact_sha256"]
    actual_sha256 = _sha_bytes(evo_path.read_bytes())
    if actual_sha256 != expected_sha256:
        raise ValueError(
            "data/external/evo_emo.json no longer matches the pinned "
            "ES-MemEval-Public-v1.0.0-1427 artifact hash in paper1_public_only.yaml"
        )

    users = parse_users(load_users(evo_path))
    if len(users) != EXPECTED_USER_COUNT:
        raise ValueError(f"expected {EXPECTED_USER_COUNT} users, found {len(users)}")
    total_sessions = sum(len(u.sessions) for u in users)
    if total_sessions != EXPECTED_SESSION_COUNT:
        raise ValueError(f"expected {EXPECTED_SESSION_COUNT} sessions, found {total_sessions}")

    targets = enumerate_targets(users)
    qa_targets = [t for t in targets if t.task_type is TaskType.QA]
    summary_targets = [t for t in targets if t.task_type is TaskType.SUMMARY]
    dg_targets = [t for t in targets if t.task_type is TaskType.DIALOGUE_GENERATION]
    if len(qa_targets) != PUBLIC_QA_COUNT:
        raise ValueError(f"expected {PUBLIC_QA_COUNT} public QA targets, found {len(qa_targets)}")
    if len(summary_targets) != EXPECTED_SUMMARY_COUNT:
        raise ValueError(
            f"expected {EXPECTED_SUMMARY_COUNT} summary targets, found {len(summary_targets)}"
        )
    if len(dg_targets) != EXPECTED_DG_COUNT:
        raise ValueError(
            f"expected {EXPECTED_DG_COUNT} dialogue-generation targets, found {len(dg_targets)}"
        )

    derived_row_ids = {t.target_id for t in qa_targets}
    result: dict[str, Any] = {
        "protocol": "pm-paper1-es-memeval-public-identity-validation-v1",
        "artifact_name": PUBLIC_ARTIFACT_NAME,
        "source_sha256": actual_sha256,
        "paper_qa_count": PAPER_QA_COUNT,
        "public_qa_count": PUBLIC_QA_COUNT,
        "derived_counts": {
            "users": len(users),
            "sessions": total_sessions,
            "qa": len(qa_targets),
            "summary": len(summary_targets),
            "dialogue_generation": len(dg_targets),
        },
        "outcome_calls": 0,
    }

    authority_path = (
        project_root
        / "data"
        / "v3_authority"
        / "es_memeval_public_v1_0_0_1427_row_identity_v1.jsonl"
    )
    result["authority_manifest_present"] = authority_path.exists()
    if authority_path.exists():
        authority_rows = [
            json.loads(line) for line in authority_path.read_text(encoding="utf-8").splitlines() if line
        ]
        authority_row_ids = {row["row_id"] for row in authority_rows}
        result["authority_row_count"] = len(authority_row_ids)
        result["row_ids_match_authority_manifest"] = derived_row_ids == authority_row_ids

    return result
