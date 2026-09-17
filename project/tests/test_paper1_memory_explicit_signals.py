from metacom_pm.paper1.memory.explicit_signals import (
    entity_like_tokens,
    has_current_action_request,
    has_explicit_return_marker,
    thread_entity_overlap_count,
)


def test_return_marker_detects_again():
    assert has_explicit_return_marker("This is happening again this week.")


def test_return_marker_detects_last_time():
    assert has_explicit_return_marker("Like last time, I feel overwhelmed.")


def test_return_marker_detects_like_i_said():
    assert has_explicit_return_marker("Like I said, my sister has been distant.")


def test_return_marker_absent_on_fresh_topic():
    assert not has_explicit_return_marker("I started a new job this week and I am nervous.")


def test_action_request_detects_what_should_i_do():
    assert has_current_action_request("What should I do about my landlord?")


def test_action_request_detects_any_advice():
    assert has_current_action_request("Any advice on how to bring this up with my mom?")


def test_action_request_detects_how_do_i():
    assert has_current_action_request("How do I even start this conversation?")


def test_action_request_absent_on_pure_venting():
    assert not has_current_action_request("I just feel so exhausted lately.")


def test_action_request_is_not_triggered_by_unrelated_how_do():
    # "how do" without "i" right after should not match "how do i"
    assert not has_current_action_request("How do these things even happen to people?")


def test_entity_like_tokens_excludes_sentence_initial_capitalization():
    tokens = entity_like_tokens("Mark called about the trip to London.")
    assert "mark" not in tokens
    assert "london" in tokens


def test_entity_like_tokens_empty_for_generic_lowercase_text():
    assert entity_like_tokens("i feel tired and stressed about work") == frozenset()


def test_thread_entity_overlap_counts_shared_entities():
    query = "Has Sarah reached out about the Boston trip again?"
    candidate = "action: I talked to Sarah about the Boston trip result: it went well"
    count = thread_entity_overlap_count(query, candidate)
    assert count == 2


def test_thread_entity_overlap_none_when_query_has_no_entities():
    query = "how are things going with your family"
    candidate = "action: I talked to Sarah about the trip result: it went well"
    assert thread_entity_overlap_count(query, candidate) is None


def test_thread_entity_overlap_none_when_candidate_has_no_entities():
    query = "Has Sarah reached out again?"
    candidate = "action: i talked to a friend result: it went well"
    assert thread_entity_overlap_count(query, candidate) is None


def test_thread_entity_overlap_zero_when_entities_present_but_disjoint():
    query = "Has Sarah reached out about the Boston trip again?"
    candidate = "action: I talked to Marcus about the Chicago conference result: it went well"
    assert thread_entity_overlap_count(query, candidate) == 0
