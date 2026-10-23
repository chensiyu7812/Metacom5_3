from __future__ import annotations

import hashlib
import math

import pytest

from metacom_pm.paper1.rs.strategy_bank import StrategySourceCard
from metacom_pm.paper1.rs.zero_outcome_census import RSDecisionState
from metacom_pm.paper1.rs_atomic_move.catalog import (
    AtomicMoveRetrievalDocument,
    build_atomic_move_retrieval_document,
)
from metacom_pm.paper1.rs_atomic_move.contracts import (
    AcceptedAtomicMoveUnit,
    AtomicMoveFamily,
    SupportingSpan,
)
from metacom_pm.paper1.rs_atomic_move.zero_outcome_census import (
    BgeAuditIndex,
    build_rs_atomic_move_zero_outcome_census,
)

HEX64 = "a" * 64
DIM = 1024  # BgeAuditIndex's real default -- these tests exercise the real production dimension


def _pad(vector: tuple[float, ...]) -> tuple[float, ...]:
    """Zero-extend a short unit vector to DIM dims. Appending zeros changes
    neither its L2 norm nor its dot product with another zero-padded
    vector, so the small, easy-to-reason-about 3-component similarity math
    below still holds exactly at the real 1024-dim shape BgeAuditIndex
    validates against."""

    return vector + (0.0,) * (DIM - len(vector))


def _card(card_id_suffix: str, dialogue_id: str, dialogue_ids: tuple[str, ...]) -> StrategySourceCard:
    return StrategySourceCard(
        card_id=f"rs_src_{card_id_suffix}",
        source_dialogue_id=dialogue_id,
        source_dialogue_ids=dialogue_ids,
        source_turn_index=3,
        strategy_label="Question",
        retrieval_text="seeker: I am overwhelmed.",
        guidance_text="Use the strategy.",
        example_response="What feels hardest right now?",
        retrieval_text_sha256=HEX64,
        example_response_sha256=HEX64,
    )


def _unit(card_id_suffix: str, dialogue_ids: tuple[str, ...], rendered: str) -> AcceptedAtomicMoveUnit:
    return AcceptedAtomicMoveUnit(
        card_id=f"rs_atomic_{card_id_suffix}",
        source_dialogue_ids=dialogue_ids,
        source_turn_index=3,
        atomic_move_family=AtomicMoveFamily.QUESTION,
        action_description="ask what feels hardest",
        supporting_spans=(
            SupportingSpan(
                span_id="s1",
                source_dialogue_id=dialogue_ids[0],
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


def _document(card_suffix: str, dialogue_ids: tuple[str, ...], rendered: str) -> AtomicMoveRetrievalDocument:
    card = _card(card_suffix, dialogue_ids[0], dialogue_ids)
    unit = _unit(card_suffix, dialogue_ids, rendered)
    return build_atomic_move_retrieval_document(card, unit)


def _state(state_id_suffix: str, dialogue_id: str) -> RSDecisionState:
    return RSDecisionState(
        state_id=f"rs_state_{state_id_suffix}",
        source_dialogue_id=dialogue_id,
        source_split="train",
        decision_turn_index=3,
        visible_dialogue_text="seeker: I am overwhelmed.",
        query_text="seeker: I am overwhelmed.",
        current_user_text="I am overwhelmed.",
        visible_turn_count=1,
        query_turn_count=1,
        current_user_turn_count=1,
    )


# All vectors below are exact unit vectors in R^3 (norm == 1.0), chosen so
# their dot product with QUERY=(1,0,0) is an exact, predictable cosine
# similarity -- BgeAuditIndex now mechanically validates normalization, so
# these can no longer be arbitrary toy tuples the way a pre-hardening test
# might have used.
QUERY = _pad((1.0, 0.0, 0.0))
SIM_09 = math.sqrt(1 - 0.9**2)
SIM_05 = math.sqrt(1 - 0.5**2)


def _docs_and_vectors():
    documents = (
        _document("1" * 24, ("esconv_0001",), "Ask what feels hardest."),
        _document("2" * 24, ("esconv_0002",), "Offer a brief grounding exercise."),
        _document("3" * 24, ("esconv_0002", "esconv_0003"), "Reflect the feeling back."),
        _document("4" * 24, ("esconv_0004",), "Suggest a short walk."),
    )
    vectors = {
        "rs_atomic_" + "1" * 24: _pad((1.0, 0.0, 0.0)),  # sim(QUERY) == 1.0
        "rs_atomic_" + "2" * 24: _pad((0.9, SIM_09, 0.0)),  # sim(QUERY) == 0.9
        "rs_atomic_" + "3" * 24: _pad((0.0, 1.0, 0.0)),  # sim(QUERY) == 0.0
        "rs_atomic_" + "4" * 24: _pad((0.5, SIM_05, 0.0)),  # sim(QUERY) == 0.5
    }
    return documents, vectors


def _index(documents, vectors) -> BgeAuditIndex:
    return BgeAuditIndex(documents, document_vectors=vectors)


def test_bge_audit_index_excludes_by_full_source_dialogue_ids_lineage():
    documents, vectors = _docs_and_vectors()
    index = _index(documents, vectors)
    # document 3 lists esconv_0003 as a secondary lineage dialogue even
    # though its primary source_card_id's dialogue is esconv_0002 -- excluding
    # esconv_0003 must still exclude document 3.
    candidate_count, _nonzero, selected = index.rank(
        query_vector=QUERY, excluded_dialogue_id="esconv_0003", top_k=3
    )
    assert candidate_count == 3
    selected_ids = {doc.atomic_card_id for doc, _sim, _words in selected}
    assert "rs_atomic_" + "3" * 24 not in selected_ids


def test_bge_audit_index_ranks_by_descending_cosine_similarity():
    documents, vectors = _docs_and_vectors()
    index = _index(documents, vectors)
    _candidate_count, _nonzero, selected = index.rank(
        query_vector=QUERY, excluded_dialogue_id="esconv_9999", top_k=4
    )
    ids_in_order = [doc.atomic_card_id for doc, _sim, _words in selected]
    assert ids_in_order == [
        "rs_atomic_" + "1" * 24,  # sim 1.0
        "rs_atomic_" + "2" * 24,  # sim 0.9
        "rs_atomic_" + "4" * 24,  # sim 0.5
        "rs_atomic_" + "3" * 24,  # sim 0.0
    ]
    similarities = [sim for _doc, sim, _words in selected]
    assert similarities == sorted(similarities, reverse=True)


def test_bge_audit_index_nonzero_count_respects_exclusion():
    documents, vectors = _docs_and_vectors()
    index = _index(documents, vectors)
    _candidate_count, nonzero_count, _selected = index.rank(
        query_vector=QUERY, excluded_dialogue_id="esconv_0001", top_k=3
    )
    # documents 2 and 4 have positive similarity with QUERY; document 3 has
    # zero. document 1 (also positive) is excluded by dialogue.
    assert nonzero_count == 2


def test_bge_audit_index_rejects_duplicate_ids():
    documents, vectors = _docs_and_vectors()
    with pytest.raises(ValueError, match="unique atomic_card_ids"):
        _index(documents + (documents[0],), vectors)


def test_bge_audit_index_rejects_missing_vectors():
    documents, vectors = _docs_and_vectors()
    incomplete = dict(vectors)
    del incomplete["rs_atomic_" + "1" * 24]
    with pytest.raises(ValueError, match="missing document vectors"):
        _index(documents, incomplete)


def test_bge_audit_index_rejects_empty_documents():
    with pytest.raises(ValueError, match="requires documents"):
        BgeAuditIndex((), document_vectors={}, expected_dimension=DIM)


def test_rank_rejects_top_k_larger_than_eligible_candidates():
    documents, vectors = _docs_and_vectors()
    index = _index(documents, vectors)
    with pytest.raises(ValueError, match="fewer fold-exclusive documents"):
        index.rank(query_vector=QUERY, excluded_dialogue_id="esconv_0001", top_k=4)


# ---- mechanical vector validation (defense in depth) ----


def test_bge_audit_index_rejects_a_wrong_dimension_document_vector():
    documents, vectors = _docs_and_vectors()
    bad = dict(vectors)
    bad["rs_atomic_" + "1" * 24] = (1.0, 0.0)
    with pytest.raises(RuntimeError, match="dimensions, expected"):
        _index(documents, bad)


def test_bge_audit_index_rejects_an_unnormalized_document_vector():
    documents, vectors = _docs_and_vectors()
    bad = dict(vectors)
    bad["rs_atomic_" + "1" * 24] = _pad((5.0, 0.0, 0.0))
    with pytest.raises(RuntimeError, match="L2 norm"):
        _index(documents, bad)


def test_bge_audit_index_rejects_a_non_finite_document_vector():
    documents, vectors = _docs_and_vectors()
    bad = dict(vectors)
    bad["rs_atomic_" + "1" * 24] = _pad((float("nan"), 0.0, 0.0))
    with pytest.raises(RuntimeError, match="non-finite"):
        _index(documents, bad)


def test_rank_rejects_an_unnormalized_query_vector():
    documents, vectors = _docs_and_vectors()
    index = _index(documents, vectors)
    with pytest.raises(RuntimeError, match="L2 norm"):
        index.rank(query_vector=_pad((2.0, 0.0, 0.0)), excluded_dialogue_id="esconv_9999", top_k=1)


# ---- build_rs_atomic_move_zero_outcome_census ----


def test_build_census_requires_a_query_vector_for_every_state():
    documents, vectors = _docs_and_vectors()
    states = (_state("a" * 24, "esconv_0005"),)
    with pytest.raises(ValueError, match="missing query vectors"):
        build_rs_atomic_move_zero_outcome_census(
            states=states,
            documents=documents,
            document_vectors=vectors,
            query_vectors={},
            diagnostic_top_k=2,
        )


def test_build_census_produces_one_row_per_state_with_real_similarities():
    documents, vectors = _docs_and_vectors()
    states = (_state("a" * 24, "esconv_0005"),)
    rows = build_rs_atomic_move_zero_outcome_census(
        states=states,
        documents=documents,
        document_vectors=vectors,
        query_vectors={"rs_state_" + "a" * 24: QUERY},
        diagnostic_top_k=2,
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.state_id == "rs_state_" + "a" * 24
    assert row.candidate_count_after_leave_dialogue_out == 4  # no dialogue overlap with esconv_0005
    assert len(row.diagnostic_candidate_ids) == 2
    assert row.diagnostic_candidate_ids[0] == "rs_atomic_" + "1" * 24
    assert row.diagnostic_bge_cosine_similarities[0] == pytest.approx(1.0)
    assert row.diagnostic_document_word_counts[0] > 0


def test_build_census_injected_token_counts_default_to_whitespace_split():
    documents, vectors = _docs_and_vectors()
    states = (_state("a" * 24, "esconv_0005"),)
    rows = build_rs_atomic_move_zero_outcome_census(
        states=states,
        documents=documents,
        document_vectors=vectors,
        query_vectors={"rs_state_" + "a" * 24: QUERY},
        diagnostic_top_k=1,
    )
    row = rows[0]
    # top candidate is document 1, rendered_card_text="Ask what feels hardest."
    assert row.diagnostic_injected_token_counts == (len("Ask what feels hardest.".split()),)


def test_build_census_injected_token_counts_use_the_given_token_counter():
    documents, vectors = _docs_and_vectors()
    states = (_state("a" * 24, "esconv_0005"),)
    rows = build_rs_atomic_move_zero_outcome_census(
        states=states,
        documents=documents,
        document_vectors=vectors,
        query_vectors={"rs_state_" + "a" * 24: QUERY},
        diagnostic_top_k=1,
        token_counter=lambda text: 999,
    )
    assert rows[0].diagnostic_injected_token_counts == (999,)
