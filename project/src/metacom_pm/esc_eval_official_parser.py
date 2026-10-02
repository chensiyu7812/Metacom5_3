"""Versioned compatibility layer for the pinned official ESC-Eval parser.

This module is deliberately separate from ``esc_rank_runtime`` because that
older module is a hash-bound dependency of completed historical RQ0 evidence.
The 2026-09-02 pre-outcome amendment authorizes this official parser only for
new Paper-1 evaluator qualification and later authorized ESC-Eval runs.
"""

from __future__ import annotations

from metacom_pm.esc_rank_runtime import parse_strict_ordinal


OFFICIAL_LABEL_LIST = ("0", "1", "2", "3", "4")


def parse_official_ordinal(raw: str) -> int | None:
    """Reproduce the pinned ESC-Eval ``score.py`` label-loop semantics."""

    for label in OFFICIAL_LABEL_LIST:
        if label in raw:
            return int(label)
    return None


def official_parser_diagnostics(raw: str) -> dict[str, object]:
    """Return non-gating diagnostics without changing official semantics."""

    hits = [label for label in OFFICIAL_LABEL_LIST if label in raw]
    strict = parse_strict_ordinal(raw)
    return {
        "official_label_hits": hits,
        "multiple_official_label_hits": len(hits) > 1,
        "strict_full_string_ordinal": strict,
        "strict_full_string_valid": strict is not None,
    }
