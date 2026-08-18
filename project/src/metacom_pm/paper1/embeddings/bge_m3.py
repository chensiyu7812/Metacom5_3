"""Pinned BGE-M3 encoder binding shared by RS and MP/MS/ME.

This module owns the encoder identity only (revision/pooling/normalization
and the actual encode call). It does not decide *what text* is embedded for
any given head -- that is a per-head query/document construction choice
recorded in ``paper1_bge_m3_formal_binding_v1.json``, not here. It also does
not run corpus-wide embedding materialization; callers pass whatever texts
they have.

The revision is the exact same commit-addressed Hub PR-130 snapshot already
used by the official RAG comparator's attestation
(``data/paper1_authority/paper1_official_rag_runtime_attestation_v1.json``),
so PM-feature similarity and the official RAG comparator share one encoder
identity rather than each freezing their own. That attestation explicitly
disclaims covering "Typed Memory retrieval design or utility" or "RS
retriever selection or utility" -- this module is the separate, formal
PM-feature binding those items were left pending for.

model_safetensors_sha256 is asserted equal to the value already recorded in
that attestation (same revision, so the weights must be byte-identical);
this module does not re-hash the weights file itself, since sentence-
transformers manages the local Hub cache path, not a project-controlled
file this code can hash directly.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

BGE_M3_EMBEDDING_BINDING_VERSION = "paper1-bge-m3-embedding-binding-v1"
BGE_M3_REPO = "BAAI/bge-m3"
# Same commit-addressed Hub PR-130 snapshot as
# data/paper1_authority/paper1_official_rag_runtime_attestation_v1.json's
# local_model_binding.revision -- one shared encoder identity project-wide.
BGE_M3_REVISION = "9a0624b896d81da7492a910ffa53731274b6cf3d"
BGE_M3_MODEL_SAFETENSORS_SHA256 = "993b2248881724788dcab8c644a91dfd63584b6e5604ff2037cb5541e1e38e7e"
BGE_M3_POOLING_MODE = "cls"
BGE_M3_NORMALIZE_EMBEDDINGS = True
BGE_M3_EMBEDDING_DIMENSION = 1024


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class BgeM3Binding:
    """The frozen encoder identity: revision + pooling + normalization only.

    Two ``BgeM3Binding`` instances with different fields must never be
    treated as producing comparable vectors -- ``identity_sha256`` is meant
    to be threaded through the embedding cache identity for exactly this
    reason (see ``embeddings/cache.py``).
    """

    binding_version: str = BGE_M3_EMBEDDING_BINDING_VERSION
    repo: str = BGE_M3_REPO
    revision: str = BGE_M3_REVISION
    model_safetensors_sha256: str = BGE_M3_MODEL_SAFETENSORS_SHA256
    pooling_mode: str = BGE_M3_POOLING_MODE
    normalize_embeddings: bool = BGE_M3_NORMALIZE_EMBEDDINGS
    embedding_dimension: int = BGE_M3_EMBEDDING_DIMENSION

    @property
    def identity_sha256(self) -> str:
        return hashlib.sha256(
            _canonical_json(
                {
                    "binding_version": self.binding_version,
                    "repo": self.repo,
                    "revision": self.revision,
                    "model_safetensors_sha256": self.model_safetensors_sha256,
                    "pooling_mode": self.pooling_mode,
                    "normalize_embeddings": self.normalize_embeddings,
                    "embedding_dimension": self.embedding_dimension,
                }
            ).encode("utf-8")
        ).hexdigest()


FROZEN_BGE_M3_BINDING = BgeM3Binding()


@lru_cache(maxsize=1)
def _load_model(binding: BgeM3Binding):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError(
            "install the project sentence-transformers/torch dependencies before encoding"
        ) from exc
    return SentenceTransformer(binding.repo, revision=binding.revision, device="cuda")


class BgeM3Encoder:
    """Thin, identity-bound wrapper around the pinned BGE-M3 SentenceTransformer.

    Never called with anything other than ``FROZEN_BGE_M3_BINDING`` in
    production code -- the constructor still takes an explicit binding
    (rather than hardcoding the module constants) so tests can assert
    behavior under a *different* binding without this class silently
    reusing the wrong pinned model.
    """

    def __init__(self, binding: BgeM3Binding = FROZEN_BGE_M3_BINDING) -> None:
        self.binding = binding

    def encode(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        if not texts:
            raise ValueError("encode requires at least one text")
        if any(not text for text in texts):
            raise ValueError("encode does not accept empty strings")
        model = _load_model(self.binding)
        vectors = model.encode(
            list(texts),
            normalize_embeddings=self.binding.normalize_embeddings,
            convert_to_numpy=True,
            batch_size=min(32, len(texts)),
        )
        if vectors.shape != (len(texts), self.binding.embedding_dimension):
            raise RuntimeError(
                f"unexpected embedding shape {vectors.shape} for binding "
                f"{self.binding.identity_sha256}"
            )
        return tuple(tuple(float(value) for value in row) for row in vectors)
