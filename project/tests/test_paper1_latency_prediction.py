import pytest
from pydantic import ValidationError

from metacom_pm.paper1.contracts import Head, TaskType
from metacom_pm.paper1.core.latency_prediction import (
    LATENCY_PREDICTION_PROTOCOL,
    PairedLatencyProfileSample,
    build_frozen_latency_lookup,
    build_pre_call_head_latency_candidate,
)


def _sample(index: int, *, resource_tokens: int = 100) -> PairedLatencyProfileSample:
    return PairedLatencyProfileSample(
        profile_sample_id=f"sample-{index}",
        target_id=f"target-{index}",
        target_microblock_id=f"micro-{index}",
        task_type=TaskType.QA,
        head=Head.ME,
        visible_context_tokens=400,
        resource_tokens=resource_tokens,
        off_client_ttft_ms=100,
        on_client_ttft_ms=120 + index,
        off_client_completion_ms=200,
        on_client_completion_ms=250 + index,
    )


def test_outcome_blind_lookup_builds_exact_pre_call_candidate():
    lookup = build_frozen_latency_lookup(tuple(_sample(index) for index in range(20)))
    candidate = build_pre_call_head_latency_candidate(
        lookup=lookup,
        task_type=TaskType.QA,
        head=Head.ME,
        visible_context_tokens=400,
        resource_tokens=100,
        eligible=True,
        predicted_positive_effect_probability=0.8,
        frozen_probability_threshold=0.5,
    )
    assert candidate.latency_prediction_protocol_id == LATENCY_PREDICTION_PROTOCOL
    assert candidate.incremental_p95_client_ttft_ms == 38
    assert candidate.incremental_p95_client_completion_ms == 68
    assert candidate.prediction_made_pre_call is True
    assert candidate.realized_post_action_latency_read is False


def test_lookup_missing_bin_fails_instead_of_using_realized_request_latency():
    lookup = build_frozen_latency_lookup((_sample(0),))
    with pytest.raises(ValueError, match="no unique pre-call latency lookup cell"):
        build_pre_call_head_latency_candidate(
            lookup=lookup,
            task_type=TaskType.QA,
            head=Head.ME,
            visible_context_tokens=10_000,
            resource_tokens=100,
            eligible=True,
            predicted_positive_effect_probability=0.8,
            frozen_probability_threshold=0.5,
        )


def test_latency_profile_rejects_quality_or_effect_reads():
    with pytest.raises(ValidationError, match="cannot read quality/effect"):
        PairedLatencyProfileSample(
            **{
                **_sample(0).model_dump(),
                "response_quality_or_effect_read": True,
            }
        )
