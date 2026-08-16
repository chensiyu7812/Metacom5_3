"""Sanitized runtime types for ES-MemEval-Public-v1.0.0-1427 (B12).

``MemorySourceUser`` and ``parse_memory_source_users`` are parsed directly
from the same raw ``data/external/evo_emo.json`` JSON that
``metacom_pm.paper1.data.es_memeval.parse_users`` reads, but *independently*
-- this module never constructs an ``es_memeval.UserRecord``,
``QuestionItem``, or ``SummaryItem`` at any point, so there is no code path
here where QA/Summary ``evidence`` is loaded and then merely not used. It is
structurally unreachable: this file contains no reference to the word
``evidence`` in any parsing logic, by construction.

This is the *only* module ``candidates/``, ``memory/``, and ``features/``
may import for a "which user/target am I looking at" type. ``Target`` here
carries only mechanical identity, the strict-past ``cutoff_rank``, and the
task's own premise/context session ids (``context_session_ids``) -- never an
exact-evidence fingerprint or any other gold-derived field; that lives
exclusively in ``metacom_pm.paper1.splits`` (``GroupComponentAssignment`` /
``SplitEvidenceRecord``), built from ``metacom_pm.paper1.data.es_memeval``.

``enumerate_targets`` and ``validate_es_memeval_identity`` also live here
(moved from ``es_memeval.py``) because they are part of the outcome-blind
runtime surface, not the evaluator/split surface.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from metacom_pm.paper1.contracts import TaskType
from metacom_pm.paper1.data.es_memeval import (
    EXPECTED_DG_COUNT,
    EXPECTED_SESSION_COUNT,
    EXPECTED_SUMMARY_COUNT,
    EXPECTED_USER_COUNT,
    PAPER_QA_COUNT,
    PUBLIC_ARTIFACT_NAME,
    PUBLIC_QA_COUNT,
    TIMELINE_QUESTION_GROUP_ID,
    Session,
    Turn,
    _normalize_text_field,
    _parse_date,
    dg_primary_group_key,
    dg_target_id,
    load_users,
    qa_primary_group_key,
    qa_target_id,
    summary_primary_group_key,
    summary_target_id,
)


def _sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class MemorySourceQuestionItem:
    """No ``evidence``, no ``question``/``answer`` text -- identity only."""

    idx: str


@dataclass(frozen=True)
class MemorySourceQuestionGroup:
    question_group_id: str
    items: tuple[MemorySourceQuestionItem, ...]


@dataclass(frozen=True)
class MemorySourceSummaryItem:
    """No ``evidence``, no ``question``/``answer``/``theme`` text.

    ``group`` (the dataset's session-cluster premise for this summary
    target) is kept: it is the task's own premise, not answer-justifying
    evidence -- see ``Target.context_session_ids`` docstring below.
    """

    idx: int
    group: tuple[str, ...]


@dataclass(frozen=True)
class MemorySourceSubsequentTopic:
    """No narrative fields (``topic``/``more_details``/``physical_condition``/
    ``psychological_condition``) -- those are DG evaluator-authored premise
    text. Only ``related_sessions`` (the task's own premise session ids) is
    kept, same rationale as ``MemorySourceSummaryItem.group``.
    """

    idx: int
    related_sessions: tuple[str, ...]


@dataclass(frozen=True)
class MemorySourceUser:
    """Sanitized runtime user: public history only, no gold/evidence fields.

    Carries ``owner_id`` and the public session/turn/timestamp/topic/emotion
    history, plus the minimal QA/Summary/DG identity needed to enumerate
    targets (group/topic ids, item indices, premise session ids) -- never a
    QA/Summary ``evidence`` set, ``answer``, ``question`` text, session
    ``summary``/``observation``, or DG narrative field.
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


def parse_memory_source_users(raw: list[dict[str, Any]]) -> tuple[MemorySourceUser, ...]:
    """Parse raw EvoEmo user records into the sanitized runtime type.

    Independent of ``es_memeval.parse_users`` (see module docstring): reads
    only ``id``/``timestamp``/``emotion``/``topic``/``dialogue`` (sessions),
    ``id``/``idx`` (question groups/items), ``idx``/``group`` (summaries),
    and ``idx``/``related_sessions`` (subsequent topics) from the raw dicts.
    Never indexes ``"evidence"``, ``"answer"``, ``"question"``, ``"theme"``,
    ``"summary"``, ``"observation"``, ``"more_details"``,
    ``"physical_condition"``, or ``"psychological_condition"``.
    """

    users: list[MemorySourceUser] = []
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
            MemorySourceQuestionGroup(
                question_group_id=group["id"],
                items=tuple(
                    MemorySourceQuestionItem(idx=str(item["idx"])) for item in group["questions"]
                ),
            )
            for group in raw_user["questions"]
        )
        summaries = tuple(
            MemorySourceSummaryItem(idx=item["idx"], group=tuple(item.get("group", ())))
            for item in raw_user["summaries"]
        )
        subsequent_topics = tuple(
            MemorySourceSubsequentTopic(
                idx=item["idx"], related_sessions=tuple(item.get("related_sessions", ()))
            )
            for item in raw_user["subsequent_topics"]
        )

        users.append(
            MemorySourceUser(
                owner_id=owner_id,
                sessions=tuple(sessions),
                question_groups=question_groups,
                summaries=summaries,
                subsequent_topics=subsequent_topics,
            )
        )
    return tuple(users)


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

    This type carries only mechanical identity, ``cutoff_rank``, and
    ``context_session_ids`` -- no exact-evidence fingerprint, no
    ``fold_id``/``group_component_id``, no other gold-derived field. Those
    live exclusively in ``metacom_pm.paper1.splits``
    (``GroupComponentAssignment`` / ``SplitEvidenceRecord``), built from the
    evaluator/split-only ``metacom_pm.paper1.data.es_memeval`` module.
    ``Target`` is constructed here from ``MemorySourceUser`` alone, so a
    module that only imports ``Target``/``enumerate_targets`` structurally
    cannot reach evidence at all -- not merely asked not to use it.

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


def enumerate_targets(users: tuple[MemorySourceUser, ...]) -> tuple[Target, ...]:
    """Enumerate every QA / Summary / DG target with its strict-past cutoff.

    Grouping keys follow the frozen mechanical rule (AGENTS.md / execution
    reconciliation): QA groups by ``owner::question_group_id`` (the whole
    session's question set, or the per-owner ``timeline`` group, is one
    primary group); Summary and DG are one target per item, left for the
    splits layer to union across exact evidence fingerprints rather than
    folding evidence into the primary key here. Operates entirely on the
    sanitized ``MemorySourceUser`` -- never touches evidence.
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
    ``row_id`` values from ``data/external/evo_emo.json`` (via the sanitized
    ``parse_memory_source_users``, not the evaluator/split loader) and
    cross-checks them against the already-frozen ``data/v3_authority`` row
    identity manifest, without depending on that manifest for parsing. Zero
    outcome reads; raises on any pinned-hash or count drift instead of
    silently tolerating it.
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

    users = parse_memory_source_users(load_users(evo_path))
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
