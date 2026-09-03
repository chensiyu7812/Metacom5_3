from __future__ import annotations

import json
from pathlib import Path

import pytest

from metacom_pm.io import sha256_text
from metacom_pm.paper1.execution.dg_official import (
    build_official_dg_seeker_system_prompt,
    official_dg_seeker_messages,
)


PROJECT = Path(__file__).resolve().parents[1]


def _first_scenario():
    users = json.loads(
        (PROJECT / "outputs/vendor_es_memeval/data/evo_emo.json").read_text(
            encoding="utf-8"
        )
    )
    return users[0], users[0]["subsequent_topics"][0]


def test_official_seeker_prompt_is_hash_bound_and_keeps_hidden_scenario() -> None:
    user, topic = _first_scenario()
    prompt = build_official_dg_seeker_system_prompt(user=user, topic=topic)
    assert sha256_text(prompt) == (
        "58826b1816b399ed33bd03b81f9104e1440b87e124640b64057b036ef8f7a0f7"
    )
    assert topic["topic"] in prompt
    assert topic["psychological_condition"] in prompt
    assert topic["physical_condition"] in prompt
    assert topic["more_details"] in prompt
    assert "Additionally, your output is limited to 60 tokens" in prompt


def test_official_seeker_message_roles_follow_upstream_room_direction() -> None:
    messages = official_dg_seeker_messages(
        system_prompt="hidden scenario",
        first_supporter_message="Hi",
        prior_turns=(("seeker one", "supporter one"),),
    )
    assert [message["role"] for message in messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert messages[-1]["content"] == "supporter one"


def test_official_seeker_messages_reject_more_than_nine_prior_turns() -> None:
    with pytest.raises(ValueError, match="prior_turns"):
        official_dg_seeker_messages(
            system_prompt="hidden scenario",
            first_supporter_message="Hi",
            prior_turns=tuple(("s", "p") for _ in range(10)),
        )
