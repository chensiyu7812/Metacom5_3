import math

import pytest
from pydantic import ValidationError

from metacom_pm.io import sha256_text
from metacom_pm.paper1.embeddings.bge_m3 import BGE_M3_EMBEDDING_DIMENSION, BgeM3Binding, FROZEN_BGE_M3_BINDING
from metacom_pm.paper1.embeddings.cache import EmbeddingCallIdentity, EmbeddingSuccessCache


FAKE_RUNTIME_IDENTITY_SHA256 = sha256_text("torch==2.13.0+cu130;sentence-transformers==5.7.0")


def _identity(
    text: str = "hello world",
    field_source: str = "rs.query_text",
    runtime_identity_sha256: str = FAKE_RUNTIME_IDENTITY_SHA256,
) -> EmbeddingCallIdentity:
    return EmbeddingCallIdentity(
        binding_identity_sha256=FROZEN_BGE_M3_BINDING.identity_sha256,
        runtime_identity_sha256=runtime_identity_sha256,
        field_source=field_source,
        text_sha256=sha256_text(text),
    )


def _unit_vector(seed: float = 0.0) -> tuple[float, ...]:
    """A real 1024-dim, L2-normalized vector -- BGE-M3's actual output
    shape, not a toy tuple. Two different seeds give two different (but
    both valid) vectors."""

    raw = [math.sin(i + seed) + 2.0 for i in range(BGE_M3_EMBEDDING_DIMENSION)]
    norm = math.sqrt(sum(value * value for value in raw))
    return tuple(value / norm for value in raw)


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


def test_binding_identity_changes_when_max_seq_length_changes():
    other = BgeM3Binding(max_seq_length=512)
    assert other.identity_sha256 != FROZEN_BGE_M3_BINDING.identity_sha256


def test_binding_identity_changes_when_dtype_changes():
    other = BgeM3Binding(dtype="torch.float16")
    assert other.identity_sha256 != FROZEN_BGE_M3_BINDING.identity_sha256


def test_cache_miss_returns_none(tmp_path):
    cache = EmbeddingSuccessCache(tmp_path)
    assert cache.load(_identity()) is None


def test_cache_round_trip(tmp_path):
    cache = EmbeddingSuccessCache(tmp_path)
    identity = _identity()
    vector = _unit_vector()
    cache.store_success(identity, vector)
    loaded = cache.load(identity)
    assert loaded == vector


def test_cache_is_content_addressed_by_text_and_binding(tmp_path):
    cache = EmbeddingSuccessCache(tmp_path)
    a = _identity(text="hello world")
    b = _identity(text="goodbye world")
    assert a.cache_key != b.cache_key
    vec_a, vec_b = _unit_vector(1), _unit_vector(2)
    cache.store_success(a, vec_a)
    cache.store_success(b, vec_b)
    assert cache.load(a) == vec_a
    assert cache.load(b) == vec_b


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
    vector = _unit_vector()
    cache.store_success(identity, vector)
    cache.store_success(identity, vector)
    assert cache.load(identity) == vector


def test_rewriting_the_same_identity_with_a_different_vector_fails_closed(tmp_path):
    cache = EmbeddingSuccessCache(tmp_path)
    identity = _identity()
    cache.store_success(identity, _unit_vector(1))
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        cache.store_success(identity, _unit_vector(2))


def test_embedding_call_identity_rejects_bad_hash_shape():
    with pytest.raises(ValidationError):
        EmbeddingCallIdentity(
            binding_identity_sha256="not-a-hash",
            runtime_identity_sha256=FAKE_RUNTIME_IDENTITY_SHA256,
            field_source="rs.query_text",
            text_sha256=sha256_text("x"),
        )


def test_embedding_call_identity_requires_runtime_identity_sha256():
    with pytest.raises(ValidationError):
        EmbeddingCallIdentity(
            binding_identity_sha256=FROZEN_BGE_M3_BINDING.identity_sha256,
            field_source="rs.query_text",
            text_sha256=sha256_text("x"),
        )


def test_cache_key_changes_when_runtime_identity_changes(tmp_path):
    # A torch/sentence-transformers version bump can change numerical output
    # without changing BgeM3Binding at all -- the cache key must still
    # change, so a stale vector from the old runtime is never silently
    # returned as if it came from the new one.
    a = _identity(runtime_identity_sha256=sha256_text("runtime-a"))
    b = _identity(runtime_identity_sha256=sha256_text("runtime-b"))
    assert a.cache_key != b.cache_key


# ---- 2026-08-19 hardening: vector shape/finiteness/norm validation ----
# Regression coverage for the exact gap review found: v1's round-trip tests
# used non-1024-dim vectors as if valid, which should not have passed
# review.


def test_store_rejects_wrong_dimension(tmp_path):
    cache = EmbeddingSuccessCache(tmp_path)
    with pytest.raises(RuntimeError, match="dimensions, expected"):
        cache.store_success(_identity(), (0.5, 0.5))


def test_store_rejects_non_finite_value(tmp_path):
    cache = EmbeddingSuccessCache(tmp_path)
    bad = list(_unit_vector())
    bad[0] = float("nan")
    with pytest.raises(RuntimeError, match="non-finite"):
        cache.store_success(_identity(), tuple(bad))


def test_store_rejects_infinite_value(tmp_path):
    cache = EmbeddingSuccessCache(tmp_path)
    bad = list(_unit_vector())
    bad[0] = float("inf")
    with pytest.raises(RuntimeError, match="non-finite"):
        cache.store_success(_identity(), tuple(bad))


def test_store_rejects_unnormalized_vector(tmp_path):
    cache = EmbeddingSuccessCache(tmp_path)
    unnormalized = tuple(value * 5.0 for value in _unit_vector())
    with pytest.raises(RuntimeError, match="L2 norm"):
        cache.store_success(_identity(), unnormalized)


def test_cache_allows_non_normalized_vectors_when_binding_says_so(tmp_path):
    cache = EmbeddingSuccessCache(tmp_path, expect_normalized=False)
    unnormalized = tuple(value * 5.0 for value in _unit_vector())
    cache.store_success(_identity(), unnormalized)
    assert cache.load(_identity()) == unnormalized


def test_load_detects_a_corrupted_stored_vector(tmp_path):
    # A cache file that somehow got a bad vector written to it (e.g. by an
    # older, unvalidated version of this module) must fail closed on read
    # too, not just on write.
    import json

    cache = EmbeddingSuccessCache(tmp_path)
    identity = _identity()
    path = cache.path_for(identity)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "protocol": "paper1-bge-m3-embedding-success-cache-v1",
                "identity": identity.model_dump(mode="json"),
                "vector": [0.1, 0.2],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="dimensions, expected"):
        cache.load(identity)
