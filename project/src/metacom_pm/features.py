from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence
import numpy as np
from scipy import sparse
from sklearn.feature_extraction.text import TfidfVectorizer, HashingVectorizer

from .contracts import MemorySource, RuntimeState, StrategyMode, parse_action_id
from .retrieval import context_query

ACTION_ORDER = (MemorySource.MP, MemorySource.MS, MemorySource.ME)


def state_context(state: RuntimeState) -> str:
    return context_query(
        state.current_user_text,
        [x.model_dump(mode="json") for x in state.current_session_history],
        state.current_session_summary,
    )


@dataclass
class FeatureBuilder:
    """Deployment-observable state/action features with explicit ablations.

    Modes:
      * text_only: current-session text × action, no inventory statistics/catalog.
      * metadata_only: availability/count/age/token metadata × action, no text/catalog.
      * text_metadata: current-session text plus inventory metadata, no catalog.
      * catalog_only: query-to-cached-catalog relevance × action, no count/age features.
      * full: union of all three.

    Actual memory/strategy snippets, selected IDs, retrieval results, responses and
    judge values are never accepted by this API.
    """

    mode: str = "full"
    max_text_features: int = 2048
    ngram_range: tuple[int, int] = (1, 2)
    vectorizer: TfidfVectorizer | None = None
    metadata_min: np.ndarray | None = None
    metadata_max: np.ndarray | None = None
    stable_caps: dict[str, Any] | None = None
    _query_cache: dict[str, np.ndarray] = field(default_factory=dict, repr=False)

    def fit(self, states: Sequence[RuntimeState]) -> "FeatureBuilder":
        if self.mode not in {
            "full",
            "text_only",
            "metadata_only",
            "text_metadata",
            "text_metadata_stable",
            "catalog_only",
        }:
            raise ValueError(f"unknown feature mode: {self.mode}")
        if not states:
            raise ValueError("cannot fit features without states")
        if self.mode in {"full", "text_only", "text_metadata", "text_metadata_stable"}:
            self.vectorizer = TfidfVectorizer(
                lowercase=True,
                ngram_range=self.ngram_range,
                max_features=self.max_text_features,
                min_df=2 if len(states) >= 2 else 1,
                sublinear_tf=True,
                norm="l2",
            )
            self.vectorizer.fit([state_context(x) for x in states])
        else:
            self.vectorizer = None
        self.stable_caps = self._fit_stable_caps(states) if self.mode == "text_metadata_stable" else None
        dense = np.vstack([
            self._dense_raw(state, action_id)
            for state in states
            for action_id in state.allowed_actions
        ])
        self.metadata_min = dense.min(axis=0)
        self.metadata_max = dense.max(axis=0)
        return self

    @property
    def text_dim(self) -> int:
        return len(self.vectorizer.vocabulary_) if self.vectorizer is not None else 0

    def _query_fingerprint(self, state: RuntimeState) -> np.ndarray:
        # Same dialogue state is intentionally shared by counterfactual inventories.
        cached = self._query_cache.get(state.state_id)
        if cached is not None:
            return cached
        vectorizer = HashingVectorizer(
            n_features=64,
            alternate_sign=False,
            norm="l2",
            lowercase=True,
            ngram_range=(1, 2),
        )
        value = np.asarray(
            vectorizer.transform([state_context(state)]).toarray()[0], dtype=float
        )
        self._query_cache[state.state_id] = value
        return value

    def _catalog_similarity(self, state: RuntimeState, source: MemorySource) -> float:
        query = self._query_fingerprint(state)
        catalog = np.asarray(state.inventory[source].catalog_fingerprint, dtype=float)
        qnorm, cnorm = np.linalg.norm(query), np.linalg.norm(catalog)
        if not query.size or not catalog.size or qnorm == 0 or cnorm == 0:
            return 0.0
        return float(query @ catalog / (qnorm * cnorm))

    def _fit_stable_caps(self, states: Sequence[RuntimeState]) -> dict[str, Any]:
        """Learn deployment-stable caps from the development feature domain.

        The stable mode is for external longitudinal settings whose memory
        inventory can be much larger than the synthetic development users.  It
        keeps the feature semantics pre-evidence while preventing raw count,
        age, token, or session-depth scale from creating guaranteed OOD at
        deployment time.
        """
        caps: dict[str, Any] = {
            "session_index": max(float(s.session_index) for s in states),
            "sources": {},
        }
        for source in ACTION_ORDER:
            cats = [state.inventory[source] for state in states]
            caps["sources"][source.value] = {
                "count": max(float(cat.count) for cat in cats),
                "min_age_sessions": max(float(cat.min_age_sessions or 0) for cat in cats),
                "max_age_sessions": max(float(cat.max_age_sessions or 0) for cat in cats),
                "estimated_tokens": max(float(cat.estimated_tokens) for cat in cats),
            }
        return caps

    def _cap_value(self, source: MemorySource | None, name: str, value: float) -> float:
        if self.mode != "text_metadata_stable" or self.stable_caps is None:
            return value
        if source is None:
            cap = float(self.stable_caps.get(name, value))
        else:
            cap = float(
                self.stable_caps["sources"].get(source.value, {}).get(name, value)
            )
        return min(value, cap)

    def _metadata_values(
        self, state: RuntimeState, source: MemorySource, selected: float
    ) -> list[float]:
        cat = state.inventory[source]
        count = self._cap_value(source, "count", float(cat.count))
        min_age = self._cap_value(source, "min_age_sessions", float(cat.min_age_sessions or 0))
        max_age = self._cap_value(source, "max_age_sessions", float(cat.max_age_sessions or 0))
        estimated_tokens = self._cap_value(source, "estimated_tokens", float(cat.estimated_tokens))
        return [
            float(cat.available),
            np.log1p(count),
            np.log1p(min_age),
            np.log1p(max_age),
            np.log1p(estimated_tokens),
            selected * np.log1p(count),
            selected * np.log1p(estimated_tokens),
        ]

    def _dense_raw(self, state: RuntimeState, action_id: str) -> np.ndarray:
        sources, strategy = parse_action_id(action_id)
        values: list[float] = []
        for source in ACTION_ORDER:
            selected = float(source in sources)
            values.append(selected)
            if self.mode in {"full", "metadata_only", "text_metadata", "text_metadata_stable"}:
                values.extend(self._metadata_values(state, source, selected))
            if self.mode in {"full", "catalog_only"}:
                similarity = self._catalog_similarity(state, source)
                values.extend([
                    similarity,
                    selected * similarity,
                ])
        values.extend([
            float(strategy is StrategyMode.RS),
            float(len(sources)),
            float(len(sources) ** 2),
        ])
        if self.mode in {"full", "metadata_only", "text_metadata", "text_metadata_stable"}:
            session_index = self._cap_value(None, "session_index", float(state.session_index))
            values.append(np.log1p(session_index))
        if self.mode in {"full", "catalog_only"}:
            for source in ACTION_ORDER:
                fp = state.inventory[source].catalog_fingerprint
                values.extend(float(x) for x in fp)
                values.extend(float(x) * float(source in sources) for x in fp)
        return np.asarray(values, dtype=np.float64)

    def ood_report(
        self, state_action_rows: Sequence[tuple[RuntimeState, str]]
    ) -> dict[str, float | int | bool | str]:
        if self.metadata_min is None or self.metadata_max is None:
            raise RuntimeError("FeatureBuilder is not fitted")
        dense = np.vstack([self._dense_raw(s, a) for s, a in state_action_rows])
        below = dense < (self.metadata_min - 1e-12)
        above = dense > (self.metadata_max + 1e-12)
        outside = below | above

        # Count/token/age scalar metadata must not be diluted by hundreds of
        # catalog-fingerprint dimensions.  Recompute scalar and catalog drift
        # explicitly from semantically meaningful fields.
        scalar_outside = 0
        scalar_total = 0
        catalog_dim_outside = 0
        catalog_dim_total = 0
        for state, action_id in state_action_rows:
            ref_states = []
            sources, _ = parse_action_id(action_id)
            for source in ACTION_ORDER:
                cat = state.inventory[source]
                vals = self._metadata_values(
                    state, source, float(source in sources)
                )
                # Locate the corresponding values inside dense by relying on the
                # already-computed outside mask would be brittle across ablations,
                # so compare scalar values against the scalar ranges observed in
                # the fitted dense matrix via a conservative global envelope.
                scalar_total += len(vals)
                # Use conservative global envelope; a proper per-feature range
                # comparison would require saving named ranges at fit time.
                # Flag as outside only when clearly beyond the training envelope,
                # not on any tiny floating-point deviation.
                lo = float(np.min(self.metadata_min)) - 0.05
                hi = float(np.max(self.metadata_max)) + 0.05
                scalar_outside += sum(v < lo or v > hi for v in vals)
                if self.mode in {"full", "catalog_only"}:
                    fp = np.asarray(cat.catalog_fingerprint, dtype=float)
                    catalog_dim_total += int(fp.size)
                    catalog_dim_outside += int(np.sum((fp < -1e-12) | (fp > 1.0 + 1e-12)))
        scalar_fraction = scalar_outside / scalar_total if scalar_total else 0.0
        catalog_fraction = catalog_dim_outside / catalog_dim_total if catalog_dim_total else 0.0
        # Use the dense per-feature OOD fraction (per-dimension training bounds)
        # rather than a global-envelope scalar comparison. The global envelope
        # fails when a large-range feature (e.g. session_depth) dominates the
        # global max, masking extreme values in narrow-range features like count.
        # Threshold >10%: catches extreme OOD (count=1000 when training max~5)
        # but tolerates mild user-heldout drift in a few dense dimensions.
        dense_ood_fraction = float(outside.mean()) if outside.size > 0 else 0.0
        above_margin = np.where(above, dense - self.metadata_max, 0.0)
        below_margin = np.where(below, self.metadata_min - dense, 0.0)
        max_outside_margin = float(max(above_margin.max(), below_margin.max()))
        severe_scalar = bool(
            dense_ood_fraction > 0.10
            or scalar_fraction > 0.05
            or max_outside_margin > 1.0
        )
        severe_catalog = bool(catalog_fraction > 0.10)
        return {
            "n_rows": int(dense.shape[0]),
            "n_dimensions": int(dense.shape[1]),
            "outside_value_fraction": float(outside.mean()),
            "rows_with_any_outside_fraction": float(outside.any(axis=1).mean()),
            "outside_dimensions": int(outside.any(axis=0).sum()),
            "scalar_outside_fraction": float(scalar_fraction),
            "catalog_outside_fraction": float(catalog_fraction),
            "max_outside_margin": max_outside_margin,
            "severe_scalar_ood": severe_scalar,
            "severe_catalog_ood": severe_catalog,
            "recommendation": (
                "ABORT_OR_USE_OOD_BASELINE"
                if severe_scalar or severe_catalog
                else "OK"
            ),
        }

    def transform(
        self,
        state_action_rows: Sequence[tuple[RuntimeState, str]],
        *,
        clip_metadata: bool = True,
    ) -> sparse.csr_matrix:
        if not state_action_rows:
            raise ValueError("cannot transform an empty row set")
        dense = np.vstack([self._dense_raw(s, a) for s, a in state_action_rows])
        if clip_metadata:
            if self.metadata_min is None or self.metadata_max is None:
                raise RuntimeError("FeatureBuilder is not fitted")
            dense = np.clip(dense, self.metadata_min, self.metadata_max)
        blocks: list[sparse.spmatrix] = [sparse.csr_matrix(dense)]
        if self.vectorizer is not None:
            contexts = [state_context(state) for state, _ in state_action_rows]
            text = self.vectorizer.transform(contexts).tocsr()
            # Shared text alone cancels in pairwise differences; gate it by action.
            for source in ACTION_ORDER:
                gates = np.asarray([
                    float(source in parse_action_id(action_id)[0])
                    for _, action_id in state_action_rows
                ])[:, None]
                blocks.append(text.multiply(gates))
            strategy_gate = np.asarray([
                float(parse_action_id(action_id)[1] is StrategyMode.RS)
                for _, action_id in state_action_rows
            ])[:, None]
            blocks.append(text.multiply(strategy_gate))
        return sparse.hstack(blocks, format="csr")
