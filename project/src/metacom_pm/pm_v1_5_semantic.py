"""Frozen, local semantic observations for the PM-v1.5 pre-retrieval router.

The encoder is a deployable feature extractor, not a judge and not an oracle.  It
may read only text already visible to the router.  Reportable runs resolve an
exact local Hugging Face snapshot and never download or update weights at run
time.  Model identity and file hashes are audit metadata; neither is exposed as
a numerical PM feature.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Literal, Mapping, Protocol, Sequence

import numpy as np
from pydantic import Field

from .contracts import StrictModel
from .io import canonical_json, sha256_file, sha256_text


SEMANTIC_ENCODER_PROTOCOL = "pm-v1.5-frozen-visible-text-encoder-v1"
SEMANTIC_INPUT_PROTOCOL = "pm-v1.5-visible-dialogue-state-v1"
SEMANTIC_SNAPSHOT_HASH_PROTOCOL = "relative-path-tab-sha256-v1"


class FrozenSemanticEncoderSpec(StrictModel):
    protocol: Literal["pm-v1.5-frozen-visible-text-encoder-v1"] = (
        SEMANTIC_ENCODER_PROTOCOL
    )
    model_id: str = Field(min_length=1)
    revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    snapshot_tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pooling: Literal["cls"] = "cls"
    normalize: Literal[True] = True
    max_length: int = Field(ge=32, le=4096)
    output_dimension: int = Field(ge=16, le=4096)
    output_round_decimals: int = Field(default=8, ge=4, le=12)
    local_files_only: Literal[True] = True
    trust_remote_code: Literal[False] = False
    language_scope: Literal["english"] = "english"

    def digest(self) -> str:
        return sha256_text(canonical_json(self.model_dump(mode="json")))


class SemanticEncoderBinding(StrictModel):
    protocol: Literal["pm-v1.5-semantic-encoder-binding-v1"] = (
        "pm-v1.5-semantic-encoder-binding-v1"
    )
    spec_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_tree_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_file_count: int = Field(ge=1)
    implementation: Literal["transformers-auto-model-cls-float32"]


class SemanticTextEncoder(Protocol):
    spec: FrozenSemanticEncoderSpec
    binding: SemanticEncoderBinding

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        """Return a finite, row-normalized ``[n, dimension]`` float matrix."""


def resolve_semantic_encoder_binding(
    spec: FrozenSemanticEncoderSpec,
) -> tuple[Path, SemanticEncoderBinding]:
    """Resolve and hash the local snapshot without loading model weights."""

    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:  # pragma: no cover - deployment preflight
        raise RuntimeError(
            "frozen semantic encoding requires installed huggingface_hub"
        ) from exc
    snapshot_path = Path(
        snapshot_download(
            repo_id=spec.model_id,
            revision=spec.revision,
            local_files_only=True,
        )
    ).resolve()
    observed_hash = semantic_snapshot_tree_sha256(snapshot_path)
    if observed_hash != spec.snapshot_tree_sha256:
        raise RuntimeError(
            "semantic encoder snapshot hash mismatch: "
            f"expected={spec.snapshot_tree_sha256}, observed={observed_hash}"
        )
    rows = _snapshot_file_manifest(snapshot_path)
    return snapshot_path, SemanticEncoderBinding(
        spec_sha256=spec.digest(),
        snapshot_tree_sha256=observed_hash,
        snapshot_file_count=len(rows),
        implementation="transformers-auto-model-cls-float32",
    )


def semantic_encoder_spec_from_config(
    config: Mapping[str, Any],
) -> FrozenSemanticEncoderSpec:
    raw = config.get("semantic_encoder")
    if not isinstance(raw, Mapping):
        raise RuntimeError("PM-v1.5 config lacks the frozen semantic_encoder contract")
    if raw.get("enabled") is not True:
        raise RuntimeError("reportable PM-v1.5 requires semantic_encoder.enabled=true")
    payload = {key: value for key, value in raw.items() if key != "enabled"}
    return FrozenSemanticEncoderSpec.model_validate(payload)


def _snapshot_file_manifest(snapshot_path: str | Path) -> list[dict[str, str]]:
    root = Path(snapshot_path).resolve()
    if not root.is_dir():
        raise RuntimeError(f"semantic encoder snapshot is absent: {root}")
    rows = [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": sha256_file(path),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]
    if not rows:
        raise RuntimeError("semantic encoder snapshot contains no files")
    return rows


def semantic_snapshot_tree_sha256(snapshot_path: str | Path) -> str:
    """Hash resolved snapshot files without including a machine-local path."""

    rows = _snapshot_file_manifest(snapshot_path)
    lines = "".join(f"{row['path']}\t{row['sha256']}\n" for row in rows)
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


@dataclass
class FrozenTransformerSemanticEncoder:
    spec: FrozenSemanticEncoderSpec
    binding: SemanticEncoderBinding
    tokenizer: Any
    model: Any

    @classmethod
    def load(cls, spec: FrozenSemanticEncoderSpec) -> "FrozenTransformerSemanticEncoder":
        """Resolve and load one already-cached immutable snapshot.

        ``snapshot_download(..., local_files_only=True)`` is a resolver only.  It
        cannot contact the network under this contract.
        """

        try:
            from transformers import AutoModel, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - exercised by deployment preflight
            raise RuntimeError(
                "frozen semantic encoding requires installed transformers and "
                "huggingface_hub dependencies"
            ) from exc
        snapshot_path, binding = resolve_semantic_encoder_binding(spec)
        tokenizer = AutoTokenizer.from_pretrained(
            snapshot_path,
            local_files_only=True,
            trust_remote_code=False,
        )
        model = AutoModel.from_pretrained(
            snapshot_path,
            local_files_only=True,
            trust_remote_code=False,
        )
        model.eval()
        hidden_size = int(getattr(model.config, "hidden_size", 0))
        if hidden_size != spec.output_dimension:
            raise RuntimeError(
                "semantic encoder output dimension mismatch: "
                f"expected={spec.output_dimension}, observed={hidden_size}"
            )
        return cls(spec=spec, binding=binding, tokenizer=tokenizer, model=model)

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        normalized = [" ".join(str(text).split()) for text in texts]
        if not normalized or any(not text for text in normalized):
            raise ValueError("semantic encoder requires non-empty normalized text")
        import torch

        tokens = self.tokenizer(
            normalized,
            padding=True,
            truncation=True,
            max_length=self.spec.max_length,
            return_tensors="pt",
        )
        with torch.inference_mode():
            output = self.model(**tokens).last_hidden_state[:, 0]
        matrix = output.detach().cpu().to(torch.float32).numpy().astype(np.float64)
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        if np.any(norms <= 0.0) or not np.all(np.isfinite(matrix)):
            raise RuntimeError("semantic encoder returned invalid vectors")
        matrix = matrix / norms
        matrix = np.round(matrix, decimals=self.spec.output_round_decimals)
        renorm = np.linalg.norm(matrix, axis=1, keepdims=True)
        matrix = matrix / np.maximum(renorm, 1e-12)
        return matrix.astype(np.float64)


def visible_dialogue_state_text(
    *,
    current_user_text: str,
    current_session_history: Sequence[Any],
    current_session_summary: str,
) -> str:
    turns: list[str] = []
    for turn in current_session_history:
        if isinstance(turn, Mapping):
            role = str(turn.get("role") or "")
            content = str(turn.get("content") or "")
        else:
            role = str(getattr(turn, "role", ""))
            content = str(getattr(turn, "content", ""))
        if role not in {"user", "assistant"} or not content.strip():
            raise ValueError("visible dialogue state contains an invalid turn")
        turns.append(f"{role}: {' '.join(content.split())}")
    return (
        f"CURRENT_USER:\n{' '.join(current_user_text.split())}\n\n"
        f"RECENT_DIALOGUE:\n{chr(10).join(turns)}\n\n"
        f"SESSION_SUMMARY:\n{' '.join(current_session_summary.split())}"
    )


def encode_visible_state(
    encoder: SemanticTextEncoder,
    *,
    current_user_text: str,
    current_session_history: Sequence[Any],
    current_session_summary: str,
) -> tuple[list[float], dict[str, Any]]:
    """Encode current-turn and dialogue-state views once per state."""

    state_text = visible_dialogue_state_text(
        current_user_text=current_user_text,
        current_session_history=current_session_history,
        current_session_summary=current_session_summary,
    )
    matrix = encoder.encode([current_user_text, state_text])
    expected = (2, encoder.spec.output_dimension)
    if matrix.shape != expected or not np.all(np.isfinite(matrix)):
        raise RuntimeError(
            f"semantic visible-state matrix has shape {matrix.shape}, expected {expected}"
        )
    flattened = matrix.reshape(-1).astype(float).tolist()
    audit = {
        "protocol": SEMANTIC_INPUT_PROTOCOL,
        "encoder_spec_sha256": encoder.binding.spec_sha256,
        "encoder_snapshot_tree_sha256": encoder.binding.snapshot_tree_sha256,
        "views": ["current_user_text", "visible_dialogue_state"],
        "per_view_dimension": encoder.spec.output_dimension,
        "combined_dimension": len(flattened),
        "visible_input_sha256": sha256_text(
            canonical_json(
                {
                    "current_user_text": " ".join(current_user_text.split()),
                    "visible_dialogue_state": state_text,
                }
            )
        ),
    }
    audit["observation_sha256"] = sha256_text(canonical_json(audit))
    return flattened, audit


def semantic_centroid(
    encoder: SemanticTextEncoder, texts: Sequence[str]
) -> tuple[float, ...]:
    if not texts:
        return tuple(0.0 for _ in range(encoder.spec.output_dimension))
    matrix = encoder.encode(texts)
    centroid = np.mean(matrix, axis=0)
    norm = float(np.linalg.norm(centroid))
    if norm <= 0.0 or not np.all(np.isfinite(centroid)):
        raise RuntimeError("semantic centroid is invalid")
    centroid = centroid / norm
    return tuple(
        round(float(value), encoder.spec.output_round_decimals) for value in centroid
    )


def semantic_query_similarity(
    encoder: SemanticTextEncoder,
    query_text: str,
    centroid: Sequence[float],
) -> float:
    vector = np.asarray(centroid, dtype=np.float64)
    if vector.shape != (encoder.spec.output_dimension,):
        raise ValueError("semantic centroid dimension does not match the encoder")
    norm = float(np.linalg.norm(vector))
    if norm <= 0.0:
        return 0.0
    query = encoder.encode([query_text])[0]
    return float(np.clip(query @ (vector / norm), -1.0, 1.0))
