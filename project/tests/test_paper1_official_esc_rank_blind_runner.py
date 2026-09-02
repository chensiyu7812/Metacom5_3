from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


PROJECT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT / "scripts/paper1/35_score_official_esc_rank_blind_qualification.py"


def _module():
    spec = importlib.util.spec_from_file_location("official_esc_blind", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_frozen_blind_loader_requires_exact_hash_and_24_opaque_rows(tmp_path):
    module = _module()
    rows = [
        {
            "blind_item_id": f"blind_{index}",
            "dialogue": ["ESC-Role：help", "AI assistant：support"],
            "protocol": "pm-paper1-esc-evaluator-judge-blind-input-v1",
        }
        for index in range(24)
    ]
    path = tmp_path / "blind.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    module.BLIND_INPUT_SHA256 = module.sha_file(path)
    assert len(module.load_frozen_blind_rows(path)) == 24
    rows[0]["arm"] = "ours"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    module.BLIND_INPUT_SHA256 = module.sha_file(path)
    with pytest.raises(ValueError, match="forbidden fields"):
        module.load_frozen_blind_rows(path)


def test_blind_runner_pins_real_frozen_input_identity():
    module = _module()
    path = PROJECT / "data/paper1_authority/paper1_esc_evaluator_judge_blind_input_20260820_v1.jsonl"
    assert module.sha_file(path) == module.BLIND_INPUT_SHA256
    assert len(module.load_frozen_blind_rows(path)) == 24
