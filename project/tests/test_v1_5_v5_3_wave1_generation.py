from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re

import pytest

from metacom_pm.v1_5_v5_3_wave1_generation import (
    candidate_requirements,
    chunk_ranges,
    preference_assignments,
    validate_world,
)


ROOT = Path(__file__).resolve().parents[1]


def test_chunk_ranges_are_exact_and_contiguous() -> None:
    assert chunk_ranges(13) == ((1, 5), (6, 9), (10, 13))
    assert chunk_ranges(15) == ((1, 5), (6, 10), (11, 15))


def test_candidate_requirements_have_exact_per_user_contract() -> None:
    rows = candidate_requirements("u", ["t0", "t1", "t2", "t3"], 13)
    subtypes = Counter(row["subtype"] for row in rows)
    tiers = Counter(row.get("me_tier") for row in rows)
    assert subtypes == {
        "MS_SESSION": 8,
        "ME_REUSABLE_OUTCOME": 10,
        "ME_UNRESOLVED_EVENT": 5,
        "ME_CONTEXT_EVENT": 4,
    }
    assert tiers["executable_core"] == 8
    assert tiers["natural_coverage_challenge"] == 2
    assert len({row["candidate_id"] for row in rows}) == 27
    assert all(1 <= row["session_index"] <= 13 for row in rows)


def test_wave1_preferences_preserve_final_quota_reachability() -> None:
    assignments = json.loads(
        (
            ROOT
            / "data/pm_v1_5_contracts/v5_3_wave1_sentinel_assignments_v1.json"
        ).read_text(encoding="utf-8")
    )["rows"]
    existing = (
        ROOT
        / "data/pm_v1_5_v5_3_formal_longitudinal_catalog_intake_v1/canonical_users"
    )
    result = preference_assignments(assignments, existing)
    assert set(result) == {row["user_id"] for row in assignments}
    assert all(len(value) == 3 and len(set(value)) == 3 for value in result.values())

    counts = {"chatgpt_pro": Counter(), "claude": Counter()}
    user_counts = Counter()
    for path in existing.glob("*.json"):
        row = json.loads(path.read_text(encoding="utf-8"))
        counts[row["content_author"]].update(
            item["preference_type"] for item in row["response_preference_history"]
        )
        user_counts[row["content_author"]] += 1
    for row in assignments:
        counts[row["content_author"]].update(result[row["user_id"]])
        user_counts[row["content_author"]] += 1
    for author in counts:
        remaining_users = 40 - user_counts[author]
        assert all(0 <= 20 - count <= remaining_users for count in counts[author].values())


def test_wave1a_and_wave1b_are_an_exact_partition_of_frozen_wave1() -> None:
    def ids(name: str) -> list[str]:
        return [
            row["user_id"]
            for row in json.loads((ROOT / "data/pm_v1_5_contracts" / name).read_text(encoding="utf-8"))["rows"]
        ]

    full = ids("v5_3_wave1_sentinel_assignments_v1.json")
    canary = ids("v5_3_wave1a_canary_assignments_v1.json")
    scale = ids("v5_3_wave1b_scale_assignments_v1.json")
    assert canary == ["p2r_formal_gpt_u010", "p2r_formal_claude_u005"]
    assert len(scale) == 11
    assert len(set(canary + scale)) == 13
    assert set(canary + scale) == set(full)


def test_world_validation_rejects_unknown_cross_references() -> None:
    user = json.loads(
        (
            ROOT
            / "data/pm_v1_5_v5_3_formal_longitudinal_catalog_intake_v1/canonical_users/p2r_formal_gpt_u000.json"
        ).read_text(encoding="utf-8")
    )

    def source_session(item: dict) -> int:
        return int(re.fullmatch(r"s(\d{3})_t\d{2}", item["source_turn_ids"][0]).group(1))

    def plan_item(item: dict, excluded: set[str]) -> dict:
        row = {key: value for key, value in item.items() if key not in excluded}
        row["source_session"] = source_session(item)
        return row

    world = {
        "secondary_superdomains": user["secondary_superdomains"],
        "topic_threads": user["topic_threads"],
        "relationships": user["relationships"],
        "events": user["events"],
        "profile_plan": [
            plan_item(item, {"subtype", "owner_id", "source_turn_ids", "literal_source_span"})
            for item in user["profile_history"]
        ],
        "preference_plan": [
            {
                **plan_item(item, {"subtype", "owner_id", "source_turn_ids", "literal_source_span"}),
                "supersedes_item_id": None,
            }
            for item in user["response_preference_history"]
        ],
        "session_plan": [
            {
                "session_index": item["session_index"],
                "relative_time": item["relative_time"],
                "event_ids": item["event_ids"],
                "topic_thread_ids": list(item["topic_thread_ids"]),
                "entity_ids": item["entity_ids"],
                "resolution_status": item["resolution_status"],
                "narrative_goal": item["summary"],
            }
            for item in user["sessions"]
        ],
        "qa_transport_bundles": [
            {"bundle_type": "temporal_sequence", "evidence_session_indices": [1, 2]},
            {"bundle_type": "conflict_or_update", "evidence_session_indices": [1, 2]},
            {"bundle_type": "user_model_trajectory", "evidence_session_indices": [1, 2]},
            {"bundle_type": "abstention_no_evidence", "evidence_session_indices": []},
        ],
    }
    contract = json.loads(
        (ROOT / "data/pm_v1_5_contracts/v5_3_complete_training_data_generation_v2.json").read_text(encoding="utf-8")
    )
    excerpt = {
        "relationships_per_user_schedule": contract["catalog_targets"]["relationships_per_user_schedule"],
        "events_per_user_schedule": contract["catalog_targets"]["events_per_user_schedule"],
    }
    assignment = {
        "user_id": user["user_id"],
        "content_author": user["content_author"],
        "primary_superdomain": user["primary_superdomain"],
        "schedule_position": 0,
        "session_count": 13,
        "profile_update_count": 2,
        "preference_version_mode": "stable",
    }
    preferences = [item["preference_type"] for item in user["response_preference_history"]]
    validate_world(world, assignment, preferences, excerpt)
    world["session_plan"][0]["topic_thread_ids"].append("missing_thread")
    with pytest.raises(ValueError, match="unknown threads"):
        validate_world(world, assignment, preferences, excerpt)
