import hashlib

import pytest

from metacom_pm.paper1.rs.strategy_bank import StrategySourceCard
from metacom_pm.paper1.rs_atomic_move.catalog import build_atomic_move_retrieval_document
from metacom_pm.paper1.rs_atomic_move.contracts import (
    AcceptedAtomicMoveUnit,
    AtomicMoveFamily,
    SupportingSpan,
)

HEX64 = "a" * 64


def _source() -> StrategySourceCard:
    return StrategySourceCard(
        card_id="rs_src_" + "0" * 24,
        source_dialogue_id="esconv_0001",
        source_dialogue_ids=("esconv_0001", "esconv_0007"),
        source_turn_index=3,
        strategy_label="Question",
        retrieval_text="seeker: I am overwhelmed.",
        guidance_text="Use the strategy.",
        example_response="What feels hardest right now?",
        retrieval_text_sha256=HEX64,
        example_response_sha256=HEX64,
    )


def _unit(card_id: str, rendered: str) -> AcceptedAtomicMoveUnit:
    return AcceptedAtomicMoveUnit(
        card_id=card_id,
        source_dialogue_ids=("esconv_0001", "esconv_0007"),
        source_turn_index=3,
        atomic_move_family=AtomicMoveFamily.QUESTION,
        action_description="ask what feels hardest",
        supporting_spans=(
            SupportingSpan(
                span_id="s1",
                source_dialogue_id="esconv_0001",
                source_turn_index=3,
                start_char=0,
                end_char=5,
                exact_text="What ",
            ),
        ),
        rendered_card_text=rendered,
        rendered_card_text_sha256=hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
        renderer_version="renderer-v1",
        compiler_version="compiler-v1",
        extractor_prompt_sha256=HEX64,
        extractor_response_sha256=HEX64,
        verifier_prompt_sha256=HEX64,
        verifier_response_sha256=HEX64,
    )


def test_each_atomic_unit_gets_a_distinct_hash_bound_retrieval_document():
    source = _source()
    left = build_atomic_move_retrieval_document(
        source, _unit("rs_atomic_" + "1" * 24, "Ask what feels hardest.")
    )
    right = build_atomic_move_retrieval_document(
        source, _unit("rs_atomic_" + "2" * 24, "Offer a brief grounding exercise.")
    )
    assert left.text.startswith(source.retrieval_text + "\n")
    assert left.text != right.text
    assert left.text_sha256 != right.text_sha256


def test_retrieval_document_fails_closed_on_lineage_mismatch():
    source = _source()
    unit = _unit("rs_atomic_" + "1" * 24, "Ask what feels hardest.").model_copy(
        update={"source_dialogue_ids": ("esconv_0001",)}
    )
    with pytest.raises(ValueError, match="lineage mismatch"):
        build_atomic_move_retrieval_document(source, unit)
