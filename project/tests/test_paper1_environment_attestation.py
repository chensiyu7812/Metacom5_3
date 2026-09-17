from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "scripts/paper1/10_attest_paper1_environment.py"
LOCK = PROJECT_ROOT / "environments/requirements-paper1-py311.lock.txt"
ATTESTATION = (
    PROJECT_ROOT
    / "data/paper1_authority/paper1_local_environment_attestation_v1.json"
)


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
    assert packages["langchain-huggingface"] == "0.3.1"
    assert packages["sentence-transformers"] == "5.1.0"
    assert packages["faiss-cpu"] == "1.12.0"
    assert packages["tiktoken"] == "0.12.0"


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
    assert '"hosted_nim_parity": "NOT_CLAIMED_RETIRED_PROVIDER"' in source
    assert '"provider": "local_A6000_Transformers_reference_server"' in source
    assert module.BGE_M3_REPO == "BAAI/bge-m3"
    assert module.BGE_M3_REVISION == "9a0624b896d81da7492a910ffa53731274b6cf3d"


def test_encoder_roles_distinguish_smoke_challenger_from_official_model_id() -> None:
    module = _load_module()
    source = SCRIPT.read_text(encoding="utf-8")
    assert "RS_LIGHTWEIGHT_CHALLENGER_AND_ENGINEERING_SMOKE_NOT_RETRIEVER_FREEZE" in source
    assert "ACTIVE_TYPED_MEMORY_ENCODER_AND_OFFICIAL_RAG_COMPARATOR_MODEL_ID" in source
    assert "OFFICIAL_LIBRARY_RUNTIME_ATTESTED_UPSTREAM_MAIN_WEIGHT_EQUIVALENCE_NOT_ESTABLISHED_REVISION_FREEZE_PENDING" in source
    assert module.BGE_REPO != module.BGE_M3_REPO


def test_checked_in_attestation_records_both_cuda_encoder_probes() -> None:
    payload = json.loads(ATTESTATION.read_text(encoding="utf-8"))
    assert payload["outcome_calls"] == 0
    assert payload["bge_small_encoder_candidate"]["probe"]["shape"] == [2, 384]
    assert payload["bge_m3_encoder_candidate"]["probe"]["shape"] == [2, 1024]
    assert payload["bge_small_encoder_candidate"]["probe"]["device"] == "cuda"
    assert payload["bge_m3_encoder_candidate"]["probe"]["device"] == "cuda"
    binding = payload["bge_m3_encoder_candidate"]["official_es_memeval_binding"]
    assert binding["model_id"] == "BAAI/bge-m3"
    assert binding["store"] == "FAISS"
    assert binding["session_level_top_k"] == 4
    assert binding["revision_in_official_source"] is None
