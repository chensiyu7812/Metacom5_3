"""BGE-M3-ranked zero-outcome census over the real RS atomic-move catalog.

Supersedes the card-level lexical audit in ``rs.zero_outcome_census.
build_rs_zero_outcome_census``, which ranked over ``StrategySourceCard``
(the pre-atomic-move source-turn granularity, 12169 cards) with a token-
Jaccard index -- that function still exists unchanged (nothing here removes
or rewrites it) but is now superseded diagnostic history.

This module ranks over ``AtomicMoveRetrievalDocument`` (one row per accepted
atomic-move unit -- the catalog granularity RS M2 freeze decision 10 already
approved: one catalog entry per accepted unit, no bundling), using real
BGE-M3 cosine similarity. Leave-dialogue-out exclusion uses each document's
full ``source_dialogue_ids`` lineage (not a single id), so a unit whose
source turn is dedup-equivalent to content from another dialogue is
correctly excluded from that other dialogue's states too.

Similarity scoring is vectorized with NumPy (one (N_documents, 1024)
float32 matrix, one matrix-vector product per state) rather than a Python
loop -- with up to 11883 decision states each ranking against up to ~15000
documents, a pure-Python per-pair dot product would be computationally
infeasible; both vectors are already L2-normalized by construction (BGE-M3
binding), so the matrix-vector product is directly cosine similarity.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence

import numpy as np
from pydantic import Field

from ..contracts import StrictContract
from ..embeddings.cache import _validate_vector
from ..rs.zero_outcome_census import (
    _ADVICE_REQUEST_RE,
    _LISTEN_ONLY_RE,
    _NO_PROBING_RE,
    RSDecisionState,
)
from .catalog import AtomicMoveRetrievalDocument

RS_ATOMIC_MOVE_CENSUS_ROW_PROTOCOL = "pm-paper1-rs-atomic-move-zero-outcome-census-row-v1"


def _word_count(value: str) -> int:
    return len(value.split())


class RSAtomicMoveCensusRow(StrictContract):
    """One row per RS decision state, ranked against the real atomic-move
    catalog. ``diagnostic_document_word_counts`` is the full retrieval
    document's word count (source context + rendered move together, the
    text actually embedded for matching) -- not the injection cost.
    ``diagnostic_injected_token_counts`` is the actually-injectable
    ``rendered_card_text`` alone, counted by whatever ``token_counter`` was
    passed to ``build_rs_atomic_move_zero_outcome_census`` (whitespace-split
    by default; pass ``metacom_pm.paper1.llama_tokenizer.
    build_llama_token_counter(...)`` for the real Generator tokenizer)."""

    protocol: str = RS_ATOMIC_MOVE_CENSUS_ROW_PROTOCOL
    state_id: str
    source_dialogue_id: str
    source_split: str
    decision_turn_index: int = Field(ge=1)
    query_word_count: int = Field(ge=1)
    current_user_word_count: int = Field(ge=1)
    candidate_count_after_leave_dialogue_out: int = Field(ge=1)
    nonzero_bge_similarity_candidate_count: int = Field(ge=0)
    diagnostic_candidate_ids: tuple[str, ...]
    diagnostic_bge_cosine_similarities: tuple[float, ...]
    diagnostic_document_word_counts: tuple[int, ...]
    diagnostic_injected_token_counts: tuple[int, ...]
    advice_request_visible: bool
    listen_only_visible: bool
    no_probing_visible: bool


class BgeAuditIndex:
    """Vectorized nearest-neighbor index over a fixed set of atomic-move
    retrieval documents, honoring leave-dialogue-out exclusion by full
    lineage.

    Every vector is mechanically validated (1024-dim, finite, L2-normalized)
    at construction/rank time rather than trusted to already be correct --
    ``EmbeddingSuccessCache`` validates on its own store/load path, but nothing
    stops a caller from building ``document_vectors``/``query_vector`` some
    other way, and a silently-wrong vector would corrupt every similarity
    score without raising."""

    def __init__(
        self,
        documents: Sequence[AtomicMoveRetrievalDocument],
        *,
        document_vectors: dict[str, tuple[float, ...]],
        expected_dimension: int = 1024,
    ) -> None:
        if not documents:
            raise ValueError("bge audit index requires documents")
        ids = [doc.atomic_card_id for doc in documents]
        if len(set(ids)) != len(ids):
            raise ValueError("bge audit index requires unique atomic_card_ids")
        missing = [doc.atomic_card_id for doc in documents if doc.atomic_card_id not in document_vectors]
        if missing:
            raise ValueError(f"missing document vectors for {len(missing)} atomic-move units")

        self.documents = tuple(documents)
        self.expected_dimension = expected_dimension
        matrix = np.empty((len(self.documents), expected_dimension), dtype=np.float32)
        for row_index, doc in enumerate(self.documents):
            vector = document_vectors[doc.atomic_card_id]
            _validate_vector(
                tuple(vector),
                expected_dimension=expected_dimension,
                expect_normalized=True,
                context=f"BgeAuditIndex document vector for {doc.atomic_card_id}",
            )
            matrix[row_index] = vector
        self.matrix = matrix

        self.by_dialogue: dict[str, set[int]] = defaultdict(set)
        for index, doc in enumerate(self.documents):
            for dialogue_id in doc.source_dialogue_ids:
                self.by_dialogue[dialogue_id].add(index)

    def rank(
        self,
        *,
        query_vector: tuple[float, ...],
        excluded_dialogue_id: str,
        top_k: int,
    ) -> tuple[int, int, tuple[tuple[AtomicMoveRetrievalDocument, float, int], ...]]:
        if top_k < 1:
            raise ValueError("top_k must be positive")
        _validate_vector(
            tuple(query_vector),
            expected_dimension=self.expected_dimension,
            expect_normalized=True,
            context="BgeAuditIndex query vector",
        )

        excluded_indices = self.by_dialogue.get(excluded_dialogue_id, frozenset())
        eligible_mask = np.ones(len(self.documents), dtype=bool)
        if excluded_indices:
            eligible_mask[list(excluded_indices)] = False
        candidate_count = int(eligible_mask.sum())
        if candidate_count < top_k:
            raise ValueError("fewer fold-exclusive documents than diagnostic top_k")

        query = np.asarray(query_vector, dtype=np.float32)
        similarities = self.matrix @ query
        nonzero_count = int(((similarities > 0.0) & eligible_mask).sum())

        eligible_indices = np.flatnonzero(eligible_mask)
        # Deterministic top-k: descending similarity, ties broken by the
        # smaller atomic_card_id -- same tie-break convention as the
        # lexical index (rs.zero_outcome_census._LexicalAuditIndex.rank).
        ordered = sorted(
            eligible_indices.tolist(),
            key=lambda index: (-float(similarities[index]), self.documents[index].atomic_card_id),
        )[:top_k]

        selected = tuple(
            (
                self.documents[index],
                float(similarities[index]),
                _word_count(self.documents[index].text),
            )
            for index in ordered
        )
        return candidate_count, nonzero_count, selected


def build_rs_atomic_move_zero_outcome_census(
    *,
    states: Sequence[RSDecisionState],
    documents: Sequence[AtomicMoveRetrievalDocument],
    document_vectors: dict[str, tuple[float, ...]],
    query_vectors: dict[str, tuple[float, ...]],
    diagnostic_top_k: int = 4,
    token_counter: Callable[[str], int] | None = None,
) -> tuple[RSAtomicMoveCensusRow, ...]:
    """Audit leave-dialogue-out availability against the real atomic-move
    catalog using real BGE-M3 cosine similarity. ``query_vectors`` must have
    an entry for every state's ``state_id``; ``document_vectors`` must have
    an entry for every document's ``atomic_card_id`` (enforced by
    ``BgeAuditIndex``). ``token_counter`` defaults to the whitespace-split
    proxy when not supplied (pass ``metacom_pm.paper1.llama_tokenizer.
    build_llama_token_counter(...)`` for the frozen Generator tokenizer),
    and is applied only to each selected candidate's own
    ``rendered_card_text`` -- the actual injectable content, not the full
    retrieval document."""

    if not states:
        raise ValueError("RS atomic-move census requires states")
    missing_queries = [state.state_id for state in states if state.state_id not in query_vectors]
    if missing_queries:
        raise ValueError(f"missing query vectors for {len(missing_queries)} decision states")

    resolved_token_counter = token_counter or _word_count
    index = BgeAuditIndex(documents, document_vectors=document_vectors)
    rows: list[RSAtomicMoveCensusRow] = []
    for state in states:
        candidate_count, nonzero_count, selected = index.rank(
            query_vector=query_vectors[state.state_id],
            excluded_dialogue_id=state.source_dialogue_id,
            top_k=diagnostic_top_k,
        )
        current = state.current_user_text
        rows.append(
            RSAtomicMoveCensusRow(
                state_id=state.state_id,
                source_dialogue_id=state.source_dialogue_id,
                source_split=state.source_split,
                decision_turn_index=state.decision_turn_index,
                query_word_count=_word_count(state.query_text),
                current_user_word_count=_word_count(current),
                candidate_count_after_leave_dialogue_out=candidate_count,
                nonzero_bge_similarity_candidate_count=nonzero_count,
                diagnostic_candidate_ids=tuple(doc.atomic_card_id for doc, _sim, _words in selected),
                diagnostic_bge_cosine_similarities=tuple(sim for _doc, sim, _words in selected),
                diagnostic_document_word_counts=tuple(words for _doc, _sim, words in selected),
                diagnostic_injected_token_counts=tuple(
                    resolved_token_counter(doc.rendered_card_text) for doc, _sim, _words in selected
                ),
                advice_request_visible=bool(_ADVICE_REQUEST_RE.search(current)),
                listen_only_visible=bool(_LISTEN_ONLY_RE.search(current)),
                no_probing_visible=bool(_NO_PROBING_RE.search(current)),
            )
        )
    return tuple(rows)
