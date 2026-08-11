from __future__ import annotations

import json
from pathlib import Path

import pytest

from metacom_pm.v1_5_ms_source_annotated_suitability_review import (
    MSSourceAnnotatedSuitabilityReview,
    prompt_messages,
    validate_review,
)


ROOT = Path(__file__).resolve().parents[1]
CONTROLS = ROOT / "outputs/pm_v1_5_paper1_ms_supervision_repair_packet_20260812/qualification_controls_blind.jsonl"


def _item():
    return json.loads(CONTROLS.read_text(encoding="utf-8").splitlines()[0])


def _positive(item):
    return MSSourceAnnotatedSuitabilityReview(
        repair_item_id=item["repair_item_id"],
        current_goal_span_ids=[item["visible_current_spans"][0]["span_id"]],
        current_support_goal="Understand the current problem without shifting focus.",
        past_source_span_ids=[item["strictly_past_candidate_spans"][0]["span_id"]],
        candidate_increment="The past source adds one distinct trigger.",
        entity_link="RESOLVED",
        allowed_response_change_type="ONE_QUESTION",
        allowed_response_change="Ask one tentative candidate-specific question.",
        forbidden_focus_shift="Do not turn the old event into a current certainty.",
        nonuse_condition="Do not use if the current event is different.",
        final_suitability="SUITABLE",
        decision_reason_code="PAST_ONLY_QUESTION_INCREMENT",
    )


def test_prompt_hides_gold_and_preserves_nonexclusive_scope() -> None:
    messages = prompt_messages(_item(), "TEST_REVIEWER")
    text = json.dumps(messages)
    assert "expected_final_suitability" not in text
    assert "teacher_decision" not in text
    assert "never choose a single winner" in messages[0]["content"]


def test_positive_review_validates_exact_span_ids() -> None:
    item = _item()
    row = validate_review(_positive(item), item)
    assert row["final_suitability"] == "SUITABLE"


def test_wrong_span_id_fails_closed() -> None:
    item = _item()
    parsed = _positive(item).model_copy(update={"current_goal_span_ids": ["V999"]})
    with pytest.raises(ValueError, match="current_goal_span_id_not_visible"):
        validate_review(parsed, item)


def test_not_suitable_requires_explicit_none_change() -> None:
    item = _item()
    parsed = _positive(item).model_copy(
        update={
            "final_suitability": "NOT_SUITABLE",
            "decision_reason_code": "LOW_INFORMATION_OR_PHATIC",
            "allowed_response_change_type": "NONE",
            "allowed_response_change": "The response could mention it anyway.",
        }
    )
    with pytest.raises(ValueError, match="explicit_no_allowed_change"):
        validate_review(parsed, item)


def test_abstain_requires_explicit_unresolved_change() -> None:
    item = _item()
    parsed = _positive(item).model_copy(
        update={
            "final_suitability": "SEMANTIC_ABSTAIN",
            "decision_reason_code": "ENTITY_OR_EVENT_UNRESOLVED",
            "entity_link": "UNRESOLVED",
            "allowed_response_change_type": "UNRESOLVED",
            "allowed_response_change": "UNRESOLVED: the current entity is not identified.",
            "candidate_increment": "UNRESOLVED: the prior event could be different.",
        }
    )
    assert validate_review(parsed, item)["final_suitability"] == "SEMANTIC_ABSTAIN"
