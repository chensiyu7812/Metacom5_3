from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts/paper1/10_attest_paper1_environment.py"
LOCK = PROJECT_ROOT / "environments/requirements-paper1-py311.lock.txt"


def _load_module():
    spec = importlib.util.spec_from_file_location("paper1_environment_attestation", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lock_is_exact_and_contains_required_runtime_packages() -> None:
    module = _load_module()
    packages = module.parse_lock(LOCK)
    assert packages["torch"] == "2.3.1+cu121"
    assert packages["transformers"] == "4.57.6"
    assert packages["tokenizers"] == "0.22.2"
    assert packages["scikit-learn"] == "1.9.0"
    assert packages["pytest"] == "8.4.2"


def test_snapshot_hash_verification_is_fail_closed(tmp_path: Path) -> None:
    module = _load_module()
    payload = tmp_path / "tokenizer.json"
    payload.write_bytes(b"reviewed")
    expected = {"tokenizer.json": module.hashlib.sha256(b"reviewed").hexdigest()}
    assert module.verify_files(tmp_path, expected) == expected

    payload.write_bytes(b"drifted")
    with pytest.raises(ValueError, match="snapshot hash mismatch"):
        module.verify_files(tmp_path, expected)


def test_attestation_status_cannot_claim_research_freeze() -> None:
    module = _load_module()
    assert module.STATUS == "ENGINEERING_CAPABLE_NOT_RESEARCH_FROZEN"
    source = SCRIPT.read_text(encoding="utf-8")
    assert '"outcome_calls": 0' in source
    assert '"nvidia_nim_provider_parity": "PENDING_M2_FREEZE"' in source
