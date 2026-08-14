from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from metacom_pm.v1_5_v5_3_wave1_generation import candidate_requirements, chunk_prompt


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "data/pm_v1_5_contracts/v5_3_complete_training_data_generation_v2_1.json"
ASSIGNMENTS = ROOT / "data/pm_v1_5_contracts/v5_3_catalog_assignments_v2_1.json"
SENTINELS = ROOT / "data/pm_v1_5_contracts/v5_3_wave1_sentinel_assignments_v2_1.json"
INTEGRATED = ROOT / "data/pm_v1_5_contracts/v5_3_integrated_evidence_execution_v1.json"


def test_v21_is_the_only_web_authoring_contract() -> None:
    value = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert value["supersedes_v1_and_v2_for_all_new_catalog_generation"] is True
    assert value["web_authoring_input_rule"]["upload_v1_and_v2_together_allowed"] is False
    assert value["causal_visibility_v2_1"]["full_world_visible_to_dialogue_realizer"] is False


def test_assignment_breaks_author_depth_and_update_depth_confounding() -> None:
    rows = json.loads(ASSIGNMENTS.read_text(encoding="utf-8"))["rows"]
    assert len(rows) == 80
    cells = Counter((row["content_author"], row["schedule_position"]) for row in rows)
    assert set(cells.values()) == {4}
    assert sum(row["profile_update_count"] for row in rows) == 64
    for position in range(10):
        assert len({row["profile_update_count"] for row in rows if row["schedule_position"] == position}) >= 2
    assert Counter(row["preference_version_mode"] for row in rows) == {
        "stable": 60, "replacement": 10, "withdrawal": 10,
    }


def test_revised_sentinels_cover_short_medium_and_long_histories() -> None:
    rows = json.loads(SENTINELS.read_text(encoding="utf-8"))["rows"]
    assert len(rows) == 13
    assert len({row["primary_superdomain"] for row in rows}) == 7
    assert {row["content_author"] for row in rows} == {"chatgpt_pro", "claude"}
    positions = {row["schedule_position"] for row in rows}
    assert positions & {0, 1, 2, 3}
    assert positions & {4, 5, 6, 7}
    assert positions & {8, 9}


def test_integrated_split_keys_isolate_templates_not_broad_capabilities() -> None:
    data = json.loads(INTEGRATED.read_text(encoding="utf-8"))["data"]
    assert data["split_keys"] == [
        "synthetic_user", "counterfactual_family", "template_cluster",
    ]
    assert data["semantic_family_is_not_a_split_isolation_key"] is True
    assert data["broad_capability_must_recur_across_fit_confirmation_sealed"] is True


def test_candidate_slots_are_seeded_not_fixed_by_subtype() -> None:
    first = candidate_requirements("u1", ["t0", "t1", "t2", "t3"], 13, "seed-a")
    repeat = candidate_requirements("u1", ["t0", "t1", "t2", "t3"], 13, "seed-a")
    second = candidate_requirements("u2", ["t0", "t1", "t2", "t3"], 13, "seed-b")
    assert first == repeat
    assert [(r["subtype"], r["session_index"]) for r in first] != [
        (r["subtype"], r["session_index"]) for r in second
    ]
    by_thread: dict[str, set[str]] = {}
    for row in first:
        if row["subtype"].startswith("ME_"):
            by_thread.setdefault(row["topic_thread"], set()).add(row["subtype"])
    assert len(by_thread) == 4
    assert all("ME_REUSABLE_OUTCOME" in roles for roles in by_thread.values())
    assert all(roles & {"ME_UNRESOLVED_EVENT", "ME_CONTEXT_EVENT"} for roles in by_thread.values())


def test_chunk_prompt_excludes_post_boundary_world_facts() -> None:
    assignment = {
        "user_id": "u", "session_count": 13, "candidate_schedule_seed": "s",
    }
    world = {
        "secondary_superdomains": ["x", "y"],
        "topic_threads": [{"thread_id": f"t{i}", "label": f"T{i}"} for i in range(4)],
        "relationships": [
            {"entity_id": "early", "name": "Early", "valid_from_session": 1, "valid_until_session": None},
            {"entity_id": "future", "name": "FUTURE_NAME", "valid_from_session": 10, "valid_until_session": None},
        ],
        "events": [
            {"event_id": "e1", "session_index": 1},
            {"event_id": "e10", "session_index": 10, "description": "FUTURE_EVENT"},
        ],
        "profile_plan": [{"item_id": "p", "source_session": 1}],
        "preference_plan": [{"item_id": "r", "source_session": 1}],
        "session_plan": [
            {"session_index": i, "event_ids": ["e1"] if i == 1 else [], "topic_thread_ids": ["t0"]}
            for i in range(1, 14)
        ],
    }
    surface = chunk_prompt(assignment, world, 1, 5)[1]["content"]
    assert "FUTURE_NAME" not in surface
    assert "FUTURE_EVENT" not in surface
