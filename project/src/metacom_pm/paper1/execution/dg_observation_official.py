"""Exact message builders for the pinned ES-MemEval DG observation judges.

These helpers mirror the two nested prompt builders in the pinned upstream
``dg_experiment.py``.  They are used only for zero-outcome compatibility and
throughput measurements; the formal benchmark continues to use the official
implementation.
"""

from __future__ import annotations

from typing import Any


SYSTEM_MESSAGE = (
    "In emotional support conversations, there are typically two roles: a "
    "supporter and a seeker. An AI supporter has been designed with a memory "
    "recall mechanism and has been engaged in a conversation with a seeker. "
    "Now, the user would like you to help rate the AI supporter's responses "
    "to comprehensively evaluate the ability of AI."
)
GREETING = "Hello! Could you help me to evaluate a response from an AI supporter?"
GREETING_REPLY = (
    "Of course! I'd be happy to help you evaluate a response. Please go ahead "
    "and share the response you'd like me to look at, along with any specific "
    "criteria or aspects you want me to focus on."
)


def _background(user: dict[str, Any], topic: dict[str, Any]) -> str:
    basic = user["basic_info"]
    summaries = "\n".join(
        f"[{history['timestamp']}]: {history['summary']}"
        for history in user["dialog_history"]
    )
    return f"""OK. First I will provide you some basic information of the seeker:
Name: {basic["name"]}
Age: {basic["age"]}
Gender: {basic["gender"]}
Nationality: {basic["nationality"]}
Location: {basic["location"]}
Job: {basic["job"]}
Education: {basic["education"]}

And the summaries of previous sessions:
{summaries}

And the topic they are talking about now:
{topic["topic"]}

Hope these information could be helpful."""


def _opening_messages() -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_MESSAGE},
        {"role": "user", "content": GREETING},
        {"role": "assistant", "content": GREETING_REPLY},
    ]


def build_observation_score_messages(
    *,
    user: dict[str, Any],
    topic: dict[str, Any],
    seeker_message: str,
    observation: str,
) -> list[dict[str, str]]:
    """Build the pinned official 1--3 observation-relevance prompt."""

    instruction = _background(user, topic) + """

Before evaluating the response, I'd like to score the observations of the previous session first. The observation means an objective description of the previous conversation.

I will later send an observation and a seeker's message to you. Please decide whether the observation is helpful in replying the seeker. You shall give me a score from 1 to 3, where
1 means: The observation has only a very faint or marginal connection — almost irrelevant. Even if I knew this observation, I would not mention it in my reply.
2 means: The observation shows a slight connection. Mentioning it could add a touch of context, but it's not necessary for a reasonable reply.
3 means: The observation is highly relevant. It contributes meaningful background or focus; omitting it may weaken the response's precision or depth.

I'd prefer you choose the more extreme option unless you're really wavering.

If you are ready, please reply "0"."""
    task = f"""The message by the seeker:
{seeker_message}

The observation (Note that this is describing a past situation, even though the present tense is used):
{observation}

Don't forget the task: Please decide whether the observation is helpful in replying the seeker."""
    return _opening_messages() + [
        {"role": "user", "content": instruction},
        {"role": "assistant", "content": "0"},
        {"role": "user", "content": task},
    ]


def build_observation_usage_messages(
    *,
    user: dict[str, Any],
    topic: dict[str, Any],
    seeker_message: str,
    supporter_message: str,
    observation: str,
) -> list[dict[str, str]]:
    """Build the pinned official boolean observation-usage prompt."""

    instruction = _background(user, topic) + """

I will later send the messages to you with an observation of the previous session. Please decide whether the supporter's message implies that the supporter has memory of this observation. For example, does the supporter mention a detail that the seeker does not, but that appears in this observation?

If you are ready, please reply "OK"."""
    task = f"""The message by the seeker:
{seeker_message}

The message replied by the supporter:
{supporter_message}

The observation (Note that this is describing a past situation, even though the present tense is used):
{observation}

Don't forget the task: Please decide whether the supporter's message implies that the supporter has memory of this observation."""
    return _opening_messages() + [
        {"role": "user", "content": instruction},
        {"role": "assistant", "content": "OK"},
        {"role": "user", "content": task},
    ]


SCORE_JSON_SCHEMA: dict[str, Any] = {
    "name": "ScoreSchema",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "score": {
                "type": "integer",
                "minimum": 1,
                "maximum": 3,
                "description": (
                    "Score of the observation, indicating how helpful is the "
                    "observation in replying the seeker. 1, 2 or 3."
                ),
            }
        },
        "required": ["score"],
        "additionalProperties": False,
    },
}

USAGE_JSON_SCHEMA: dict[str, Any] = {
    "name": "JudgementSchema",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "judgement": {
                "type": "boolean",
                "description": (
                    "A judgement whether the supporter's message implies that "
                    "the supporter has memory of this observation. True or False."
                ),
            }
        },
        "required": ["judgement"],
        "additionalProperties": False,
    },
}
