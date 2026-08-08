"""Frozen, staged Wave-1 catalog-generation helpers.

The language model authors synthetic longitudinal content.  Python owns the
assignment, per-user quotas, chunk boundaries, assembly, and validation
surface.  No outcome, worth-opening label, or external exam text is visible to
the author model.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any, Iterable


PREFERENCE_TYPES = (
    "concise_factual_answer",
    "reflection_before_question",
    "one_optional_suggestion",
    "listen_only_no_advice",
    "direct_answer_before_explanation",
    "choices_rather_than_commands",
)
BASE_PROFILE_FIELDS = (
    "name", "age", "gender", "job", "education", "nationality", "location"
)


def chunk_ranges(session_count: int) -> tuple[tuple[int, int], ...]:
    """Return three contiguous, non-empty ranges covering every session."""

    base, remainder = divmod(session_count, 3)
    sizes = [base + int(index < remainder) for index in range(3)]
    ranges: list[tuple[int, int]] = []
    start = 1
    for size in sizes:
        ranges.append((start, start + size - 1))
        start += size
    assert ranges[-1][1] == session_count
    return tuple(ranges)


def preference_assignments(
    assignments: list[dict[str, Any]], existing_users_dir: Path
) -> dict[str, list[str]]:
    """Allocate Wave-1 preference triples while preserving final 20/type reachability.

    Existing accepted users are immutable.  At every new user, choose the
    three types with the largest remaining quota for that author, using the
    frozen type order only as a deterministic tie-break.
    """

    counts: dict[str, Counter[str]] = {
        "chatgpt_pro": Counter(),
        "claude": Counter(),
    }
    user_counts = Counter()
    for path in sorted(existing_users_dir.glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        author = row["content_author"]
        user_counts[author] += 1
        counts[author].update(
            item["preference_type"] for item in row["response_preference_history"]
        )
    result: dict[str, list[str]] = {}
    type_order = {value: index for index, value in enumerate(PREFERENCE_TYPES)}
    for row in assignments:
        author = row["content_author"]
        chosen = sorted(
            PREFERENCE_TYPES,
            key=lambda value: (-(20 - counts[author][value]), type_order[value]),
        )[:3]
        if any(counts[author][value] >= 20 for value in chosen):
            raise RuntimeError(f"preference quota already exhausted for {author}")
        result[row["user_id"]] = list(chosen)
        counts[author].update(chosen)
        user_counts[author] += 1
        remaining_users = 40 - user_counts[author]
        for value in PREFERENCE_TYPES:
            remaining = 20 - counts[author][value]
            if remaining < 0 or remaining > remaining_users:
                raise RuntimeError(
                    f"preference schedule is no longer reachable: {author}/{value}"
                )
    return result


def candidate_requirements(
    user_id: str, topic_thread_ids: list[str], session_count: int
) -> list[dict[str, Any]]:
    """Materialize exact per-user candidate slots without authoring their text."""

    if len(topic_thread_ids) < 4:
        raise ValueError("at least four topic threads are required")
    threads = topic_thread_ids[:4]
    rows: list[dict[str, Any]] = []

    def add(
        subtype: str,
        session_indices: Iterable[int],
        prefix: str,
        *,
        tiers: list[str | None] | None = None,
    ) -> None:
        for ordinal, session_index in enumerate(session_indices, 1):
            if not 1 <= session_index <= session_count:
                raise ValueError("candidate session outside user chronology")
            row = {
                "candidate_id": f"{user_id}_{prefix}_{ordinal:03d}",
                "subtype": subtype,
                "session_index": session_index,
                "topic_thread": threads[(ordinal - 1) % 4],
            }
            if tiers is not None:
                row["me_tier"] = tiers[ordinal - 1]
            rows.append(row)

    add("MS_SESSION", range(1, 9), "ms")
    add(
        "ME_REUSABLE_OUTCOME",
        range(2, 10),
        "me_reusable_core",
        tiers=["executable_core"] * 8,
    )
    add(
        "ME_REUSABLE_OUTCOME",
        (10, 11),
        "me_reusable_challenge",
        tiers=["natural_coverage_challenge"] * 2,
    )
    add("ME_UNRESOLVED_EVENT", (1, 4, 7, 10, 12), "me_unresolved")
    add("ME_CONTEXT_EVENT", (2, 5, 8, 13), "me_context")
    return rows


def world_prompt(
    assignment: dict[str, Any], preference_types: list[str], contract_excerpt: dict[str, Any]
) -> list[dict[str, str]]:
    relationship_count = int(
        contract_excerpt["relationships_per_user_schedule"][assignment["schedule_position"]]
    )
    event_count = int(
        contract_excerpt["events_per_user_schedule"][assignment["schedule_position"]]
    )
    update_count = 2 if assignment["schedule_position"] <= 1 else 1
    system = """You author one wholly synthetic longitudinal emotional-support user.
Return exactly one JSON object and no prose or Markdown. Do not copy any benchmark,
external dataset, existing person, or exam content. The assignment metadata is for
construction only and must not be mentioned in the user's dialogue. Build a coherent
world before surface dialogue: recurring threads must evolve, facts must remain stable
until explicitly updated, and entities must never be conflated."""
    user = f"""Create the compact world/chronology plan for this user.

Frozen assignment:
{json.dumps(assignment, ensure_ascii=False, sort_keys=True)}

Exact requirements:
- primary_superdomain exactly {assignment['primary_superdomain']!r}; add 2-3 distinct secondary_superdomains.
- 4-6 topic_threads, each {{thread_id,label}} with user-specific IDs.
- exactly {relationship_count} relationships, each {{entity_id,name,relationship,valid_from_session,valid_until_session}}. Every non-self entity first appears exactly at valid_from_session and never earlier.
- exactly {event_count} events distributed across all {assignment['session_count']} sessions; every session has at least one event. Each event has {{event_id,session_index,topic_thread_ids,entity_ids,resolution_status,description}}.
- profile_plan has the seven base fields {list(BASE_PROFILE_FIELDS)} plus exactly {update_count} later updates to distinct mutable fields. Every item has {{item_id,item_role,field_type,field_value,valid_from_session,valid_until_session,version,active,supersedes_item_id,applicability_scope,source_session}}. Superseded versions end immediately before the update begins.
- preference_plan has exactly these three types: {preference_types}. Each has {{item_id,preference_type,preference_text,valid_from_session,valid_until_session,version,active,supersedes_item_id,source_session}}. They are stable, user-expressed interaction preferences, not construction labels.
- session_plan has exactly sessions 1..{assignment['session_count']}; each row has {{session_index,relative_time,event_ids,topic_thread_ids,entity_ids,resolution_status,narrative_goal}}.
- Include at least one temporal sequence, one genuine update/conflict, one evolving user-model trajectory, and one session where no old evidence answers the new question.
- Use English natural-language content. Keep names, locations, occupations, relationships and chronology internally consistent.

Output keys exactly: secondary_superdomains, topic_threads, relationships, events, profile_plan, preference_plan, session_plan."""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def validate_world(
    world: dict[str, Any], assignment: dict[str, Any], preference_types: list[str], contract_excerpt: dict[str, Any]
) -> None:
    expected_keys = {
        "secondary_superdomains", "topic_threads", "relationships", "events",
        "profile_plan", "preference_plan", "session_plan",
    }
    if set(world) != expected_keys:
        raise ValueError(f"world keys differ: {sorted(set(world) ^ expected_keys)}")
    if not 4 <= len(world["topic_threads"]) <= 6:
        raise ValueError("world must contain 4-6 topic threads")
    schedule = int(assignment["schedule_position"])
    if len(world["relationships"]) != int(contract_excerpt["relationships_per_user_schedule"][schedule]):
        raise ValueError("relationship quota mismatch")
    if len(world["events"]) != int(contract_excerpt["events_per_user_schedule"][schedule]):
        raise ValueError("event quota mismatch")
    n = int(assignment["session_count"])
    if sorted(int(row["session_index"]) for row in world["session_plan"]) != list(range(1, n + 1)):
        raise ValueError("session plan is not contiguous")
    if set(item["field_type"] for item in world["profile_plan"] if item["item_role"] == "base") != set(BASE_PROFILE_FIELDS):
        raise ValueError("base profile fields mismatch")
    update_count = sum(item["item_role"] == "update" for item in world["profile_plan"])
    if update_count != 2:
        raise ValueError("Wave-1 schedule requires exactly two profile updates")
    if {item["preference_type"] for item in world["preference_plan"]} != set(preference_types):
        raise ValueError("preference plan differs from frozen assignment")

    thread_ids = [str(row["thread_id"]) for row in world["topic_threads"]]
    event_ids = [str(row["event_id"]) for row in world["events"]]
    entity_ids = [str(row["entity_id"]) for row in world["relationships"]]
    for label, values in (
        ("topic thread", thread_ids), ("event", event_ids), ("relationship entity", entity_ids)
    ):
        if len(values) != len(set(values)):
            raise ValueError(f"duplicate {label} id")
    known_threads = set(thread_ids)
    known_entities = set(entity_ids) | {"self"}
    events_by_id = {str(row["event_id"]): row for row in world["events"]}
    sessions_by_index = {
        int(row["session_index"]): row for row in world["session_plan"]
    }
    for session_index, session in sessions_by_index.items():
        unknown_threads = set(session["topic_thread_ids"]) - known_threads
        unknown_entities = set(session["entity_ids"]) - known_entities
        if unknown_threads:
            raise ValueError(
                f"session {session_index} references unknown threads: {sorted(unknown_threads)}"
            )
        if unknown_entities:
            raise ValueError(
                f"session {session_index} references unknown entities: {sorted(unknown_entities)}"
            )
        for event_id in session["event_ids"]:
            if event_id not in events_by_id:
                raise ValueError(f"session {session_index} references unknown event {event_id}")
            if int(events_by_id[event_id]["session_index"]) != session_index:
                raise ValueError(f"event {event_id} session index disagrees with session plan")
    for event_id, event in events_by_id.items():
        session_index = int(event["session_index"])
        if session_index not in sessions_by_index:
            raise ValueError(f"event {event_id} has unknown session")
        if event_id not in sessions_by_index[session_index]["event_ids"]:
            raise ValueError(f"event {event_id} is absent from its session plan")
        unknown_threads = set(event["topic_thread_ids"]) - known_threads
        unknown_entities = set(event["entity_ids"]) - known_entities
        if unknown_threads:
            raise ValueError(f"event {event_id} references unknown threads: {sorted(unknown_threads)}")
        if unknown_entities:
            raise ValueError(f"event {event_id} references unknown entities: {sorted(unknown_entities)}")

    for relationship in world["relationships"]:
        entity_id = str(relationship["entity_id"])
        references = [
            session_index
            for session_index, session in sessions_by_index.items()
            if entity_id in session["entity_ids"]
        ] + [
            int(event["session_index"])
            for event in world["events"]
            if entity_id in event["entity_ids"]
        ]
        if not references:
            raise ValueError(f"relationship entity {entity_id} is never used")
        valid_from = int(relationship["valid_from_session"])
        if min(references) != valid_from:
            raise ValueError(
                f"relationship entity {entity_id} first appears in {min(references)}, not {valid_from}"
            )
        valid_until = relationship.get("valid_until_session")
        if valid_until is not None and max(references) > int(valid_until):
            raise ValueError(f"relationship entity {entity_id} appears after valid_until")

    profile_by_id = {str(row["item_id"]): row for row in world["profile_plan"]}
    if len(profile_by_id) != len(world["profile_plan"]):
        raise ValueError("duplicate profile item id")
    for item in world["profile_plan"]:
        source_session = int(item["source_session"])
        if not 1 <= source_session <= n:
            raise ValueError(f"profile item {item['item_id']} has invalid source session")
        if source_session != int(item["valid_from_session"]):
            raise ValueError(f"profile item {item['item_id']} source/valid-from mismatch")
        if item["item_role"] == "update":
            prior = profile_by_id.get(str(item.get("supersedes_item_id")))
            if prior is None:
                raise ValueError(f"profile update {item['item_id']} has no prior version")
            if prior["field_type"] != item["field_type"]:
                raise ValueError(f"profile update {item['item_id']} changes field identity")
            if prior.get("valid_until_session") != int(item["valid_from_session"]) - 1:
                raise ValueError(f"profile update {item['item_id']} has a noncontiguous validity chain")
            if bool(prior["active"]) or not bool(item["active"]):
                raise ValueError(f"profile update {item['item_id']} has invalid active flags")
    preference_ids = [str(row["item_id"]) for row in world["preference_plan"]]
    if len(preference_ids) != len(set(preference_ids)):
        raise ValueError("duplicate preference item id")
    for item in world["preference_plan"]:
        source_session = int(item["source_session"])
        if not 1 <= source_session <= n:
            raise ValueError(f"preference item {item['item_id']} has invalid source session")
        if source_session != int(item["valid_from_session"]):
            raise ValueError(f"preference item {item['item_id']} source/valid-from mismatch")


def chunk_prompt(
    assignment: dict[str, Any], world: dict[str, Any], start: int, end: int
) -> list[dict[str, str]]:
    thread_ids = [row["thread_id"] for row in world["topic_threads"]]
    requirements = [
        row for row in candidate_requirements(
            assignment["user_id"], thread_ids, int(assignment["session_count"])
        ) if start <= row["session_index"] <= end
    ]
    profiles = [
        row for row in world["profile_plan"] if start <= int(row["source_session"]) <= end
    ]
    preferences = [
        row for row in world["preference_plan"] if start <= int(row["source_session"]) <= end
    ]
    session_plan = [
        row for row in world["session_plan"] if start <= int(row["session_index"]) <= end
    ]
    relevant_event_ids = {event_id for row in session_plan for event_id in row["event_ids"]}
    relevant_events = [row for row in world["events"] if row["event_id"] in relevant_event_ids]
    system = """You render one chunk of a previously frozen synthetic user world.
Return exactly one JSON object and no prose or Markdown. Do not change, add, merge,
or rename world facts, entities, threads, events, profile values, preference types,
session indices, or required candidate IDs. Every literal_source_span, action_span,
and result_span must be an exact character-for-character substring of one USER turn
in the same session. Never put construction labels in dialogue."""
    user = f"""Render sessions {start} through {end} for {assignment['user_id']}.

Frozen world:
{json.dumps(world, ensure_ascii=False, sort_keys=True)}

This chunk's session plan:
{json.dumps(session_plan, ensure_ascii=False, sort_keys=True)}

This chunk's event rows:
{json.dumps(relevant_events, ensure_ascii=False, sort_keys=True)}

Required profile items whose evidence must appear in this chunk:
{json.dumps(profiles, ensure_ascii=False, sort_keys=True)}

Required preference items whose evidence must appear in this chunk:
{json.dumps(preferences, ensure_ascii=False, sort_keys=True)}

Required typed candidate slots (no extra typed candidates):
{json.dumps(requirements, ensure_ascii=False, sort_keys=True)}

Output exactly {{"sessions": [...], "profile_history_items": [...], "response_preference_history_items": [...]}}.

Each session must copy its structural IDs from session_plan and contain:
{{session_index,relative_time,event_ids,topic_thread_ids,entity_ids,resolution_status,dialogue,summary,typed_candidates}}.
Dialogue has 2-6 alternating turns, starts with user, IDs sNNN_tNN, and contains at least one user turn. Summary is 12-40 words.

For every profile item, copy its frozen plan fields, remove source_session, and add owner_id={assignment['user_id']!r}, subtype="MP_PROFILE", source_turn_ids, literal_source_span. The span must explicitly state the planned field value.
For every preference item, copy its frozen plan fields, remove source_session, and add owner_id={assignment['user_id']!r}, subtype="MP_PREFERENCE", source_turn_ids, literal_source_span. The span must naturally express the planned preference.

Every typed candidate has candidate_id/subtype/session/topic exactly as required plus owner_id, source_turn_ids, literal_source_span, candidate_text (equal to the literal span), entity_ids, resolution_status.
- MS_SESSION additionally has memory_function.
- ME_REUSABLE_OUTCOME has me_tier and nonempty action_span/result_span. For executable_core, use a concrete first-person past action and observed result. For natural_coverage_challenge, keep a valid action-result meaning but use natural varied syntax.
- ME_UNRESOLVED_EVENT has a nonempty action_span and result_span=null.
- ME_CONTEXT_EVENT has action_span=null and result_span=null.

Preserve chronology and owner/entity boundaries. Mention each relationship name or stable role label in a user turn exactly at its first valid session, never earlier."""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def assemble_user(
    assignment: dict[str, Any], world: dict[str, Any], chunks: list[dict[str, Any]]
) -> dict[str, Any]:
    sessions = [row for chunk in chunks for row in chunk["sessions"]]
    profiles = [row for chunk in chunks for row in chunk["profile_history_items"]]
    preferences = [
        row for chunk in chunks for row in chunk["response_preference_history_items"]
    ]
    sessions.sort(key=lambda row: int(row["session_index"]))
    expected_sessions = list(range(1, int(assignment["session_count"]) + 1))
    if [int(row["session_index"]) for row in sessions] != expected_sessions:
        raise ValueError("assembled sessions are not exact and contiguous")
    for item in profiles + preferences:
        item.pop("source_session", None)
    return {
        "protocol": "pm-v1.5-v5.3-formal-longitudinal-user-v1",
        "user_id": assignment["user_id"],
        "content_author": assignment["content_author"],
        "primary_superdomain": assignment["primary_superdomain"],
        "secondary_superdomains": world["secondary_superdomains"],
        "topic_threads": world["topic_threads"],
        "profile_history": profiles,
        "response_preference_history": preferences,
        "relationships": world["relationships"],
        "events": world["events"],
        "sessions": sessions,
    }
