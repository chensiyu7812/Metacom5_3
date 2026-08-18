"""Content-addressed, atomic success cache for BGE-M3 embeddings.

Mirrors ``rs_atomic_move/cache.py``'s pattern (content-addressed identity,
write-once, protocol/identity re-validated on every read) but for
deterministic local embedding calls rather than LLM API calls. There is no
budget ledger here -- embedding is local GPU compute, not a metered paid
call -- but the same fail-closed identity binding matters for a different
reason: if ``BgeM3Binding`` ever changes (a revision bump, a pooling change),
a stale cached vector must never be silently reused as if it were comparable
to a fresh one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from pydantic import Field

from metacom_pm.io import canonical_json, read_json, sha256_text, write_json
from metacom_pm.paper1.contracts import StrictContract

SHA256_PATTERN = r"^[0-9a-f]{64}$"
EMBEDDING_CACHE_PROTOCOL = "paper1-bge-m3-embedding-success-cache-v1"


class EmbeddingCallIdentity(StrictContract):
    protocol: str = EMBEDDING_CACHE_PROTOCOL
    binding_identity_sha256: str = Field(pattern=SHA256_PATTERN)
    # Which head/field this text came from -- pure audit metadata, not part
    # of the cache key's uniqueness beyond text_sha256+binding: the same
    # exact text embeds to the same vector regardless of which head asked
    # for it, and this field must never be read as changing that.
    field_source: str = Field(min_length=1)
    text_sha256: str = Field(pattern=SHA256_PATTERN)

    @property
    def cache_key(self) -> str:
        return sha256_text(canonical_json(self.model_dump(mode="json")))


class EmbeddingSuccessCache:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

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
        return tuple(float(value) for value in vector)

    def store_success(
        self,
        identity: EmbeddingCallIdentity,
        vector: Mapping[str, Any] | Any,
    ) -> Path:
        path = self.path_for(identity)
        row = {
            "protocol": EMBEDDING_CACHE_PROTOCOL,
            "identity": identity.model_dump(mode="json"),
            "vector": [float(value) for value in vector],
        }
        if path.exists():
            existing = read_json(path)
            if canonical_json(existing) != canonical_json(row):
                raise RuntimeError(f"refusing to overwrite immutable embedding cache: {path}")
            return path
        write_json(path, row)
        return path
