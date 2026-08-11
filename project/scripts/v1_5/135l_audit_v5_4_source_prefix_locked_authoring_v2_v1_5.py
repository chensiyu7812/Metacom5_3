#!/usr/bin/env python3
"""Machine-audit and de-label source-prefix-locked V5.4 authoring V2."""

from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402


PROTOCOL = "pm-v1.5-v5.4-source-prefix-locked-authoring-v2-machine-audit"
DIR = ROOT / "outputs/pm_v1_5_v5_4_source_prefix_locked_authoring_v2_20260810"
PACKET = DIR / "source_prefix_locked_authoring_packet_private.jsonl"
AUTHORED = DIR / "authored_pairs_source_prefix_locked_outcome_blind.jsonl"
ASSIGNMENT = DIR / "construction_assignment_private_do_not_join_to_pm_features.jsonl"
RUNTIME = DIR / "runtime_visible_variants_unlabeled.jsonl"
SCAFFOLD = ("candidate_text", "resource_id", "low_opportunity", "incremental:", "construction assignment", "oracle action")


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", text.lower()))


def main() -> None:
    packet = {str(row["pair_id"]): row for row in _jsonl(PACKET)}
    authored_rows = _jsonl(AUTHORED); authored = {str(row["pair_id"]): row for row in authored_rows}
    assignments = {str(row["pair_id"]): row for row in _jsonl(ASSIGNMENT)}
    prefix_mismatch = []; candidate_copy = []; scaffold = []; original_turn_copy = []; pair_surface_fail = []; runtime_rows = []; surfaces = {}
    for pair_id, row in authored.items():
        item = packet[pair_id]
        if row["exact_public_source_visible_prefix_locked"] != item["exact_public_source_visible_prefix_locked"] or row.get("source_prefix_generated_or_modified") is not False:
            prefix_mismatch.append(pair_id)
        a = str(row["variant_A_current_user_turn"]); b = str(row["variant_B_current_user_turn"]); aw, bw = len(a.split()), len(b.split())
        similarity = SequenceMatcher(None, _norm(a), _norm(b)).ratio(); length_ratio = max(aw, bw) / max(1, min(aw, bw))
        if a == b or similarity < .25 or length_ratio > 1.5 or not 8 <= aw <= 80 or not 8 <= bw <= 80: pair_surface_fail.append(pair_id)
        if _norm(str(item["frozen_candidate_text"])) in _norm(a + " " + b): candidate_copy.append(pair_id)
        if any(token in (a + " " + b).lower() for token in SCAFFOLD): scaffold.append(pair_id)
        original = _norm(str(item["original_current_user_turn_for_world_and_tone_only"]))
        if _norm(a) == original: original_turn_copy.append({"pair_id": pair_id, "variant": "A", "assignment": assignments[pair_id]["variant_A_assignment"]})
        if _norm(b) == original: original_turn_copy.append({"pair_id": pair_id, "variant": "B", "assignment": assignments[pair_id]["variant_B_assignment"]})
        for name, text in (("A", a), ("B", b)):
            variant_id = pair_id + "_" + name.lower(); visible = item["exact_public_source_visible_prefix_locked"] + [{"role": "user", "content": text}]
            surface = _norm(" ".join(turn["content"] for turn in visible)); surfaces.setdefault(surface, []).append(variant_id)
            runtime_rows.append({"protocol": PROTOCOL, "variant_id": variant_id, "pair_id": pair_id, "semantic_family_id": row["semantic_family_id"], "source_dataset": row["source_dataset"], "component": row["component_private_lineage"], "visible_dialogue": visible, "current_user_text": text, "frozen_source_candidate": row["frozen_candidate"], "frozen_source_candidate_text": row["frozen_candidate_text"], "construction_assignment_present": False, "effect_quality_risk_function_oracle_outcome_present": False, "source_prefix_modified": False, "actual_rank1_recomputation_status": "PENDING", "independent_fidelity_review_status": "PENDING"})
    duplicates = [ids for ids in surfaces.values() if len(ids) > 1]
    components = Counter(row["component_private_lineage"] for row in authored_rows); authors = Counter(row["assigned_author_endpoint"] for row in authored_rows)
    original_copy_assignments = Counter(row["assignment"] for row in original_turn_copy)
    original_copy_nuisance_gate = (
        len(original_turn_copy) / max(1, len(authored_rows)) <= 0.10
        and original_copy_assignments.get("INCREMENTAL", 0) == original_copy_assignments.get("LOW_OPPORTUNITY", 0)
    )
    checks = {
        "48_unique_complete_pairs": len(authored_rows) == len(authored) == 48 and set(authored) == set(packet),
        "private_assignment_complete_and_separate": set(assignments) == set(packet),
        "12_pairs_per_component": components == Counter({"MP": 12, "MS": 12, "ME": 12, "RS": 12}),
        "24_pairs_per_author": authors == Counter({"anthropic_claude_haiku_4_5": 24, "openai_gpt_5_mini": 24}),
        "source_prefix_byte_structure_unchanged": not prefix_mismatch,
        "generated_assistant_turns_zero": all(row.get("source_prefix_generated_or_modified") is False for row in authored_rows),
        "minimal_pair_surface_gates_pass": not pair_surface_fail,
        "candidate_exact_copy_zero": not candidate_copy,
        "scaffold_leak_zero": not scaffold,
        "original_current_turn_copy_rate_at_most_0_10_and_assignment_balanced": original_copy_nuisance_gate,
        "runtime_exact_duplicate_zero": not duplicates,
        "runtime_rows_two_per_pair": len(runtime_rows) == 96,
        "runtime_assignment_and_outcome_absent": all(not row["construction_assignment_present"] and not row["effect_quality_risk_function_oracle_outcome_present"] for row in runtime_rows),
    }
    status = "V2_MACHINE_AUDIT_PASS_AWAITING_INDEPENDENT_FIDELITY_AND_RANK1" if all(checks.values()) else "V2_MACHINE_AUDIT_FAIL"
    write_jsonl(RUNTIME, runtime_rows)
    report = {"protocol": PROTOCOL, "status": status, "checks": checks, "pairs": len(authored), "runtime_variants": len(runtime_rows), "components": dict(components), "authors": dict(authors), "prefix_mismatch_ids": prefix_mismatch, "pair_surface_fail_ids": pair_surface_fail, "candidate_copy_ids": candidate_copy, "scaffold_leak_ids": scaffold, "original_turn_copy_records": original_turn_copy, "original_turn_copy_assignment_counts": dict(original_copy_assignments), "original_turn_copy_rate": len(original_turn_copy) / max(1, len(authored_rows)), "duplicate_groups": duplicates, "assignment_joined_to_runtime": False, "independent_fidelity_review_run": False, "actual_rank1_recomputed": False, "representation_observability_run": False, "response_effect_or_judge_calls": 0, "private_paired_outcome_key_read": False, "authored_sha256": sha256_file(AUTHORED), "runtime_sha256": sha256_file(RUNTIME)}
    write_json(DIR / "authoring_v2_machine_audit_report.json", report)
    print(json.dumps({"status": status, "pairs": report["pairs"], "runtime_variants": report["runtime_variants"], "checks": checks}, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
