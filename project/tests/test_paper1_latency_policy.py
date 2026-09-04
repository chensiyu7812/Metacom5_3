import pytest

from metacom_pm.paper1.contracts import Head
from metacom_pm.paper1.core.latency_policy import (
    HeadLatencyCandidate,
    allocate_latency_constrained_heads,
)
from metacom_pm.paper1.core.threshold import ClientLatencyConstraint


def _client_latency(*, scenario: bool = True) -> ClientLatencyConstraint:
    return ClientLatencyConstraint(
        deployment_scenario_id="test-deployment-v1" if scenario else None,
        deployment_ttft_budget_ms=1_000 if scenario else None,
        deployment_completion_budget_ms=2_000 if scenario else None,
        zero_outcome_profiled=True,
        researcher_frozen=True,
    )


def _candidate(
    head: Head,
    probability: float,
    completion_ms: float,
    *,
    ttft_ms: float = 50,
    eligible: bool = True,
) -> HeadLatencyCandidate:
    return HeadLatencyCandidate(
        head=head,
        eligible=eligible,
        predicted_positive_effect_probability=probability,
        frozen_probability_threshold=0.5,
        incremental_p95_client_ttft_ms=ttft_ms,
        incremental_p95_client_completion_ms=completion_ms,
        latency_prediction_protocol_id="test-pre-call-lookup-v1",
        latency_lookup_cell_id=f"test-{head.value}",
    )


def test_allocator_fails_closed_instead_of_ranking_incomparable_head_margins():
    allocation = allocate_latency_constrained_heads(
        (
            _candidate(Head.MP, 0.9, 1_000),
            _candidate(Head.ME, 0.7, 200),
            _candidate(Head.MS, 0.8, 700),
        ),
        client_latency=_client_latency(),
        base_p95_client_ttft_ms=500,
        base_p95_client_completion_ms=1_000,
    )
    assert allocation.selected_heads == ()
    assert allocation.bundle_budget_collision
    assert set(allocation.rejected_heads.values()) == {
        "named_deployment_scenario_bundle_collision_fail_closed"
    }
    assert allocation.predicted_p95_client_completion_ms == 1_000


def test_allocator_keeps_every_threshold_positive_head_when_bundle_is_feasible():
    allocation = allocate_latency_constrained_heads(
        (
            _candidate(Head.MS, 0.55, 200),
            _candidate(Head.MP, 0.9, 100),
            _candidate(Head.ME, 0.7, 200),
        ),
        client_latency=_client_latency(),
        base_p95_client_ttft_ms=100,
        base_p95_client_completion_ms=1_000,
    )
    assert allocation.selected_heads == (Head.MP, Head.ME, Head.MS)
    assert not allocation.bundle_budget_collision
    assert allocation.predicted_p95_client_completion_ms == 1_500


def test_allocator_never_rewards_ineligible_or_threshold_negative_heads():
    allocation = allocate_latency_constrained_heads(
        (
            _candidate(Head.MP, 0.9, 100, eligible=False),
            _candidate(Head.ME, 0.5, 100),
            _candidate(Head.MS, 0.6, 100),
        ),
        client_latency=_client_latency(),
        base_p95_client_ttft_ms=100,
        base_p95_client_completion_ms=500,
    )
    assert allocation.selected_heads == (Head.MS,)
    assert not allocation.bundle_budget_collision
    assert allocation.rejected_heads == {
        Head.MP: "mechanically_ineligible",
        Head.ME: "not_quality_effect_threshold_positive",
    }


def test_allocator_fails_when_even_r0_m0_violates_sla():
    with pytest.raises(ValueError, match=r"R0\+M0"):
        allocate_latency_constrained_heads(
            (),
            client_latency=_client_latency(),
            base_p95_client_ttft_ms=1_100,
            base_p95_client_completion_ms=1_500,
        )


def test_allocator_rejects_rs_and_duplicate_heads():
    with pytest.raises(ValueError, match="MP/ME/MS"):
        _candidate(Head.RS, 0.8, 100)
    candidate = _candidate(Head.MP, 0.8, 100)
    with pytest.raises(ValueError, match="unique"):
        allocate_latency_constrained_heads(
            (candidate, candidate),
            client_latency=_client_latency(),
            base_p95_client_ttft_ms=100,
            base_p95_client_completion_ms=500,
        )


def test_allocator_without_tighter_scenario_only_enforces_catastrophic_ceiling():
    allocation = allocate_latency_constrained_heads(
        (_candidate(Head.MP, 0.9, 20_000, ttft_ms=2_000),),
        client_latency=_client_latency(scenario=False),
        base_p95_client_ttft_ms=1_000,
        base_p95_client_completion_ms=10_000,
    )
    assert allocation.selected_heads == (Head.MP,)

    rejected = allocate_latency_constrained_heads(
        (_candidate(Head.MP, 0.9, 50_001, ttft_ms=2_000),),
        client_latency=_client_latency(scenario=False),
        base_p95_client_ttft_ms=1_000,
        base_p95_client_completion_ms=10_000,
    )
    assert rejected.selected_heads == ()
    assert rejected.bundle_budget_collision
    assert rejected.rejected_heads[Head.MP] == (
        "catastrophic_bundle_collision_fail_closed"
    )
