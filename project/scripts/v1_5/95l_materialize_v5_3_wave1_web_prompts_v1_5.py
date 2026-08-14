#!/usr/bin/env python3
"""Materialize copy/upload-ready Wave-1 web prompts without any API call."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import read_json, write_json  # noqa: E402
from metacom_pm.v1_5_v5_3_wave1_generation import (  # noqa: E402
    chunk_prompt, chunk_ranges, preference_assignments, validate_world, world_prompt,
)


CONTRACT = ROOT / "data/pm_v1_5_contracts/v5_3_complete_training_data_generation_v2_1.json"
ASSIGNMENTS = ROOT / "data/pm_v1_5_contracts/v5_3_wave1_sentinel_assignments_v2_1.json"
EXISTING = ROOT / "data/pm_v1_5_v5_3_formal_longitudinal_catalog_intake_v1/canonical_users"
DEFAULT_OUT = ROOT / "outputs/pm_v1_5_v5_3_wave1_web_prompt_packets_v2_1"


def _surface(messages: list[dict[str, str]]) -> str:
    return "\n\n".join(
        f"===== {row['role'].upper()} MESSAGE =====\n{row['content']}" for row in messages
    ) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--world-json", type=Path)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    rows = read_json(ASSIGNMENTS)["rows"]
    by_id = {row["user_id"]: row for row in rows}
    if args.user_id not in by_id:
        raise RuntimeError("user is not in frozen Wave-1 assignments")
    assignment = by_id[args.user_id]
    preferences = preference_assignments(rows, EXISTING)[args.user_id]
    contract = read_json(CONTRACT)
    targets = contract["catalog_targets"]
    excerpt = {
        "relationships_per_user_schedule": targets["relationships_per_user_schedule"],
        "events_per_user_schedule": targets["events_per_user_schedule"],
    }
    user_dir = args.out_dir / args.user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    (user_dir / "01_world_prompt.txt").write_text(
        _surface(world_prompt(assignment, preferences, excerpt)), encoding="utf-8"
    )
    status = "WORLD_PROMPT_READY"
    files = [str(user_dir / "01_world_prompt.txt")]
    if args.world_json is not None:
        world = read_json(args.world_json)
        validate_world(world, assignment, preferences, excerpt)
        write_json(user_dir / "world.json", world)
        files.append(str(user_dir / "world.json"))
        for index, (start, end) in enumerate(chunk_ranges(int(assignment["session_count"])), 1):
            path = user_dir / f"0{index + 1}_chunk_{index}_prompt.txt"
            path.write_text(
                _surface(chunk_prompt(assignment, world, start, end)), encoding="utf-8"
            )
            files.append(str(path))
        status = "WORLD_VALID_AND_THREE_CHUNK_PROMPTS_READY"
    manifest = {
        "protocol": "pm-v1.5-v5.3-wave1-web-prompt-packet-v2-1",
        "status": status,
        "user_id": args.user_id,
        "assignment": assignment,
        "frozen_preference_types": preferences,
        "fresh_chat_rule": (
            "Run the world prompt in one fresh web chat. Run every materialized "
            "chunk prompt in a separate fresh chat so the realizer cannot retain "
            "the planner's future facts. Never paste V1 or V2 into those chats."
        ),
        "files": files,
        "api_calls": 0,
    }
    write_json(user_dir / "manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
