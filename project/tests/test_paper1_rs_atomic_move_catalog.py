import hashlib

import pytest

from metacom_pm.io import canonical_json
from metacom_pm.paper1.rs.strategy_bank import StrategySourceCard
from metacom_pm.paper1.rs_atomic_move.catalog import (
    build_atomic_move_retrieval_document,
    load_atomic_move_retrieval_documents,
)
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


def _session_results_row(source_card_id: str, unit: AcceptedAtomicMoveUnit) -> dict:
    return {
        "source_card_id": source_card_id,
        "source_dialogue_id": "esconv_0001",
        "source_turn_index": 3,
        "accepted_units": [unit.model_dump(mode="json")],
    }


def test_load_atomic_move_retrieval_documents_binds_units_to_their_source_card(tmp_path):
    source = _source()
    unit = _unit("rs_atomic_" + "1" * 24, "Ask what feels hardest.")
    results_path = tmp_path / "session_results.jsonl"
    results_path.write_text(
        canonical_json(_session_results_row(source.card_id, unit)) + "\n", encoding="utf-8"
    )

    documents = load_atomic_move_retrieval_documents(
        results_path, cards_by_id={source.card_id: source}
    )

    assert len(documents) == 1
    assert documents[0].atomic_card_id == unit.card_id
    assert documents[0].source_card_id == source.card_id
    assert documents[0].text.startswith(source.retrieval_text + "\n")


def test_load_atomic_move_retrieval_documents_skips_rows_with_no_accepted_units(tmp_path):
    source = _source()
    results_path = tmp_path / "session_results.jsonl"
    row = {
        "source_card_id": source.card_id,
        "source_dialogue_id": "esconv_0001",
        "source_turn_index": 3,
        "accepted_units": [],
    }
    results_path.write_text(canonical_json(row) + "\n", encoding="utf-8")

    documents = load_atomic_move_retrieval_documents(
        results_path, cards_by_id={source.card_id: source}
    )

    assert documents == ()


def test_load_atomic_move_retrieval_documents_fails_closed_on_unknown_source_card(tmp_path):
    source = _source()
    unit = _unit("rs_atomic_" + "1" * 24, "Ask what feels hardest.")
    results_path = tmp_path / "session_results.jsonl"
    results_path.write_text(
        canonical_json(_session_results_row(source.card_id, unit)) + "\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="not in the live catalog"):
        load_atomic_move_retrieval_documents(results_path, cards_by_id={})


def test_load_atomic_move_retrieval_documents_requires_unique_atomic_card_ids(tmp_path):
    source = _source()
    unit = _unit("rs_atomic_" + "1" * 24, "Ask what feels hardest.")
    results_path = tmp_path / "session_results.jsonl"
    row = _session_results_row(source.card_id, unit)
    results_path.write_text(
        canonical_json(row) + "\n" + canonical_json(row) + "\n", encoding="utf-8"
    )

    with pytest.raises(RuntimeError, match="not uniquely identified"):
        load_atomic_move_retrieval_documents(results_path, cards_by_id={source.card_id: source})
