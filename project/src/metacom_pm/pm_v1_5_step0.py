"""Deterministic, coarse Step-0 observations for PM-v1.5.

The serialized observation contains only task-related scalars. Family/source
centroid vectors, encoder details, and build hashes remain in the audit object
returned by :func:`build_strategy_family_catalog` and never enter PMV2State.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping, Sequence

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer

from .contracts import MemorySource, StrategyCard
from .io import canonical_json, sha256_text
from .pm_v2_contracts import (
    STRATEGY_FAMILY_IDS,
    ObservableSourceSummary,
    Step0MemoryObservation,
    Step0Observation,
    Step0StrategyObservation,
)
from .retrieval import DEFAULT_MEMORY_TOP_K


STEP0_PROTOCOL = "pm-v1.5-step0-source-observation-v1"
STRATEGY_FAMILY_CATALOG_PROTOCOL = "pm-v1.5-strategy-family-centroids-v1"
STRATEGY_FAMILY_HASH_FEATURES = 128
MEMORY_TOP_K = dict(DEFAULT_MEMORY_TOP_K)
MEMORY_ITEM_FEATURE_TOKEN_CLIP = 256

STRATEGY_LABEL_TO_FAMILY_ID: dict[str, str] = {
    "Question": "question",
    "Others": "other",
    "Providing Suggestions": "suggestion",
    "Affirmation and Reassurance": "affirmation_reassurance",
    "Self-disclosure": "self_disclosure",
    "Reflection of feelings": "reflection",
    "Information": "information",
    "Restatement or Paraphrasing": "restatement",
}


def _vectorizer(n_features: int = STRATEGY_FAMILY_HASH_FEATURES) -> HashingVectorizer:
    return HashingVectorizer(
        n_features=n_features,
        alternate_sign=False,
        norm=None,
        lowercase=True,
        ngram_range=(1, 2),
        analyzer="word",
    )


@dataclass(frozen=True)
class StrategyFamilyCatalog:
    vectors: Mapping[str, tuple[float, ...]]
    counts: Mapping[str, int]
    audit: Mapping[str, object]

    @property
    def digest(self) -> str:
        return str(self.audit["catalog_sha256"])


def build_strategy_family_catalog(
    cards: Sequence[StrategyCard],
    *,
    n_features: int = STRATEGY_FAMILY_HASH_FEATURES,
    require_all_families: bool = True,
) -> StrategyFamilyCatalog:
    """Build eight fixed family centroids without running item retrieval."""

    if not cards:
        raise ValueError("Step-0 strategy-family catalog cannot be empty")
    unknown = sorted({card.strategy_label for card in cards} - set(STRATEGY_LABEL_TO_FAMILY_ID))
    if unknown:
        raise ValueError(f"unmapped Strategy labels for Step-0: {unknown}")
    grouped: dict[str, list[str]] = {family: [] for family in STRATEGY_FAMILY_IDS}
    for card in cards:
        grouped[STRATEGY_LABEL_TO_FAMILY_ID[card.strategy_label]].append(
            card.retrieval_text
        )
    missing_families = [
        family for family in STRATEGY_FAMILY_IDS if not grouped[family]
    ]
    if require_all_families and missing_families:
        raise ValueError("every frozen Step-0 strategy family must contain cards")

    vectorizer = _vectorizer(n_features)
    vectors: dict[str, tuple[float, ...]] = {}
    representation_hashes: dict[str, str] = {}
    counts: dict[str, int] = {}
    for family in STRATEGY_FAMILY_IDS:
        if not grouped[family]:
            rounded = tuple(0.0 for _ in range(n_features))
            vectors[family] = rounded
            counts[family] = 0
            representation_hashes[family] = sha256_text(canonical_json(rounded))
            continue
        matrix = vectorizer.transform(grouped[family]).astype(np.float64)
        centroid = np.asarray(matrix.mean(axis=0)).reshape(-1)
        norm = float(np.linalg.norm(centroid))
        if norm <= 0.0:
            raise ValueError(f"Step-0 strategy family {family} has a zero centroid")
        rounded = tuple(round(float(value / norm), 8) for value in centroid)
        vectors[family] = rounded
        counts[family] = len(grouped[family])
        representation_hashes[family] = sha256_text(canonical_json(rounded))

    audit_payload = {
        "protocol": STRATEGY_FAMILY_CATALOG_PROTOCOL,
        "algorithm_id": "hashing-vectorizer-word-1-2-family-mean-l2-v1",
        "n_features": int(n_features),
        "family_order": list(STRATEGY_FAMILY_IDS),
        "family_counts": counts,
        "representation_sha256": representation_hashes,
        "cards": len(cards),
        "complete_family_coverage": not missing_families,
        "missing_families": missing_families,
    }
    audit = {
        **audit_payload,
        "catalog_sha256": sha256_text(canonical_json(audit_payload)),
    }
    return StrategyFamilyCatalog(vectors=vectors, counts=counts, audit=audit)


def _query_family_similarities(
    query_text: str,
    catalog: StrategyFamilyCatalog | None,
) -> tuple[bool, dict[str, float]]:
    zeros = {family: 0.0 for family in STRATEGY_FAMILY_IDS}
    if catalog is None:
        return False, zeros
    vectorizer = _vectorizer(len(next(iter(catalog.vectors.values()))))
    query = vectorizer.transform([query_text]).toarray()[0].astype(np.float64)
    norm = float(np.linalg.norm(query))
    if norm <= 0.0:
        return False, zeros
    query /= norm
    return True, {
        family: float(np.clip(query @ np.asarray(catalog.vectors[family]), -1.0, 1.0))
        for family in STRATEGY_FAMILY_IDS
    }


_ADVICE_REQUEST = re.compile(
    r"\b(what should i|what can i|how should i|how can i|any advice|suggest|recommend)\b",
    re.IGNORECASE,
)
_ADVICE_REJECT = re.compile(
    r"\b(no advice|do not advise|don't advise|not looking for advice|just listen|hear me out)\b",
    re.IGNORECASE,
)


def deterministic_strategy_readiness(query_text: str) -> dict[str, bool]:
    """Return bank-independent, deterministic readiness scalars."""

    normalized = " ".join(str(query_text).split())
    return {
        "advice_requested": bool(_ADVICE_REQUEST.search(normalized)),
        "advice_rejected": bool(_ADVICE_REJECT.search(normalized)),
        "question_present": "?" in normalized or "？" in normalized,
    }


def _expected_source_tokens(
    catalog: ObservableSourceSummary,
    source: MemorySource,
) -> int:
    if not catalog.available or catalog.count <= 0:
        return 0
    retrieved_count = min(catalog.count, int(MEMORY_TOP_K[source]))
    mean_item_tokens = float(catalog.estimated_tokens) / float(catalog.count)
    bounded = min(
        float(catalog.estimated_tokens),
        mean_item_tokens * retrieved_count,
        float(MEMORY_TOP_K[source] * MEMORY_ITEM_FEATURE_TOKEN_CLIP),
    )
    return int(round(bounded))


def build_step0_observation(
    *,
    query_text: str,
    inventory: Mapping[MemorySource, ObservableSourceSummary],
    strategy_catalog_count: int,
    strategy_estimated_tokens: int,
    strategy_family_catalog: StrategyFamilyCatalog | None = None,
) -> Step0Observation:
    """Materialize the complete PM-visible observation before item retrieval."""

    if set(inventory) != set(MemorySource):
        raise ValueError("Step-0 inventory must contain exactly MP, MS, and ME")
    memory: dict[MemorySource, Step0MemoryObservation] = {}
    for source in MemorySource:
        catalog = inventory[source]
        valid = bool(catalog.representation_valid)
        similarity = float(catalog.query_similarity_mean) if valid else 0.0
        memory[source] = Step0MemoryObservation(
            available=catalog.available,
            count=catalog.count,
            min_age_sessions=catalog.min_age_sessions,
            median_age_sessions=catalog.median_age_sessions,
            max_age_sessions=catalog.max_age_sessions,
            expected_retrieval_tokens=_expected_source_tokens(catalog, source),
            representation_valid=valid,
            query_to_source_similarity=similarity,
        )

    strategy_available = int(strategy_catalog_count) > 0
    strategy_valid, family_similarities = _query_family_similarities(
        query_text,
        strategy_family_catalog,
    )
    if not strategy_available:
        strategy_valid = False
        family_similarities = {family: 0.0 for family in STRATEGY_FAMILY_IDS}
    readiness = deterministic_strategy_readiness(query_text)
    return Step0Observation(
        memory_sources=memory,
        strategy=Step0StrategyObservation(
            available=strategy_available,
            count=int(strategy_catalog_count),
            expected_retrieval_tokens=(
                int(strategy_estimated_tokens) if strategy_available else 0
            ),
            representation_valid=strategy_valid,
            family_similarities=family_similarities,
            **readiness,
        ),
    )
