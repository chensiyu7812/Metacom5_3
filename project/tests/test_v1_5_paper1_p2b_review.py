from collections import Counter

from metacom_pm.v1_5_paper1_suitability import SUITABILITY_AXES, validate_atomic_judgment
from metacom_pm.v1_5_paper1_suitability_review import (
    build_reviewer_controls,
    prompt_messages,
)


def test_control_surface_is_complete_balanced_and_private_gold_is_separate():
    items, key = build_reviewer_controls()
    assert len(items) == len(key) == 24
    assert Counter(row["component"] for row in items) == Counter({"MP": 6, "MS": 6, "ME": 6, "RS": 6})
    assert {row["review_item_id"] for row in items} == {row["review_item_id"] for row in key}
    assert not any("gold" in field for row in items for field in row)
    assert Counter(row["gold_derived"] for row in key)["SUITABLE"] >= 2 * 4
    assert Counter(row["gold_derived"] for row in key)["NOT_SUITABLE"] >= 2 * 4


def test_prompt_forbids_holistic_outcomes_and_preserves_item_id():
    items, _ = build_reviewer_controls()
    messages = prompt_messages(items[0], "REVIEWER_A")
    assert items[0]["review_item_id"] in messages[1]["content"]
    assert "Do not judge overall helpfulness" in messages[0]["content"]
    assert "Do not output a composite label" in messages[0]["content"]


def test_atomic_validator_rejects_unknown_without_reason():
    judgment = {
        "axes": {
            axis: {
                "decision": "UNKNOWN",
                "visible_span_ids": [],
                "candidate_span_ids": [],
                "absence_reason_code": "NONE",
                "unknown_reason_code": "NONE",
            }
            for axis in SUITABILITY_AXES
        },
        "derived_suitability": "UNKNOWN",
    }
    errors = validate_atomic_judgment(
        judgment,
        allowed_visible_span_ids=["V001"],
        allowed_candidate_span_ids=["C001"],
    )
    assert len([error for error in errors if error.endswith("unknown_without_reason")]) == 4
