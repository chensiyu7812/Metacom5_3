from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer
from sklearn.preprocessing import RobustScaler

from .contracts import MemorySource, StrategyMode, parse_action_id
from .io import canonical_json, sha256_text
from .pm_v2_contracts import PMV2State


SOURCE_ORDER = (MemorySource.MP, MemorySource.MS, MemorySource.ME)


def state_text(state: PMV2State) -> str:
    history = "\n".join(f"{turn.role}: {turn.content}" for turn in state.current_session_history)
    return (
        f"CURRENT_USER:\n{state.current_user_text}\n\n"
        f"RECENT_DIALOGUE:\n{history}\n\n"
        f"SESSION_SUMMARY:\n{state.current_session_summary}"
    )


@dataclass
class PMV2FeatureBuilder:
    """OOV-robust, strictly pre-retrieval state-action features.

    The builder uses the current/recent text plus inventory-level metadata. It never
    reads actual memory snippets, retrieved IDs, item-level top scores, or a
    current-state conflict oracle. Query relevance is limited to similarity against a
    cached source-level catalog representation supplied by the runtime state.
    """

    word_features: int = 256
    char_features: int = 256
    use_precomputed_embeddings: bool = True
    metadata_scaler: RobustScaler = field(default_factory=RobustScaler)
    embedding_dim: int = 0
    train_text_centroid: np.ndarray | None = None
    train_text_radius_p95: float = 0.0
    metadata_reference_low: np.ndarray | None = None
    metadata_reference_high: np.ndarray | None = None
    fitted: bool = False

    def __post_init__(self):
        self._word = HashingVectorizer(
            n_features=self.word_features,
            alternate_sign=False,
            norm="l2",
            lowercase=True,
            ngram_range=(1, 2),
            analyzer="word",
        )
        self._char = HashingVectorizer(
            n_features=self.char_features,
            alternate_sign=False,
            norm="l2",
            lowercase=True,
            ngram_range=(3, 5),
            analyzer="char_wb",
        )

    @property
    def state_text_dim(self) -> int:
        return self.word_features + self.char_features + self.embedding_dim

    @staticmethod
    def _log(value: float) -> float:
        return float(np.log1p(max(0.0, value)))

    def _state_text_vector(self, state: PMV2State) -> np.ndarray:
        text = state_text(state)
        word = self._word.transform([text]).toarray()[0].astype(np.float64)
        char = self._char.transform([text]).toarray()[0].astype(np.float64)
        blocks = [word, char]
        if self.use_precomputed_embeddings and self.embedding_dim:
            if len(state.text_embedding) != self.embedding_dim:
                raise ValueError(
                    f"state {state.card_id} has embedding dim {len(state.text_embedding)}; "
                    f"expected {self.embedding_dim}"
                )
            emb = np.asarray(state.text_embedding, dtype=np.float64)
            norm = np.linalg.norm(emb)
            blocks.append(emb / norm if norm > 0 else emb)
        return np.concatenate(blocks)

    def _metadata_raw(self, state: PMV2State) -> np.ndarray:
        values: list[float] = [self._log(state.session_index)]
        for source in SOURCE_ORDER:
            cat = state.inventory[source]
            values.extend(
                [
                    float(cat.available),
                    self._log(cat.count),
                    self._log(cat.min_age_sessions or 0),
                    self._log(cat.median_age_sessions or 0.0),
                    self._log(cat.max_age_sessions or 0),
                    self._log(cat.estimated_tokens),
                    # Source-centroid similarity only. Max/P90 item-level scores are
                    # intentionally excluded because they approximate retrieval.
                    float(cat.query_similarity_mean),
                    # Age-derived stale metadata may be maintained by the memory
                    # store. Current-state conflict labels are never exposed.
                    float(cat.stale_fraction),
                ]
            )
            if cat.catalog_embedding:
                emb = np.asarray(cat.catalog_embedding, dtype=np.float64)
                values.extend(
                    [
                        float(np.linalg.norm(emb)),
                        float(np.mean(emb)),
                        float(np.std(emb)),
                    ]
                )
            else:
                values.extend([0.0, 0.0, 0.0])
        values.extend(
            [
                self._log(state.strategy_catalog_count),
                self._log(state.strategy_estimated_tokens),
            ]
        )
        return np.asarray(values, dtype=np.float64)

    def _action_raw(self, state: PMV2State, action_id: str) -> np.ndarray:
        sources, strategy = parse_action_id(action_id)
        source_bits = [float(source in sources) for source in SOURCE_ORDER]
        source_count = float(len(sources))
        memory_tokens = sum(
            state.inventory[source].estimated_tokens / max(state.inventory[source].count, 1)
            * min(state.inventory[source].count, {MemorySource.MP: 2, MemorySource.MS: 2, MemorySource.ME: 3}[source])
            for source in sources
        )
        retrieval_calls = len(sources) + int(strategy is StrategyMode.RS)
        estimated_tokens = memory_tokens + (
            state.strategy_estimated_tokens if strategy is StrategyMode.RS else 0
        )
        return np.asarray(
            [
                *source_bits,
                float(strategy is StrategyMode.RS),
                source_count,
                source_count**2,
                self._log(estimated_tokens),
                float(retrieval_calls),
            ],
            dtype=np.float64,
        )

    def estimate_action_cost(self, state: PMV2State, action_id: str) -> float:
        raw = self._action_raw(state, action_id)
        estimated_tokens = float(np.expm1(raw[-2]))
        return max(0.0, estimated_tokens + 24.0 * raw[-1])

    def fit(self, states: Sequence[PMV2State]) -> "PMV2FeatureBuilder":
        if not states:
            raise ValueError("cannot fit PM-v2 features without states")
        embedding_dims = {len(state.text_embedding) for state in states if state.text_embedding}
        if len(embedding_dims) > 1:
            raise ValueError(f"inconsistent text embedding dimensions: {sorted(embedding_dims)}")
        self.embedding_dim = next(iter(embedding_dims), 0) if self.use_precomputed_embeddings else 0
        text = np.vstack([self._state_text_vector(state) for state in states])
        metadata = np.vstack([self._metadata_raw(state) for state in states])
        self.metadata_scaler.fit(metadata)
        self.metadata_reference_low = np.quantile(metadata, 0.01, axis=0)
        self.metadata_reference_high = np.quantile(metadata, 0.99, axis=0)
        normalized_text = text / np.maximum(np.linalg.norm(text, axis=1, keepdims=True), 1e-12)
        centroid = normalized_text.mean(axis=0)
        centroid /= max(float(np.linalg.norm(centroid)), 1e-12)
        self.train_text_centroid = centroid
        distances = 1.0 - normalized_text @ centroid
        self.train_text_radius_p95 = float(np.quantile(distances, 0.95))
        self.fitted = True
        return self

    def transform(self, rows: Sequence[tuple[PMV2State, str]]) -> np.ndarray:
        if not self.fitted:
            raise RuntimeError("PMV2FeatureBuilder must be fitted before transform")
        if not rows:
            raise ValueError("cannot transform an empty row set")
        result: list[np.ndarray] = []
        for state, action_id in rows:
            if action_id not in state.allowed_actions:
                raise ValueError(f"action {action_id} is not legal for state {state.card_id}")
            text = self._state_text_vector(state)
            metadata = self.metadata_scaler.transform([self._metadata_raw(state)])[0]
            action = self._action_raw(state, action_id)
            source_bits = action[:3]
            strategy_bit = action[3]
            interactions = np.concatenate(
                [
                    text * source_bits[0],
                    text * source_bits[1],
                    text * source_bits[2],
                    text * strategy_bit,
                ]
            )
            result.append(np.concatenate([text, metadata, action, interactions]))
        return np.vstack(result).astype(np.float32)

    def ood_report(self, state: PMV2State) -> dict[str, float | bool | str]:
        if not self.fitted or self.train_text_centroid is None:
            raise RuntimeError("PMV2FeatureBuilder must be fitted before OOD reporting")
        text = self._state_text_vector(state)
        text /= max(float(np.linalg.norm(text)), 1e-12)
        semantic_distance = float(1.0 - text @ self.train_text_centroid)
        metadata = self._metadata_raw(state)
        assert self.metadata_reference_low is not None
        assert self.metadata_reference_high is not None
        lower_span = np.maximum(np.abs(self.metadata_reference_low), 1.0)
        upper_span = np.maximum(np.abs(self.metadata_reference_high), 1.0)
        below = np.maximum(0.0, self.metadata_reference_low - metadata) / lower_span
        above = np.maximum(0.0, metadata - self.metadata_reference_high) / upper_span
        metadata_ood = float(np.mean(np.maximum(below, above)))
        severe_semantic = semantic_distance > max(0.45, self.train_text_radius_p95 * 2.0)
        severe_metadata = metadata_ood > 0.25
        return {
            "semantic_ood_score": semantic_distance,
            "metadata_ood_score": metadata_ood,
            "train_semantic_radius_p95": self.train_text_radius_p95,
            "severe_semantic_ood": severe_semantic,
            "severe_metadata_ood": severe_metadata,
            "recommendation": "FALLBACK" if severe_semantic or severe_metadata else "OK",
        }

    def config_hash(self) -> str:
        payload: dict[str, Any] = {
            "word_features": self.word_features,
            "char_features": self.char_features,
            "use_precomputed_embeddings": self.use_precomputed_embeddings,
            "embedding_dim": self.embedding_dim,
            "source_similarity": "catalog_centroid_only",
            "current_state_conflict_feature": False,
        }
        return sha256_text(canonical_json(payload))
