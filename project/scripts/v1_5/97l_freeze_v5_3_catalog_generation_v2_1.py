#!/usr/bin/env python3
"""Freeze the V2.1 catalog contract, 80-user assignments, and 13 sentinels."""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
from pathlib import Path
import random
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import read_json, write_json  # noqa: E402


V2 = ROOT / "data/pm_v1_5_contracts/v5_3_complete_training_data_generation_v2.json"
V21 = ROOT / "data/pm_v1_5_contracts/v5_3_complete_training_data_generation_v2_1.json"
ASSIGNMENTS = ROOT / "data/pm_v1_5_contracts/v5_3_catalog_assignments_v2_1.json"
SENTINELS = ROOT / "data/pm_v1_5_contracts/v5_3_wave1_sentinel_assignments_v2_1.json"
EXISTING = ROOT / "data/pm_v1_5_v5_3_formal_longitudinal_catalog_intake_v1/canonical_users"

DOMAINS = (
    "work_education", "relationships", "family_caregiving", "relocation_culture",
    "sleep_health_energy", "grief_life_transition", "finance_housing",
    "social_identity_creative",
)
SESSION_COUNTS = (13, 15, 17, 19, 21, 23, 25, 27, 30, 33)
GPT_POSITIONS = (
    (0, 2, 4, 6, 8),
    (0, 1, 4, 5, 8),
    (2, 3, 6, 7, 9),
    (0, 2, 5, 6, 9),
    (1, 3, 4, 7, 8),
    (1, 2, 4, 5, 9),
    (0, 3, 6, 7, 8),
    (1, 3, 5, 7, 9),
)
STYLE_PACKS = (
    "direct_short_sentences", "restrained_self_correction", "indirect_body_cues",
    "colloquial_elliptical", "reflective_compound", "matter_of_fact",
    "hesitant_indirect", "metaphoric_but_concrete", "spare_and_reserved",
    "practical_with_uncertainty",
)
SENTINEL_IDS = (
    "p2r_formal_claude_u005",
    "p2r_formal_gpt_u014", "p2r_formal_claude_u010",
    "p2r_formal_gpt_u017", "p2r_formal_claude_u019",
    "p2r_formal_gpt_u020", "p2r_formal_claude_u024",
    "p2r_formal_gpt_u027", "p2r_formal_claude_u025",
    "p2r_formal_gpt_u034", "p2r_formal_claude_u032",
    "p2r_formal_gpt_u039", "p2r_formal_claude_u035",
)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _base_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for domain_index, domain in enumerate(DOMAINS):
        gpt = tuple(sorted(GPT_POSITIONS[domain_index]))
        claude = tuple(sorted(set(range(10)) - set(gpt)))
        for author, prefix, positions in (
            ("chatgpt_pro", "gpt", gpt), ("claude", "claude", claude)
        ):
            for within, position in enumerate(positions):
                ordinal = domain_index * 5 + within
                user_id = f"p2r_formal_{prefix}_u{ordinal:03d}"
                rows.append({
                    "user_id": user_id,
                    "content_author": author,
                    "primary_superdomain": domain,
                    "schedule_position": position,
                    "session_count": SESSION_COUNTS[position],
                    "world_seed": f"v53v21_{_hash(user_id + ':world')[:16]}",
                    "candidate_schedule_seed": f"v53v21_{_hash(user_id + ':candidates')[:16]}",
                })
    return rows


def _allocate_styles(rows: list[dict[str, Any]]) -> None:
    for author in ("chatgpt_pro", "claude"):
        author_rows = sorted(
            (row for row in rows if row["content_author"] == author),
            key=lambda row: _hash(str(row["user_id"]) + ":style"),
        )
        packs = [pack for pack in STYLE_PACKS for _ in range(4)]
        random.Random(int(_hash(author + ":style-allocation"), 16)).shuffle(packs)
        for row, pack in zip(author_rows, packs, strict=True):
            row["style_pack_id"] = pack


def _allocate_updates(rows: list[dict[str, Any]], existing: dict[str, dict[str, Any]]) -> None:
    # Four position/author cells carry four units; the other sixteen carry
    # three.  Thus each author has 32 and the whole catalog has exactly 64,
    # without making update count a deterministic function of history depth.
    four_unit_cells = {(0, "chatgpt_pro"), (1, "claude"), (8, "chatgpt_pro"), (9, "claude")}
    by_cell: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        row["profile_update_count"] = 0
        by_cell[(int(row["schedule_position"]), str(row["content_author"]))].append(row)
    for cell, cell_rows in by_cell.items():
        for row in cell_rows:
            old = existing.get(str(row["user_id"]))
            if old is not None:
                row["profile_update_count"] = sum(
                    item.get("item_role") == "update" for item in old["profile_history"]
                )
                row["grandfathered_existing_user"] = True
            else:
                row["grandfathered_existing_user"] = False
        target = 4 if cell in four_unit_cells else 3
        remaining = target - sum(int(row["profile_update_count"]) for row in cell_rows)
        available = sorted(
            (row for row in cell_rows if not row["grandfathered_existing_user"]),
            key=lambda row: _hash(str(row["user_id"]) + ":updates"),
        )
        while remaining:
            progressed = False
            for row in available:
                if int(row["profile_update_count"]) < 2 and remaining:
                    row["profile_update_count"] += 1
                    remaining -= 1
                    progressed = True
            if not progressed:
                raise RuntimeError(f"profile-update cell is infeasible: {cell}")


def _allocate_preference_versions(rows: list[dict[str, Any]]) -> None:
    eligible = sorted(
        (row for row in rows if not row["grandfathered_existing_user"]),
        key=lambda row: _hash(str(row["user_id"]) + ":preference-version"),
    )
    selected = eligible[:20]
    replacement = {str(row["user_id"]) for row in selected[:10]}
    withdrawal = {str(row["user_id"]) for row in selected[10:]}
    for row in rows:
        user_id = str(row["user_id"])
        row["preference_version_mode"] = (
            "replacement" if user_id in replacement
            else "withdrawal" if user_id in withdrawal
            else "stable"
        )


def build_assignments() -> dict[str, Any]:
    existing = {
        path.stem: read_json(path) for path in sorted(EXISTING.glob("*.json"))
    }
    rows = _base_rows()
    _allocate_styles(rows)
    _allocate_updates(rows, existing)
    _allocate_preference_versions(rows)
    rows.sort(key=lambda row: str(row["user_id"]))

    author_position = Counter(
        (str(row["content_author"]), int(row["schedule_position"])) for row in rows
    )
    if any(author_position[(author, position)] != 4 for author in ("chatgpt_pro", "claude") for position in range(10)):
        raise RuntimeError("author/session-depth Latin balance failed")
    if sum(int(row["profile_update_count"]) for row in rows) != 64:
        raise RuntimeError("profile update total differs from 64")
    if Counter(row["content_author"] for row in rows) != {"chatgpt_pro": 40, "claude": 40}:
        raise RuntimeError("author balance failed")
    if Counter(row["preference_version_mode"] for row in rows) != {
        "stable": 60, "replacement": 10, "withdrawal": 10,
    }:
        raise RuntimeError("preference-version allocation failed")
    return {
        "protocol": "pm-v1.5-v5.3-catalog-assignments-v2-1",
        "status": "FROZEN_BEFORE_NEW_V2_1_CONTENT_GENERATION",
        "contract_protocol": "pm-v1.5-v5.3-complete-training-data-generation-v2-1",
        "assignment_metadata_excluded_from_model_features": True,
        "existing_users_are_grandfathered_not_regenerated": True,
        "rows": rows,
    }


def build_contract() -> dict[str, Any]:
    value = read_json(V2)
    value.update({
        "protocol": "pm-v1.5-v5.3-complete-training-data-generation-v2-1",
        "status": "READY_FOR_REVISED_SENTINEL_GENERATION_NOT_FORMAL_EFFECT_GENERATION",
        "supersedes_v1_and_v2_for_all_new_catalog_generation": True,
        "web_authoring_input_rule": {
            "upload_v1_and_v2_together_allowed": False,
            "single_standalone_v2_1_human_contract_required": True,
            "one_assignment_specific_packet_per_fresh_web_chat": True,
            "world_planner_and_dialogue_realizer_must_use_separate_fresh_chats": True,
        },
        "assignment_manifest": str(ASSIGNMENTS.relative_to(ROOT)),
        "assignment_balance_v2_1": {
            "each_author_users_at_each_schedule_position": 4,
            "profile_update_count_is_an_independent_assignment_field": True,
            "profile_update_total": 64,
            "grandfathered_11_users_keep_their_observed_counts": True,
            "preference_version_modes": {"stable": 60, "replacement": 10, "withdrawal": 10},
            "candidate_session_and_thread_slots_use_private_per_user_seed": True,
        },
        "causal_visibility_v2_1": {
            "full_world_visible_to_dialogue_realizer": False,
            "fresh_chat_required_for_each_world_or_chunk_surface": True,
            "chunk_realizer_receives_only_facts_valid_through_chunk_end": True,
            "future_literal_fact_leakage_is_a_hard_validation_failure": True,
        },
        "split_keys_v2_1": {
            "broad_capability": "must recur across fit/dev/sealed",
            "counterfactual_family": "must remain inside one split",
            "template_cluster": "must remain inside one split",
            "user_id": "must remain inside one split",
            "semantic_family_is_not_a_split_isolation_key": True,
            "complete_broad_family_held_out": "additional transport diagnostic only",
        },
        "machine_gate_v2_1": {
            "qa_transport_bundles_required_for_new_users": [
                "temporal_sequence", "conflict_or_update", "user_model_trajectory",
                "abstention_no_evidence",
            ],
            "nuisance_probe_fields": [
                "content_author", "primary_superdomain", "style_pack_id", "session_count",
                "session_index", "template_cluster",
            ],
            "actual_rank1_and_current_state_are_post_catalog_gates": True,
            "catalog_machine_pass_does_not_equal_training_authorized": True,
        },
    })
    return value


def main() -> None:
    assignments = build_assignments()
    write_json(ASSIGNMENTS, assignments)
    by_id = {row["user_id"]: row for row in assignments["rows"]}
    sentinel_rows = [by_id[user_id] for user_id in SENTINEL_IDS]
    write_json(SENTINELS, {
        "protocol": "pm-v1.5-v5.3-wave1-sentinel-assignments-v2-1",
        "status": "FROZEN_BEFORE_REVISED_SENTINEL_CONTENT_GENERATION",
        "contract_protocol": "pm-v1.5-v5.3-complete-training-data-generation-v2-1",
        "rows": sentinel_rows,
    })
    write_json(V21, build_contract())
    print(f"wrote {V21.relative_to(ROOT)}, {ASSIGNMENTS.relative_to(ROOT)}, {SENTINELS.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
