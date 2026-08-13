from __future__ import annotations

import pytest

from metacom_pm.v1_5_ms_rs_interaction_blind_review import (
    MSRSInteractionBlindReview,
    decode_interaction_verdict,
    interaction_prompt_messages,
)


def test_verdict_unchanged_when_ms_rs_is_at_position_b():
    assert decode_interaction_verdict("STRENGTHENED", ms_rs_position="B") == "STRENGTHENED"
    assert decode_interaction_verdict("WEAKENED", ms_rs_position="B") == "WEAKENED"
    assert decode_interaction_verdict("PRESERVED", ms_rs_position="B") == "PRESERVED"
    assert decode_interaction_verdict("NONE_IN_EITHER", ms_rs_position="B") == "NONE_IN_EITHER"
    assert decode_interaction_verdict("UNCERTAIN", ms_rs_position="B") == "UNCERTAIN"


def test_verdict_swapped_when_ms_rs_is_at_position_a():
    assert decode_interaction_verdict("STRENGTHENED", ms_rs_position="A") == "WEAKENED"
    assert decode_interaction_verdict("WEAKENED", ms_rs_position="A") == "STRENGTHENED"
    assert decode_interaction_verdict("PRESERVED", ms_rs_position="A") == "PRESERVED"
    assert decode_interaction_verdict("NONE_IN_EITHER", ms_rs_position="A") == "NONE_IN_EITHER"
    assert decode_interaction_verdict("UNCERTAIN", ms_rs_position="A") == "UNCERTAIN"


def test_decode_rejects_unknown_inputs():
    with pytest.raises(ValueError):
        decode_interaction_verdict("BOGUS", ms_rs_position="B")
    with pytest.raises(ValueError):
        decode_interaction_verdict("PRESERVED", ms_rs_position="C")


def test_prompt_never_names_the_arms():
    messages = interaction_prompt_messages(
        pair_id="p1",
        current_context="hi",
        authorized_resource_text="fact",
        reply_a="reply a text",
        reply_b="reply b text",
    )
    text = " ".join(m["content"] for m in messages)
    assert "MS+RS" not in text
    assert "MS+R0" not in text
    assert "treatment arm" not in text.lower()


def test_schema_field_names():
    assert set(MSRSInteractionBlindReview.model_json_schema()["properties"]) == {
        "pair_id",
        "verdict",
        "a_evidence_quote",
        "b_evidence_quote",
        "rationale",
    }
