"""Historical V3 anchored-parser provenance; excluded from routine CI."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


PROJECT = Path(__file__).resolve().parents[2]
ANCHORED = PROJECT / "scripts/v3/14_derive_g0_esc_rank_anchored_scores.py"
spec = importlib.util.spec_from_file_location("paper1_rq0_anchored", ANCHORED)
assert spec is not None and spec.loader is not None
anchored = importlib.util.module_from_spec(spec)
spec.loader.exec_module(anchored)


@pytest.mark.parametrize(
    "adapter,raw,expected",
    [
        ("fluency", "The fluecy score is 3.", 3),
        ("empathic", "The empathy score is 4", 4),
        ("tech", " 2 ", 2),
        ("overall", "The human preference score is 0.", 0),
    ],
)
def test_anchored_parser_accepts_only_pinned_forms(adapter, raw, expected):
    assert anchored.parse_anchored_ordinal(raw, adapter) == expected


@pytest.mark.parametrize(
    "adapter,raw",
    [
        ("empathic", "score: 3"),
        ("empathic", "The empathy score is 3 because it is good."),
        ("empathic", "The fluency score is 3."),
        ("unknown", "The empathy score is 3."),
    ],
)
def test_anchored_parser_rejects_unbound_prose(adapter, raw):
    assert anchored.parse_anchored_ordinal(raw, adapter) is None
