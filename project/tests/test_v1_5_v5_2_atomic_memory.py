from metacom_pm.v1_5_v5_2_atomic_memory import (
    compile_atomic_reusable_outcome,
    compile_atomic_session_observation,
)


def test_rejects_grief_explanation_as_reusable_outcome() -> None:
    text = (
        "I've started having recurring dreams about my late dog. "
        "When I wake up, the loss hits all over again. "
        "I wonder if it's because I've been feeling stressed with work."
    )
    assert compile_atomic_reusable_outcome(text) is None


def test_rejects_unresolved_relationship_narrative() -> None:
    text = (
        "We've grown apart, and it's hard to rely on her. "
        "I have tried, but reconnecting feels like another task because I am exhausted."
    )
    assert compile_atomic_reusable_outcome(text) is None


def test_accepts_same_sentence_action_and_positive_result() -> None:
    item = compile_atomic_reusable_outcome(
        "I tried writing one short note first, and it helped me say what mattered."
    )
    assert item is not None
    assert item.polarity == "positive"
    assert item.sentence_count == 1
    assert item.literal_evidence_span.startswith("I tried")


def test_accepts_immediately_anaphoric_result() -> None:
    item = compile_atomic_reusable_outcome(
        "I paused before replying. That helped me avoid escalating the disagreement."
    )
    assert item is not None
    assert item.sentence_count == 2
    assert item.polarity == "positive"


def test_accepts_negative_result_as_avoidance_evidence() -> None:
    item = compile_atomic_reusable_outcome(
        "I tried making a long checklist, but it did not help me feel less overwhelmed."
    )
    assert item is not None
    assert item.polarity == "negative"


def test_session_observation_requires_specific_bounded_note() -> None:
    assert compile_atomic_session_observation("The seeker discussed the topic.") is None
    item = compile_atomic_session_observation(
        "The seeker felt overloaded after a shift change and wanted to separate sleep loss from workload."
    )
    assert item is not None
    assert "shift change" in item.literal_past_note
