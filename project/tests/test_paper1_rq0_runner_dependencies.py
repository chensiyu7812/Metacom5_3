from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from metacom_pm.esc_rank_runtime import (
    ESCRankRuntimeIdentity,
    parse_strict_ordinal,
    repair_official_adapter_paths,
)


ROOT = Path(__file__).resolve().parents[1]
ANCHORED = ROOT / "scripts/v3/14_derive_g0_esc_rank_anchored_scores.py"
spec = importlib.util.spec_from_file_location("paper1_rq0_anchored", ANCHORED)
assert spec is not None and spec.loader is not None
anchored = importlib.util.module_from_spec(spec)
spec.loader.exec_module(anchored)


@pytest.mark.parametrize("raw,expected", [("0", 0), (" 1\n", 1), ("4", 4)])
def test_strict_parser_accepts_only_complete_ordinals(raw, expected):
    assert parse_strict_ordinal(raw) == expected


@pytest.mark.parametrize("raw", ["", "5", "score: 4", "4 because it is good", "[3]"])
def test_strict_parser_rejects_prose(raw):
    assert parse_strict_ordinal(raw) is None


def test_adapter_path_repair_is_bounded():
    source = 'a="./ESC-RANK1/fluency"\nb="./ESC-RANK1/fluency_en"\n'
    repaired = repair_official_adapter_paths(source)
    assert repaired == 'a="./ESC-RANK/fluency"\nb="./ESC-RANK/fluency_en"\n'
    with pytest.raises(ValueError):
        repair_official_adapter_paths(repaired)


def test_runtime_identity_pins_public_revisions():
    identity = ESCRankRuntimeIdentity().as_dict()
    assert all(
        len(identity[key]) == 40
        for key in ("esc_eval_commit", "esc_rank_revision", "esc_role_revision", "base_model_revision")
    )


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
