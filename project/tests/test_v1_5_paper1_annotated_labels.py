from metacom_pm.v1_5_paper1_annotated_labels import (
    event_ancestor_source_sessions,
    memory_source_annotated_label,
    rs_source_annotated_label,
)


def test_rs_mapping_uses_annotation_only_as_label():
    turn = {"speaker": "supporter", "content": "What feels hardest?", "annotation": {"strategy": "Question"}}
    assert rs_source_annotated_label(move_id="AM02_ask_one_focused_clarification", current_user_text="I am unsure.", next_supporter_turn=turn)
    assert not rs_source_annotated_label(move_id="AM10_offer_one_optional_micro_step", current_user_text="I am unsure.", next_supporter_turn=turn)


def test_rs_am14_requires_both_sides_of_closure():
    close = {"speaker": "supporter", "content": "Take care, and we can talk later.", "annotation": {"strategy": "Others"}}
    assert rs_source_annotated_label(move_id="AM14_supportive_transition", current_user_text="Thanks for listening, I need to go.", next_supporter_turn=close)
    assert not rs_source_annotated_label(move_id="AM14_supportive_transition", current_user_text="I still need help.", next_supporter_turn=close)


def test_event_ancestry_is_recursive_and_session_local():
    user = {
        "event_experience": [
            {"id": "e1", "conv_id": "s1", "influenced_by": []},
            {"id": "e2", "conv_id": "s2", "influenced_by": ["e1"]},
            {"id": "e3", "conv_id": "s3", "influenced_by": ["e2"]},
        ],
        "dialog_history": [{"id": "s1"}, {"id": "s2"}, {"id": "s3"}],
    }
    ancestors = event_ancestor_source_sessions(user)
    assert ancestors["s3"] == {"s1", "s2"}
    assert memory_source_annotated_label(source_session_id="s1", current_session_id="s3", ancestors=ancestors)
    assert not memory_source_annotated_label(source_session_id="s3", current_session_id="s3", ancestors=ancestors)
