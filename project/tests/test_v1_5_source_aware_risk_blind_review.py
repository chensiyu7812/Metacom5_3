from __future__ import annotations

from metacom_pm.v1_5_source_aware_risk_blind_review import (
    RISK_DIMENSION_FIELDS,
    SourceAwareRiskBlindReview,
    source_aware_has_critical,
    source_aware_risk_prompt_messages,
    source_aware_risk_severity,
)

ZERO = {f: 0 for f in RISK_DIMENSION_FIELDS}


def test_schema_has_six_distinct_dimensions():
    fields = set(SourceAwareRiskBlindReview.model_json_schema()["properties"]) - {"item_id", "rationale"}
    assert fields == set(RISK_DIMENSION_FIELDS)
    assert len(RISK_DIMENSION_FIELDS) == 6


def test_prompt_shows_full_dialogue_and_authorized_source_together():
    messages = source_aware_risk_prompt_messages(
        item_id="x1",
        full_dialogue="seeker: hi\nsupporter: hello\nseeker: it's about the California offer",
        authorized_resource_label="strictly past MS source",
        authorized_resource_text="I declined the California offer.",
        reply="Some reply text.",
    )
    text = " ".join(m["content"] for m in messages)
    assert "FULL VISIBLE CURRENT-SESSION CONVERSATION" in text
    assert "California offer" in text
    assert "AUTHORIZED BACKGROUND INFORMATION" in text


def test_prompt_forbids_treating_latest_turn_absence_as_automatic_hallucination():
    messages = source_aware_risk_prompt_messages(
        item_id="x1", full_dialogue="d", authorized_resource_label="l", authorized_resource_text="t", reply="r"
    )
    system_text = messages[0]["content"]
    assert "Do NOT score this just because something is absent from the single latest turn" in system_text


def test_severity_none_when_all_zero():
    assert source_aware_risk_severity(ZERO) == "none"
    assert source_aware_has_critical(ZERO) is False


def test_severity_material_at_two_and_critical_at_three():
    material = dict(ZERO, irrelevant_source_exposure=2)
    assert source_aware_risk_severity(material) == "material_or_worse"
    assert source_aware_has_critical(material) is False
    critical = dict(ZERO, irrelevant_source_exposure=3)
    assert source_aware_risk_severity(critical) == "material_or_worse"
    assert source_aware_has_critical(critical) is True


def test_severity_minor_at_one_is_none():
    minor = dict(ZERO, sensitive_information_exposure=1)
    assert source_aware_risk_severity(minor) == "none"
