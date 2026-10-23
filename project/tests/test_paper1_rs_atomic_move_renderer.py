from __future__ import annotations

import pytest

from metacom_pm.paper1.rs_atomic_move.contracts import AtomicMoveFamily, ProposedAtomicMoveUnit, ProposedSpanQuote
from metacom_pm.paper1.rs_atomic_move.renderer import (
    UnscrubbedActionDescriptionError,
    render_atomic_move,
)


def _proposal(action_description: str) -> ProposedAtomicMoveUnit:
    return ProposedAtomicMoveUnit(
        proposal_id="p1",
        atomic_move_family=AtomicMoveFamily.AFFIRMATION_AND_REASSURANCE,
        action_description=action_description,
        supporting_spans=(ProposedSpanQuote(span_id="s1", exact_text="I'm sorry that happened"),),
    )


def test_render_clean_action_description():
    proposal = _proposal(
        "validate the user's frustration and acknowledge the effort already made"
    )
    text = render_atomic_move(proposal)
    assert text == (
        "Strategy family [Affirmation And Reassurance]: "
        "validate the user's frustration and acknowledge the effort already made"
    )


def test_render_rejects_leaked_capitalized_name():
    proposal = _proposal("validate that talking to Jack was difficult")
    with pytest.raises(UnscrubbedActionDescriptionError):
        render_atomic_move(proposal)


def test_render_rejects_leaked_all_caps_acronym():
    proposal = _proposal("suggest talking to HR about the situation")
    with pytest.raises(UnscrubbedActionDescriptionError):
        render_atomic_move(proposal)


def test_render_rejects_leaked_kinship_term():
    proposal = _proposal("acknowledge how hard it was to confront her mother")
    with pytest.raises(UnscrubbedActionDescriptionError):
        render_atomic_move(proposal)


def test_render_rejects_leaked_number_or_date():
    proposal = _proposal("validate that 6 months of poor sleep is exhausting")
    with pytest.raises(UnscrubbedActionDescriptionError):
        render_atomic_move(proposal)


def test_render_does_not_catch_spelled_out_numbers_known_limitation():
    # The reused _TIME_OR_NUMBER_RE proxy only matches digit sequences and
    # named weekdays/months, not spelled-out number words. This is an
    # inherited, documented limitation of the diagnostic regex (see
    # rs/preoutcome_audit.py), not a claim of complete detection -- recorded
    # here so the gap is visible rather than silently assumed away.
    proposal = _proposal("validate that six months of poor sleep is exhausting")
    text = render_atomic_move(proposal)
    assert "six months" in text


def test_render_allows_sentence_initial_capitalization():
    # Sentence-initial capitals of ordinary words must not false-positive.
    proposal = _proposal("Validate the user's frustration before suggesting a next step")
    text = render_atomic_move(proposal)
    assert "Validate the user's frustration" in text
