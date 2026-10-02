"""Deterministic helpers for exact-treatment canonical BGE ranking."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from .canonicalization import ExactTreatmentAlias


def select_top_indices(
    similarities: np.ndarray,
    *,
    treatment_ids: Sequence[str],
    eligible_mask: np.ndarray,
    top_k: int,
) -> tuple[int, ...]:
    """Select a deterministic cosine top-k without sorting the whole catalog.

    ``argpartition`` finds the boundary efficiently; all exact boundary ties
    are then included before the final ``(-score, treatment_id)`` ordering.
    Thus the result is deterministic even when more than ``k`` tickets share
    the kth score.
    """

    if similarities.ndim != 1 or eligible_mask.ndim != 1:
        raise ValueError("similarities and eligible_mask must be one-dimensional")
    if len(similarities) != len(treatment_ids) or len(eligible_mask) != len(treatment_ids):
        raise ValueError("similarity, treatment-id and eligibility lengths differ")
    if top_k < 1:
        raise ValueError("top_k must be positive")
    eligible_indices = np.flatnonzero(eligible_mask)
    if len(eligible_indices) < top_k:
        raise ValueError("fewer eligible canonical treatments than top_k")
    eligible_scores = similarities[eligible_indices]
    partition = np.argpartition(-eligible_scores, top_k - 1)[:top_k]
    boundary = float(np.min(eligible_scores[partition]))
    tied = eligible_indices[eligible_scores >= boundary]
    ordered = sorted(
        (int(index) for index in tied),
        key=lambda index: (-float(similarities[index]), treatment_ids[index]),
    )
    return tuple(ordered[:top_k])


def build_dialogue_exclusion_index(
    aliases: Sequence[ExactTreatmentAlias],
) -> dict[str, tuple[int, ...]]:
    by_dialogue: dict[str, list[int]] = {}
    for index, alias in enumerate(aliases):
        for dialogue_id in alias.source_dialogue_ids:
            by_dialogue.setdefault(dialogue_id, []).append(index)
    return {key: tuple(sorted(value)) for key, value in by_dialogue.items()}
