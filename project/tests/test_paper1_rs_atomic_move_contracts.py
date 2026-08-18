from __future__ import annotations

import pytest
from pydantic import ValidationError

from metacom_pm.paper1.rs_atomic_move.contracts import (
    AcceptedAtomicMoveUnit,
    AtomicMoveFamily,
    ExtractorProposalBatch,
    ProposedAtomicMoveUnit,
    ProposedSpanQuote,
    SourceCardCompileInput,
    SourceTurnInput,
    SupportingSpan,
    VerifierDecidableRejectionReason,
    VerifierDecision,
    VerifierDecisionBatch,
    VerifierRejectionReason,
    fold_exclusion_dialogue_ids,
)

HEX64 = "a" * 64


def _quote(text: str = "frustrated and overwhelmed", span_id: str = "s1") -> ProposedSpanQuote:
    return ProposedSpanQuote(span_id=span_id, exact_text=text)


def _span(dialogue_id: str = "esconv_0001", turn: int = 3, start: int = 0, end: int = 10) -> SupportingSpan:
    return SupportingSpan(
        span_id="s1",
        source_dialogue_id=dialogue_id,
        source_turn_index=turn,
        exact_text="frustrated and overwhelmed",
        start_char=start,
        end_char=end,
    )


def _proposal(**overrides) -> ProposedAtomicMoveUnit:
    fields = dict(
        proposal_id="p1",
        atomic_move_family=AtomicMoveFamily.AFFIRMATION_AND_REASSURANCE,
        action_description="validate the user's frustration",
        supporting_spans=(_quote(),),
    )
    fields.update(overrides)
    return ProposedAtomicMoveUnit(**fields)


def _accepted(**overrides) -> AcceptedAtomicMoveUnit:
    fields = dict(
        card_id="rs_atomic_" + "0" * 24,
        source_dialogue_ids=("esconv_0001",),
        source_turn_index=3,
        atomic_move_family=AtomicMoveFamily.AFFIRMATION_AND_REASSURANCE,
        action_description="validate the user's frustration",
        supporting_spans=(_span(),),
        rendered_card_text="Affirmation and Reassurance: validate the user's frustration",
        rendered_card_text_sha256=HEX64,
        renderer_version="paper1-rs-atomic-move-renderer-v1",
        compiler_version="paper1-rs-atomic-move-compiler-v1",
        extractor_prompt_sha256=HEX64,
        extractor_response_sha256=HEX64,
        verifier_prompt_sha256=HEX64,
        verifier_response_sha256=HEX64,
    )
    fields.update(overrides)
    return AcceptedAtomicMoveUnit(**fields)


def _turn(dialogue_id="esconv_0001", turn_index=3, role="supporter", text="You are doing great.") -> SourceTurnInput:
    return SourceTurnInput(source_dialogue_id=dialogue_id, turn_index=turn_index, role=role, text=text)


def test_valid_proposal_and_accepted_unit_round_trip():
    proposal = _proposal()
    assert proposal.atomic_move_family is AtomicMoveFamily.AFFIRMATION_AND_REASSURANCE
    accepted = _accepted()
    assert accepted.card_id.startswith("rs_atomic_")


def test_span_end_must_exceed_start():
    with pytest.raises(ValidationError):
        _span(start=10, end=10)
    with pytest.raises(ValidationError):
        _span(start=10, end=5)


def test_proposed_span_quote_has_no_location_fields():
    # The whole point of the redesign: Qwen cannot claim a location for a
    # quote at all, so it cannot claim a location in some other (e.g.
    # seeker) turn either.
    with pytest.raises(ValidationError):
        ProposedSpanQuote(
            span_id="s1",
            exact_text="x",
            source_dialogue_id="esconv_0001",  # type: ignore[call-arg]
            source_turn_index=3,  # type: ignore[call-arg]
        )


def test_proposal_has_no_source_turn_index_or_source_dialogue_ids_field():
    with pytest.raises(ValidationError):
        ProposedAtomicMoveUnit(
            proposal_id="p1",
            source_turn_index=999,  # type: ignore[call-arg]
            atomic_move_family=AtomicMoveFamily.INFORMATION,
            action_description="x",
            supporting_spans=(_quote(),),
        )


def test_proposal_has_no_delexicalized_slots_field():
    with pytest.raises(ValidationError):
        ProposedAtomicMoveUnit(
            proposal_id="p1",
            atomic_move_family=AtomicMoveFamily.INFORMATION,
            action_description="x",
            supporting_spans=(_quote(),),
            delexicalized_slots=(),  # type: ignore[call-arg]
        )


def test_proposal_rejects_duplicate_span_ids():
    with pytest.raises(ValidationError, match="duplicate span_id"):
        _proposal(supporting_spans=(_quote("a", span_id="s1"), _quote("b", span_id="s1")))


def test_proposal_allows_multiple_distinct_spans():
    proposal = _proposal(supporting_spans=(_quote("a", span_id="s1"), _quote("b", span_id="s2")))
    assert len(proposal.supporting_spans) == 2


def test_extractor_batch_rejects_duplicate_proposal_ids():
    with pytest.raises(ValidationError, match="duplicate proposal_id"):
        ExtractorProposalBatch(proposals=(_proposal(proposal_id="p1"), _proposal(proposal_id="p1")))


def test_verifier_decision_schema_has_exactly_three_decidable_reasons():
    # Architectural fix, 2026-08-18: the verifier's own schema must make
    # leaked_source_specific_content and ambiguous_span structurally
    # impossible to emit, not merely discouraged in the prompt -- both are
    # decided by the deterministic grounding layer before the verifier ever
    # runs (see grounding.py / VerifierDecidableRejectionReason docstring).
    assert set(VerifierDecidableRejectionReason) == {
        VerifierDecidableRejectionReason.MULTIPLE_DISTINCT_ACTIONS,
        VerifierDecidableRejectionReason.UNGROUNDED_ADDITION,
        VerifierDecidableRejectionReason.WRONG_FAMILY,
    }
    schema = VerifierDecisionBatch.model_json_schema()
    enum_values = schema["$defs"]["VerifierDecidableRejectionReason"]["enum"]
    assert "leaked_source_specific_content" not in enum_values
    assert "ambiguous_span" not in enum_values
    assert set(enum_values) == {"multiple_distinct_actions", "ungrounded_addition", "wrong_family"}


def test_verifier_decision_rejects_leaked_source_specific_content_as_a_value():
    with pytest.raises(ValidationError):
        VerifierDecision(proposal_id="p1", accept=False, rejection_reason="leaked_source_specific_content")


def test_verifier_decision_rejects_ambiguous_span_as_a_value():
    with pytest.raises(ValidationError):
        VerifierDecision(proposal_id="p1", accept=False, rejection_reason="ambiguous_span")


def test_verifier_batch_rejects_duplicate_decision_ids():
    with pytest.raises(ValidationError, match="duplicate proposal_id decided twice"):
        VerifierDecisionBatch(
            decisions=(
                VerifierDecision(proposal_id="p1", accept=True),
                VerifierDecision(
                    proposal_id="p1", accept=False,
                    rejection_reason=VerifierRejectionReason.WRONG_FAMILY,
                ),
            )
        )


def test_extra_fields_are_rejected_strict_contract():
    with pytest.raises(ValidationError):
        ProposedAtomicMoveUnit(
            proposal_id="p1",
            atomic_move_family=AtomicMoveFamily.INFORMATION,
            action_description="x",
            supporting_spans=(_quote(),),
            worth_opening=True,  # type: ignore[call-arg]
        )


def test_fold_exclusion_dialogue_ids_covers_all_aggregated_sources():
    # AcceptedAtomicMoveUnit.source_dialogue_ids is assigned locally by the
    # runtime (e.g. from a dedup-equivalence-group manifest), never by Qwen
    # -- this test exercises that locally-assigned field directly.
    accepted = _accepted(source_dialogue_ids=("esconv_0001", "esconv_0007"))
    ids = fold_exclusion_dialogue_ids(accepted)
    assert ids == frozenset({"esconv_0001", "esconv_0007"})
    assert "esconv_0007" in ids


def test_atomic_move_family_enum_is_closed_to_the_frozen_esconv_taxonomy():
    values = {member.value for member in AtomicMoveFamily}
    assert values == {
        "question",
        "restatement_or_paraphrasing",
        "reflection_of_feelings",
        "self_disclosure",
        "affirmation_and_reassurance",
        "providing_suggestions",
        "information",
        "others",
    }


# ---- SourceCardCompileInput cross-field consistency ----

def _compile_input(**overrides) -> SourceCardCompileInput:
    fields = dict(
        source_card_id="rs_src_" + "0" * 24,
        target_dialogue_id="esconv_0001",
        target_turn_index=3,
        preceding_turns=(_turn(turn_index=1, role="seeker", text="I feel awful."),),
        target_turn=_turn(turn_index=3, role="supporter"),
    )
    fields.update(overrides)
    return SourceCardCompileInput(**fields)


def test_compile_input_valid_construction():
    source = _compile_input()
    assert source.target_turn.role == "supporter"


def test_compile_input_rejects_target_turn_dialogue_mismatch():
    with pytest.raises(ValidationError, match="does not match the declared target"):
        _compile_input(target_turn=_turn(dialogue_id="esconv_9999", turn_index=3, role="supporter"))


def test_compile_input_rejects_target_turn_index_mismatch():
    with pytest.raises(ValidationError, match="does not match the declared target"):
        _compile_input(target_turn=_turn(turn_index=77, role="supporter"))


def test_compile_input_rejects_non_supporter_target_role():
    with pytest.raises(ValidationError, match="must be a supporter turn"):
        _compile_input(target_turn=_turn(turn_index=3, role="seeker"))


def test_compile_input_rejects_preceding_turn_from_a_different_dialogue():
    with pytest.raises(ValidationError, match="same dialogue"):
        _compile_input(
            preceding_turns=(_turn(dialogue_id="esconv_9999", turn_index=1, role="seeker"),)
        )


def test_compile_input_rejects_preceding_turn_not_strictly_earlier():
    with pytest.raises(ValidationError, match="strictly earlier"):
        _compile_input(
            preceding_turns=(_turn(turn_index=3, role="seeker"),)  # same index as target
        )
    with pytest.raises(ValidationError, match="strictly earlier"):
        _compile_input(
            preceding_turns=(_turn(turn_index=5, role="seeker"),)  # after target
        )


def test_compile_input_rejects_duplicate_preceding_turn_indices():
    with pytest.raises(ValidationError, match="unique"):
        _compile_input(
            preceding_turns=(
                _turn(turn_index=1, role="seeker", text="a"),
                _turn(turn_index=1, role="supporter", text="b"),
            )
        )


def test_compile_input_rejects_out_of_order_preceding_turns():
    with pytest.raises(ValidationError, match="ascending"):
        _compile_input(
            preceding_turns=(
                _turn(turn_index=2, role="seeker", text="a"),
                _turn(turn_index=1, role="supporter", text="b"),
            )
        )
