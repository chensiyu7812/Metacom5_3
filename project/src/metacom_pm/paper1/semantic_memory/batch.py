"""Stable 401-session ordering and append-only batch resume."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from metacom_pm.io import append_jsonl, iter_jsonl, sha256_file, write_json
from metacom_pm.paper1.data.memory_source import MemorySourceUser, Session

from .contracts import AcceptedSemanticMemoryUnit
from .grounding import prior_memory_table_sha256, source_sha256
from .input_projection import build_session_compile_input
from .runtime import SessionCompilationResult


class SessionCompiler(Protocol):
    @property
    def compiler_version(self) -> str: ...

    @property
    def grounding_version(self) -> str: ...

    def compile_session(self, source) -> SessionCompilationResult: ...


@dataclass(frozen=True)
class OrderedSession:
    owner_id: str
    session: Session


def ordered_public_sessions(users: tuple[MemorySourceUser, ...]) -> tuple[OrderedSession, ...]:
    """Deterministic owner order and authority-required within-owner order."""

    rows: list[OrderedSession] = []
    owner_ids = [user.owner_id for user in users]
    if len(owner_ids) != len(set(owner_ids)):
        raise ValueError("sanitized runtime users contain duplicate owner IDs")
    for user in sorted(users, key=lambda item: item.owner_id):
        seen_session_ids: set[str] = set()
        for session in sorted(user.sessions, key=lambda item: (item.timestamp, item.session_id)):
            if session.session_id in seen_session_ids:
                raise ValueError(f"duplicate session ID for owner {user.owner_id}")
            seen_session_ids.add(session.session_id)
            rows.append(OrderedSession(owner_id=user.owner_id, session=session))
    return tuple(rows)


def run_session_prefix(
    *,
    users: tuple[MemorySourceUser, ...],
    compiler: SessionCompiler,
    maximum_sessions: int,
    results_path: str | Path,
    report_path: str | Path,
) -> dict[str, object]:
    """Compile a stable prefix; existing successful rows must be an exact prefix."""

    if maximum_sessions < 1:
        raise ValueError("maximum_sessions must be positive")
    ordered = ordered_public_sessions(users)
    selected = ordered[:maximum_sessions]
    path = Path(results_path)
    existing_rows = list(iter_jsonl(path)) if path.exists() else []
    if len(existing_rows) > len(selected):
        raise RuntimeError("existing semantic compiler rows exceed selected session prefix")

    accepted_by_owner: dict[str, list[AcceptedSemanticMemoryUnit]] = defaultdict(list)
    for index, row in enumerate(existing_rows):
        expected = selected[index]
        result = SessionCompilationResult.model_validate(row)
        if (result.owner_id, result.session_id) != (
            expected.owner_id,
            expected.session.session_id,
        ):
            raise RuntimeError("existing semantic compiler rows are not the exact ordered prefix")
        source = build_session_compile_input(
            owner_id=expected.owner_id,
            session=expected.session,
            strictly_past_accepted_units=tuple(accepted_by_owner[expected.owner_id]),
        )
        if result.compiler_version != compiler.compiler_version:
            raise RuntimeError("existing semantic compiler row has a compiler-version mismatch")
        if result.grounding_version != compiler.grounding_version:
            raise RuntimeError("existing semantic compiler row has a grounding-version mismatch")
        if result.source_sha256 != source_sha256(source):
            raise RuntimeError("existing semantic compiler row has a source-identity mismatch")
        if result.prior_memory_table_sha256 != prior_memory_table_sha256(source):
            raise RuntimeError("existing semantic compiler row has a prior-table mismatch")
        accepted_by_owner[result.owner_id].extend(result.accepted_units)

    cache_hits = 0
    physical_stage_calls = 0
    for item in selected[len(existing_rows) :]:
        source = build_session_compile_input(
            owner_id=item.owner_id,
            session=item.session,
            strictly_past_accepted_units=tuple(accepted_by_owner[item.owner_id]),
        )
        result = compiler.compile_session(source)
        if result.compiler_version != compiler.compiler_version:
            raise RuntimeError("compiler result version mismatch")
        if result.grounding_version != compiler.grounding_version:
            raise RuntimeError("compiler result grounding-version mismatch")
        if result.source_sha256 != source_sha256(source):
            raise RuntimeError("compiler result source identity mismatch")
        if result.prior_memory_table_sha256 != prior_memory_table_sha256(source):
            raise RuntimeError("compiler result prior-table identity mismatch")
        append_jsonl(path, result.model_dump(mode="json"))
        accepted_by_owner[item.owner_id].extend(result.accepted_units)
        cache_hits += int(result.extractor_cache_hit) + int(result.verifier_cache_hit)
        physical_stage_calls += int(not result.extractor_cache_hit) + int(
            not result.verifier_cache_hit
        )

    all_rows = list(iter_jsonl(path)) if path.exists() else []
    validated = [SessionCompilationResult.model_validate(row) for row in all_rows]
    report: dict[str, object] = {
        "protocol": "paper1-semantic-memory-batch-report-v1",
        "selected_sessions": len(selected),
        "completed_sessions": len(validated),
        "accepted_units": sum(len(result.accepted_units) for result in validated),
        "extractor_proposals": sum(
            len(result.extractor.proposals) for result in validated
        ),
        "schema_invalid_proposals": sum(
            int(not bool(item.get("schema_valid")))
            for result in validated
            for item in result.grounding
        )
        + sum(
            int(item.phase == "extractor")
            for result in validated
            for item in result.schema_rejections
        ),
        "verifier_schema_invalid_decisions": sum(
            int(item.phase == "verifier")
            for result in validated
            for item in result.schema_rejections
        ),
        "structural_invalid_proposals": sum(
            int(not bool(item.get("structural_valid")))
            for result in validated
            for item in result.grounding
        ),
        "verifier_rejections": sum(len(result.rejected_decisions) for result in validated),
        "cache_hits_this_invocation": cache_hits,
        "physical_stage_calls_this_invocation": physical_stage_calls,
        "complete": len(validated) == len(selected),
        "results_sha256": sha256_file(path) if path.exists() else None,
        "outcome_calls": 0,
        "outcome_lock": "LOCKED_PRE_ZERO_OUTCOME_FREEZE",
    }
    write_json(report_path, report)
    return report
