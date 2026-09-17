from metacom_pm.paper1.execution.dg_observation_official import (
    SCORE_JSON_SCHEMA,
    USAGE_JSON_SCHEMA,
    build_observation_score_messages,
    build_observation_usage_messages,
)


def _fixture():
    user = {
        "basic_info": {
            "name": "A",
            "age": 30,
            "gender": "x",
            "nationality": "N",
            "location": "L",
            "job": "J",
            "education": "E",
        },
        "dialog_history": [{"timestamp": "2025-01-01", "summary": "Summary."}],
    }
    return user, {"topic": "Topic."}


def test_score_builder_preserves_official_role_sequence_and_contract():
    user, topic = _fixture()
    messages = build_observation_score_messages(
        user=user,
        topic=topic,
        seeker_message="Seeker.",
        observation="Observation.",
    )
    assert [message["role"] for message in messages] == [
        "system",
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
    ]
    assert messages[4]["content"] == "0"
    assert "choose the more extreme option" in messages[3]["content"]
    assert "Seeker." in messages[5]["content"]
    assert "Observation." in messages[5]["content"]
    score = SCORE_JSON_SCHEMA["schema"]["properties"]["score"]
    assert (score["minimum"], score["maximum"]) == (1, 3)


def test_usage_builder_preserves_official_role_sequence_and_contract():
    user, topic = _fixture()
    messages = build_observation_usage_messages(
        user=user,
        topic=topic,
        seeker_message="Seeker.",
        supporter_message="Supporter.",
        observation="Observation.",
    )
    assert [message["role"] for message in messages] == [
        "system",
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
    ]
    assert messages[4]["content"] == "OK"
    assert "Supporter." in messages[5]["content"]
    judgement = USAGE_JSON_SCHEMA["schema"]["properties"]["judgement"]
    assert judgement["type"] == "boolean"
