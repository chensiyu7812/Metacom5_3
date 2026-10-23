"""Outcome-blind, pre-call latency lookup for Paper-1 runtime allocation.

The lookup is deliberately simple and auditable.  It is fitted only from
adjacent ON/OFF timing-profile microblocks, indexed by task, head, visible
context-token bin, and resource-token bin.  No response quality, effect label,
official score, or post-action latency from the request being decided may enter
the prediction.
"""

from __future__ import annotations

import math
from collections import defaultdict

from pydantic import Field, model_validator

from ..contracts import Head, StrictContract, TaskType
from .latency_policy import HeadLatencyCandidate


LATENCY_PREDICTION_PROTOCOL = "paper1-outcome-blind-paired-p95-lookup-v1"
DEFAULT_CONTEXT_TOKEN_BIN_UPPER_BOUNDS = (256, 512, 1_024, 2_048, 4_096, 8_192, 16_384)
DEFAULT_RESOURCE_TOKEN_BIN_UPPER_BOUNDS = (64, 128, 256, 512, 1_024, 2_048, 4_096)


def _bin_label(value: int, upper_bounds: tuple[int, ...]) -> str:
    for lower, upper in zip((0, *upper_bounds[:-1]), upper_bounds, strict=True):
        if value <= upper:
            return f"{lower}-{upper}"
    return f">{upper_bounds[-1]}"


def _nearest_rank_p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


class PairedLatencyProfileSample(StrictContract):
    profile_sample_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    target_microblock_id: str = Field(min_length=1)
    task_type: TaskType
    head: Head
    visible_context_tokens: int = Field(ge=0)
    resource_tokens: int = Field(gt=0)
    off_client_ttft_ms: float = Field(ge=0.0)
    on_client_ttft_ms: float = Field(ge=0.0)
    off_client_completion_ms: float = Field(ge=0.0)
    on_client_completion_ms: float = Field(ge=0.0)
    measurement_protocol_id: str = "paper1-client-latency-measurement-v3"
    response_quality_or_effect_read: bool = False

    @model_validator(mode="after")
    def validate_profile_sample(self) -> "PairedLatencyProfileSample":
        if self.off_client_ttft_ms > self.off_client_completion_ms:
            raise ValueError("OFF TTFT cannot exceed OFF completion")
        if self.on_client_ttft_ms > self.on_client_completion_ms:
            raise ValueError("ON TTFT cannot exceed ON completion")
        if self.response_quality_or_effect_read:
            raise ValueError("latency profiling cannot read quality/effect outcomes")
        return self


class LatencyLookupCell(StrictContract):
    cell_id: str = Field(min_length=1)
    task_type: TaskType
    head: Head
    context_token_bin: str = Field(min_length=1)
    resource_token_bin: str = Field(min_length=1)
    paired_samples: int = Field(ge=1)
    incremental_p95_client_ttft_ms: float = Field(ge=0.0)
    incremental_p95_client_completion_ms: float = Field(ge=0.0)


class FrozenLatencyLookup(StrictContract):
    protocol: str = LATENCY_PREDICTION_PROTOCOL
    context_token_bin_upper_bounds: tuple[int, ...]
    resource_token_bin_upper_bounds: tuple[int, ...]
    cells: tuple[LatencyLookupCell, ...]
    response_quality_or_effect_calls: int = 0

    @model_validator(mode="after")
    def validate_lookup(self) -> "FrozenLatencyLookup":
        for bounds in (
            self.context_token_bin_upper_bounds,
            self.resource_token_bin_upper_bounds,
        ):
            if not bounds or tuple(sorted(set(bounds))) != bounds or bounds[0] <= 0:
                raise ValueError("latency token-bin upper bounds must be unique positive ascending integers")
        keys = [
            (cell.task_type, cell.head, cell.context_token_bin, cell.resource_token_bin)
            for cell in self.cells
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("latency lookup cells must have unique task/head/token-bin keys")
        if self.response_quality_or_effect_calls != 0:
            raise ValueError("latency lookup cannot use response quality/effect calls")
        return self

    def lookup(
        self,
        *,
        task_type: TaskType,
        head: Head,
        visible_context_tokens: int,
        resource_tokens: int,
    ) -> LatencyLookupCell:
        context_bin = _bin_label(visible_context_tokens, self.context_token_bin_upper_bounds)
        resource_bin = _bin_label(resource_tokens, self.resource_token_bin_upper_bounds)
        matches = [
            cell
            for cell in self.cells
            if (
                cell.task_type,
                cell.head,
                cell.context_token_bin,
                cell.resource_token_bin,
            )
            == (task_type, head, context_bin, resource_bin)
        ]
        if len(matches) != 1:
            raise ValueError(
                "no unique pre-call latency lookup cell for "
                f"{task_type.value}/{head.value}/{context_bin}/{resource_bin}"
            )
        return matches[0]


def build_frozen_latency_lookup(
    samples: tuple[PairedLatencyProfileSample, ...],
    *,
    context_token_bin_upper_bounds: tuple[int, ...] = DEFAULT_CONTEXT_TOKEN_BIN_UPPER_BOUNDS,
    resource_token_bin_upper_bounds: tuple[int, ...] = DEFAULT_RESOURCE_TOKEN_BIN_UPPER_BOUNDS,
) -> FrozenLatencyLookup:
    if not samples:
        raise ValueError("latency lookup requires paired zero-outcome profile samples")
    ids = [sample.profile_sample_id for sample in samples]
    if len(ids) != len(set(ids)):
        raise ValueError("latency profile sample ids must be unique")

    grouped: dict[tuple[TaskType, Head, str, str], list[PairedLatencyProfileSample]] = defaultdict(list)
    for sample in samples:
        key = (
            sample.task_type,
            sample.head,
            _bin_label(sample.visible_context_tokens, context_token_bin_upper_bounds),
            _bin_label(sample.resource_tokens, resource_token_bin_upper_bounds),
        )
        grouped[key].append(sample)

    cells = []
    for (task_type, head, context_bin, resource_bin), rows in sorted(
        grouped.items(), key=lambda item: tuple(str(part) for part in item[0])
    ):
        ttft_increments = [max(0.0, row.on_client_ttft_ms - row.off_client_ttft_ms) for row in rows]
        completion_increments = [
            max(0.0, row.on_client_completion_ms - row.off_client_completion_ms)
            for row in rows
        ]
        # Independent nearest-rank p95 increments may invert because paired
        # OFF baselines differ. Preserve the allocator's clock ordering by
        # raising completion conservatively, never by suppressing TTFT.
        p95_ttft = _nearest_rank_p95(ttft_increments)
        p95_completion = max(_nearest_rank_p95(completion_increments), p95_ttft)
        cell_id = (
            f"{task_type.value}:{head.value}:context={context_bin}:resource={resource_bin}"
        )
        cells.append(
            LatencyLookupCell(
                cell_id=cell_id,
                task_type=task_type,
                head=head,
                context_token_bin=context_bin,
                resource_token_bin=resource_bin,
                paired_samples=len(rows),
                incremental_p95_client_ttft_ms=p95_ttft,
                incremental_p95_client_completion_ms=p95_completion,
            )
        )
    return FrozenLatencyLookup(
        context_token_bin_upper_bounds=context_token_bin_upper_bounds,
        resource_token_bin_upper_bounds=resource_token_bin_upper_bounds,
        cells=tuple(cells),
    )


def build_pre_call_head_latency_candidate(
    *,
    lookup: FrozenLatencyLookup,
    task_type: TaskType,
    head: Head,
    visible_context_tokens: int,
    resource_tokens: int,
    eligible: bool,
    predicted_positive_effect_probability: float,
    frozen_probability_threshold: float,
) -> HeadLatencyCandidate:
    cell = lookup.lookup(
        task_type=task_type,
        head=head,
        visible_context_tokens=visible_context_tokens,
        resource_tokens=resource_tokens,
    )
    return HeadLatencyCandidate(
        head=head,
        eligible=eligible,
        predicted_positive_effect_probability=predicted_positive_effect_probability,
        frozen_probability_threshold=frozen_probability_threshold,
        incremental_p95_client_ttft_ms=cell.incremental_p95_client_ttft_ms,
        incremental_p95_client_completion_ms=cell.incremental_p95_client_completion_ms,
        latency_prediction_protocol_id=lookup.protocol,
        latency_lookup_cell_id=cell.cell_id,
    )


__all__ = [
    "DEFAULT_CONTEXT_TOKEN_BIN_UPPER_BOUNDS",
    "DEFAULT_RESOURCE_TOKEN_BIN_UPPER_BOUNDS",
    "FrozenLatencyLookup",
    "LATENCY_PREDICTION_PROTOCOL",
    "LatencyLookupCell",
    "PairedLatencyProfileSample",
    "build_frozen_latency_lookup",
    "build_pre_call_head_latency_candidate",
]
