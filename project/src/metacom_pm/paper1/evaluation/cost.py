"""Objective cost accounting kept separate from capability outcomes."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from ..contracts import CostRecord, StrictContract


class TokenPricing(StrictContract):
    input_usd_per_million: float = Field(ge=0.0)
    output_usd_per_million: float = Field(ge=0.0)


def build_cost_record(
    *,
    generator_input_tokens: int,
    resource_injected_tokens: int,
    output_tokens: int,
    latency_ms: float,
    retrieval_calls: int = 0,
    embedding_calls: int = 0,
    retries: int = 0,
    pricing: TokenPricing | None = None,
    metadata: dict[str, Any] | None = None,
) -> CostRecord:
    if resource_injected_tokens > generator_input_tokens:
        raise ValueError("resource tokens must be a subset of generator input tokens")

    api_cost = None
    if pricing is not None:
        api_cost = (
            generator_input_tokens * pricing.input_usd_per_million
            + output_tokens * pricing.output_usd_per_million
        ) / 1_000_000

    return CostRecord(
        generator_input_tokens=generator_input_tokens,
        resource_injected_tokens=resource_injected_tokens,
        output_tokens=output_tokens,
        total_tokens=generator_input_tokens + output_tokens,
        retrieval_calls=retrieval_calls,
        embedding_calls=embedding_calls,
        latency_ms=latency_ms,
        retries=retries,
        recoverable_api_cost_usd=api_cost,
        metadata=metadata or {},
    )
