"""Fail-closed loading of completed semantic-compiler result artifacts."""

from __future__ import annotations

from pathlib import Path

from metacom_pm.io import iter_jsonl
from metacom_pm.paper1.data.memory_source import MemorySourceUser

from .batch import ordered_public_sessions
from .contracts import AcceptedSemanticMemoryUnit
from .grounding import (
    GROUNDING_VERSION,
    prior_memory_table_sha256,
    source_sha256,
)
from .input_projection import build_session_compile_input
from .runtime import COMPILER_VERSION, SessionCompilationResult


def load_accepted_semantic_units(
    results_path: str | Path,
    *,
    users: tuple[MemorySourceUser, ...],
) -> tuple[AcceptedSemanticMemoryUnit, ...]:
    """Load a complete, exact ordered 401-session artifact.

    A smoke prefix is intentionally not a formal candidate source.  Rebuild
    each request projection from the sanitized runtime and the previously
    accepted units so source/prior-table identities are checked as well as
    schema versions.
    """

    path = Path(results_path)
    if not path.is_file():
        raise FileNotFoundError(f"semantic compiler result artifact not found: {path}")
    raw_rows = list(iter_jsonl(path))
    expected = ordered_public_sessions(users)
    if len(raw_rows) != len(expected):
        raise RuntimeError(
            "semantic compiler artifact is not complete: "
            f"expected {len(expected)} sessions, found {len(raw_rows)}"
        )

    units: list[AcceptedSemanticMemoryUnit] = []
    accepted_by_owner: dict[str, list[AcceptedSemanticMemoryUnit]] = {}
    for line_no, (raw, expected_row) in enumerate(zip(raw_rows, expected), 1):
        result = SessionCompilationResult.model_validate(raw)
        expected_key = (expected_row.owner_id, expected_row.session.session_id)
        if (result.owner_id, result.session_id) != expected_key:
            raise RuntimeError(
                f"semantic compiler artifact is not the exact ordered session set at line {line_no}"
            )
        if result.compiler_version != COMPILER_VERSION:
            raise RuntimeError(f"compiler version mismatch at line {line_no}")
        if result.grounding_version != GROUNDING_VERSION:
            raise RuntimeError(f"grounding version mismatch at line {line_no}")
        if (result.extractor.owner_id, result.extractor.session_id) != expected_key:
            raise RuntimeError(f"extractor binding mismatch at line {line_no}")
        if (result.verifier.owner_id, result.verifier.session_id) != expected_key:
            raise RuntimeError(f"verifier binding mismatch at line {line_no}")

        prior_units = tuple(accepted_by_owner.get(result.owner_id, ()))
        source = build_session_compile_input(
            owner_id=expected_row.owner_id,
            session=expected_row.session,
            strictly_past_accepted_units=prior_units,
        )
        if result.source_sha256 != source_sha256(source):
            raise RuntimeError(f"source identity mismatch at line {line_no}")
        if result.prior_memory_table_sha256 != prior_memory_table_sha256(source):
            raise RuntimeError(f"prior-memory-table mismatch at line {line_no}")
        for unit in result.accepted_units:
            if unit.compiler_version != result.compiler_version:
                raise RuntimeError(f"accepted-unit compiler mismatch at line {line_no}")
            if (unit.owner_id, unit.source_session_id) != expected_key:
                raise RuntimeError(f"accepted-unit source binding mismatch at line {line_no}")
            if unit.source_session_rank != expected_row.session.chronological_rank:
                raise RuntimeError(f"accepted-unit session-rank mismatch at line {line_no}")
            if unit.timestamp != expected_row.session.timestamp:
                raise RuntimeError(f"accepted-unit timestamp mismatch at line {line_no}")
            if unit.source_sha256 != result.source_sha256:
                raise RuntimeError(f"accepted-unit source hash mismatch at line {line_no}")
            if unit.prior_memory_table_sha256 != result.prior_memory_table_sha256:
                raise RuntimeError(f"accepted-unit prior-table hash mismatch at line {line_no}")
            units.append(unit)
        accepted_by_owner.setdefault(result.owner_id, []).extend(result.accepted_units)
    memory_ids = [unit.memory_id for unit in units]
    if len(memory_ids) != len(set(memory_ids)):
        raise RuntimeError("semantic compiler artifact contains duplicate memory IDs")
    return tuple(units)
