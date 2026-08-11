from __future__ import annotations

from metacom_pm.v1_5_ms_executor_function_review_v2 import (
    MSExecutorFunctionReview,
    validate_review_provider_safe,
)


ITEM = {
    "blind_item_id": "x",
    "strictly_past_user_owned_source": "Earlier I went blank without preparation time.",
    "response": "When this happened before, preparation time was the hard part.",
}


def test_nonboundary_provider_cross_contamination_is_cleared_without_changing_label() -> None:
    parsed = MSExecutorFunctionReview.model_validate(
        {
            "blind_item_id": "x",
            "label": "FUNCTIONAL",
            "source_evidence_quote": "went blank without preparation time",
            "response_evidence_quote": "preparation time was the hard part",
            "boundary_event_quote": "</parameter><parameter name=rationale>garbage",
            "rationale": "The past constraint changes the reply.",
        }
    )
    row = validate_review_provider_safe(parsed, ITEM)
    assert row["label"] == "FUNCTIONAL"
    assert row["boundary_event_quote"] == ""


def test_boundary_failure_still_requires_literal_response_evidence() -> None:
    parsed = MSExecutorFunctionReview.model_validate(
        {
            "blind_item_id": "x",
            "label": "BOUNDARY_FAILURE",
            "source_evidence_quote": "",
            "response_evidence_quote": "",
            "boundary_event_quote": "invented current fact",
            "rationale": "Past was upgraded to present.",
        }
    )
    try:
        validate_review_provider_safe(parsed, ITEM)
    except ValueError as exc:
        assert str(exc) == "boundary_event_quote_not_literal"
    else:
        raise AssertionError("boundary evidence must remain fail-closed")
