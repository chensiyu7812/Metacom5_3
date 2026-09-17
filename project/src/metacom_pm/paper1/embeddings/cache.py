"""Content-addressed, atomic success cache for BGE-M3 embeddings.

Mirrors ``rs_atomic_move/cache.py``'s pattern (content-addressed identity,
write-once, protocol/identity re-validated on every read) but for
deterministic local embedding calls rather than LLM API calls. There is no
budget ledger here -- embedding is local GPU compute, not a metered paid
call -- but the same fail-closed identity binding matters for a different
reason: if ``BgeM3Binding`` ever changes (a revision bump, a pooling change),
a stale cached vector must never be silently reused as if it were comparable
to a fresh one.

2026-08-19 hardening: v1 accepted and returned any vector regardless of
length, finiteness, or norm -- its own round-trip tests used non-1024-dim
vectors as "valid", which should never have passed review. store_success and
load now validate shape/finiteness/norm against the frozen BGE-M3 policy by
default.

2026-08-19 hardening (v2): ``BgeM3Binding.identity_sha256`` alone was never
enough to guarantee a cached vector is comparable to a fresh one -- a torch
or sentence-transformers version bump can change numerical output without
changing the binding at all, and v1 only left a docstring comment telling
callers to "fold in" ``BgeM3Encoder.runtime_identity`` themselves, which no
code path actually enforced. ``EmbeddingCallIdentity`` now requires
``runtime_identity_sha256`` directly, so a stale cache entry cannot be
reused across a runtime change without going through this field.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Mapping

from pydantic import Field

from metacom_pm.io import canonical_json, read_json, sha256_text, write_json
from metacom_pm.paper1.contracts import StrictContract

from .bge_m3 import BGE_M3_EMBEDDING_DIMENSION, BGE_M3_NORMALIZE_EMBEDDINGS

SHA256_PATTERN = r"^[0-9a-f]{64}$"
EMBEDDING_CACHE_PROTOCOL = "paper1-bge-m3-embedding-success-cache-v1"
NORM_TOLERANCE = 1e-3


class EmbeddingCallIdentity(StrictContract):
    protocol: str = EMBEDDING_CACHE_PROTOCOL
    binding_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    # BgeM3Encoder.runtime_identity.identity_sha256 (torch/sentence-
    # transformers versions, re-verified weight hash) -- required, not
    # optional, so a runtime change cannot silently reuse a stale vector
    # cached under an unrelated identity_sha256. See module docstring.
    runtime_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    # Which head/field this text came from -- pure audit metadata, not part
    # of the cache key's uniqueness beyond text_sha256+binding: the same
    # exact text embeds to the same vector regardless of which head asked
    # for it, and this field must never be read as changing that.
    field_source: str = Field(min_length=1)
    text_sha256: str = Field(pattern=SHA256_PATTERN)

    @property
    def cache_key(self) -> str:
        return sha256_text(canonical_json(self.model_dump(mode="json")))


def _validate_vector(
    vector: tuple[float, ...],
    *,
    expected_dimension: int,
    expect_normalized: bool,
    context: str,
) -> None:
    if len(vector) != expected_dimension:
        raise RuntimeError(
            f"embedding vector has {len(vector)} dimensions, expected {expected_dimension}: {context}"
        )
    if not all(math.isfinite(value) for value in vector):
        raise RuntimeError(f"embedding vector contains a non-finite value: {context}")
    if expect_normalized:
        norm = math.sqrt(sum(value * value for value in vector))
        if abs(norm - 1.0) > NORM_TOLERANCE:
            raise RuntimeError(
                f"embedding vector L2 norm is {norm:.6f}, expected ~1.0 (tolerance "
                f"{NORM_TOLERANCE}): {context}"
            )


class EmbeddingSuccessCache:
    def __init__(
        self,
        root: str | Path,
        *,
        expected_dimension: int = BGE_M3_EMBEDDING_DIMENSION,
        expect_normalized: bool = BGE_M3_NORMALIZE_EMBEDDINGS,
    ) -> None:
        self.root = Path(root)
        self.expected_dimension = expected_dimension
        self.expect_normalized = expect_normalized

    def path_for(self, identity: EmbeddingCallIdentity) -> Path:
        return self.root / f"{identity.cache_key}.json"

    def load(self, identity: EmbeddingCallIdentity) -> tuple[float, ...] | None:
        path = self.path_for(identity)
        if not path.exists():
            return None
        row = read_json(path)
        if row.get("protocol") != EMBEDDING_CACHE_PROTOCOL:
            raise RuntimeError(f"embedding cache protocol mismatch: {path}")
        if row.get("identity") != identity.model_dump(mode="json"):
            raise RuntimeError(f"embedding cache identity mismatch: {path}")
        vector = row.get("vector")
        if not isinstance(vector, list) or not vector:
            raise RuntimeError(f"embedding cache vector is invalid: {path}")
        parsed = tuple(float(value) for value in vector)
        _validate_vector(
            parsed,
            expected_dimension=self.expected_dimension,
            expect_normalized=self.expect_normalized,
            context=f"loaded from {path}",
        )
        return parsed

    def store_success(
        self,
        identity: EmbeddingCallIdentity,
        vector: Mapping[str, Any] | Any,
    ) -> Path:
        parsed = tuple(float(value) for value in vector)
        _validate_vector(
            parsed,
            expected_dimension=self.expected_dimension,
            expect_normalized=self.expect_normalized,
            context=f"storing for cache_key={identity.cache_key}",
        )
        path = self.path_for(identity)
        row = {
            "protocol": EMBEDDING_CACHE_PROTOCOL,
            "identity": identity.model_dump(mode="json"),
            "vector": list(parsed),
        }
        if path.exists():
            existing = read_json(path)
            if canonical_json(existing) != canonical_json(row):
                raise RuntimeError(f"refusing to overwrite immutable embedding cache: {path}")
            return path
        write_json(path, row)
        return path
