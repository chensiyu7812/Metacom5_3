#!/usr/bin/env python3
"""Materialize the fresh V4 fidelity V2 packet, hidden from all outcomes."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402

PROTOCOL = "pm-v1.5-v5.4-v4-fidelity-v2-packet"
AUTHOR_DIR = ROOT / "outputs/pm_v1_5_v5_4_state_local_authoring_v4_20260810"
PACKET = AUTHOR_DIR / "authoring_v4_packet_private_outcome_blind.jsonl"
AUTHORED_RANK1 = AUTHOR_DIR / "authored_pairs_v4_after_rank1_repair_outcome_blind.jsonl"
AUTHORED_FIDELITY = AUTHOR_DIR / "authored_pairs_v4_after_fidelity_repair_outcome_blind.jsonl"
ASSIGN = AUTHOR_DIR / "construction_assignment_private_do_not_join.jsonl"
RANK1 = ROOT / "outputs/pm_v1_5_v5_4_v4_state_local_actual_rank1_20260810/report.json"
CONTRACT = ROOT / "data/pm_v1_5_contracts/v5_4_state_local_rank1_factorial_oracle_v1.json"
OUT = ROOT / "outputs/pm_v1_5_v5_4_v4_fidelity_v2_20260810"


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    authored_path = AUTHORED_FIDELITY if AUTHORED_FIDELITY.exists() else AUTHORED_RANK1
    source = {row["pair_id"]: row for row in rows(PACKET)}
    authored = {row["pair_id"]: row for row in rows(authored_path)}
    assignment = {row["pair_id"]: row for row in rows(ASSIGN)}
    rank1 = json.loads(RANK1.read_text())
    contract = json.loads(CONTRACT.read_text())
    if set(source) != set(authored) or set(source) != set(assignment) or len(source) != 48:
        raise RuntimeError("V4 fidelity identities incomplete")
    if rank1["status"] != "STATE_LOCAL_RANK1_MACHINE_PASS_AWAITING_FIDELITY":
        raise RuntimeError("state-local Rank-1 gate not passed")
    if not contract["current_authorization"]["fresh_fidelity_review_after_complete_machine_pass"]:
        raise RuntimeError("fresh fidelity review not authorized")
    packet = []
    for pair_id in sorted(source):
        s, a, key = source[pair_id], authored[pair_id], assignment[pair_id]
        packet.append({
            "protocol": PROTOCOL,
            "pair_id": pair_id,
            "semantic_family_id": s["semantic_family_id"],
            "component": s["component"],
            "source_dataset": s["source_dataset"],
            "exact_public_source_prefix": s["exact_public_source_visible_prefix_locked"],
            "original_public_current_turn_world_tone_reference": s["original_current_user_turn_for_world_and_tone_only"],
            "verified_strictly_prior_source_candidate_world_fact_or_card": {
                "text": s["frozen_candidate_text"],
                "typed_metadata": s["frozen_candidate"],
            },
            "variant_A_current_user_turn": a["variant_A_current_user_turn"],
            "variant_B_current_user_turn": a["variant_B_current_user_turn"],
            "variant_A_construction_instruction": s["variant_A_private_instruction"],
            "variant_B_construction_instruction": s["variant_B_private_instruction"],
            "low_mode": key["low_mode"],
            "assistant_move_is_prospective": True,
            "cross_state_same_candidate_required": False,
            "actual_state_local_rank1_identity_visible_to_fidelity_reviewer": False,
            "author_identity_visible": False,
            "response_effect_or_oracle_outcome_visible": False,
            "should_open_question_present": False,
        })
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "fidelity_v2_packet_private_assignment_outcome_blind.jsonl"
    write_jsonl(target, packet)
    report = {
        "protocol": PROTOCOL,
        "status": "V4_FIDELITY_V2_PACKET_FROZEN_READY",
        "pairs": 48,
        "logical_calls": 96,
        "author_identity_visible": False,
        "response_effect_or_oracle_outcome_visible": False,
        "actual_rank1_identity_visible": False,
        "should_open_question_present": False,
        "hashes": {
            "packet": sha256_file(target), "authoring_plan": sha256_file(PACKET),
            "authored": sha256_file(authored_path), "assignment": sha256_file(ASSIGN),
            "authored_surface": str(authored_path.relative_to(ROOT)),
            "rank1_report": sha256_file(RANK1), "contract": sha256_file(CONTRACT),
        },
        "api_calls": 0,
    }
    write_json(OUT / "packet_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
