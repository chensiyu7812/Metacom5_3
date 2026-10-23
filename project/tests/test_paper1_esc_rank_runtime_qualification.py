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


class _Cuda:
    def __init__(self, *, available: bool, count: int, total_memory: int = 0):
        self._available = available
        self._count = count
        self._total_memory = total_memory

    def is_available(self) -> bool:
        return self._available

    def device_count(self) -> int:
        return self._count

    def get_device_properties(self, _index: int):
        return type("Properties", (), {"total_memory": self._total_memory})()


def test_gpu_inventory_uses_cuda_visible_device_namespace():
    module = _module()
    cuda = _Cuda(available=True, count=1, total_memory=48 * 1024**3)
    assert module._gpu_total_mib(cuda) == 48 * 1024


def test_gpu_inventory_rejects_zero_or_multiple_visible_devices():
    module = _module()
    with pytest.raises(RuntimeError, match="available CUDA"):
        module._gpu_total_mib(_Cuda(available=False, count=0))
    with pytest.raises(RuntimeError, match="exactly one visible"):
        module._gpu_total_mib(_Cuda(available=True, count=2))


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
