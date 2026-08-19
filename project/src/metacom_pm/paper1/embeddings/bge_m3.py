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

2026-08-19 hardening (v2): the v1 binding only recorded revision/pooling/
normalization, declared as static fields never checked against reality.
Fixed:
- ``model_safetensors_sha256`` is now re-hashed from the actual local Hub
  cache file at load time and compared, not just declared.
- ``pooling_mode``, ``max_seq_length``, and ``dtype`` are asserted against
  the live loaded model's real config at load time, not merely declared.
- torch/sentence-transformers versions are captured live (not hardcoded --
  a version bump should change identity, not require editing a constant
  every time pip upgrades something) via ``BgeM3Encoder.runtime_identity``,
  which callers must fold into any cache/provenance identity alongside
  ``BgeM3Binding.identity_sha256``.
- ``encode`` no longer hardcodes batch_size=32 regardless of text length;
  it starts from a length-aware estimate and backs off adaptively on CUDA
  OOM rather than being untested for long RS/MS document text.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

BGE_M3_EMBEDDING_BINDING_VERSION = "paper1-bge-m3-embedding-binding-v2"
BGE_M3_REPO = "BAAI/bge-m3"
# Same commit-addressed Hub PR-130 snapshot as
# data/paper1_authority/paper1_official_rag_runtime_attestation_v1.json's
# local_model_binding.revision -- one shared encoder identity project-wide.
BGE_M3_REVISION = "9a0624b896d81da7492a910ffa53731274b6cf3d"
BGE_M3_MODEL_SAFETENSORS_SHA256 = "993b2248881724788dcab8c644a91dfd63584b6e5604ff2037cb5541e1e38e7e"
BGE_M3_POOLING_MODE = "cls"
BGE_M3_NORMALIZE_EMBEDDINGS = True
BGE_M3_EMBEDDING_DIMENSION = 1024
# Real values read directly off the live model during the 2026-08-19
# hardening probe on this project's RTX 2070 (sentence-transformers 5.7.0,
# torch 2.13.0+cu130) -- max_seq_length and dtype are genuine inference
# config that changes behavior (a shorter max_seq_length silently truncates
# more text), so they are frozen fields, not auto-detected like the package
# versions below.
BGE_M3_MAX_SEQ_LENGTH = 8192
BGE_M3_TRUNCATION_SIDE = "right"
BGE_M3_DTYPE = "torch.float32"


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class BgeM3Binding:
    """The frozen encoder identity: revision + pooling + normalization +
    sequence-length/truncation/dtype policy.

    Two ``BgeM3Binding`` instances with different fields must never be
    treated as producing comparable vectors -- ``identity_sha256`` is meant
    to be threaded through the embedding cache identity for exactly this
    reason (see ``embeddings/cache.py``). Package/runtime versions
    (torch, sentence-transformers) are deliberately NOT part of this frozen
    dataclass -- see ``BgeM3Encoder.runtime_identity``.
    """

    binding_version: str = BGE_M3_EMBEDDING_BINDING_VERSION
    repo: str = BGE_M3_REPO
    revision: str = BGE_M3_REVISION
    model_safetensors_sha256: str = BGE_M3_MODEL_SAFETENSORS_SHA256
    pooling_mode: str = BGE_M3_POOLING_MODE
    normalize_embeddings: bool = BGE_M3_NORMALIZE_EMBEDDINGS
    embedding_dimension: int = BGE_M3_EMBEDDING_DIMENSION
    max_seq_length: int = BGE_M3_MAX_SEQ_LENGTH
    truncation_side: str = BGE_M3_TRUNCATION_SIDE
    dtype: str = BGE_M3_DTYPE

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
                    "max_seq_length": self.max_seq_length,
                    "truncation_side": self.truncation_side,
                    "dtype": self.dtype,
                }
            ).encode("utf-8")
        ).hexdigest()


FROZEN_BGE_M3_BINDING = BgeM3Binding()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _locate_and_verify_weights(binding: BgeM3Binding) -> str:
    """Find the actual local Hub cache file for this revision and re-hash
    it, failing closed on any mismatch with the declared identity -- the
    v1 module's docstring explicitly disclaimed doing this ("does not
    re-hash the weights file itself"); the cache path is real and stable
    (huggingface_hub's on-disk layout), so there is no reason not to."""

    try:
        from huggingface_hub import scan_cache_dir
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError("install huggingface_hub before encoding") from exc

    cache_info = scan_cache_dir()
    for repo in cache_info.repos:
        if repo.repo_id != binding.repo:
            continue
        for rev in repo.revisions:
            if rev.commit_hash != binding.revision:
                continue
            for file in rev.files:
                if file.file_name == "model.safetensors":
                    actual = _hash_file(Path(file.file_path))
                    if actual != binding.model_safetensors_sha256:
                        raise RuntimeError(
                            f"model.safetensors hash mismatch: declared "
                            f"{binding.model_safetensors_sha256}, actual {actual} -- "
                            "refusing to encode with unverified weights"
                        )
                    return actual
    raise RuntimeError(
        f"could not find a locally-cached model.safetensors for {binding.repo}@{binding.revision} "
        "to verify -- load the model at least once (which populates the Hub cache) before calling encode"
    )


@dataclass(frozen=True)
class BgeM3RuntimeIdentity:
    """Captured live from the actual running environment, never hardcoded --
    a torch/sentence-transformers version bump changes this identity
    automatically instead of requiring a manual constant edit that could
    silently go stale. Callers fold this into cache/provenance identity
    alongside ``BgeM3Binding.identity_sha256`` (see ``embeddings/cache.py``);
    it is intentionally NOT part of ``BgeM3Binding`` itself, which is meant
    to be a portable, environment-independent spec."""

    torch_version: str
    sentence_transformers_version: str
    weights_sha256_verified: str

    @property
    def identity_sha256(self) -> str:
        return hashlib.sha256(
            _canonical_json(
                {
                    "torch_version": self.torch_version,
                    "sentence_transformers_version": self.sentence_transformers_version,
                    "weights_sha256_verified": self.weights_sha256_verified,
                }
            ).encode("utf-8")
        ).hexdigest()


@lru_cache(maxsize=1)
def _load_model(binding: BgeM3Binding) -> tuple[object, BgeM3RuntimeIdentity]:
    try:
        import torch
        import sentence_transformers
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError(
            "install the project sentence-transformers/torch dependencies before encoding"
        ) from exc

    model = SentenceTransformer(binding.repo, revision=binding.revision, device="cuda")

    # Assert the declared identity against the model actually loaded, not
    # merely trust the declaration.
    pooling_module = model[1]
    real_pooling_mode = pooling_module.get_config_dict().get("pooling_mode")
    if real_pooling_mode != binding.pooling_mode:
        raise RuntimeError(
            f"pooling_mode mismatch: binding declares {binding.pooling_mode!r}, "
            f"live model config is {real_pooling_mode!r}"
        )
    if model.max_seq_length != binding.max_seq_length:
        raise RuntimeError(
            f"max_seq_length mismatch: binding declares {binding.max_seq_length}, "
            f"live model is {model.max_seq_length}"
        )
    if model.tokenizer.truncation_side != binding.truncation_side:
        raise RuntimeError(
            f"truncation_side mismatch: binding declares {binding.truncation_side!r}, "
            f"live tokenizer is {model.tokenizer.truncation_side!r}"
        )
    real_dtype = str(next(model[0].auto_model.parameters()).dtype)
    if real_dtype != binding.dtype:
        raise RuntimeError(
            f"dtype mismatch: binding declares {binding.dtype!r}, live model is {real_dtype!r}"
        )

    weights_sha256 = _locate_and_verify_weights(binding)
    runtime_identity = BgeM3RuntimeIdentity(
        torch_version=torch.__version__,
        sentence_transformers_version=sentence_transformers.__version__,
        weights_sha256_verified=weights_sha256,
    )
    return model, runtime_identity


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

    @property
    def runtime_identity(self) -> BgeM3RuntimeIdentity:
        _, runtime_identity = _load_model(self.binding)
        return runtime_identity

    def encode(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        if not texts:
            raise ValueError("encode requires at least one text")
        if any(not text for text in texts):
            raise ValueError("encode does not accept empty strings")
        model, _ = _load_model(self.binding)

        # Fail closed on any text that would silently be truncated rather
        # than let sentence-transformers cut semantic content off the end
        # (truncation_side="right") without anyone noticing. Tokenize
        # without truncation to get the real length the tokenizer would
        # otherwise clip.
        for index, text in enumerate(texts):
            real_token_count = len(model.tokenizer(text, add_special_tokens=True)["input_ids"])
            if real_token_count > self.binding.max_seq_length:
                raise RuntimeError(
                    f"text at index {index} tokenizes to {real_token_count} tokens, "
                    f"exceeding max_seq_length={self.binding.max_seq_length}; refusing "
                    "to silently truncate -- shorten the input or raise the bound "
                    "binding.max_seq_length deliberately"
                )

        try:
            import torch
        except ImportError as exc:  # pragma: no cover - environment guard
            raise RuntimeError("install torch before encoding") from exc

        # Adaptive batch sizing: a fixed batch_size=32 was never tested
        # against long RS/MS document text (see module docstring). Start
        # from a length-aware guess and back off on CUDA OOM rather than
        # assuming any fixed size is always safe.
        longest_chars = max(len(text) for text in texts)
        if longest_chars > 4000:
            batch_size = min(4, len(texts))
        elif longest_chars > 1000:
            batch_size = min(16, len(texts))
        else:
            batch_size = min(32, len(texts))

        while True:
            try:
                vectors = model.encode(
                    list(texts),
                    normalize_embeddings=self.binding.normalize_embeddings,
                    convert_to_numpy=True,
                    batch_size=batch_size,
                )
                break
            except torch.cuda.OutOfMemoryError:
                torch.cuda.empty_cache()
                if batch_size <= 1:
                    raise
                batch_size = max(1, batch_size // 2)

        if vectors.shape != (len(texts), self.binding.embedding_dimension):
            raise RuntimeError(
                f"unexpected embedding shape {vectors.shape} for binding "
                f"{self.binding.identity_sha256}"
            )
        return tuple(tuple(float(value) for value in row) for row in vectors)
