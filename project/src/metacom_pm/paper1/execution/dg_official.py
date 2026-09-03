"""Pinned ES-MemEval dialogue-generation seeker surface.

The seeker receives scenario fields that are deliberately hidden from the
supporter and Policy Manager.  This module reproduces only the public prompt
construction at the pinned upstream commit; it does not call a model or
expose the hidden fields to a supporter request.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

DG_OFFICIAL_SEEKER_PROTOCOL = "paper1-es-memeval-official-dg-seeker-prompt-v1"
DG_OFFICIAL_SEEKER_MODEL_ALIAS = "gpt-4o"
DG_REPRODUCIBLE_SEEKER_SNAPSHOT = "gpt-4o-2024-11-20"
DG_OFFICIAL_ROUNDS = 10
DG_OFFICIAL_MAX_OUTPUT_TOKENS = 60


def build_official_dg_seeker_system_prompt(
    *,
    user: Mapping[str, Any],
    topic: Mapping[str, Any],
) -> str:
    """Reproduce ``DgExperiment.generate_dialogue``'s seeker prompt.

    ``topic['related_sessions']`` is resolved against the user's public
    history in the same history order as upstream ``_load_topics``.
    """

    basic = user["basic_info"]
    related_ids = {str(value) for value in topic["related_sessions"]}
    sessions = [
        session
        for session in user["dialog_history"]
        if str(session["id"]) in related_ids
    ]
    if {str(session["id"]) for session in sessions} != related_ids:
        raise ValueError("DG topic references a session absent from the owner history")

    system_message = f"""In emotional support conversations, there are typically two roles: a supporter and a seeker. As an AI, you are asked to role-play the seeker, allowing us to assess the supporter's counseling skills from all angles.

The basic information of the seeker is listed below:
Name: {basic["name"]}
Age: {basic["age"]}
Gender: {basic["gender"]}
Nationality: {basic["nationality"]}
Location: {basic["location"]}
Job: {basic["job"]}
Education: {basic["education"]}

Summaries of previous sessions:
{chr(10).join(f'[{history["timestamp"]}]: {history["summary"]}' for history in user["dialog_history"])}

Summaries of previous events:
{chr(10).join(f'[{event["date"]}]: {event["event"]}' for event in user["event_experience"])}

To help you better play this role, here are the detailed messages of related sessions:
"""
    for session in sessions:
        lines = [
            f'{dialogue["role"]}: {dialogue["content"]}'
            for dialogue in session["dialogue"]
        ]
        lines.insert(0, f'Session [{session["timestamp"]}] ({session["summary"]}):')
        lines.append("")
        system_message += "\n".join(lines)
    system_message += f"""
And this is the topic you are going to talk about later:
Topic:
{topic["topic"]}
Your Psychological Condition:
{topic["psychological_condition"]}
Your Physical Condition:
{topic["physical_condition"]}
More Details:
{topic["more_details"]}

I want to emphasize again that, from now, you are not an AI assistant, but a real seeker. The seeker has its own emotions and thoughts, and is seeking help from the supporter.

You should also be careful not to be led off topic by the supporter. Your conversation should revolve around the above topic (the topic revolves around events that happened to you, so the supporter doesn't know what the topic is and needs you to guide it).

However, the primary purpose of this test is to confirm the supporter's ability to recall the seeker's information. You should be careful to guide the supporter in recalling relevant memories. For example, you can use guiding questions like "Do you remember what I said earlier about ...?" to start the conversation, rather than directly informing the supporter of the topic. You can also use more obscure phrases, such as "He appeared in my dream again", but do not specify who he is (of course, the premise is that the supporter can recall based on the "dream" as a clue).

Additionally, your output is limited to 60 tokens, so don't try to say anything too long."""
    return system_message


def official_dg_seeker_messages(
    *,
    system_prompt: str,
    first_supporter_message: str,
    prior_turns: Sequence[tuple[str, str]],
) -> tuple[dict[str, str], ...]:
    """Build the role sequence visible to the seeker before its next turn."""

    if not system_prompt or not first_supporter_message:
        raise ValueError("DG seeker system and opening supporter message must be nonempty")
    if len(prior_turns) >= DG_OFFICIAL_ROUNDS:
        raise ValueError("prior_turns must precede one of the ten official seeker turns")
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": first_supporter_message},
    ]
    for seeker_message, supporter_message in prior_turns:
        if not seeker_message or not supporter_message:
            raise ValueError("DG prior seeker/supporter messages must be nonempty")
        messages.extend(
            (
                {"role": "assistant", "content": seeker_message},
                {"role": "user", "content": supporter_message},
            )
        )
    return tuple(messages)


__all__ = [
    "DG_OFFICIAL_MAX_OUTPUT_TOKENS",
    "DG_OFFICIAL_ROUNDS",
    "DG_OFFICIAL_SEEKER_MODEL_ALIAS",
    "DG_OFFICIAL_SEEKER_PROTOCOL",
    "DG_REPRODUCIBLE_SEEKER_SNAPSHOT",
    "build_official_dg_seeker_system_prompt",
    "official_dg_seeker_messages",
]
