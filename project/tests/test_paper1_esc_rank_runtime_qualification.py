from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


PROJECT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT / "scripts/paper1/26_qualify_esc_rank_runtime_24gib.py"


def _module():
    spec = importlib.util.spec_from_file_location("esc_rank_qualification", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(item_id: str) -> dict[str, object]:
    return {
        "blind_item_id": item_id,
        "dialogue": ["User: hello", "AI assistant: hi"],
        "source_role": "public_baseline",
    }


def test_runtime_dialogues_use_frozen_blind_item_id_schema(tmp_path: Path):
    module = _module()
    path = tmp_path / "dialogues.jsonl"
    rows = [_row(f"blind-{index}") for index in range(3)]
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    assert [row["blind_item_id"] for row in module._load_dialogues(path)] == [
        "blind-0",
        "blind-1",
        "blind-2",
    ]


def test_runtime_dialogues_reject_missing_blind_item_id(tmp_path: Path):
    module = _module()
    path = tmp_path / "dialogues.jsonl"
    rows = [_row(f"blind-{index}") for index in range(3)]
    rows[-1].pop("blind_item_id")
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="blind_item_id"):
        module._load_dialogues(path)
