import hashlib

import pytest

from metacom_pm.paper1.rs_atomic_move.qualification import (
    AssignedExactTreatment,
    QualificationState,
    UptakeArm,
    UptakeAssignment,
    render_step2_prompt,
)


def _state():
    return QualificationState(
        qualification_state_id="q1",
        source_split="validation",
        source_dialogue_id="esconv_1",
        visible_state="seeker: I feel overwhelmed.",
        query_text="I feel overwhelmed.",
    )


def _treatment():
    text = "Acknowledge the seeker's feeling of being overwhelmed."
    return AssignedExactTreatment(
        treatment_id="rs_treatment_" + hashlib.sha256(text.encode()).hexdigest()[:24],
        rendered_card_text=text,
        rendered_card_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
        source_card_ids=("rs_src_" + "a" * 24,),
        source_dialogue_ids=("esconv_2",),
        atomic_move_families=("reflection_of_feelings",),
    )


def test_uptake_assignment_enforces_off_none_on_exactly_one():
    with pytest.raises(ValueError, match="OFF"):
        UptakeAssignment(assignment_id="bad", state=_state(), arm=UptakeArm.OFF, treatment=_treatment())
    with pytest.raises(ValueError, match="ON"):
        UptakeAssignment(assignment_id="bad", state=_state(), arm=UptakeArm.ON)


def test_step2_off_has_no_move_and_on_has_exact_assigned_text():
    off = UptakeAssignment(assignment_id="off", state=_state(), arm=UptakeArm.OFF)
    on = UptakeAssignment(assignment_id="on", state=_state(), arm=UptakeArm.ON, treatment=_treatment())
    off_prompt = render_step2_prompt(base_prompt="Respond supportively.", assignment=off)
    on_prompt = render_step2_prompt(base_prompt="Respond supportively.", assignment=on)
    assert "exact_atomic_move=" not in off_prompt
    assert on.treatment.rendered_card_text in on_prompt
    assert on_prompt.count("exact_atomic_move=") == 1
