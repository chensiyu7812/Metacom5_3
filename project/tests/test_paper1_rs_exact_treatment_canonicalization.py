import hashlib

from metacom_pm.paper1.rs_atomic_move.canonicalization import canonicalize_exact_treatments
from metacom_pm.paper1.rs_atomic_move.catalog import AtomicMoveRetrievalDocument
from metacom_pm.paper1.rs_atomic_move.contracts import (
    AcceptedAtomicMoveUnit,
    AtomicMoveFamily,
    SupportingSpan,
)


def _unit(card_id: str, dialogue: str, text: str, family=AtomicMoveFamily.QUESTION):
    return AcceptedAtomicMoveUnit(
        card_id=card_id,
        source_dialogue_ids=(dialogue,),
        source_turn_index=2,
        atomic_move_family=family,
        action_description="ask one open question",
        supporting_spans=(
            SupportingSpan(
                span_id="s",
                source_dialogue_id=dialogue,
                source_turn_index=2,
                exact_text="hello",
                start_char=0,
                end_char=5,
            ),
        ),
        rendered_card_text=text,
        rendered_card_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
        renderer_version="r",
        compiler_version="c",
        extractor_prompt_sha256="a" * 64,
        extractor_response_sha256="b" * 64,
        verifier_prompt_sha256="c" * 64,
        verifier_response_sha256="d" * 64,
    )


def _document(unit, source_card_id, retrieval_text):
    text = f"{retrieval_text}\n{unit.rendered_card_text}"
    return AtomicMoveRetrievalDocument(
        source_card_id=source_card_id,
        atomic_card_id=unit.card_id,
        source_dialogue_ids=unit.source_dialogue_ids,
        text=text,
        text_sha256=hashlib.sha256(text.encode()).hexdigest(),
        rendered_card_text=unit.rendered_card_text,
    )


def test_exact_identity_collapses_once_and_unions_all_provenance():
    text = "Support move: Ask one open question."
    a = _unit("rs_atomic_" + "1" * 24, "esconv_0001", text)
    b = _unit("rs_atomic_" + "2" * 24, "esconv_0002", text)
    docs = (
        _document(a, "rs_src_" + "2" * 24, "context b"),
        _document(b, "rs_src_" + "3" * 24, "context a"),
    )
    aliases = canonicalize_exact_treatments(docs, units_by_id={a.card_id: a, b.card_id: b})
    assert len(aliases) == 1
    assert aliases[0].atomic_card_ids == tuple(sorted((a.card_id, b.card_id)))
    assert aliases[0].source_dialogue_ids == ("esconv_0001", "esconv_0002")
    assert aliases[0].representative_atomic_card_id == a.card_id


def test_duplicate_occurrence_never_creates_an_extra_ranking_ticket():
    text = "Support move: Reflect the user's feeling."
    a = _unit("rs_atomic_" + "3" * 24, "esconv_0003", text)
    b = _unit("rs_atomic_" + "4" * 24, "esconv_0003", text)
    aliases = canonicalize_exact_treatments(
        (
            _document(a, "rs_src_" + "4" * 24, "same context"),
            _document(b, "rs_src_" + "4" * 24, "same context"),
        ),
        units_by_id={a.card_id: a, b.card_id: b},
    )
    assert len(aliases) == 1
    assert len({alias.representative_atomic_card_id for alias in aliases}) == 1


def test_near_duplicate_text_is_not_deleted_by_any_semantic_threshold():
    a = _unit("rs_atomic_" + "5" * 24, "esconv_0004", "Support move: Ask an open question.")
    b = _unit("rs_atomic_" + "6" * 24, "esconv_0005", "Support move: Ask one open-ended question.")
    aliases = canonicalize_exact_treatments(
        (
            _document(a, "rs_src_" + "5" * 24, "context"),
            _document(b, "rs_src_" + "6" * 24, "context"),
        ),
        units_by_id={a.card_id: a, b.card_id: b},
    )
    assert len(aliases) == 2
