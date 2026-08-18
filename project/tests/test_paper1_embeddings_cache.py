import pytest
from pydantic import ValidationError

from metacom_pm.io import sha256_text
from metacom_pm.paper1.embeddings.bge_m3 import BgeM3Binding, FROZEN_BGE_M3_BINDING
from metacom_pm.paper1.embeddings.cache import EmbeddingCallIdentity, EmbeddingSuccessCache


def _identity(text: str = "hello world", field_source: str = "rs.query_text") -> EmbeddingCallIdentity:
    return EmbeddingCallIdentity(
        binding_identity_sha256=FROZEN_BGE_M3_BINDING.identity_sha256,
        field_source=field_source,
        text_sha256=sha256_text(text),
    )


def test_frozen_binding_identity_is_stable_across_instances():
    assert BgeM3Binding().identity_sha256 == FROZEN_BGE_M3_BINDING.identity_sha256


def test_binding_identity_changes_when_revision_changes():
    other = BgeM3Binding(revision="0000000000000000000000000000000000000000")
    assert other.identity_sha256 != FROZEN_BGE_M3_BINDING.identity_sha256


def test_binding_identity_changes_when_pooling_changes():
    other = BgeM3Binding(pooling_mode="mean")
    assert other.identity_sha256 != FROZEN_BGE_M3_BINDING.identity_sha256


def test_binding_identity_changes_when_normalization_changes():
    other = BgeM3Binding(normalize_embeddings=False)
    assert other.identity_sha256 != FROZEN_BGE_M3_BINDING.identity_sha256


def test_cache_miss_returns_none(tmp_path):
    cache = EmbeddingSuccessCache(tmp_path)
    assert cache.load(_identity()) is None


def test_cache_round_trip(tmp_path):
    cache = EmbeddingSuccessCache(tmp_path)
    identity = _identity()
    vector = (0.1, 0.2, 0.3)
    cache.store_success(identity, vector)
    loaded = cache.load(identity)
    assert loaded == vector


def test_cache_is_content_addressed_by_text_and_binding(tmp_path):
    cache = EmbeddingSuccessCache(tmp_path)
    a = _identity(text="hello world")
    b = _identity(text="goodbye world")
    assert a.cache_key != b.cache_key
    cache.store_success(a, (1.0,))
    cache.store_success(b, (2.0,))
    assert cache.load(a) == (1.0,)
    assert cache.load(b) == (2.0,)


def test_cache_key_is_stable_regardless_of_field_source_metadata_ordering(tmp_path):
    # field_source is audit metadata, not part of what makes two embeddings
    # comparable, but it IS part of the identity model -- two different
    # field_source values for the same text still get distinct cache
    # entries (harmless duplication), not silently merged.
    cache = EmbeddingSuccessCache(tmp_path)
    a = _identity(text="same text", field_source="rs.query_text")
    b = _identity(text="same text", field_source="mp.visible_query_text")
    assert a.cache_key != b.cache_key


def test_rewriting_the_same_identity_with_the_same_vector_is_a_noop(tmp_path):
    cache = EmbeddingSuccessCache(tmp_path)
    identity = _identity()
    cache.store_success(identity, (0.5, 0.5))
    cache.store_success(identity, (0.5, 0.5))
    assert cache.load(identity) == (0.5, 0.5)


def test_rewriting_the_same_identity_with_a_different_vector_fails_closed(tmp_path):
    cache = EmbeddingSuccessCache(tmp_path)
    identity = _identity()
    cache.store_success(identity, (0.5, 0.5))
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        cache.store_success(identity, (0.9, 0.9))


def test_embedding_call_identity_rejects_bad_hash_shape():
    with pytest.raises(ValidationError):
        EmbeddingCallIdentity(
            binding_identity_sha256="not-a-hash",
            field_source="rs.query_text",
            text_sha256=sha256_text("x"),
        )
