#!/usr/bin/env python3
"""Zero-API round-trip validation of the staged Wave-1 generation design."""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import canonical_json, read_json, sha256_text, write_json  # noqa: E402
from metacom_pm.v1_5_v5_3_wave1_generation import (  # noqa: E402
    assemble_user, chunk_ranges, validate_world,
)


CONTRACT = ROOT / "data/pm_v1_5_contracts/v5_3_complete_training_data_generation_v2.json"
VALIDATOR = ROOT / "scripts/v1_5/82l_validate_formal_longitudinal_user_v1_5.py"
USERS = ROOT / "data/pm_v1_5_v5_3_formal_longitudinal_catalog_intake_v1/canonical_users"
OUT = ROOT / "outputs/pm_v1_5_v5_3_wave1_staged_design_validation_v1"
SURROGATES = ("p2r_formal_gpt_u000", "p2r_formal_claude_u000")


def _source_session(item: dict[str, Any]) -> int:
    turn_id = str(item["source_turn_ids"][0])
    match = re.fullmatch(r"s(\d{3})_t\d{2}", turn_id)
    if not match:
        raise ValueError(f"invalid source turn id: {turn_id}")
    return int(match.group(1))


def _decompose(user: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    profile_plan = []
    for item in user["profile_history"]:
        row = {key: value for key, value in item.items() if key not in {"subtype", "owner_id", "source_turn_ids", "literal_source_span"}}
        row["source_session"] = _source_session(item)
        profile_plan.append(row)
    preference_plan = []
    for item in user["response_preference_history"]:
        row = {key: value for key, value in item.items() if key not in {"subtype", "owner_id", "source_turn_ids", "literal_source_span"}}
        row["source_session"] = _source_session(item)
        preference_plan.append(row)
    session_plan = [
        {
            "session_index": row["session_index"],
            "relative_time": row["relative_time"],
            "event_ids": row["event_ids"],
            "topic_thread_ids": row["topic_thread_ids"],
            "entity_ids": row["entity_ids"],
            "resolution_status": row["resolution_status"],
            "narrative_goal": row["summary"],
        }
        for row in user["sessions"]
    ]
    world = {
        "secondary_superdomains": user["secondary_superdomains"],
        "topic_threads": user["topic_threads"],
        "relationships": user["relationships"],
        "events": user["events"],
        "profile_plan": profile_plan,
        "preference_plan": preference_plan,
        "session_plan": session_plan,
    }
    chunks = []
    for start, end in chunk_ranges(len(user["sessions"])):
        chunks.append(
            {
                "sessions": [row for row in user["sessions"] if start <= row["session_index"] <= end],
                "profile_history_items": [dict(row) for row in user["profile_history"] if start <= _source_session(row) <= end],
                "response_preference_history_items": [dict(row) for row in user["response_preference_history"] if start <= _source_session(row) <= end],
            }
        )
    return world, chunks


def _inventory(user: dict[str, Any]) -> dict[str, list[str]]:
    return {
        "profiles": sorted(row["item_id"] for row in user["profile_history"]),
        "preferences": sorted(row["item_id"] for row in user["response_preference_history"]),
        "relationships": sorted(row["entity_id"] for row in user["relationships"]),
        "events": sorted(row["event_id"] for row in user["events"]),
        "sessions": [str(row["session_index"]) for row in user["sessions"]],
        "candidates": sorted(
            row["candidate_id"]
            for session in user["sessions"]
            for row in session["typed_candidates"]
        ),
    }


def main() -> None:
    contract = read_json(CONTRACT)
    targets = contract["catalog_targets"]
    excerpt = {
        "relationships_per_user_schedule": targets["relationships_per_user_schedule"],
        "events_per_user_schedule": targets["events_per_user_schedule"],
    }
    if OUT.exists():
        import shutil
        shutil.rmtree(OUT)
    generated = OUT / "reassembled_users"
    generated.mkdir(parents=True)
    rows = []
    for user_id in SURROGATES:
        original = read_json(USERS / f"{user_id}.json")
        schedule_position = 0 if original["content_author"] == "chatgpt_pro" else 1
        assignment = {
            "user_id": user_id,
            "content_author": original["content_author"],
            "primary_superdomain": original["primary_superdomain"],
            "schedule_position": schedule_position,
            "session_count": len(original["sessions"]),
        }
        preferences = [row["preference_type"] for row in original["response_preference_history"]]
        world, chunks = _decompose(original)
        validate_world(world, assignment, preferences, excerpt)
        reassembled = assemble_user(assignment, world, chunks)
        if _inventory(reassembled) != _inventory(original):
            raise RuntimeError(f"round-trip inventory drift for {user_id}")
        output = generated / f"{user_id}.json"
        write_json(output, reassembled)
        rows.append(
            {
                "user_id": user_id,
                "sessions": len(reassembled["sessions"]),
                "chunk_ranges": chunk_ranges(len(reassembled["sessions"])),
                "inventory_sha256": sha256_text(canonical_json(_inventory(reassembled))),
                "world_and_three_chunk_round_trip": True,
            }
        )
    validation = OUT / "official_validator"
    command = [
        sys.executable, str(VALIDATOR), "--input", str(generated),
        "--contract", str(CONTRACT), "--out-dir", str(validation),
    ]
    completed = subprocess.run(
        command, cwd=ROOT, text=True, capture_output=True, check=False,
        env={**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")},
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout)[-3000:])
    validator_report = read_json(validation / "report.json")
    if validator_report["status"] != "MACHINE_PASS_BATCH_AND_SEMANTIC_REVIEW_PENDING":
        raise RuntimeError(f"official validator rejected staged round trip: {validator_report['status']}")
    report = {
        "protocol": "pm-v1.5-v5.3-wave1-staged-design-validation-v1",
        "status": "PASS_ZERO_API_STRUCTURAL_AND_OFFICIAL_VALIDATOR_ROUND_TRIP",
        "surrogate_users": rows,
        "official_validator_status": validator_report["status"],
        "hard_issue_count": sum(row["hard_issue_count"] for row in validator_report["users"]),
        "scope_note": "This validates the staged compiler and validator path, not a promise that a future web-model first draft will pass.",
        "api_calls": 0,
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
