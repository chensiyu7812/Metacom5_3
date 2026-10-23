"""Corpus-wide BGE-M3 embedding materialization, shared by RS and MP/MS/ME.

Encodes a batch of (id, text) items through the hardened ``BgeM3Encoder``,
checking the content-addressed ``EmbeddingSuccessCache`` first so a re-run
only pays for what changed (a new text, a different encoder binding, or a
different runtime). This module owns *how* embedding happens, not *what
text* gets embedded for any given head -- that per-head query/document
construction is recorded in
``data/paper1_authority/paper1_bge_m3_formal_binding_v1.json`` and built by
each head's own adapter (e.g. ``rs_atomic_move.catalog.
build_atomic_move_retrieval_document``), not here.

Vectors are L2-normalized by ``BgeM3Encoder`` (frozen binding:
``normalize_embeddings=True``), so cosine similarity between two vectors is
just their dot product -- ``cosine_similarity`` below relies on that
invariant rather than re-normalizing on every call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from metacom_pm.io import sha256_text

from .bge_m3 import BgeM3Encoder
from .cache import EmbeddingCallIdentity, EmbeddingSuccessCache

MATERIALIZATION_REPORT_PROTOCOL = "paper1-bge-m3-materialization-report-v1"
DEFAULT_CHUNK_SIZE = 256


@dataclass(frozen=True)
class MaterializationResult:
    vectors: dict[str, tuple[float, ...]]
    cache_hits: int
    newly_encoded: int
    max_input_chars: int


def materialize_embeddings(
    items: Sequence[tuple[str, str]],
    *,
    field_source: str,
    encoder: BgeM3Encoder,
    cache: EmbeddingSuccessCache,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
) -> MaterializationResult:
    """Encode every distinct text not already cached under this exact
    (binding, runtime, field_source, text) identity. Returns id -> vector
    for the full input set, cache hits included. Ids must be unique; a
    chunked encode call bounds peak GPU/host memory for large corpora
    (RS: 15061 documents; MP/MS/ME: 2745 units) rather than one call over
    the entire input.

    Items are grouped by exact text before encoding: two different ids can
    legitimately share byte-identical text (e.g. two accepted memory units
    whose rendered content happens to match), and re-encoding the same text
    twice in two different batches can produce a bitwise-different vector
    (attention padding/batch-composition-dependent floating point) -- which
    would then collide on the same cache_key and trip
    EmbeddingSuccessCache.store_success's immutability guard. Grouping first
    guarantees each distinct text is encoded at most once per call, and
    every id sharing it gets the exact same vector object."""

    if not items:
        raise ValueError("materialize_embeddings requires at least one item")
    ids = [item_id for item_id, _text in items]
    if len(set(ids)) != len(ids):
        raise ValueError("materialize_embeddings requires unique ids")
    if chunk_size < 1:
        raise ValueError("chunk_size must be positive")

    binding_identity_sha256 = encoder.binding.identity_sha256
    runtime_identity_sha256 = encoder.runtime_identity.identity_sha256

    def _identity(text: str) -> EmbeddingCallIdentity:
        return EmbeddingCallIdentity(
            binding_identity_sha256=binding_identity_sha256,
            runtime_identity_sha256=runtime_identity_sha256,
            field_source=field_source,
            text_sha256=sha256_text(text),
        )

    ids_by_text: dict[str, list[str]] = {}
    max_input_chars = 0
    for item_id, text in items:
        max_input_chars = max(max_input_chars, len(text))
        ids_by_text.setdefault(text, []).append(item_id)

    text_vectors: dict[str, tuple[float, ...]] = {}
    cache_hit_item_count = 0
    pending: list[tuple[str, EmbeddingCallIdentity]] = []
    for text, ids_sharing in ids_by_text.items():
        identity = _identity(text)
        cached = cache.load(identity)
        if cached is not None:
            text_vectors[text] = cached
            cache_hit_item_count += len(ids_sharing)
        else:
            pending.append((text, identity))

    for start in range(0, len(pending), chunk_size):
        chunk = pending[start : start + chunk_size]
        texts = [text for text, _identity in chunk]
        encoded = encoder.encode(texts)
        for (text, identity), vector in zip(chunk, encoded, strict=True):
            cache.store_success(identity, vector)
            text_vectors[text] = vector

    vectors = {
        item_id: text_vectors[text]
        for text, ids_sharing in ids_by_text.items()
        for item_id in ids_sharing
    }

    return MaterializationResult(
        vectors=vectors,
        cache_hits=cache_hit_item_count,
        newly_encoded=len(items) - cache_hit_item_count,
        max_input_chars=max_input_chars,
    )


def cosine_similarity(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    """Dot product of two BGE-M3 vectors -- valid as cosine similarity only
    because both are already L2-normalized by construction (enforced by
    EmbeddingSuccessCache's expect_normalized check on every stored/loaded
    vector)."""

    if len(a) != len(b):
        raise ValueError("cosine_similarity requires equal-length vectors")
    return sum(x * y for x, y in zip(a, b, strict=True))


def build_materialization_report(
    *,
    field_source: str,
    result: MaterializationResult,
    encoder: BgeM3Encoder,
) -> dict[str, Any]:
    return {
        "protocol": MATERIALIZATION_REPORT_PROTOCOL,
        "field_source": field_source,
        "item_count": len(result.vectors),
        "cache_hits": result.cache_hits,
        "newly_encoded": result.newly_encoded,
        "binding_identity_sha256": encoder.binding.identity_sha256,
        "runtime_identity_sha256": encoder.runtime_identity.identity_sha256,
        "max_input_chars": result.max_input_chars,
        "max_seq_length": encoder.binding.max_seq_length,
        "truncation_fail_closed": True,
        "outcome_calls": 0,
    }
