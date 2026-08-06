import pytest

from metacom_pm.v1_5_typed_resource_adapter import TypedResourceCandidate
from metacom_pm.v1_5_v5_3_typed_response_program import (
    GeneratorResponse,
    build_typed_response_program,
    call_with_guard_and_rewrite,
    evidence_aware_generation_messages,
    evidence_usage_plausibility_errors,
    m0_fallback_response,
    parse_generator_response_dict,
    speaker_attribution_guard_errors,
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
    full_text = " ".join(m["content"] for m in messages)
    assert "shift change" in full_text
    assert "memory_session_001" in full_text
    assert "strategy_card_001" in full_text
    assert "conflict is unresolved or unsafe" in full_text
    # current_context (what the user actually said this turn) stays isolated
    # in its own user-role message, separate from background evidence.
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "User: I'm nervous about this."
    assert "shift change" not in messages[1]["content"]


def test_owned_evidence_is_tagged_and_ownerless_evidence_is_not() -> None:
    # 2026-08-06 regression: a real live test found the generator claiming
    # the user's own facts (spouse, job, education) as its own experience,
    # because owner_id was compiled onto ExecutionEvidence but never
    # rendered into the request at all. Evidence with an owner must say so;
    # RS (no owner_id -- not a personal fact) must not be mistagged as owned.
    program = build_typed_response_program(
        requested_action_id="MS+RS", current_goal="raise a concern with a friend",
        current_user_id="u1", candidates={"MS": ms(), "RS": rs()},
    )
    system_text = evidence_aware_generation_messages(
        current_context="User: I'm nervous about this.", program=program
    )[0]["content"]
    assert "you are not role-playing the user" in system_text.lower()
    assert "address them in the second person" in system_text
    assert "owner=none" in system_text
    # regression: an earlier wording used the literal token "you/your" as a
    # notational shorthand, which an 8B model echoed verbatim into a real
    # reply ("That's a great approach, you/your...") instead of treating it
    # as an instruction -- see the 2026-08-06 live re-test. Never reintroduce
    # a literal slash-notation example the model could copy into output.
    assert "you/your" not in system_text
    # both an "owned" and an "ownerless" evidence tag are present, and they
    # are distinguishable (not just both silently present somewhere).
    ms_evidence_id = program.evidence[0].evidence_id
    rs_evidence_id = program.evidence[1].evidence_id
    assert program.evidence[0].component == "MS" and program.evidence[0].owner_id == "u1"
    assert program.evidence[1].component == "RS" and program.evidence[1].owner_id is None
    ms_line = next(line for line in system_text.split("\n") if ms_evidence_id in line)
    rs_line = next(line for line in system_text.split("\n") if rs_evidence_id in line)
    assert "owner=the person you are talking to" in ms_line
    assert "owner=none" in rs_line


def test_no_alias_instruction_when_no_known_aliases_given() -> None:
    program = build_typed_response_program(
        requested_action_id="MS+R0", current_goal="x", current_user_id="u1", candidates={"MS": ms()},
    )
    assert program.current_user_known_aliases == ()
    system_text = evidence_aware_generation_messages(
        current_context="hi", program=program
    )[0]["content"]
    assert "sometimes referred to by name" not in system_text


def test_known_alias_resolves_third_person_pseudonym_to_the_user() -> None:
    # 2026-08-06 regression: a real live re-test found the generator failing
    # to resolve a third-person pseudonym in MS evidence text (EvoEmo's own
    # narrative convention, e.g. "Anna") back to the person it's talking to,
    # instead addressing it as a separate third party ("You mentioned
    # Anna...I'm worried she might be..."). EvoEmo's basic_info.name is
    # already known, structured data -- this threads it through explicitly
    # rather than asking the model to infer it.
    program = build_typed_response_program(
        requested_action_id="MS+R0", current_goal="x", current_user_id="u1",
        candidates={"MS": ms()}, current_user_known_aliases=("Anna", "Anna Li"),
    )
    assert program.current_user_known_aliases == ("Anna", "Anna Li")
    system_text = evidence_aware_generation_messages(
        current_context="hi", program=program
    )[0]["content"]
    assert "sometimes referred to by name" in system_text
    assert '"Anna"' in system_text and '"Anna Li"' in system_text
    assert "the same person you are talking to" in system_text
    # no slash-notation pronoun shorthand anywhere -- see the sibling test's
    # note on why the model cannot be trusted not to echo it verbatim.
    assert "you/your" not in system_text


def test_blank_known_aliases_are_dropped_not_rendered_as_empty_quotes() -> None:
    program = build_typed_response_program(
        requested_action_id="MS+R0", current_goal="x", current_user_id="u1",
        candidates={"MS": ms()}, current_user_known_aliases=("", "  ", "Anna"),
    )
    assert program.current_user_known_aliases == ("Anna",)


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


def _resp(reply: str, used: tuple[str, ...] = ()) -> GeneratorResponse:
    return GeneratorResponse(reply=reply, used_evidence_ids=used, realized_response_act="reflection")


def test_speaker_attribution_guard_catches_direct_biographical_claim() -> None:
    # Real 2026-08-06 live-test pattern (paraphrased, not the verbatim
    # output): the model claimed the user's spouse/child as its own.
    reply = "As a business owner, I've had my fair share of challenges, including my husband's job loss."
    assert speaker_attribution_guard_errors(response=_resp(reply)) == (
        "POSSIBLE_ASSISTANT_SELF_ATTRIBUTION_OF_USER_FACT",
    )


def test_speaker_attribution_guard_catches_extended_narrative_without_trigger_noun() -> None:
    # Real 2026-08-06 pattern: no single forbidden noun, but a sustained
    # first-person reflection co-occurring with a possessive in one sentence.
    reply = (
        "I've been thinking about how this might affect my long-term goals, "
        "like saving for a house."
    )
    assert speaker_attribution_guard_errors(response=_resp(reply)) == (
        "POSSIBLE_ASSISTANT_SELF_ATTRIBUTION_OF_USER_FACT",
    )


def test_speaker_attribution_guard_allows_normal_assistant_first_person() -> None:
    reply = (
        "I hear you, and I'm sorry this has been so hard. I recall that you mentioned "
        "your husband recently changed jobs -- how are you feeling about that today?"
    )
    assert speaker_attribution_guard_errors(response=_resp(reply)) == ()


def test_evidence_usage_plausibility_catches_claimed_but_untraced_evidence() -> None:
    # 2026-08-06, per an independent review: used_evidence_ids is
    # self-reported and was never checked against the reply at all. This is
    # a deliberately cheap check (word-overlap, reusing the same primitive
    # as candidate matching elsewhere), not a full grounding verifier.
    program = build_typed_response_program(
        requested_action_id="MS+R0", current_goal="x", current_user_id="u1", candidates={"MS": ms()},
    )
    evidence_id = program.evidence[0].evidence_id
    reply_with_no_trace = _resp(
        "I hear you, that sounds really difficult.", used=(evidence_id,)
    )
    assert evidence_usage_plausibility_errors(response=reply_with_no_trace, program=program) == (
        "EVIDENCE_CLAIMED_USED_BUT_NO_WORD_TRACE_IN_REPLY",
    )


def test_evidence_usage_plausibility_passes_when_evidence_word_appears() -> None:
    program = build_typed_response_program(
        requested_action_id="MS+R0", current_goal="x", current_user_id="u1", candidates={"MS": ms()},
    )
    evidence_id = program.evidence[0].evidence_id
    # ms()'s prior_observation is "The seeker felt overloaded after a shift change."
    reply_with_trace = _resp(
        "I recall you mentioned a shift change recently -- how has that been?",
        used=(evidence_id,),
    )
    assert evidence_usage_plausibility_errors(response=reply_with_trace, program=program) == ()


def test_evidence_usage_plausibility_ignores_unclaimed_evidence() -> None:
    # Evidence NOT listed in used_evidence_ids is not this check's business
    # (that gap is REQUIRED_EVIDENCE_NOT_USED, a different, existing check).
    program = build_typed_response_program(
        requested_action_id="MS+R0", current_goal="x", current_user_id="u1", candidates={"MS": ms()},
    )
    reply_using_nothing = _resp("I hear you.", used=())
    assert evidence_usage_plausibility_errors(response=reply_using_nothing, program=program) == ()


def test_call_with_guard_and_rewrite_all_four_branches() -> None:
    program = build_typed_response_program(
        requested_action_id="MS+R0", current_goal="x", current_user_id="u1", candidates={"MS": ms()},
    )
    evidence_id = program.evidence[0].evidence_id
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]

    class _FakeParsed:
        def __init__(self, d):
            self._d = d

        def model_dump(self):
            return self._d

    class _FakeClient:
        def __init__(self, replies):
            self.replies = list(replies)
            self.calls = 0

        def chat(self, messages, response_schema=None):
            self.calls += 1
            d = self.replies.pop(0)
            if d is None:
                return ("no schema", None)
            return ("ok", _FakeParsed(d))

    def resp_dict(reply):
        return {"reply": reply, "used_evidence_ids": [evidence_id], "realized_response_act": "reflection"}

    # clean first pass
    client = _FakeClient([resp_dict("I recall your shift change -- how are you now?")])
    response, status, errors = call_with_guard_and_rewrite(client, None, messages, program)
    assert status == "clean" and client.calls == 1 and errors == ()

    # bad first pass (no word trace -> plausibility guard fires), good rewrite
    client = _FakeClient([
        resp_dict("I hear you."),
        resp_dict("I recall your shift change -- that sounds hard."),
    ])
    response, status, errors = call_with_guard_and_rewrite(client, None, messages, program)
    assert status == "fixed_by_rewrite" and client.calls == 2
    assert errors == ("EVIDENCE_CLAIMED_USED_BUT_NO_WORD_TRACE_IN_REPLY",)

    # bad both times -> falls back to M0; MS+R0 has atomic_move_budget=0
    # (no RS requested), so the context-aware fallback picks a statement,
    # not a question -- see the 2026-08-06 fix for why this matters.
    client = _FakeClient([resp_dict("I hear you."), resp_dict("I hear you.")])
    response, status, errors = call_with_guard_and_rewrite(client, None, messages, program)
    assert status == "fell_back_to_m0" and client.calls == 2
    assert response.used_evidence_ids == ()
    assert response.reply == m0_fallback_response("concise_reflection")

    # no structured output
    client = _FakeClient([None])
    response, status, errors = call_with_guard_and_rewrite(client, None, messages, program)
    assert status == "no_structured_output" and response is None


def test_call_with_guard_and_rewrite_fallback_boundary_when_rs_present() -> None:
    program = build_typed_response_program(
        requested_action_id="MS+RS", current_goal="x", current_user_id="u1",
        candidates={"MS": ms(), "RS": rs()},
    )
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]

    class _FakeParsed:
        def __init__(self, d):
            self._d = d

        def model_dump(self):
            return self._d

    class _FakeClient:
        def __init__(self, replies):
            self.replies = list(replies)

        def chat(self, messages, response_schema=None):
            return ("ok", _FakeParsed(self.replies.pop(0)))

    bad = {"reply": "I hear you.", "used_evidence_ids": [], "realized_response_act": "x"}
    client = _FakeClient([bad, bad])
    response, status, _errors = call_with_guard_and_rewrite(client, None, messages, program)
    assert status == "fell_back_to_m0"
    assert response.reply == m0_fallback_response("one_focused_question")


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
