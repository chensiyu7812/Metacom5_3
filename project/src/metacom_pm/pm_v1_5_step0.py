"""Deterministic, coarse Step-0 observations for PM-v1.5.

The serialized observation contains only task-related scalars. Family/source
centroid vectors, encoder details, and build hashes remain in the audit object
returned by :func:`build_strategy_family_catalog` and never enter PMV2State.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer

from .contracts import MemorySource, StrategyCard
from .io import canonical_json, sha256_text
from .pm_v2_contracts import (
    ADVICE_READINESS_IDS,
    STRATEGY_FAMILY_IDS,
    ObservableSourceSummary,
    Step0MemoryObservation,
    Step0Observation,
    Step0StrategyObservation,
)
from .pm_v1_5_semantic import (
    SemanticTextEncoder,
    semantic_centroid,
)
from .retrieval import DEFAULT_MEMORY_TOP_K


STEP0_PROTOCOL = "pm-v1.5-step0-semantic-source-observation-v2"
STRATEGY_FAMILY_CATALOG_PROTOCOL = "pm-v1.5-strategy-family-centroids-v2"
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
    readiness_vectors: Mapping[str, tuple[float, ...]]
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
    semantic_encoder: SemanticTextEncoder | None = None,
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
            dimension = (
                semantic_encoder.spec.output_dimension
                if semantic_encoder is not None
                else n_features
            )
            rounded = tuple(0.0 for _ in range(dimension))
            vectors[family] = rounded
            counts[family] = 0
            representation_hashes[family] = sha256_text(canonical_json(rounded))
            continue
        if semantic_encoder is not None:
            rounded = semantic_centroid(semantic_encoder, grouped[family])
        else:
            matrix = vectorizer.transform(grouped[family]).astype(np.float64)
            centroid = np.asarray(matrix.mean(axis=0)).reshape(-1)
            norm = float(np.linalg.norm(centroid))
            if norm <= 0.0:
                raise ValueError(f"Step-0 strategy family {family} has a zero centroid")
            rounded = tuple(round(float(value / norm), 8) for value in centroid)
        vectors[family] = rounded
        counts[family] = len(grouped[family])
        representation_hashes[family] = sha256_text(canonical_json(rounded))

    readiness_vectors = _build_readiness_vectors(
        semantic_encoder=semantic_encoder,
        n_features=n_features,
    )
    audit_payload = {
        "protocol": STRATEGY_FAMILY_CATALOG_PROTOCOL,
        "algorithm_id": (
            "frozen-semantic-encoder-family-mean-l2-v1"
            if semantic_encoder is not None
            else "nonreportable-hash-test-family-mean-l2-v1"
        ),
        "representation_dimension": len(next(iter(vectors.values()))),
        "encoder_spec_sha256": (
            semantic_encoder.binding.spec_sha256
            if semantic_encoder is not None
            else None
        ),
        "family_order": list(STRATEGY_FAMILY_IDS),
        "family_counts": counts,
        "representation_sha256": representation_hashes,
        "cards": len(cards),
        "complete_family_coverage": not missing_families,
        "missing_families": missing_families,
        "advice_readiness_ids": list(ADVICE_READINESS_IDS),
        "advice_readiness_is_independent_of_rs_target": True,
    }
    audit = {
        **audit_payload,
        "catalog_sha256": sha256_text(canonical_json(audit_payload)),
    }
    return StrategyFamilyCatalog(
        vectors=vectors,
        readiness_vectors=readiness_vectors,
        counts=counts,
        audit=audit,
    )


_ADVICE_READINESS_ANCHORS: dict[str, tuple[str, ...]] = {
    "listen_only": (
        "Please just listen; I am not ready for advice.",
        "I need to be heard without suggestions right now.",
        "Can I talk this through without trying to fix it yet?",
        "I would like understanding rather than a plan.",
    ),
    "explore_first": (
        "Can you help me understand what I am feeling?",
        "I am not sure what part of this matters most yet.",
        "Could we explore why this keeps affecting me?",
        "I want to sort through this before deciding what to do.",
    ),
    "light_suggestion": (
        "Could you suggest one small next step?",
        "Do you have any tips that might help?",
        "Can you help me figure out what I could try?",
        "What is one low-pressure thing I can do?",
    ),
    "structured_plan": (
        "Can you help me make a clear step-by-step plan?",
        "I am ready to map out concrete actions and priorities.",
        "Could we build a structured plan with several steps?",
        "Please help me organize exactly what to do next.",
    ),
    "ambiguous": (
        "I do not know whether I want advice or just to talk.",
        "Part of me wants ideas, but part of me is not ready.",
        "I am unsure what kind of support would help right now.",
        "Maybe we can start here and see what I need.",
    ),
}


def _build_readiness_vectors(
    *, semantic_encoder: SemanticTextEncoder | None, n_features: int
) -> dict[str, tuple[float, ...]]:
    if semantic_encoder is not None:
        return {
            readiness: semantic_centroid(semantic_encoder, anchors)
            for readiness, anchors in _ADVICE_READINESS_ANCHORS.items()
        }
    vectorizer = _vectorizer(n_features)
    result: dict[str, tuple[float, ...]] = {}
    for readiness, anchors in _ADVICE_READINESS_ANCHORS.items():
        matrix = vectorizer.transform(anchors).astype(np.float64)
        centroid = np.asarray(matrix.mean(axis=0)).reshape(-1)
        norm = float(np.linalg.norm(centroid))
        result[readiness] = tuple(
            round(float(value / max(norm, 1e-12)), 8) for value in centroid
        )
    return result


def _query_family_similarities(
    query_text: str,
    catalog: StrategyFamilyCatalog | None,
    semantic_encoder: SemanticTextEncoder | None,
) -> tuple[bool, dict[str, float]]:
    zeros = {family: 0.0 for family in STRATEGY_FAMILY_IDS}
    if catalog is None:
        return False, zeros
    if semantic_encoder is not None:
        if catalog.audit.get("encoder_spec_sha256") != semantic_encoder.binding.spec_sha256:
            raise RuntimeError("Strategy Step-0 catalog/encoder binding mismatch")
        query = semantic_encoder.encode([query_text])[0]
    else:
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


def semantic_strategy_readiness(
    query_text: str,
    catalog: StrategyFamilyCatalog | None,
    semantic_encoder: SemanticTextEncoder | None,
) -> dict[str, float]:
    if catalog is None:
        return {readiness: 0.0 for readiness in ADVICE_READINESS_IDS}
    if semantic_encoder is not None:
        query = semantic_encoder.encode([query_text])[0]
    else:
        vectorizer = _vectorizer(len(next(iter(catalog.readiness_vectors.values()))))
        query = vectorizer.transform([query_text]).toarray()[0].astype(np.float64)
        query /= max(float(np.linalg.norm(query)), 1e-12)
    return {
        readiness: float(
            np.clip(query @ np.asarray(catalog.readiness_vectors[readiness]), -1.0, 1.0)
        )
        for readiness in ADVICE_READINESS_IDS
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
    semantic_encoder: SemanticTextEncoder | None = None,
    readiness_text: str | None = None,
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
        semantic_encoder,
    )
    if not strategy_available:
        strategy_valid = False
        family_similarities = {family: 0.0 for family in STRATEGY_FAMILY_IDS}
    readiness_scores = semantic_strategy_readiness(
        readiness_text or query_text,
        strategy_family_catalog,
        semantic_encoder,
    )
    if not strategy_available:
        readiness_scores = {
            readiness: 0.0 for readiness in ADVICE_READINESS_IDS
        }
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
            advice_readiness_similarities=readiness_scores,
            question_present=(
                "?" in (readiness_text or query_text)
                or "？" in (readiness_text or query_text)
            ),
        ),
    )
