"""Fail-closed loading of a complete active Multi-View compiler artifact."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from metacom_pm.io import iter_jsonl
from metacom_pm.paper1.data.memory_source import MemorySourceUser

from .batch import ordered_public_sessions
from .contracts import AcceptedAtomicMemoryUnit
from .grounding import MULTI_VIEW_GROUNDING_VERSION, prior_profile_sha256, source_sha256
from .input_projection import build_session_input
from .runtime import MULTI_VIEW_COMPILER_VERSION, SessionCompilationResult


def load_accepted_multi_view_units(
    results_path: str | Path,
    *,
    users: tuple[MemorySourceUser, ...],
) -> tuple[AcceptedAtomicMemoryUnit, ...]:
    """Load the exact ordered 401-session result and rebuild its strict-past chain."""

    path = Path(results_path)
    if not path.is_file():
        raise FileNotFoundError(f"Multi-View compiler result artifact not found: {path}")
    raw_rows = list(iter_jsonl(path))
    expected = ordered_public_sessions(users)
    if len(raw_rows) != len(expected):
        raise RuntimeError(
            "Multi-View compiler artifact is not complete: "
            f"expected {len(expected)} sessions, found {len(raw_rows)}"
        )

    accepted_by_owner: dict[str, list[AcceptedAtomicMemoryUnit]] = defaultdict(list)
    units: list[AcceptedAtomicMemoryUnit] = []
    compiler_identities: set[str] = set()
    for line_no, (raw, expected_row) in enumerate(zip(raw_rows, expected), 1):
        result = SessionCompilationResult.model_validate(raw)
        expected_key = (expected_row.owner_id, expected_row.session.session_id)
        if (result.owner_id, result.session_id) != expected_key:
            raise RuntimeError(
                f"Multi-View artifact is not the exact ordered session set at line {line_no}"
            )
        if result.compiler_version != MULTI_VIEW_COMPILER_VERSION:
            raise RuntimeError(f"compiler version mismatch at line {line_no}")
        if result.grounding_version != MULTI_VIEW_GROUNDING_VERSION:
            raise RuntimeError(f"grounding version mismatch at line {line_no}")
        if (result.extractor.owner_id, result.extractor.session_id) != expected_key:
            raise RuntimeError(f"extractor binding mismatch at line {line_no}")
        if (result.verifier.owner_id, result.verifier.session_id) != expected_key:
            raise RuntimeError(f"verifier binding mismatch at line {line_no}")

        source = build_session_input(
            owner_id=expected_row.owner_id,
            session=expected_row.session,
            strictly_past_units=tuple(accepted_by_owner[result.owner_id]),
        )
        if result.source_sha256 != source_sha256(source):
            raise RuntimeError(f"source identity mismatch at line {line_no}")
        if result.prior_profile_sha256 != prior_profile_sha256(source):
            raise RuntimeError(f"prior-profile identity mismatch at line {line_no}")

        turns = {turn.turn_id: turn for turn in source.turns}
        for unit in result.accepted_units:
            if (
                unit.owner_id,
                unit.source_session_id,
                unit.source_session_rank,
                unit.timestamp,
            ) != (
                expected_row.owner_id,
                expected_row.session.session_id,
                expected_row.session.chronological_rank,
                expected_row.session.timestamp,
            ):
                raise RuntimeError(f"accepted-unit source binding mismatch at line {line_no}")
            compiler_identities.add(unit.compiler_identity_sha256)
            for span in unit.supporting_spans:
                turn = turns.get(span.turn_id)
                if turn is None or turn.role != "seeker":
                    raise RuntimeError(f"accepted-unit span role/identity mismatch at line {line_no}")
                if span.turn_index != turn.turn_index:
                    raise RuntimeError(f"accepted-unit span index mismatch at line {line_no}")
                if turn.content[span.start_char : span.end_char] != span.exact_text:
                    raise RuntimeError(f"accepted-unit span text/offset mismatch at line {line_no}")
            units.append(unit)
        accepted_by_owner[result.owner_id].extend(result.accepted_units)

    memory_ids = [unit.memory_id for unit in units]
    if len(memory_ids) != len(set(memory_ids)):
        raise RuntimeError("Multi-View compiler artifact contains duplicate memory IDs")
    if len(compiler_identities) != 1:
        raise RuntimeError("accepted units do not share one compiler identity")
    return tuple(units)


__all__ = ["load_accepted_multi_view_units"]
