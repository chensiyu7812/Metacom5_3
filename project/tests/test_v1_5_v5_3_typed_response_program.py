import pytest

from metacom_pm.v1_5_typed_resource_adapter import TypedResourceCandidate
from metacom_pm.v1_5_v5_3_typed_response_program import (
    GeneratorResponse,
    build_typed_response_program,
    evidence_aware_generation_messages,
    m0_fallback_response,
    parse_generator_response_dict,
    typed_response_guard_errors,
)


def ms() -> TypedResourceCandidate:
    return TypedResourceCandidate(
        component="MS",
        subtype="MS_SESSION_OBSERVATION",
        resource_id="memory_session_001",
        candidate_version="v1",
        source_kind="session",
        owner_id="u1",
        strictly_prior=True,
        age_sessions=2,
        prior_observation="The seeker felt overloaded after a shift change.",
    )


def me() -> TypedResourceCandidate:
    return TypedResourceCandidate(
        component="ME",
        subtype="ME_REUSABLE_OUTCOME",
        resource_id="memory_event_001",
        candidate_version="v1",
        source_kind="event",
        owner_id="u1",
        strictly_prior=True,
        age_sessions=3,
        past_action="I paused before replying.",
        observed_outcome="That helped me avoid escalating the disagreement.",
    )


def rs() -> TypedResourceCandidate:
    return TypedResourceCandidate(
        component="RS",
        subtype="RS_ATOMIC_MOVE",
        resource_id="strategy_card_001",
        candidate_version="v1",
        source_kind="strategy",
        support_move="Offer one optional, low-conflict way to begin a conversation.",
        when_to_use="user already wants to have this conversation",
        when_not_to_use="conflict is unresolved or unsafe",
    )


def test_generator_sees_full_evidence_unlike_v5_2() -> None:
    program = build_typed_response_program(
        requested_action_id="MS+RS", current_goal="raise a concern with a friend",
        current_user_id="u1", candidates={"MS": ms(), "RS": rs()},
    )
    messages = evidence_aware_generation_messages(
        current_context="User: I'm nervous about this.", program=program
    )
    assert "shift change" in messages[1]["content"]
    assert "memory_session_001" in messages[1]["content"]
    assert "strategy_card_001" in messages[1]["content"]
    assert "conflict is unresolved or unsafe" in messages[1]["content"]


def test_me_literal_evidence_uses_required_fields_not_optional_mechanism() -> None:
    program = build_typed_response_program(
        requested_action_id="ME+R0", current_goal="x", current_user_id="u1", candidates={"ME": me()},
    )
    assert program.evidence[0].literal_evidence == "I paused before replying. That helped me avoid escalating the disagreement."


def test_requested_action_must_match_provided_candidates() -> None:
    with pytest.raises(ValueError):
        build_typed_response_program(
            requested_action_id="M0+R0", current_goal="x", current_user_id="u1", candidates={"ME": me()},
        )
    with pytest.raises(ValueError):
        build_typed_response_program(
            requested_action_id="MS+RS", current_goal="x", current_user_id="u1", candidates={"MS": ms()},
        )


def test_owner_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError):
        build_typed_response_program(
            requested_action_id="MS+R0", current_goal="x", current_user_id="someone_else",
            candidates={"MS": ms()},
        )


def test_execution_candidate_id_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError):
        build_typed_response_program(
            requested_action_id="MS+R0", current_goal="x", current_user_id="u1",
            candidates={"MS": ms()},
            expected_execution_candidate_ids={"MS": "memory_session_999"},
        )


def test_cannot_integrate_program_refuses_generation_and_falls_back() -> None:
    program = build_typed_response_program(
        requested_action_id="MS+R0", current_goal="x", current_user_id="u1", candidates={"MS": ms()},
        cannot_integrate_reason="no contribution slot for current goal",
    )
    assert program.allowed_reply_actions == ("m0_fallback",)
    with pytest.raises(ValueError):
        evidence_aware_generation_messages(current_context="hi", program=program)
    assert m0_fallback_response("listen_only") == "I hear you."
    with pytest.raises(ValueError):
        m0_fallback_response("not_a_real_boundary")


def test_guard_flags_internal_label_leak_and_unauthorized_id() -> None:
    program = build_typed_response_program(
        requested_action_id="MS+RS", current_goal="x", current_user_id="u1",
        candidates={"MS": ms(), "RS": rs()},
    )
    response = parse_generator_response_dict(
        {"reply": "MP says something.", "used_evidence_ids": ["memory_nonexistent"], "realized_response_act": "did a thing"}
    )
    errors = typed_response_guard_errors(response=response, program=program)
    assert "INTERNAL_LABEL_OR_ID_LEAK" in errors
    assert "TRACE_REFERENCES_UNAUTHORIZED_EVIDENCE_ID" in errors


def test_guard_flags_required_evidence_not_used() -> None:
    program = build_typed_response_program(
        requested_action_id="MS+RS", current_goal="x", current_user_id="u1",
        candidates={"MS": ms(), "RS": rs()},
    )
    response = GeneratorResponse(
        reply="A generic reply that never used either resource.",
        used_evidence_ids=(), realized_response_act="generic",
    )
    errors = typed_response_guard_errors(response=response, program=program)
    assert "REQUIRED_EVIDENCE_NOT_USED" in errors


def test_guard_catches_real_v5_2_leak_phrases() -> None:
    program = build_typed_response_program(
        requested_action_id="MS+R0", current_goal="x", current_user_id="u1", candidates={"MS": ms()},
    )
    real_leaks = [
        'It sounds like seeing John again has reopened some old wounds. One current practical '
        'constraint on record is: "high school (in progress)" I will keep the response within '
        'that constraint. An earlier session recorded: "..." I am keeping that as past context '
        "rather than assuming it is still true now.",
        'You mentioned before... An earlier session recorded: "x" I am keeping that as past '
        "context rather than assuming it is still true now.",
        'You previously said: "we went hiking" If it still fits, that past result can be one '
        "optional starting point, not a prediction that it will work now.",
    ]
    for text in real_leaks:
        response = GeneratorResponse(
            reply=text, used_evidence_ids=("memory_session_001",), realized_response_act="x"
        )
        errors = typed_response_guard_errors(response=response, program=program)
        assert "RECORD_LOG_PHRASING_LEAK" in errors, text


def test_guard_passes_clean_natural_use_of_evidence() -> None:
    program = build_typed_response_program(
        requested_action_id="MS+RS", current_goal="x", current_user_id="u1",
        candidates={"MS": ms(), "RS": rs()},
    )
    response = GeneratorResponse(
        reply=(
            "You mentioned feeling overloaded after a shift change -- does that still feel "
            "true right now? In the meantime, would it help to start with a low-key check-in "
            "the next time you two talk?"
        ),
        used_evidence_ids=("memory_session_001", "strategy_card_001"),
        realized_response_act="tentative continuity check plus low-conflict opener",
    )
    errors = typed_response_guard_errors(response=response, program=program)
    assert errors == ()


def test_parse_generator_response_dict_rejects_malformed_shape() -> None:
    with pytest.raises(ValueError):
        parse_generator_response_dict({"reply": "hi"})
    with pytest.raises(ValueError):
        parse_generator_response_dict({"reply": "hi", "used_evidence_ids": "not_a_list", "realized_response_act": "x"})
