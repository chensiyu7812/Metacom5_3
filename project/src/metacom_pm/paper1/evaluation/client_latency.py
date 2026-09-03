"""Outcome-blind scheduling and summaries for client-observed text latency."""

from __future__ import annotations

import math
import random
from statistics import fmean

from pydantic import Field

from ..contracts import (
    EndToEndLatencyRecord,
    ExperimentArm,
    LatencyMeasurementSurface,
    StrictContract,
    TaskType,
    WarmState,
)


CLIENT_LATENCY_MEASUREMENT_PROTOCOL = "paper1-client-latency-measurement-v2"
CATASTROPHIC_COMPLETION_CEILING_MS = 60_000.0


class InterleavedLatencyScheduleRow(StrictContract):
    target_id: str = Field(min_length=1)
    task_type: TaskType
    arm: ExperimentArm
    time_block_id: str = Field(min_length=1)
    repeat_index: int = Field(ge=0)
    randomized_sequence_position: int = Field(ge=0)


class ClientLatencyObservation(StrictContract):
    """One raw request trace; content quality is intentionally absent."""

    target_id: str = Field(min_length=1)
    task_type: TaskType
    arm: ExperimentArm
    record: EndToEndLatencyRecord


class ClientLatencySummary(StrictContract):
    protocol: str = CLIENT_LATENCY_MEASUREMENT_PROTOCOL
    task_type: TaskType
    arm: ExperimentArm
    measurement_surface: LatencyMeasurementSurface
    warm_state: WarmState
    concurrency: int = Field(ge=1)
    calls: int = Field(ge=1)
    unique_targets: int = Field(ge=1)
    time_blocks: int = Field(ge=1)
    p50_client_ttft_ms: float = Field(ge=0.0)
    p90_client_ttft_ms: float = Field(ge=0.0)
    p95_client_ttft_ms: float = Field(ge=0.0)
    max_client_ttft_ms: float = Field(ge=0.0)
    p50_client_completion_ms: float = Field(ge=0.0)
    p90_client_completion_ms: float = Field(ge=0.0)
    p95_client_completion_ms: float = Field(ge=0.0)
    max_client_completion_ms: float = Field(ge=0.0)
    catastrophic_ceiling_violation_rate: float = Field(ge=0.0, le=1.0)
    timeout_or_fallback_rate: float = Field(ge=0.0, le=1.0)
    mean_retry_count: float = Field(ge=0.0)
    mean_input_tokens: float = Field(ge=0.0)
    mean_output_tokens: float = Field(ge=0.0)
    primary_controlled_surface: bool
    timeout_penalty_floor_ms: float = CATASTROPHIC_COMPLETION_CEILING_MS


def _nearest_rank(values: tuple[float, ...], percentile: float) -> float:
    if not values:
        raise ValueError("latency percentile requires at least one raw call")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def build_interleaved_latency_schedule(
    target_ids: tuple[str, ...],
    *,
    task_type: TaskType,
    arms: tuple[ExperimentArm, ...],
    repeats: int,
    seed: int,
) -> tuple[InterleavedLatencyScheduleRow, ...]:
    """Randomize all target-by-arm calls independently inside each time block."""

    if not target_ids or len(set(target_ids)) != len(target_ids):
        raise ValueError("target ids must be nonempty and unique")
    if not arms or len(set(arms)) != len(arms):
        raise ValueError("arms must be nonempty and unique")
    if repeats < 1:
        raise ValueError("repeats must be positive")

    rng = random.Random(seed)
    result: list[InterleavedLatencyScheduleRow] = []
    for repeat_index in range(repeats):
        block = [(target_id, arm) for target_id in target_ids for arm in arms]
        rng.shuffle(block)
        time_block_id = f"{task_type.value}-latency-block-{repeat_index:03d}"
        result.extend(
            InterleavedLatencyScheduleRow(
                target_id=target_id,
                task_type=task_type,
                arm=arm,
                time_block_id=time_block_id,
                repeat_index=repeat_index,
                randomized_sequence_position=position,
            )
            for position, (target_id, arm) in enumerate(block)
        )
    return tuple(result)


def summarize_client_latency(
    observations: tuple[ClientLatencyObservation, ...],
) -> ClientLatencySummary:
    """Summarize one arm/task/surface/warm/concurrency stratum from raw calls.

    Timeout or fallback traces are never dropped. Their TTFT and completion
    samples are floored at the catastrophic ceiling so a failed request cannot
    look artificially fast. Non-streaming completed calls use completion as
    the first-visible measurement.
    """

    if not observations:
        raise ValueError("client latency summary requires raw observations")
    signature = {
        (
            row.task_type,
            row.arm,
            row.record.measurement_surface,
            row.record.warm_state,
            row.record.concurrency,
        )
        for row in observations
    }
    if len(signature) != 1:
        raise ValueError(
            "one latency summary cannot mix task, arm, surface, warm state, or concurrency"
        )
    if any(not row.record.text_only for row in observations):
        raise ValueError("Paper-1 client latency primary is text-only")
    trace_ids = [row.record.trace_id for row in observations]
    if len(trace_ids) != len(set(trace_ids)):
        raise ValueError("raw client latency trace ids must be unique")

    ttfts: list[float] = []
    completions: list[float] = []
    for row in observations:
        record = row.record
        completion = record.client_send_to_final_visible_text_ms
        ttft = (
            record.client_send_to_first_visible_text_ms
            if record.client_send_to_first_visible_text_ms is not None
            else completion
        )
        if record.timeout_or_fallback:
            completion = max(completion, CATASTROPHIC_COMPLETION_CEILING_MS)
            ttft = max(ttft, CATASTROPHIC_COMPLETION_CEILING_MS)
        completions.append(completion)
        ttfts.append(ttft)

    task_type, arm, surface, warm_state, concurrency = next(iter(signature))
    ttft_samples = tuple(ttfts)
    completion_samples = tuple(completions)
    primary_controlled = (
        surface is LatencyMeasurementSurface.REFERENCE_CLIENT
        and warm_state is WarmState.WARM
        and concurrency == 1
    )
    return ClientLatencySummary(
        task_type=task_type,
        arm=arm,
        measurement_surface=surface,
        warm_state=warm_state,
        concurrency=concurrency,
        calls=len(observations),
        unique_targets=len({row.target_id for row in observations}),
        time_blocks=len({row.record.time_block_id for row in observations}),
        p50_client_ttft_ms=_nearest_rank(ttft_samples, 0.5),
        p90_client_ttft_ms=_nearest_rank(ttft_samples, 0.9),
        p95_client_ttft_ms=_nearest_rank(ttft_samples, 0.95),
        max_client_ttft_ms=max(ttft_samples),
        p50_client_completion_ms=_nearest_rank(completion_samples, 0.5),
        p90_client_completion_ms=_nearest_rank(completion_samples, 0.9),
        p95_client_completion_ms=_nearest_rank(completion_samples, 0.95),
        max_client_completion_ms=max(completion_samples),
        catastrophic_ceiling_violation_rate=fmean(
            int(value >= CATASTROPHIC_COMPLETION_CEILING_MS)
            for value in completion_samples
        ),
        timeout_or_fallback_rate=fmean(
            int(row.record.timeout_or_fallback) for row in observations
        ),
        mean_retry_count=fmean(row.record.retry_count for row in observations),
        mean_input_tokens=fmean(row.record.input_tokens for row in observations),
        mean_output_tokens=fmean(row.record.output_tokens for row in observations),
        primary_controlled_surface=primary_controlled,
    )


__all__ = [
    "CATASTROPHIC_COMPLETION_CEILING_MS",
    "CLIENT_LATENCY_MEASUREMENT_PROTOCOL",
    "ClientLatencyObservation",
    "ClientLatencySummary",
    "InterleavedLatencyScheduleRow",
    "build_interleaved_latency_schedule",
    "summarize_client_latency",
]
