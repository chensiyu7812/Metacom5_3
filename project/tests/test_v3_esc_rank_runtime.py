from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from metacom_pm.esc_rank_runtime import (
    ESCRankRuntimeIdentity,
    parse_strict_ordinal,
    repair_official_adapter_paths,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT_PATH = PROJECT_ROOT / "scripts" / "v3" / "08_materialize_esc_rank_runtime_preflight.py"


def _preflight_module():
    spec = importlib.util.spec_from_file_location("esc_rank_preflight", PREFLIGHT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("raw, expected", [("0", 0), (" 1\n", 1), ("4", 4)])
def test_strict_parser_accepts_only_complete_ordinals(raw: str, expected: int) -> None:
    assert parse_strict_ordinal(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "5", "-1", "score: 4", "4 because it is good", "0/4", "[3]", "three"],
)
def test_strict_parser_rejects_prose_and_out_of_range_values(raw: str) -> None:
    assert parse_strict_ordinal(raw) is None


def test_path_repair_is_bounded_and_fail_closed() -> None:
    source = 'a="./ESC-RANK1/fluency"\nb="./ESC-RANK1/fluency_en"\n'
    repaired = repair_official_adapter_paths(source)
    assert repaired == 'a="./ESC-RANK/fluency"\nb="./ESC-RANK/fluency_en"\n'
    with pytest.raises(ValueError):
        repair_official_adapter_paths(repaired)


def test_runtime_identity_pins_all_public_model_revisions() -> None:
    identity = ESCRankRuntimeIdentity().as_dict()
    assert all(len(identity[key]) == 40 for key in ("esc_eval_commit", "esc_rank_revision", "esc_role_revision", "base_model_revision"))


def test_static_preflight_is_zero_inference(tmp_path: Path) -> None:
    # Use the pinned public checkout only when it is present in the development
    # environment; clean CI validates the deterministic helpers above.
    checkout = Path("/tmp/metacom-v3-scorer.n72OOF/esc_eval")
    if not checkout.is_dir():
        pytest.skip("pinned public ESC-Eval checkout not present")
    result = _preflight_module().materialize(checkout)
    assert result["inference_calls"] == 0
    assert result["model_weights_downloaded"] == 0
    assert result["status"].startswith("STATIC_OVERLAY_PREFLIGHT_PASS")
