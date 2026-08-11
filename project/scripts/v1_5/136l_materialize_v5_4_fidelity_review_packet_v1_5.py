#!/usr/bin/env python3
"""Materialize the frozen, outcome-blind dual-reviewer fidelity packet."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402

PROTOCOL = "pm-v1.5-v5.4-fidelity-review-packet-v1"
DIR = ROOT / "outputs/pm_v1_5_v5_4_source_prefix_locked_authoring_v2_20260810"
AUTHOR_PACKET = DIR / "source_prefix_locked_authoring_packet_private.jsonl"
AUTHORED = DIR / "authored_pairs_source_prefix_locked_outcome_blind.jsonl"
ASSIGNMENT = DIR / "construction_assignment_private_do_not_join_to_pm_features.jsonl"
MACHINE_AUDIT = DIR / "authoring_v2_machine_audit_report.json"
CONTRACT = ROOT / "data/pm_v1_5_contracts/v5_4_fidelity_and_rank1_gate_v1.json"
OUT = ROOT / "outputs/pm_v1_5_v5_4_fidelity_review_20260810"


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    authored = {row["pair_id"]: row for row in rows(AUTHORED)}; source = {row["pair_id"]: row for row in rows(AUTHOR_PACKET)}; assignments = {row["pair_id"]: row for row in rows(ASSIGNMENT)}
    audit = json.loads(MACHINE_AUDIT.read_text()); contract = json.loads(CONTRACT.read_text())
    if audit["status"] != "V2_MACHINE_AUDIT_PASS_AWAITING_INDEPENDENT_FIDELITY_AND_RANK1" or len(authored) != 48 or set(authored) != set(source) != set():
        if len(authored) != 48 or set(authored) != set(source) or set(source) != set(assignments): raise RuntimeError("fidelity input identity mismatch")
    if not contract["downstream_authorization"]["fidelity_review"]: raise RuntimeError("fidelity review not authorized")
    packet = []
    for pair_id in sorted(authored):
        a = authored[pair_id]; s = source[pair_id]; key = assignments[pair_id]
        packet.append({"protocol": PROTOCOL, "pair_id": pair_id, "semantic_family_id": a["semantic_family_id"], "component": a["component_private_lineage"], "source_dataset": a["source_dataset"], "exact_public_source_prefix": a["exact_public_source_visible_prefix_locked"], "original_current_user_turn_world_tone_reference": s["original_current_user_turn_for_world_and_tone_only"], "verified_strictly_prior_candidate": {"text": a["frozen_candidate_text"], "typed_metadata": a["frozen_candidate"]}, "variant_A_current_user_turn": a["variant_A_current_user_turn"], "variant_B_current_user_turn": a["variant_B_current_user_turn"], "variant_A_construction_instruction": s["variant_A_private_instruction"], "variant_B_construction_instruction": s["variant_B_private_instruction"], "low_mode": key["low_mode"], "author_identity_visible": False, "response_or_outcome_visible": False, "should_open_question_present": False})
    OUT.mkdir(parents=True, exist_ok=True); write_jsonl(OUT / "fidelity_packet_private_assignment_outcome_blind.jsonl", packet)
    report = {"protocol": PROTOCOL, "status": "FIDELITY_PACKET_FROZEN_READY", "pairs": len(packet), "reviewers_planned": 2, "logical_calls": 96, "author_identity_visible": False, "response_or_outcome_visible": False, "should_open_question_present": False, "author_packet_sha256": sha256_file(AUTHOR_PACKET), "authored_sha256": sha256_file(AUTHORED), "assignment_sha256": sha256_file(ASSIGNMENT), "machine_audit_sha256": sha256_file(MACHINE_AUDIT), "contract_sha256": sha256_file(CONTRACT), "api_calls": 0}
    write_json(OUT / "fidelity_packet_report.json", report); print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
