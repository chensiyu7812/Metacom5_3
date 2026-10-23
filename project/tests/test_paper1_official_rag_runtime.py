from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


PROJECT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT / "scripts/paper1/13_attest_official_rag_runtime.py"
ATTESTATION = (
    PROJECT
    / "data/paper1_authority/paper1_official_rag_runtime_attestation_v1.json"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("official_rag_attestation", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_official_rag_runtime_role_is_narrow_and_outcome_locked() -> None:
    payload = json.loads(ATTESTATION.read_text(encoding="utf-8"))
    assert payload["status"] == (
        "ENGINEERING_RUNTIME_ATTESTED_NOT_BASELINE_OR_RETRIEVER_FREEZE"
    )
    assert payload["outcome_calls"] == 0
    assert payload["formal_unlock"] is False
    assert payload["scope"] == {
        "arm": "ES_MEMEVAL_OFFICIAL_RAG_BASELINE_ENGINEERING_PATH",
        "benchmark_gold_or_scorer_outputs_read": False,
        "benchmark_targets_read": False,
        "generator_calls": 0,
        "rs_retriever_selected": False,
        "typed_memory_method_changed": False,
        "winner_selected": False,
    }


def test_official_source_and_local_revision_are_distinctly_bound() -> None:
    module = _load_module()
    payload = json.loads(ATTESTATION.read_text(encoding="utf-8"))
    official = payload["official_source_binding"]
    local = payload["local_model_binding"]
    assert official["commit"] == module.OFFICIAL_COMMIT
    assert official["model_id"] == "BAAI/bge-m3"
    assert official["model_revision_in_official_source"] is None
    assert official["retrieval_k"] == 4
    assert official["document_grain"] == "one_historical_session_per_Document"
    assert local["revision"] == module.LOCAL_MODEL_REVISION
    assert local["official_unpinned_main_weight_equivalence"] == "NOT_ESTABLISHED"
    assert local["revision_status"].endswith("NOT_RESEARCH_FREEZE")
    assert set(official["source_blobs"]) == set(module.OFFICIAL_SOURCE_BLOBS)


def test_checked_in_probe_uses_official_library_shape_and_deterministic_top4() -> None:
    payload = json.loads(ATTESTATION.read_text(encoding="utf-8"))
    runtime = payload["runtime"]
    assert runtime["package_versions"] == {
        "faiss-cpu": "1.12.0",
        "langchain-community": "0.3.28",
        "langchain-huggingface": "0.3.1",
        "sentence-transformers": "5.1.0",
    }
    probe = runtime["probe"]
    assert probe["device"] == "cuda"
    assert probe["embedding_client_class"] == "SentenceTransformer"
    assert probe["document_embedding_shape"] == [5, 1024]
    assert probe["faiss_index_class"] == "IndexFlatL2"
    assert probe["faiss_document_count"] == 5
    assert probe["faiss_dimension"] == 1024
    assert probe["repeat_exact"] is True
    assert len(probe["top4"]) == 4
    assert len({row["session_fixture_id"] for row in probe["top4"]}) == 4
    assert all(abs(norm - 1.0) < 1e-5 for norm in probe["document_vector_l2_norms"])


def test_model_snapshot_check_is_fail_closed(tmp_path: Path) -> None:
    module = _load_module()
    wrong_revision = tmp_path / "wrong-revision"
    wrong_revision.mkdir()
    with pytest.raises(RuntimeError, match="commit-addressed BGE-M3 revision"):
        module._verify_model_snapshot(wrong_revision)


def test_attestation_is_portable_and_does_not_contain_home_paths() -> None:
    text = ATTESTATION.read_text(encoding="utf-8")
    assert "/home/tokkio" not in text
    assert "metacom_paper1_rq1" not in text
    payload = json.loads(text)
    assert set(payload["attestation_inputs"]) == {
        "environment_lock_sha256",
        "local_environment_attestation_sha256",
        "public_only_config_sha256",
        "script_sha256",
    }
