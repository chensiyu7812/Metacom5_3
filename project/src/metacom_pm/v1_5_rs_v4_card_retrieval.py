"""RS Step2 card selection over the 79 LLM-audit-qualified Strategy Bank V4 cards.

Reuses two already-proven pieces rather than inventing new ones:
- eligible_families() (v1_5_strategy_rag_v4.py) for family-level eligibility,
  fed by the same repaired_observable_opportunity_flags() the RS opportunity
  router (Step1) already uses and that was independently verified construct-
  faithful on real EvoEmo dialogue (paper1_rs_evoemo_opportunity_anchor round).
- lexical_score() (text.py), the same TF-cosine ranking function the only
  other qualified Strategy RAG runtime (v1_5_strategy_rag_runtime.py,
  frozen 6-card development catalog) uses for ranking.

This does not replace or modify either of those; it assembles them against a
larger, richer, differently-sourced card pool (81 -> 79 LLM-audit-qualified
V4 cards spanning all 5 strategy families) than the frozen 6-card runtime
supports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .text import lexical_score
from .v1_5_strategy_rag_repair import repaired_observable_opportunity_flags
from .v1_5_strategy_rag_runtime import query_text
from .v1_5_strategy_rag_v4 import eligible_families


MINIMUM_SCORE = 0.05


@dataclass(frozen=True)
class RSV4RetrievalDecision:
    status: str
    eligible_families: tuple[str, ...]
    eligible_card_count: int
    selected_card: Mapping[str, Any] | None
    selected_score: float | None
    query_text: str


def retrieve(
    *,
    recent_dialogue: Sequence[Mapping[str, Any]],
    qualified_cards: Sequence[Mapping[str, Any]],
    minimum_score: float = MINIMUM_SCORE,
) -> RSV4RetrievalDecision:
    """Select at most one card from an already LLM-audit-qualified pool.

    ``qualified_cards`` must already be filtered to llm_audit_qualified=True
    by the caller -- this function does not re-check that flag, to keep it
    usable against any future, differently-qualified card pool without a
    hidden dependency on this specific audit's field name.
    """

    if not recent_dialogue:
        raise ValueError("recent_dialogue must be non-empty")
    if not qualified_cards:
        raise ValueError("qualified_cards must be non-empty")

    current_user_text = next(
        (
            str(turn.get("content", "")).strip()
            for turn in reversed(list(recent_dialogue))
            if str(turn.get("speaker", "")).casefold() in {"seeker", "user"}
        ),
        "",
    )
    flags = repaired_observable_opportunity_flags(
        current_user_text=current_user_text,
        visible_dialogue=recent_dialogue,
    )
    families = eligible_families(flags)
    query = query_text(recent_dialogue)

    if not families:
        return RSV4RetrievalDecision(
            status="off_no_eligible_family",
            eligible_families=(),
            eligible_card_count=0,
            selected_card=None,
            selected_score=None,
            query_text=query,
        )

    candidates = [card for card in qualified_cards if card.get("strategy_family") in families]
    if not candidates:
        return RSV4RetrievalDecision(
            status="off_no_qualified_card_in_eligible_families",
            eligible_families=families,
            eligible_card_count=0,
            selected_card=None,
            selected_score=None,
            query_text=query,
        )

    ranked = sorted(
        (
            (lexical_score(query, str(card.get("retrieval_text", ""))), card)
            for card in candidates
        ),
        key=lambda pair: (pair[0], str(pair[1].get("card_id", ""))),
        reverse=True,
    )
    score, card = ranked[0]
    if score < minimum_score:
        return RSV4RetrievalDecision(
            status="off_below_score_floor",
            eligible_families=families,
            eligible_card_count=len(candidates),
            selected_card=None,
            selected_score=float(score),
            query_text=query,
        )
    return RSV4RetrievalDecision(
        status="retrieved_top1",
        eligible_families=families,
        eligible_card_count=len(candidates),
        selected_card=card,
        selected_score=float(score),
        query_text=query,
    )
