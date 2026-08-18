import pytest

from metacom_pm.paper1.embeddings.bge_m3 import BgeM3Encoder, FROZEN_BGE_M3_BINDING

pytest.importorskip("torch")
pytest.importorskip("sentence_transformers")


def test_frozen_binding_matches_the_attested_official_rag_revision():
    # Same commit-addressed Hub PR-130 snapshot as
    # data/paper1_authority/paper1_official_rag_runtime_attestation_v1.json's
    # local_model_binding -- one shared encoder identity, not two.
    assert FROZEN_BGE_M3_BINDING.repo == "BAAI/bge-m3"
    assert FROZEN_BGE_M3_BINDING.revision == "9a0624b896d81da7492a910ffa53731274b6cf3d"
    assert FROZEN_BGE_M3_BINDING.pooling_mode == "cls"
    assert FROZEN_BGE_M3_BINDING.normalize_embeddings is True
    assert FROZEN_BGE_M3_BINDING.embedding_dimension == 1024


def test_encode_rejects_empty_input():
    encoder = BgeM3Encoder()
    with pytest.raises(ValueError, match="at least one"):
        encoder.encode([])


def test_encode_rejects_empty_string():
    encoder = BgeM3Encoder()
    with pytest.raises(ValueError, match="empty strings"):
        encoder.encode(["hello", ""])


@pytest.mark.gpu
def test_real_local_encode_produces_normalized_1024_dim_vectors():
    encoder = BgeM3Encoder()
    vectors = encoder.encode(
        [
            "I have been feeling really overwhelmed with work lately.",
            "My sister has been distant since the argument last month.",
        ]
    )
    assert len(vectors) == 2
    for vector in vectors:
        assert len(vector) == 1024
        norm = sum(value * value for value in vector) ** 0.5
        assert abs(norm - 1.0) < 1e-4


@pytest.mark.gpu
def test_real_local_encode_is_deterministic_for_the_same_text():
    encoder = BgeM3Encoder()
    a = encoder.encode(["consistent embedding check"])[0]
    b = encoder.encode(["consistent embedding check"])[0]
    assert a == b


@pytest.mark.gpu
def test_real_local_encode_gives_different_vectors_for_different_text():
    encoder = BgeM3Encoder()
    a, b = encoder.encode(["I feel anxious about my job interview.", "My cat knocked a vase off the shelf."])
    assert a != b
