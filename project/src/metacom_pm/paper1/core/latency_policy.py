"""Transparent first-order allocation under client-observed latency constraints.

The effect models remain independent probability estimators.  This module is
the deployment layer: it admits only eligible, threshold-positive heads and
greedily selects a latency-feasible subset using the pre-outcome priority rule.
It deliberately makes no interaction-aware or globally optimal claim.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from ..contracts import Head, StrictContract
from .threshold import ClientLatencyConstraint


CANONICAL_MEMORY_HEAD_ORDER = (Head.MP, Head.ME, Head.MS)


class HeadLatencyCandidate(StrictContract):
    head: Head
    eligible: bool
    predicted_positive_effect_probability: float = Field(ge=0.0, le=1.0)
    frozen_probability_threshold: float = Field(ge=0.0, le=1.0)
    incremental_p95_client_ttft_ms: float = Field(ge=0.0)
    incremental_p95_client_completion_ms: float = Field(ge=0.0)
    latency_prediction_protocol_id: str = Field(min_length=1)
    latency_lookup_cell_id: str = Field(min_length=1)
    prediction_made_pre_call: bool = True
    realized_post_action_latency_read: bool = False

    @model_validator(mode="after")
    def memory_head_and_clock_order(self) -> "HeadLatencyCandidate":
        if self.head is Head.RS:
            raise ValueError("the multi-head allocator accepts MP/ME/MS only")
        if (
            self.incremental_p95_client_ttft_ms
            > self.incremental_p95_client_completion_ms
        ):
            raise ValueError("incremental TTFT cannot exceed incremental completion latency")
        if not self.prediction_made_pre_call or self.realized_post_action_latency_read:
            raise ValueError("runtime allocation requires an outcome-blind pre-call latency prediction")
        return self

    @property
    def probability_margin(self) -> float:
        return (
            self.predicted_positive_effect_probability
            - self.frozen_probability_threshold
        )

    @property
    def threshold_positive(self) -> bool:
        return self.probability_margin > 0.0

    @property
    def priority_score(self) -> float:
        # Zero measured increment is a legitimate highest-priority candidate.
        if self.incremental_p95_client_completion_ms == 0.0:
            return float("inf") if self.probability_margin > 0.0 else 0.0
        return self.probability_margin / self.incremental_p95_client_completion_ms


class LatencyConstrainedAllocation(StrictContract):
    client_latency_measurement_protocol_id: str = Field(min_length=1)
    deployment_scenario_id: str | None = Field(default=None, min_length=1)
    selected_heads: tuple[Head, ...]
    rejected_heads: dict[Head, str]
    base_p95_client_ttft_ms: float = Field(ge=0.0)
    base_p95_client_completion_ms: float = Field(ge=0.0)
    predicted_p95_client_ttft_ms: float = Field(ge=0.0)
    predicted_p95_client_completion_ms: float = Field(ge=0.0)
    interaction_aware_optimality_claim: bool = False

    @model_validator(mode="after")
    def validate_allocation(self) -> "LatencyConstrainedAllocation":
        if len(self.selected_heads) != len(set(self.selected_heads)):
            raise ValueError("selected heads must be unique")
        if set(self.selected_heads) & set(self.rejected_heads):
            raise ValueError("a head cannot be both selected and rejected")
        if self.interaction_aware_optimality_claim:
            raise ValueError("the frozen allocator cannot claim interaction-aware optimality")
        if self.predicted_p95_client_ttft_ms > self.predicted_p95_client_completion_ms:
            raise ValueError("predicted TTFT cannot exceed predicted completion latency")
        return self


def allocate_latency_constrained_heads(
    candidates: tuple[HeadLatencyCandidate, ...],
    *,
    client_latency: ClientLatencyConstraint,
    base_p95_client_ttft_ms: float,
    base_p95_client_completion_ms: float,
) -> LatencyConstrainedAllocation:
    """Allocate MP/ME/MS using margin per incremental p95 completion latency.

    Incremental estimates must be produced by the frozen same-stack latency
    profiler. Summing them is the declared first-order approximation; joint
    interaction effects remain a diagnostic and are not silently optimized.
    """

    if base_p95_client_ttft_ms < 0 or base_p95_client_completion_ms < 0:
        raise ValueError("base latency predictions must be non-negative")
    if base_p95_client_ttft_ms > base_p95_client_completion_ms:
        raise ValueError("base TTFT cannot exceed base completion latency")
    if base_p95_client_completion_ms >= client_latency.catastrophic_completion_ceiling_ms:
        raise ValueError("R0+M0 violates the catastrophic client completion ceiling")
    if client_latency.has_tighter_deployment_scenario:
        assert client_latency.deployment_ttft_budget_ms is not None
        assert client_latency.deployment_completion_budget_ms is not None
        if (
            base_p95_client_ttft_ms > client_latency.deployment_ttft_budget_ms
            or base_p95_client_completion_ms
            > client_latency.deployment_completion_budget_ms
        ):
            raise ValueError("R0+M0 violates the named deployment scenario")

    heads = [candidate.head for candidate in candidates]
    if len(heads) != len(set(heads)):
        raise ValueError("candidate heads must be unique")

    order = {head: index for index, head in enumerate(CANONICAL_MEMORY_HEAD_ORDER)}
    qualifying = [
        candidate
        for candidate in candidates
        if candidate.eligible and candidate.threshold_positive
    ]
    qualifying.sort(
        key=lambda candidate: (
            -candidate.priority_score,
            -candidate.probability_margin,
            order[candidate.head],
        )
    )

    selected: list[Head] = []
    rejected: dict[Head, str] = {}
    predicted_ttft = base_p95_client_ttft_ms
    predicted_completion = base_p95_client_completion_ms

    for candidate in candidates:
        if not candidate.eligible:
            rejected[candidate.head] = "mechanically_ineligible"
        elif not candidate.threshold_positive:
            rejected[candidate.head] = "not_quality_effect_threshold_positive"

    for candidate in qualifying:
        proposed_ttft = predicted_ttft + candidate.incremental_p95_client_ttft_ms
        proposed_completion = (
            predicted_completion
            + candidate.incremental_p95_client_completion_ms
        )
        catastrophic_feasible = (
            proposed_completion < client_latency.catastrophic_completion_ceiling_ms
        )
        scenario_feasible = True
        if client_latency.has_tighter_deployment_scenario:
            assert client_latency.deployment_ttft_budget_ms is not None
            assert client_latency.deployment_completion_budget_ms is not None
            scenario_feasible = (
                proposed_ttft <= client_latency.deployment_ttft_budget_ms
                and proposed_completion <= client_latency.deployment_completion_budget_ms
            )
        if catastrophic_feasible and scenario_feasible:
            selected.append(candidate.head)
            predicted_ttft = proposed_ttft
            predicted_completion = proposed_completion
        else:
            rejected[candidate.head] = (
                "named_deployment_scenario_overflow"
                if client_latency.has_tighter_deployment_scenario
                else "catastrophic_client_completion_ceiling_overflow"
            )

    return LatencyConstrainedAllocation(
        client_latency_measurement_protocol_id=client_latency.measurement_protocol_id,
        deployment_scenario_id=client_latency.deployment_scenario_id,
        selected_heads=tuple(selected),
        rejected_heads=rejected,
        base_p95_client_ttft_ms=base_p95_client_ttft_ms,
        base_p95_client_completion_ms=base_p95_client_completion_ms,
        predicted_p95_client_ttft_ms=predicted_ttft,
        predicted_p95_client_completion_ms=predicted_completion,
    )


__all__ = [
    "CANONICAL_MEMORY_HEAD_ORDER",
    "HeadLatencyCandidate",
    "LatencyConstrainedAllocation",
    "allocate_latency_constrained_heads",
]
