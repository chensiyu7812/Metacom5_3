from __future__ import annotations

from metacom_pm.paper1.rs_atomic_move.contracts import (
    AtomicMoveFamily,
    ProposedAtomicMoveUnit,
    ProposedSpanQuote,
    VerifierRejectionReason,
)
from metacom_pm.paper1.rs_atomic_move.grounding import (
    check_action_description_not_leaking,
    locate_spans,
    run_deterministic_grounding,
)

SOURCE_TURN_WITH_NAME = "I told Jack about it and he said I should just quit."
SOURCE_TURN_CLEAN = "I felt really frustrated and overwhelmed by everything."
SEEKER_PRECEDING_TURN = "Maybe I should quit."

TARGET_DIALOGUE = "esconv_0001"
TARGET_TURN = 3


def _quote(text: str, span_id: str = "s1") -> ProposedSpanQuote:
    return ProposedSpanQuote(span_id=span_id, exact_text=text)


def _proposal(**overrides) -> ProposedAtomicMoveUnit:
    fields = dict(
        proposal_id="p1",
        atomic_move_family=AtomicMoveFamily.SELF_DISCLOSURE,
        action_description="the user discussed a difficult situation with someone else",
        supporting_spans=(_quote("told Jack about it"),),
    )
    fields.update(overrides)
    return ProposedAtomicMoveUnit(**fields)


def test_locate_spans_finds_unique_quote_in_target_turn():
    proposal = _proposal(supporting_spans=(_quote("Jack about it"),))
    result = locate_spans(
        proposal,
        target_dialogue_id=TARGET_DIALOGUE,
        target_turn_index=TARGET_TURN,
        target_turn_text=SOURCE_TURN_WITH_NAME,
    )
    assert result.passed
    assert len(result.located_spans) == 1
    located = result.located_spans[0]
    assert located.source_dialogue_id == TARGET_DIALOGUE
    assert located.source_turn_index == TARGET_TURN
    assert SOURCE_TURN_WITH_NAME[located.start_char : located.end_char] == "Jack about it"


def test_locate_spans_fails_closed_when_quote_absent():
    proposal = _proposal(supporting_spans=(_quote("this text is not in the turn"),))
    result = locate_spans(
        proposal,
        target_dialogue_id=TARGET_DIALOGUE,
        target_turn_index=TARGET_TURN,
        target_turn_text=SOURCE_TURN_WITH_NAME,
    )
    assert not result.passed
    assert result.reasons == (VerifierRejectionReason.AMBIGUOUS_SPAN,)


def test_locate_spans_fails_closed_when_quote_is_ambiguous():
    # "I" appears more than once in this turn -- must not silently pick one.
    ambiguous_turn = "I said I would try. I meant it."
    proposal = _proposal(supporting_spans=(_quote("I"),))
    result = locate_spans(
        proposal,
        target_dialogue_id=TARGET_DIALOGUE,
        target_turn_index=TARGET_TURN,
        target_turn_text=ambiguous_turn,
    )
    assert not result.passed
    assert any("ambiguous" in d for d in result.detail)


def test_locate_spans_never_finds_a_quote_that_only_exists_in_the_seeker_turn():
    # P0-2 regression, now structural: only target_turn_text is ever
    # searched, so a quote that exists solely in a preceding (seeker) turn
    # cannot be located at all, regardless of what Qwen claims about it --
    # there is no location field left for Qwen to lie in.
    proposal = _proposal(
        atomic_move_family=AtomicMoveFamily.PROVIDING_SUGGESTIONS,
        action_description="suggest quitting",
        supporting_spans=(_quote(SEEKER_PRECEDING_TURN),),
    )
    result = locate_spans(
        proposal,
        target_dialogue_id=TARGET_DIALOGUE,
        target_turn_index=TARGET_TURN,
        target_turn_text=SOURCE_TURN_CLEAN,  # the target turn; seeker text is elsewhere and never searched
    )
    assert not result.passed


def test_action_description_leak_check_rejects_capitalized_name():
    proposal = _proposal(action_description="validate that talking to Jack was difficult")
    result = check_action_description_not_leaking(proposal)
    assert not result.passed
    assert result.reasons == (VerifierRejectionReason.LEAKED_SOURCE_SPECIFIC_CONTENT,)


def test_action_description_leak_check_rejects_all_caps_acronym():
    proposal = _proposal(action_description="suggest talking to HR about the situation")
    result = check_action_description_not_leaking(proposal)
    assert not result.passed


def test_action_description_leak_check_passes_for_generic_text():
    proposal = _proposal(action_description="validate the user's frustration")
    result = check_action_description_not_leaking(proposal)
    assert result.passed


def test_action_description_leak_check_does_not_scan_supporting_spans():
    # Only action_description is ever rendered; supporting_spans are
    # grounding evidence and legitimately quote the specific source text
    # (e.g. "Jack") without that being a leak, since it is never shown
    # downstream.
    proposal = _proposal(
        action_description="validate the user's frustration",
        supporting_spans=(_quote("told Jack about it"),),
    )
    result = check_action_description_not_leaking(proposal)
    assert result.passed


def test_run_deterministic_grounding_combines_location_and_leak_checks():
    proposal = _proposal(
        action_description="validate that discussing this with Jack was hard",  # leaks "Jack"
        supporting_spans=(_quote("told Jack about it"),),
    )
    result = run_deterministic_grounding(
        proposal,
        target_dialogue_id=TARGET_DIALOGUE,
        target_turn_index=TARGET_TURN,
        target_turn_text=SOURCE_TURN_WITH_NAME,
    )
    assert not result.passed
    assert VerifierRejectionReason.LEAKED_SOURCE_SPECIFIC_CONTENT in result.reasons
    assert result.located_spans == ()  # not populated when grounding fails


def test_run_deterministic_grounding_rejects_seeker_grounded_proposal():
    proposal = _proposal(
        atomic_move_family=AtomicMoveFamily.PROVIDING_SUGGESTIONS,
        action_description="suggest quitting",
        supporting_spans=(_quote(SEEKER_PRECEDING_TURN),),
    )
    result = run_deterministic_grounding(
        proposal,
        target_dialogue_id=TARGET_DIALOGUE,
        target_turn_index=TARGET_TURN,
        target_turn_text=SOURCE_TURN_CLEAN,
    )
    assert not result.passed


def test_run_deterministic_grounding_passes_clean_grounded_proposal_and_returns_located_spans():
    proposal = _proposal(
        atomic_move_family=AtomicMoveFamily.REFLECTION_OF_FEELINGS,
        action_description="reflect the user's frustration",
        supporting_spans=(_quote("frustrated and overwhelmed"),),
    )
    result = run_deterministic_grounding(
        proposal,
        target_dialogue_id=TARGET_DIALOGUE,
        target_turn_index=TARGET_TURN,
        target_turn_text=SOURCE_TURN_CLEAN,
    )
    assert result.passed
    assert len(result.located_spans) == 1
    assert result.located_spans[0].exact_text == "frustrated and overwhelmed"
