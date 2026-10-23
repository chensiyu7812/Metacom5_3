from __future__ import annotations

import hashlib
import math
from types import SimpleNamespace

import pytest

from metacom_pm.io import sha256_text
from metacom_pm.paper1.embeddings.bge_m3 import BGE_M3_EMBEDDING_DIMENSION, BgeM3Encoder
from metacom_pm.paper1.embeddings.cache import EmbeddingSuccessCache
from metacom_pm.paper1.embeddings.materialization import (
    MATERIALIZATION_REPORT_PROTOCOL,
    build_materialization_report,
    cosine_similarity,
    materialize_embeddings,
)


def _unit_vector_for(text: str) -> tuple[float, ...]:
    """A real 1024-dim, L2-normalized vector deterministically derived from
    text -- distinct texts give distinct vectors, the same text always gives
    the same vector, matching what a real encoder guarantees."""

    seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF
    raw = [math.sin(i + seed * 10.0) + 2.0 for i in range(BGE_M3_EMBEDDING_DIMENSION)]
    norm = math.sqrt(sum(value * value for value in raw))
    return tuple(value / norm for value in raw)


class _FakeEncoder:
    def __init__(self, *, binding_tag: str = "fake-binding", runtime_tag: str = "fake-runtime"):
        self.binding = SimpleNamespace(
            identity_sha256=sha256_text(binding_tag), max_seq_length=8192
        )
        self.runtime_identity = SimpleNamespace(identity_sha256=sha256_text(runtime_tag))
        self.encode_call_count = 0
        self.encode_call_sizes: list[int] = []

    def encode(self, texts):
        self.encode_call_count += 1
        self.encode_call_sizes.append(len(texts))
        return tuple(_unit_vector_for(text) for text in texts)


def test_materialize_embeddings_encodes_every_uncached_item(tmp_path):
    encoder = _FakeEncoder()
    cache = EmbeddingSuccessCache(tmp_path)
    items = [("a", "hello world"), ("b", "goodbye world")]

    result = materialize_embeddings(items, field_source="rs.query_text", encoder=encoder, cache=cache)

    assert result.cache_hits == 0
    assert result.newly_encoded == 2
    assert result.vectors["a"] == _unit_vector_for("hello world")
    assert result.vectors["b"] == _unit_vector_for("goodbye world")
    assert encoder.encode_call_count == 1


def test_materialize_embeddings_uses_the_cache_on_second_call(tmp_path):
    encoder = _FakeEncoder()
    cache = EmbeddingSuccessCache(tmp_path)
    items = [("a", "hello world"), ("b", "goodbye world")]
    materialize_embeddings(items, field_source="rs.query_text", encoder=encoder, cache=cache)
    assert encoder.encode_call_count == 1

    result = materialize_embeddings(items, field_source="rs.query_text", encoder=encoder, cache=cache)

    assert result.cache_hits == 2
    assert result.newly_encoded == 0
    assert encoder.encode_call_count == 1  # no new encode() calls at all


def test_materialize_embeddings_respects_chunk_size(tmp_path):
    encoder = _FakeEncoder()
    cache = EmbeddingSuccessCache(tmp_path)
    items = [(f"id{i}", f"text number {i}") for i in range(5)]

    materialize_embeddings(
        items, field_source="rs.document_text", encoder=encoder, cache=cache, chunk_size=2
    )

    assert encoder.encode_call_count == 3
    assert encoder.encode_call_sizes == [2, 2, 1]


def test_materialize_embeddings_rejects_duplicate_ids(tmp_path):
    encoder = _FakeEncoder()
    cache = EmbeddingSuccessCache(tmp_path)
    with pytest.raises(ValueError, match="unique ids"):
        materialize_embeddings(
            [("a", "x"), ("a", "y")], field_source="rs.query_text", encoder=encoder, cache=cache
        )


def test_materialize_embeddings_rejects_empty_items(tmp_path):
    encoder = _FakeEncoder()
    cache = EmbeddingSuccessCache(tmp_path)
    with pytest.raises(ValueError, match="at least one item"):
        materialize_embeddings([], field_source="rs.query_text", encoder=encoder, cache=cache)


def test_materialize_embeddings_does_not_reuse_cache_when_runtime_identity_differs(tmp_path):
    cache = EmbeddingSuccessCache(tmp_path)
    items = [("a", "hello world")]
    old_encoder = _FakeEncoder(runtime_tag="runtime-old")
    materialize_embeddings(items, field_source="rs.query_text", encoder=old_encoder, cache=cache)

    new_encoder = _FakeEncoder(runtime_tag="runtime-new")
    result = materialize_embeddings(items, field_source="rs.query_text", encoder=new_encoder, cache=cache)

    assert result.cache_hits == 0
    assert result.newly_encoded == 1
    assert new_encoder.encode_call_count == 1


def test_materialize_embeddings_dedupes_ids_sharing_identical_text(tmp_path):
    # Two different ids (e.g. two accepted memory units) can legitimately
    # share byte-identical text. Regression for a real bug: encoding the
    # same text twice in the same call previously produced two "different"
    # vectors from the fake/real encoder's perspective and tripped the
    # cache's immutability guard on the second store_success call.
    encoder = _FakeEncoder()
    cache = EmbeddingSuccessCache(tmp_path)
    items = [("a", "same content"), ("b", "same content"), ("c", "different content")]

    result = materialize_embeddings(items, field_source="mp.candidate_text", encoder=encoder, cache=cache)

    assert result.vectors["a"] == result.vectors["b"]
    assert result.vectors["a"] != result.vectors["c"]
    assert result.newly_encoded == 3  # item-level count, not unique-text count
    assert result.cache_hits == 0
    # Only 2 distinct texts should ever reach the encoder, in a single chunk.
    assert encoder.encode_call_count == 1
    assert encoder.encode_call_sizes == [2]


def test_materialize_embeddings_duplicate_text_survives_a_real_immutable_cache_write(tmp_path):
    # The real regression: EmbeddingSuccessCache.store_success refuses to
    # overwrite an existing entry with a different vector. Without
    # text-level deduplication this would raise on the second duplicate.
    encoder = _FakeEncoder()
    cache = EmbeddingSuccessCache(tmp_path)
    items = [(f"id{i}", "repeated text") for i in range(5)]

    result = materialize_embeddings(items, field_source="mp.candidate_text", encoder=encoder, cache=cache)

    assert len({result.vectors[f"id{i}"] for i in range(5)}) == 1
    assert encoder.encode_call_sizes == [1]


def test_materialize_embeddings_tracks_max_input_chars(tmp_path):
    encoder = _FakeEncoder()
    cache = EmbeddingSuccessCache(tmp_path)
    items = [("short", "hi"), ("long", "a much longer piece of text here")]

    result = materialize_embeddings(items, field_source="rs.query_text", encoder=encoder, cache=cache)

    assert result.max_input_chars == len("a much longer piece of text here")


def test_cosine_similarity_of_identical_vectors_is_one():
    vector = _unit_vector_for("some text")
    assert cosine_similarity(vector, vector) == pytest.approx(1.0, abs=1e-9)


def test_cosine_similarity_is_symmetric():
    a = _unit_vector_for("alpha")
    b = _unit_vector_for("beta")
    assert cosine_similarity(a, b) == pytest.approx(cosine_similarity(b, a))


def test_cosine_similarity_of_distinct_vectors_is_below_one():
    a = _unit_vector_for("alpha")
    b = _unit_vector_for("beta")
    assert cosine_similarity(a, b) < 1.0


def test_cosine_similarity_rejects_mismatched_lengths():
    with pytest.raises(ValueError, match="equal-length"):
        cosine_similarity((1.0, 0.0), (1.0, 0.0, 0.0))


def test_build_materialization_report_fields(tmp_path):
    encoder = _FakeEncoder()
    cache = EmbeddingSuccessCache(tmp_path)
    items = [("a", "hello world"), ("b", "goodbye world")]
    result = materialize_embeddings(items, field_source="rs.query_text", encoder=encoder, cache=cache)

    report = build_materialization_report(field_source="rs.query_text", result=result, encoder=encoder)

    assert report["protocol"] == MATERIALIZATION_REPORT_PROTOCOL
    assert report["field_source"] == "rs.query_text"
    assert report["item_count"] == 2
    assert report["cache_hits"] == 0
    assert report["newly_encoded"] == 2
    assert report["binding_identity_sha256"] == encoder.binding.identity_sha256
    assert report["runtime_identity_sha256"] == encoder.runtime_identity.identity_sha256
    assert report["outcome_calls"] == 0


# ---- real local GPU round trip ----


@pytest.mark.gpu
def test_real_local_materialization_round_trips_through_cache(tmp_path):
    encoder = BgeM3Encoder()
    cache = EmbeddingSuccessCache(tmp_path)
    items = [
        ("a", "I have been feeling really overwhelmed with work lately."),
        ("b", "My sister has been distant since the argument last month."),
    ]

    first = materialize_embeddings(items, field_source="rs.query_text", encoder=encoder, cache=cache)
    assert first.newly_encoded == 2
    assert first.cache_hits == 0
    for vector in first.vectors.values():
        assert len(vector) == 1024

    second = materialize_embeddings(items, field_source="rs.query_text", encoder=encoder, cache=cache)
    assert second.newly_encoded == 0
    assert second.cache_hits == 2
    assert second.vectors == first.vectors
