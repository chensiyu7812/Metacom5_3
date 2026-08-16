"""Outcome-blind contracts for comparing provisional RS retrievers.

The audit compares which dialogue-only source cards different retrieval
methods return.  Agreement, score spread, and reuse are engineering/research
diagnostics; none of them is a relevance label, an effect label, or a winner
selection rule.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import Field, model_validator

from ..contracts import StrictContract
from .strategy_bank import StrategySourceCard
from .zero_outcome_census import RSDecisionState

RetrieverMethod = Literal["lexical_jaccard", "bge_small", "bge_m3"]
REQUIRED_RETRIEVER_METHODS: tuple[RetrieverMethod, ...] = (
    "lexical_jaccard",
    "bge_small",
    "bge_m3",
)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class RetrieverRanking(StrictContract):
    method: RetrieverMethod
    candidate_ids: tuple[str, ...] = Field(min_length=1)
    scores: tuple[float, ...] = Field(min_length=1)
    source_strategy_annotations: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _aligned_unique_ranking(self) -> "RetrieverRanking":
        lengths = {
            len(self.candidate_ids),
            len(self.scores),
            len(self.source_strategy_annotations),
        }
        if len(lengths) != 1:
            raise ValueError("retriever ranking fields must have equal length")
        if len(set(self.candidate_ids)) != len(self.candidate_ids):
            raise ValueError("retriever ranking contains duplicate candidate IDs")
        if any(
            self.scores[index] < self.scores[index + 1]
            for index in range(len(self.scores) - 1)
        ):
            raise ValueError("retriever scores must be non-increasing")
        return self


class RSRetrieverComparisonRow(StrictContract):
    state_id: str
    source_dialogue_id: str
    source_split: str
    decision_turn_index: int = Field(ge=1)
    query_text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_count_after_leave_dialogue_out: int = Field(ge=1)
    rankings: tuple[RetrieverRanking, ...] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def _complete_method_surface(self) -> "RSRetrieverComparisonRow":
        methods = tuple(ranking.method for ranking in self.rankings)
        if methods != REQUIRED_RETRIEVER_METHODS:
            raise ValueError(
                "retriever rankings must use the canonical three-method order"
            )
        top_ks = {len(ranking.candidate_ids) for ranking in self.rankings}
        if len(top_ks) != 1:
            raise ValueError("retriever rankings must use the same top-k")
        return self


def build_retriever_comparison_rows(
    *,
    states: Sequence[RSDecisionState],
    cards: Sequence[StrategySourceCard],
    rankings_by_method: Mapping[
        RetrieverMethod, Mapping[str, tuple[tuple[str, float], ...]]
    ],
) -> tuple[RSRetrieverComparisonRow, ...]:
    """Join text-free rankings and fail closed on identity/fold violations."""

    if not states or not cards:
        raise ValueError("retriever comparison requires non-empty states and cards")
    if tuple(rankings_by_method) != REQUIRED_RETRIEVER_METHODS:
        raise ValueError("rankings_by_method must use the canonical method order")
    state_ids = {state.state_id for state in states}
    if len(state_ids) != len(states):
        raise ValueError("state IDs must be unique")
    card_by_id = {card.card_id: card for card in cards}
    if len(card_by_id) != len(cards):
        raise ValueError("card IDs must be unique")
    for method, method_rows in rankings_by_method.items():
        if set(method_rows) != state_ids:
            raise ValueError(f"{method} ranking state identities do not match")

    rows: list[RSRetrieverComparisonRow] = []
    card_counts_by_dialogue: dict[str, int] = {}
    for card in cards:
        card_counts_by_dialogue[card.source_dialogue_id] = (
            card_counts_by_dialogue.get(card.source_dialogue_id, 0) + 1
        )

    for state in states:
        rankings: list[RetrieverRanking] = []
        for method in REQUIRED_RETRIEVER_METHODS:
            selected = rankings_by_method[method][state.state_id]
            if not selected:
                raise ValueError(f"{method} returned an empty ranking")
            selected_cards: list[StrategySourceCard] = []
            for card_id, _score in selected:
                card = card_by_id.get(card_id)
                if card is None:
                    raise ValueError(f"{method} returned unknown card {card_id}")
                if card.source_dialogue_id == state.source_dialogue_id:
                    raise ValueError(
                        f"{method} violated leave-current-dialogue-out for "
                        f"{state.state_id}"
                    )
                selected_cards.append(card)
            rankings.append(
                RetrieverRanking(
                    method=method,
                    candidate_ids=tuple(card.card_id for card in selected_cards),
                    scores=tuple(float(score) for _card_id, score in selected),
                    source_strategy_annotations=tuple(
                        card.strategy_label for card in selected_cards
                    ),
                )
            )
        rows.append(
            RSRetrieverComparisonRow(
                state_id=state.state_id,
                source_dialogue_id=state.source_dialogue_id,
                source_split=state.source_split,
                decision_turn_index=state.decision_turn_index,
                query_text_sha256=_sha256_text(state.query_text),
                candidate_count_after_leave_dialogue_out=(
                    len(cards) - card_counts_by_dialogue.get(state.source_dialogue_id, 0)
                ),
                rankings=tuple(rankings),
            )
        )
    return tuple(rows)
