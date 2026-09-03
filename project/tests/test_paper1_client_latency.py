import pytest

from metacom_pm.paper1.contracts import (
    EndToEndLatencyRecord,
    ExperimentArm,
    LatencyMeasurementSurface,
    TaskType,
    WarmState,
)
from metacom_pm.paper1.evaluation.client_latency import (
    ClientLatencyObservation,
    build_interleaved_latency_schedule,
    summarize_client_latency,
)


def _observation(
    index: int,
    *,
    completion_ms: float,
    ttft_ms: float | None,
    timeout: bool = False,
    surface: LatencyMeasurementSurface = LatencyMeasurementSurface.REFERENCE_CLIENT,
    warm_state: WarmState = WarmState.WARM,
) -> ClientLatencyObservation:
    streaming = ttft_ms is not None
    return ClientLatencyObservation(
        target_id=f"target-{index % 2}",
        task_type=TaskType.QA,
        arm=ExperimentArm.NO_MEMORY,
        record=EndToEndLatencyRecord(
            trace_id=f"trace-{index}",
            measurement_surface=surface,
            time_block_id=f"block-{index // 2}",
            randomized_sequence_position=index,
            client_region="tokyo",
            warm_state=warm_state,
            concurrency=1,
            connection_reuse=True,
            policy_decision_ms=5,
            retrieval_embedding_ms=0,
            resource_render_pack_ms=1,
            provider_request_to_first_content_ms=(
                None if ttft_ms is None else max(0, ttft_ms - 10)
            ),
            provider_request_to_completion_ms=max(0, completion_ms - 10),
            client_send_to_first_visible_text_ms=ttft_ms,
            client_send_to_final_visible_text_ms=completion_ms,
            streaming_observed=streaming,
            timeout_or_fallback=timeout,
            input_tokens=100,
            output_tokens=20,
            retry_count=int(timeout),
            finish_reason="timeout" if timeout else "stop",
        ),
    )


def test_schedule_interleaves_every_target_arm_once_per_time_block():
    schedule = build_interleaved_latency_schedule(
        ("a", "b"),
        task_type=TaskType.QA,
        arms=(ExperimentArm.NO_MEMORY, ExperimentArm.OFFICIAL_RAG_TOP4),
        repeats=3,
        seed=17,
    )
    assert len(schedule) == 12
    for repeat in range(3):
        block = [row for row in schedule if row.repeat_index == repeat]
        assert {(row.target_id, row.arm) for row in block} == {
            (target, arm)
            for target in ("a", "b")
            for arm in (ExperimentArm.NO_MEMORY, ExperimentArm.OFFICIAL_RAG_TOP4)
        }
        assert {row.randomized_sequence_position for row in block} == set(range(4))


def test_summary_uses_raw_nearest_rank_and_retains_timeout_penalty():
    observations = tuple(
        _observation(
            index,
            completion_ms=100 + index,
            ttft_ms=50 + index,
            timeout=index == 19,
        )
        for index in range(20)
    )
    summary = summarize_client_latency(observations)
    assert summary.calls == 20
    assert summary.p95_client_completion_ms == 118
    assert summary.max_client_completion_ms == 60_000
    assert summary.catastrophic_ceiling_violation_rate == pytest.approx(0.05)
    assert summary.timeout_or_fallback_rate == pytest.approx(0.05)
    assert summary.primary_controlled_surface is True


def test_summary_separates_measurement_surface_and_warm_state():
    mixed_surface = (
        _observation(0, completion_ms=100, ttft_ms=50),
        _observation(
            1,
            completion_ms=100,
            ttft_ms=50,
            surface=LatencyMeasurementSurface.BROWSER_RENDER_READY,
        ),
    )
    with pytest.raises(ValueError, match="cannot mix"):
        summarize_client_latency(mixed_surface)

    cold = summarize_client_latency(
        (
            _observation(
                2,
                completion_ms=100,
                ttft_ms=None,
                warm_state=WarmState.COLD,
            ),
        )
    )
    assert cold.p95_client_ttft_ms == 100
    assert cold.primary_controlled_surface is False
