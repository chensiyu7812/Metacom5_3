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


def test_allocator_uses_probability_margin_per_incremental_p95_latency():
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
    # ME has the largest margin/latency ratio, then MS. MP no longer fits.
    assert allocation.selected_heads == (Head.ME, Head.MS)
    assert allocation.rejected_heads[Head.MP] == "named_deployment_scenario_overflow"
    assert allocation.predicted_p95_client_completion_ms == 1_900


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
    assert rejected.rejected_heads[Head.MP] == (
        "catastrophic_client_completion_ceiling_overflow"
    )
