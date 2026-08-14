#!/usr/bin/env python3
"""Materialize the V4 state-local Rank-1 authoring plan without outcomes."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, stable_hex, write_json, write_jsonl  # noqa: E402


PROTOCOL = "pm-v1.5-v5.4-state-local-rank1-authoring-v4-plan"
V3 = ROOT / "outputs/pm_v1_5_v5_4_rank1_stable_authoring_v3_20260810"
V3_PACKET = V3 / "authoring_v3_packet_private_outcome_blind.jsonl"
V3_ASSIGN = V3 / "construction_assignment_private_do_not_join.jsonl"
CONTRACT = ROOT / "data/pm_v1_5_contracts/v5_4_state_local_rank1_factorial_oracle_v1.json"
OUT = ROOT / "outputs/pm_v1_5_v5_4_state_local_authoring_v4_20260810"


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    contract = json.loads(CONTRACT.read_text())
    if not contract["current_authorization"]["outcome_blind_v4_state_authoring"]:
        raise RuntimeError("V4 authoring not authorized")
    old_packet = _rows(V3_PACKET)
    old_assign = {row["pair_id"]: row for row in _rows(V3_ASSIGN)}
    packet = []
    assignments = []
    for row in old_packet:
        old_id = row["pair_id"]
        assignment = old_assign[old_id]
        family_id = "v54v4fam_" + stable_hex(PROTOCOL, row["source_formal_effect_group_id"], n=18)
        pair_id = "v54v4pair_" + stable_hex(PROTOCOL, family_id, n=18)
        copied = dict(row)
        copied.update({
            "protocol": PROTOCOL,
            "pair_id": pair_id,
            "semantic_family_id": family_id,
            "source_v3_pair_id_for_anchor_lineage_only": old_id,
            "cross_state_same_candidate_required": False,
            "state_local_candidate_availability_required_each_variant": True,
            "state_local_candidate_materialized_only_after_current_turn": True,
            "source_candidate_role": "verified world/semantic authoring anchor only; not the post-authoring execution identity",
            "paired_response_effect_or_oracle_outcome_visible": False,
        })
        copied.pop("shared_retrieval_stability_requirement", None)
        packet.append(copied)
        assignments.append({
            **assignment,
            "protocol": PROTOCOL,
            "pair_id": pair_id,
            "semantic_family_id": family_id,
            "source_v3_pair_id_for_lineage_only": old_id,
        })
    checks = {
        "48_pairs": len(packet) == 48,
        "48_unique": len({row["pair_id"] for row in packet}) == 48,
        "12_per_component": Counter(row["component"] for row in packet) == Counter({key: 12 for key in ("MP", "MS", "ME", "RS")}),
        "24_per_author": Counter(row["assigned_author_endpoint"] for row in packet) == Counter({"anthropic_claude_haiku_4_5": 24, "openai_gpt_5_mini": 24}),
        "rs_move_already_performed_zero": all(row["low_mode"] != "MOVE_ALREADY_PERFORMED" for row in assignments),
        "cross_state_candidate_identity_not_required": all(not row["cross_state_same_candidate_required"] for row in packet),
        "state_local_candidate_required": all(row["state_local_candidate_availability_required_each_variant"] for row in packet),
        "outcomes_hidden": all(not row["paired_response_effect_or_oracle_outcome_visible"] for row in packet),
    }
    if not all(checks.values()):
        raise RuntimeError(f"V4 plan checks failed: {checks}")
    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "authoring_v4_packet_private_outcome_blind.jsonl", packet)
    write_jsonl(OUT / "construction_assignment_private_do_not_join.jsonl", assignments)
    report = {
        "protocol": PROTOCOL,
        "status": "V4_STATE_LOCAL_AUTHORING_PLAN_FROZEN_ZERO_API",
        "checks": checks,
        "pairs": 48,
        "variants": 96,
        "causal_invariance": "candidate identity must be fixed across 16 action arms within one completed state; it need not equal another state's candidate",
        "response_effect_calls": 0,
        "private_historical_outcome_read": False,
        "source_hashes": {
            "v3_packet": sha256_file(V3_PACKET),
            "v3_assignments": sha256_file(V3_ASSIGN),
            "state_local_contract": sha256_file(CONTRACT),
        },
    }
    write_json(OUT / "plan_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
