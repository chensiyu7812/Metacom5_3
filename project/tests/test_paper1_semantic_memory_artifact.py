from __future__ import annotations

import json

import pytest

from metacom_pm.paper1.data.memory_source import MemorySourceUser, Session, Turn
from metacom_pm.paper1.semantic_memory.artifact import load_accepted_semantic_units
from metacom_pm.paper1.semantic_memory.contracts import (
    ExtractorSessionOutput,
    VerifierSessionOutput,
)
from metacom_pm.paper1.semantic_memory.grounding import (
    GROUNDING_VERSION,
    prior_memory_table_sha256,
    source_sha256,
)
from metacom_pm.paper1.semantic_memory.input_projection import build_session_compile_input
from metacom_pm.paper1.semantic_memory.runtime import (
    COMPILER_VERSION,
    SessionCompilationResult,
)


def _users() -> tuple[MemorySourceUser, ...]:
    return (
        MemorySourceUser(
            owner_id="u1",
            sessions=(
                Session(
                    session_id="s0",
                    timestamp="2024-01-01",
                    chronological_rank=0,
                    turns=(Turn(idx=1, role="seeker", content="first"),),
                ),
                Session(
                    session_id="s1",
                    timestamp="2024-01-02",
                    chronological_rank=1,
                    turns=(Turn(idx=1, role="seeker", content="second"),),
                ),
            ),
            question_groups=(),
            summaries=(),
            subsequent_topics=(),
        ),
    )


def _empty_result(owner_id: str, session: Session) -> SessionCompilationResult:
    source = build_session_compile_input(owner_id=owner_id, session=session)
    return SessionCompilationResult(
        compiler_version=COMPILER_VERSION,
        grounding_version=GROUNDING_VERSION,
        owner_id=owner_id,
        session_id=session.session_id,
        source_sha256=source_sha256(source),
        prior_memory_table_sha256=prior_memory_table_sha256(source),
        extractor=ExtractorSessionOutput(owner_id=owner_id, session_id=session.session_id),
        verifier=VerifierSessionOutput(
            owner_id=owner_id, session_id=session.session_id, decisions=()
        ),
        grounding=(),
        accepted_units=(),
        rejected_decisions=(),
        extractor_cache_hit=False,
        verifier_cache_hit=False,
    )


def _write_rows(path, rows) -> None:
    path.write_text(
        "".join(json.dumps(row.model_dump(mode="json"), sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_loader_requires_complete_exact_ordered_artifact(tmp_path) -> None:
    users = _users()
    rows = tuple(_empty_result("u1", session) for session in users[0].sessions)
    path = tmp_path / "results.jsonl"
    _write_rows(path, rows)
    assert load_accepted_semantic_units(path, users=users) == ()

    _write_rows(path, rows[:1])
    with pytest.raises(RuntimeError, match="not complete"):
        load_accepted_semantic_units(path, users=users)


def test_loader_rejects_equal_length_wrong_session_order(tmp_path) -> None:
    users = _users()
    rows = tuple(_empty_result("u1", session) for session in users[0].sessions)
    path = tmp_path / "results.jsonl"
    _write_rows(path, tuple(reversed(rows)))
    with pytest.raises(RuntimeError, match="exact ordered session set"):
        load_accepted_semantic_units(path, users=users)


def test_loader_recomputes_source_identity_from_sanitized_runtime(tmp_path) -> None:
    users = _users()
    rows = [
        _empty_result("u1", session).model_dump(mode="json")
        for session in users[0].sessions
    ]
    rows[0]["source_sha256"] = "0" * 64
    path = tmp_path / "results.jsonl"
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="source identity mismatch"):
        load_accepted_semantic_units(path, users=users)
