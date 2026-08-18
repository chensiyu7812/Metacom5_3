import json
from pathlib import Path

from metacom_pm.paper1.embeddings.bge_m3 import FROZEN_BGE_M3_BINDING

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "data/paper1_authority/paper1_bge_m3_formal_binding_v1.json"
RAG_ATTESTATION = ROOT / "data/paper1_authority/paper1_official_rag_runtime_attestation_v1.json"


def _artifact() -> dict:
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def test_artifact_encoder_identity_matches_live_code():
    doc = _artifact()
    binding = doc["encoder_binding"]
    assert binding["repo"] == FROZEN_BGE_M3_BINDING.repo
    assert binding["revision"] == FROZEN_BGE_M3_BINDING.revision
    assert binding["pooling_mode"] == FROZEN_BGE_M3_BINDING.pooling_mode
    assert binding["normalize_embeddings"] == FROZEN_BGE_M3_BINDING.normalize_embeddings
    assert binding["embedding_dimension"] == FROZEN_BGE_M3_BINDING.embedding_dimension
    assert binding["identity_sha256"] == FROZEN_BGE_M3_BINDING.identity_sha256


def test_artifact_shares_the_exact_revision_used_by_the_official_rag_attestation():
    doc = _artifact()
    rag = json.loads(RAG_ATTESTATION.read_text(encoding="utf-8"))
    assert doc["encoder_binding"]["revision"] == rag["local_model_binding"]["revision"]
    assert (
        doc["encoder_binding"]["model_safetensors_sha256"]
        == rag["local_model_binding"]["model_safetensors_sha256"]
    )


def test_official_rag_attestation_explicitly_did_not_cover_pm_features():
    # The formal binding's whole reason for existing is that this disclaimer
    # is real -- verify it, don't just assert it in prose.
    rag = json.loads(RAG_ATTESTATION.read_text(encoding="utf-8"))
    not_established = rag["interpretation"]["not_established"]
    assert any("Typed Memory" in item for item in not_established)
    assert any("RS retriever" in item for item in not_established)
    assert rag["formal_unlock"] is False


def test_artifact_declares_outcome_lock_still_engaged():
    doc = _artifact()
    assert doc["outcome_calls"] == 0
    assert doc["outcome_lock"] == "LOCKED_PRE_ZERO_OUTCOME_FREEZE"


def test_artifact_covers_all_four_heads():
    doc = _artifact()
    assert set(doc["per_head_text_construction"].keys()) == {"RS", "MP", "MS", "ME"}


def test_mp_ms_me_share_the_same_query_field_as_the_existing_lexical_proxy():
    doc = _artifact()
    for head in ("MP", "MS", "ME"):
        assert (
            doc["per_head_text_construction"][head]["query_field"]
            == "metacom_pm.paper1.data.memory_source.Target.visible_query_text"
        )


def test_rs_query_and_document_use_the_same_window_construction():
    doc = _artifact()
    rs = doc["per_head_text_construction"]["RS"]
    assert "preceding_turns=6" in rs["query_construction"] or "6" in rs["query_construction"]
    assert "6" in rs["document_construction"]


def test_artifact_is_explicit_about_what_is_not_yet_done():
    doc = _artifact()
    not_yet = " ".join(doc["not_yet_done"]).lower()
    assert "materializ" in not_yet
    assert "cosine similarity" in not_yet or "wiring" in not_yet
