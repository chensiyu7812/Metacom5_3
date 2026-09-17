"""Stable 401-session ordering and append-only active compiler resume."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from metacom_pm.io import append_jsonl, iter_jsonl, sha256_file, write_json
from metacom_pm.paper1.data.memory_source import MemorySourceUser, Session

from .contracts import AcceptedAtomicMemoryUnit, AcceptedEventExperienceUnit
from .grounding import prior_profile_sha256, source_sha256
from .input_projection import build_session_input
from .runtime import SessionCompilationResult


class SessionCompiler(Protocol):
    @property
    def compiler_identity_sha256(self) -> str: ...

    def compile_session(self, source) -> SessionCompilationResult: ...


@dataclass(frozen=True)
class OrderedSession:
    owner_id: str
    session: Session


def ordered_public_sessions(users: tuple[MemorySourceUser, ...]) -> tuple[OrderedSession, ...]:
    owner_ids = [user.owner_id for user in users]
    if len(owner_ids) != len(set(owner_ids)):
        raise ValueError("public runtime users contain duplicate owner IDs")
    return tuple(
        OrderedSession(user.owner_id, session)
        for user in sorted(users, key=lambda row: row.owner_id)
        for session in sorted(user.sessions, key=lambda row: (row.timestamp, row.session_id))
    )


def run_session_prefix(
    *,
    users: tuple[MemorySourceUser, ...],
    compiler: SessionCompiler,
    maximum_sessions: int,
    results_path: str | Path,
    report_path: str | Path,
) -> dict[str, object]:
    ordered = ordered_public_sessions(users)
    if not 1 <= maximum_sessions <= len(ordered):
        raise ValueError("maximum_sessions is outside the public session range")
    selected = ordered[:maximum_sessions]
    results = Path(results_path)
    existing = list(iter_jsonl(results)) if results.exists() else []
    if len(existing) > len(selected):
        raise RuntimeError("existing active compiler rows exceed selected prefix")

    accepted_by_owner: dict[str, list[AcceptedAtomicMemoryUnit]] = defaultdict(list)
    for index, raw in enumerate(existing):
        expected = selected[index]
        row = SessionCompilationResult.model_validate(raw)
        if (row.owner_id, row.session_id) != (
            expected.owner_id,
            expected.session.session_id,
        ):
            raise RuntimeError("active compiler resume rows are not an exact prefix")
        source = build_session_input(
            owner_id=expected.owner_id,
            session=expected.session,
            strictly_past_units=tuple(accepted_by_owner[expected.owner_id]),
        )
        if row.source_sha256 != source_sha256(source):
            raise RuntimeError("active compiler resume source identity mismatch")
        if row.prior_profile_sha256 != prior_profile_sha256(source):
            raise RuntimeError("active compiler resume prior-profile identity mismatch")
        accepted_by_owner[row.owner_id].extend(row.accepted_units)

    for item in selected[len(existing) :]:
        source = build_session_input(
            owner_id=item.owner_id,
            session=item.session,
            strictly_past_units=tuple(accepted_by_owner[item.owner_id]),
        )
        row = compiler.compile_session(source)
        if (row.owner_id, row.session_id) != (item.owner_id, item.session.session_id):
            raise RuntimeError("active compiler result owner/session mismatch")
        if row.source_sha256 != source_sha256(source):
            raise RuntimeError("active compiler result source mismatch")
        if row.prior_profile_sha256 != prior_profile_sha256(source):
            raise RuntimeError("active compiler result prior-profile mismatch")
        append_jsonl(results, row.model_dump(mode="json"))
        accepted_by_owner[row.owner_id].extend(row.accepted_units)

    rows = [SessionCompilationResult.model_validate(row) for row in iter_jsonl(results)]
    units = [unit for row in rows for unit in row.accepted_units]
    profile_units = [unit for unit in units if not isinstance(unit, AcceptedEventExperienceUnit)]
    event_units = [unit for unit in units if isinstance(unit, AcceptedEventExperienceUnit)]
    report: dict[str, object] = {
        "protocol": "paper1-multi-view-compiler-batch-report-v1",
        "status": "COMPLETE" if len(rows) == len(selected) else "INCOMPLETE",
        "compiler_identity_sha256": compiler.compiler_identity_sha256,
        "selected_sessions": len(selected),
        "completed_sessions": len(rows),
        "owners": len({row.owner_id for row in rows}),
        "accepted_units": len(units),
        "accepted_MP": len(profile_units),
        "accepted_ME": len(event_units),
        "ME_type_counts": dict(
            sorted(Counter(row.event_experience_type.value for row in event_units).items())
        ),
        "schema_rejections": sum(len(row.schema_rejections) for row in rows),
        "grounding_rejections": sum(
            sum(not bool(item["valid"]) for item in row.grounding) for row in rows
        ),
        "semantic_rejections": sum(len(row.rejected_decisions) for row in rows),
        "extractor_cache_hits": sum(row.extractor_cache_hit for row in rows),
        "verifier_cache_hits_or_skips": sum(row.verifier_cache_hit for row in rows),
        "session_results_sha256": sha256_file(results),
        "formal_outcome_calls": 0,
        "pm_training_runs": 0,
    }
    write_json(report_path, report)
    return report


__all__ = ["OrderedSession", "ordered_public_sessions", "run_session_prefix"]
