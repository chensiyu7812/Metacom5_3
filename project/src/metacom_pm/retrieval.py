from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Sequence
from .contracts import MemoryItem, MemorySource, StrategyCard
from .text import lexical_score, normalize_space


def context_query(
    current_user_text: str,
    history: Sequence[dict] | Sequence[object],
    summary: str,
) -> str:
    parts = [summary]
    for turn in history:
        if isinstance(turn, dict):
            parts.append(str(turn.get("content") or ""))
        else:
            parts.append(str(getattr(turn, "content", "")))
    parts.append(current_user_text)
    return normalize_space("\n".join(parts))


class MemoryRetriever:
    def __init__(self, top_k_by_source: dict[MemorySource, int] | None = None):
        self.top_k_by_source = top_k_by_source or {
            MemorySource.MP: 2,
            MemorySource.MS: 2,
            MemorySource.ME: 3,
        }

    def retrieve(
        self,
        query: str,
        items: Sequence[MemoryItem],
        selected_sources: frozenset[MemorySource],
    ) -> list[MemoryItem]:
        out: list[MemoryItem] = []
        for source in MemorySource:
            if source not in selected_sources:
                continue
            candidates = [x for x in items if x.source is source]
            ranked = sorted(
                candidates,
                key=lambda x: (
                    lexical_score(query, x.text),
                    x.created_session,
                    x.memory_id,
                ),
                reverse=True,
            )
            out.extend(ranked[: self.top_k_by_source[source]])
        return out


class StrategyRetriever:
    def __init__(self, cards: Sequence[StrategyCard], top_k: int = 3):
        self.cards = list(cards)
        self.top_k = top_k

    def retrieve(self, query: str) -> list[StrategyCard]:
        ranked = sorted(
            self.cards,
            key=lambda c: (
                lexical_score(query, c.retrieval_text),
                c.strategy_id,
            ),
            reverse=True,
        )
        return ranked[: self.top_k]

    def confidence(self, query: str) -> float:
        if not self.cards:
            return 0.0
        return max(lexical_score(query, card.retrieval_text) for card in self.cards)
