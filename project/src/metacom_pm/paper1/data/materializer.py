"""B18: the ONE module allowed to read raw evo_emo.json for the runtime side.

Builds ``MemorySourceUser`` records (defined in ``metacom_pm.paper1.data.
memory_source``, which this module depends on -- never the reverse) directly
from the raw JSON and writes the sanitized runtime artifact to disk. Every
other runtime consumer (``candidates/``, ``memory/``, ``features/``) reads
that artifact file via ``memory_source.load_sanitized_runtime_users`` and
never touches raw ``evo_emo.json`` or this module.

B18's other legitimate raw-JSON readers are ``metacom_pm.paper1.data.
es_memeval`` (the evaluator/split-only module ``metacom_pm.paper1.splits.
evidence`` depends on) and the official evaluator itself (Codex A's RQ1/RQ2
adapters, out of this lane's scope). This module never imports
``es_memeval`` and never reads QA/Summary ``evidence``, ``answer``, session
``summary``/``observation``, Summary ``group``, or any DG ``subsequent_
topics`` field beyond ``idx`` -- see ``memory_source`` module docstring for
why (B17 runtime-visibility finding).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from metacom_pm.paper1.contracts import TaskType
from metacom_pm.paper1.data.memory_source import (
    MemorySourceQuestionGroup,
    MemorySourceQuestionItem,
    MemorySourceSubsequentTopic,
    MemorySourceSummaryItem,
    MemorySourceUser,
    Session,
    Turn,
    enumerate_targets,
    user_to_dict,
)

PAPER_QA_COUNT = 1209
PUBLIC_QA_COUNT = 1427
PUBLIC_ARTIFACT_NAME = "ES-MemEval-Public-v1.0.0-1427"
EXPECTED_USER_COUNT = 18
EXPECTED_SESSION_COUNT = 401
EXPECTED_SUMMARY_COUNT = 125
EXPECTED_DG_COUNT = 34

SANITIZED_ARTIFACT_SCHEMA_VERSION = "pm-paper1-sanitized-runtime-artifact-v1"


def _sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _parse_date_key(raw: str):
    from datetime import date

    return date.fromisoformat(raw)


def _normalize_text_field(value: Any) -> str:
    """Raw ``topic``/``emotion`` are sometimes a string, sometimes a list of strings."""

    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def load_raw_users(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("ES-MemEval/EvoEmo source must be a JSON array of user records")
    return raw


def build_sanitized_runtime_users(raw: list[dict[str, Any]]) -> tuple[MemorySourceUser, ...]:
    """Parse raw EvoEmo user records directly into sanitized runtime types.

    Reads only ``id``/``timestamp``/``emotion``/``topic``/``dialogue``
    (sessions), ``id``/``idx``/``question`` (question groups/items),
    ``idx``/``question`` (summaries), and ``idx`` (subsequent topics).
    Never indexes ``"evidence"``, ``"answer"``, ``"theme"``, ``"group"``,
    ``"summary"``, ``"observation"``, ``"related_sessions"``, ``"topic"``
    (the DG scenario field -- distinct from the session-level ``"topic"``
    label, which *is* read), ``"more_details"``, ``"physical_condition"``,
    ``"psychological_condition"``, or ``"basic_info"``.
    """

    users: list[MemorySourceUser] = []
    for raw_user in raw:
        owner_id = raw_user["id"]
        indexed = list(enumerate(raw_user["dialog_history"]))
        indexed.sort(key=lambda pair: (_parse_date_key(pair[1]["timestamp"]), pair[0]))

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
                    MemorySourceQuestionItem(idx=str(item["idx"]), question=item["question"])
                    for item in group["questions"]
                ),
            )
            for group in raw_user["questions"]
        )
        summaries = tuple(
            MemorySourceSummaryItem(idx=item["idx"], question=item["question"])
            for item in raw_user["summaries"]
        )
        subsequent_topics = tuple(
            MemorySourceSubsequentTopic(idx=item["idx"]) for item in raw_user["subsequent_topics"]
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


def write_sanitized_runtime_artifact(evo_path: Path, out_path: Path) -> dict[str, Any]:
    """Build and write the sanitized runtime artifact; return a build report."""

    users = build_sanitized_runtime_users(load_raw_users(evo_path))
    payload = {
        "schema": SANITIZED_ARTIFACT_SCHEMA_VERSION,
        "source_artifact_name": PUBLIC_ARTIFACT_NAME,
        "source_sha256": _sha_bytes(evo_path.read_bytes()),
        "users": [user_to_dict(u) for u in users],
    }
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")

    targets = enumerate_targets(users)
    return {
        "protocol": "pm-paper1-sanitized-runtime-artifact-build-v1",
        "outcome_calls": 0,
        "schema": SANITIZED_ARTIFACT_SCHEMA_VERSION,
        "source_sha256": payload["source_sha256"],
        "artifact_sha256": _sha_bytes(rendered.encode("utf-8")),
        "users": len(users),
        "sessions": sum(len(u.sessions) for u in users),
        "qa_targets": sum(1 for t in targets if t.task_type is TaskType.QA),
        "summary_targets": sum(1 for t in targets if t.task_type is TaskType.SUMMARY),
        "dg_targets": sum(1 for t in targets if t.task_type is TaskType.DIALOGUE_GENERATION),
        "identity_anomalies": sum(1 for t in targets if t.identity_anomaly is not None),
    }


def validate_es_memeval_identity(project_root: Path) -> dict[str, Any]:
    """Recompute the ES-MemEval-Public-v1.0.0-1427 identity from raw data.

    Independently re-derives user/session/QA/Summary/DG counts and QA
    ``target_id`` values from ``data/external/evo_emo.json`` (via the
    sanitized materializer, not ``es_memeval.parse_users``) and cross-checks
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

    users = build_sanitized_runtime_users(load_raw_users(evo_path))
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
