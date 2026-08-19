import pytest

from metacom_pm.paper1.embeddings.bge_m3 import BgeM3Binding, BgeM3Encoder, FROZEN_BGE_M3_BINDING

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
    assert FROZEN_BGE_M3_BINDING.max_seq_length == 8192
    assert FROZEN_BGE_M3_BINDING.truncation_side == "right"
    assert FROZEN_BGE_M3_BINDING.dtype == "torch.float32"


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


@pytest.mark.gpu
def test_load_time_assertions_pass_against_the_real_model_and_verify_weights():
    # _load_model asserts pooling_mode/max_seq_length/truncation_side/dtype
    # against the live model and re-hashes the actual local weights file --
    # this is the real regression test for the 2026-08-19 hardening: it
    # must not raise for the genuinely-correct frozen binding.
    encoder = BgeM3Encoder()
    runtime_identity = encoder.runtime_identity
    assert runtime_identity.weights_sha256_verified == FROZEN_BGE_M3_BINDING.model_safetensors_sha256
    assert runtime_identity.torch_version
    assert runtime_identity.sentence_transformers_version


@pytest.mark.gpu
def test_load_time_assertion_fails_closed_on_a_wrong_declared_pooling_mode():
    wrong_binding = BgeM3Binding(pooling_mode="mean")
    encoder = BgeM3Encoder(wrong_binding)
    with pytest.raises(RuntimeError, match="pooling_mode mismatch"):
        encoder.encode(["trigger a real load"])


@pytest.mark.gpu
def test_load_time_assertion_fails_closed_on_a_wrong_declared_max_seq_length():
    wrong_binding = BgeM3Binding(max_seq_length=512)
    encoder = BgeM3Encoder(wrong_binding)
    with pytest.raises(RuntimeError, match="max_seq_length mismatch"):
        encoder.encode(["trigger a real load"])


@pytest.mark.gpu
def test_load_time_assertion_fails_closed_on_a_wrong_declared_weight_hash():
    wrong_binding = BgeM3Binding(model_safetensors_sha256="0" * 64)
    encoder = BgeM3Encoder(wrong_binding)
    with pytest.raises(RuntimeError, match="model.safetensors hash mismatch"):
        encoder.encode(["trigger a real load"])


@pytest.mark.gpu
def test_encode_fails_closed_on_text_that_would_be_silently_truncated():
    # 2026-08-19 hardening: max_seq_length=8192 was only asserted at
    # load-time against the model's own config, never checked against real
    # candidate/document text at encode-time -- sentence-transformers would
    # have silently truncated (truncation_side="right") anything longer
    # rather than raising. This must now fail closed instead.
    encoder = BgeM3Encoder()
    way_too_long_text = "This is a long emotional support dialogue turn. " * 2000
    with pytest.raises(RuntimeError, match="exceeding max_seq_length"):
        encoder.encode([way_too_long_text])


@pytest.mark.gpu
def test_encode_accepts_text_within_max_seq_length():
    encoder = BgeM3Encoder()
    vectors = encoder.encode(["A short, well within bounds support message."])
    assert len(vectors) == 1
    assert len(vectors[0]) == 1024


@pytest.mark.gpu
def test_adaptive_batching_handles_long_text_past_the_4000_char_tier():
    encoder = BgeM3Encoder()
    long_text = "This is a long emotional support dialogue turn. " * 100
    assert len(long_text) > 4000
    vectors = encoder.encode([long_text, "short text"])
    assert len(vectors) == 2
    for vector in vectors:
        assert len(vector) == 1024
        norm = sum(value * value for value in vector) ** 0.5
        assert abs(norm - 1.0) < 1e-3
