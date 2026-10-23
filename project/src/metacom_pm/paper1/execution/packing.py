"""Deterministic retrieval ranking and Step2 bundle packing.

This module decides neither whether a head is ON nor which resource amount is
best.  It only implements the frozen mechanics needed to compare candidate
amounts: BGE cosine ranking with an explicit identity tie-break, exact-prefix
selection, and fail-closed enforcement of a caller-supplied resource-token
cap.  It never truncates a candidate, drops an assigned item, or backfills a
different item to make an over-budget bundle fit.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from ..contracts import CandidateRecord, Head, TreatmentAssignment
from ..embeddings.materialization import cosine_similarity
from .step2 import Step2ResourceEnvelope, build_typed_treatment_bundle, render_step2_resource_envelope

PACKING_PROTOCOL = "pm-paper1-deterministic-ranked-prefix-packing-v1"


class ResourceBudgetOverflow(RuntimeError):
    """The exact selected prefix does not fit the declared resource cap."""


@dataclass(frozen=True)
class RankedCandidate:
    candidate: CandidateRecord
    similarity: float


@dataclass(frozen=True)
class PackedResource:
    protocol: str
    requested_k: int
    realized_k: int
    rendered_resource_tokens: int
    envelope: Step2ResourceEnvelope


def rank_candidates(
    *,
    query_vector: tuple[float, ...],
    candidates: Sequence[CandidateRecord],
    candidate_vectors: Mapping[str, tuple[float, ...]],
) -> tuple[RankedCandidate, ...]:
    """Rank every eligible candidate by cosine, then candidate id.

    The candidate-id tie-break is audit-only and deterministic.  Candidate
    ids are never model features and their lexical form never changes a
    non-tied score.
    """

    ids = [candidate.candidate_id for candidate in candidates]
    if len(ids) != len(set(ids)):
        raise ValueError("ranking requires unique candidate ids")
    missing = sorted(set(ids) - set(candidate_vectors))
    if missing:
        raise ValueError(f"missing candidate vectors: {missing[:3]}")
    rows = []
    for candidate in candidates:
        score = cosine_similarity(query_vector, candidate_vectors[candidate.candidate_id])
        if not math.isfinite(score):
            raise ValueError("candidate similarity must be finite")
        rows.append(RankedCandidate(candidate=candidate, similarity=score))
    return tuple(sorted(rows, key=lambda row: (-row.similarity, row.candidate.candidate_id)))


def select_ranked_prefix(
    ranked: Sequence[RankedCandidate], *, k: int
) -> tuple[RankedCandidate, ...]:
    if k < 0:
        raise ValueError("k must be nonnegative")
    return tuple(ranked[:k])


def pack_ranked_prefix(
    *,
    head: Head,
    ranked: Sequence[RankedCandidate],
    k: int,
    target_owner_id: str | None,
    token_counter: Callable[[str], int],
    max_resource_tokens: int | None = None,
) -> PackedResource:
    """Render exactly the first ``k`` candidates, or fail closed on overflow.

    ``k=0`` is the true OFF condition and therefore contains no resource
    block.  If fewer than ``k`` eligible candidates exist, every available
    candidate is used and ``realized_k`` records that fact.
    """

    if max_resource_tokens is not None and max_resource_tokens < 1:
        raise ValueError("max_resource_tokens must be positive when supplied")
    selected = select_ranked_prefix(ranked, k=k)
    if not selected:
        envelope = render_step2_resource_envelope(
            assignment=TreatmentAssignment.OFF,
            head=head,
        )
        return PackedResource(
            protocol=PACKING_PROTOCOL,
            requested_k=k,
            realized_k=0,
            rendered_resource_tokens=0,
            envelope=envelope,
        )
    candidates = tuple(row.candidate for row in selected)
    if any(candidate.head is not head for candidate in candidates):
        raise ValueError("ranked prefix contains a candidate from another head")
    bundle = build_typed_treatment_bundle(
        candidates,
        target_owner_id=target_owner_id,
    )
    envelope = render_step2_resource_envelope(
        assignment=TreatmentAssignment.ON,
        head=head,
        bundle=bundle,
    )
    rendered_tokens = int(token_counter(envelope.rendered_resource_block))
    if rendered_tokens < 1:
        raise ValueError("token_counter must return a positive count for an ON resource")
    if max_resource_tokens is not None and rendered_tokens > max_resource_tokens:
        raise ResourceBudgetOverflow(
            f"exact {head.value} top-{len(candidates)} resource uses {rendered_tokens} tokens, "
            f"exceeding cap={max_resource_tokens}; no truncation/drop/backfill is allowed"
        )
    return PackedResource(
        protocol=PACKING_PROTOCOL,
        requested_k=k,
        realized_k=len(candidates),
        rendered_resource_tokens=rendered_tokens,
        envelope=envelope,
    )


__all__ = [
    "PACKING_PROTOCOL",
    "PackedResource",
    "RankedCandidate",
    "ResourceBudgetOverflow",
    "pack_ranked_prefix",
    "rank_candidates",
    "select_ranked_prefix",
]
