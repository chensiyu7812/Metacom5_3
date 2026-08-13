from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNNER = PROJECT_ROOT / "scripts" / "v3" / "10_run_g0_esc_eval_screen.py"


def _module(path: Path, name: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_g0_manifest_materialization_is_stable_and_text_free() -> None:
    authority = PROJECT_ROOT / "data" / "v3_authority"
    report = json.loads((authority / "g0_generator_bakeoff_preflight_v1.json").read_text(encoding="utf-8"))
    rows_bytes = (authority / "g0_esc_eval_screening_manifest_v1.jsonl").read_bytes()
    rows = [json.loads(line) for line in rows_bytes.decode("utf-8").splitlines() if line]
    executor_bytes = (authority / "g0_executor_screening_manifest_v1.jsonl").read_bytes()
    executor = [json.loads(line) for line in executor_bytes.decode("utf-8").splitlines() if line]
    assert report["api_calls"] == 0
    assert report["contains_role_card_or_dialogue_text"] is False
    assert report["run_identity"] == "7a4d43f9049583d7151d0200f856ad04c8b2090f625171baa4b9868ecbd9de40"
    assert hashlib.sha256(rows_bytes).hexdigest() == report["screening_sample"]["manifest_sha256"]
    assert hashlib.sha256(executor_bytes).hexdigest() == report["executor_sample"]["manifest_sha256"]
    assert len(rows) == len({row["card_key"] for row in rows}) == 24
    assert not any("text" in key or "problem" in key for row in rows for key in row)
    assert len(executor) == 32
    assert len({row["packet_id"] for row in executor}) == 16
    assert len({row["owner_cluster_id"] for row in executor}) == 16
    assert not any("messages" in row or "context" in row for row in executor)


def test_g0_source_quota_is_stratified_not_a_convenience_sample() -> None:
    path = PROJECT_ROOT / "data" / "v3_authority" / "g0_esc_eval_screening_manifest_v1.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    assert Counter(row["source"] for row in rows) == {
        "ESconv": 8,
        "MHP": 5,
        "ExTES": 5,
        "Psych": 3,
        "EPITOME": 3,
    }


def test_role_seed_is_common_across_candidate_trajectories() -> None:
    runner = _module(RUNNER, "v3_g0_runner")
    assert runner._role_seed("english::ESconv::1", 1) == runner._role_seed("english::ESconv::1", 1)
    assert runner._role_seed("english::ESconv::1", 1) != runner._role_seed("english::ESconv::1", 2)


def test_qwen_identity_is_dated_and_thinking_is_disabled() -> None:
    contract = json.loads(
        (PROJECT_ROOT / "data" / "v3_authority" / "g0_generator_bakeoff_contract_v1.json").read_text(encoding="utf-8")
    )
    qwen = next(row for row in contract["candidates"] if row["candidate_id"] == "qwen37_plus_primary_challenger")
    assert qwen["model"] == "qwen3.7-plus-2026-05-26"
    assert qwen["enable_thinking"] is False
