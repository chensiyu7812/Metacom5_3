from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "v3" / "14_derive_g0_esc_rank_anchored_scores.py"
spec = importlib.util.spec_from_file_location("g0_anchored_derivative", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.mark.parametrize(
    "adapter,raw,expected",
    [
        ("fluency", "The fluecy score is 3.", 3),
        ("empathic", "The empathy score is 4", 4),
        ("tech", " 2 ", 2),
        ("overall", "The human preference score is 0.", 0),
    ],
)
def test_anchored_parser_accepts_only_pinned_forms(adapter: str, raw: str, expected: int) -> None:
    assert module.parse_anchored_ordinal(raw, adapter) == expected


@pytest.mark.parametrize(
    "adapter,raw",
    [
        ("empathic", "score: 3"),
        ("empathic", "The empathy score is 3 because it is good."),
        ("empathic", "The fluency score is 3."),
        ("unknown", "The empathy score is 3."),
        ("overall", "The human preference score is 7."),
    ],
)
def test_anchored_parser_rejects_unbound_prose(adapter: str, raw: str) -> None:
    assert module.parse_anchored_ordinal(raw, adapter) is None
