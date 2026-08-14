"""Provider-safe projection for the anchored MS executor Function review.

The scientific label contract and prompt remain byte-identical to V1.  V2 only
canonicalizes a field that is definitionally irrelevant outside
BOUNDARY_FAILURE.  This prevents an Anthropic tool-use serialization defect
from turning a valid, already-paid response into a semantic retry.
"""

from __future__ import annotations

from typing import Any, Mapping

from .v1_5_ms_executor_function_review import (
    MSExecutorFunctionReview,
    prompt_messages,
    validate_review,
)


def validate_review_provider_safe(
    parsed: MSExecutorFunctionReview,
    item: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate after clearing only the label-irrelevant boundary field.

    `boundary_event_quote` is required evidence only for BOUNDARY_FAILURE.  It
    carries no information for the other four labels, so clearing it cannot
    change a decision, create Function evidence, or consult hidden gold.
    All decision-bearing fields retain the strict V1 literal-span checks.
    """

    if parsed.label == "BOUNDARY_FAILURE":
        return validate_review(parsed, item)
    payload = parsed.model_dump(mode="json")
    payload["boundary_event_quote"] = ""
    return validate_review(MSExecutorFunctionReview.model_validate(payload), item)


__all__ = [
    "MSExecutorFunctionReview",
    "prompt_messages",
    "validate_review_provider_safe",
]
