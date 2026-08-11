#!/usr/bin/env python3
"""Materialize source-prefix-locked, user-turn-only V5.4 authoring V2."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402


PROTOCOL = "pm-v1.5-v5.4-source-prefix-locked-authoring-v2-plan"
V1_DIR = ROOT / "outputs/pm_v1_5_v5_4_state_variant_authoring_20260810"
V1_PACKET = V1_DIR / "authoring_packet_private.jsonl"
V1_ASSIGNMENT = V1_DIR / "construction_assignment_private_do_not_join_to_pm_features.jsonl"
CONTRACT = ROOT / "data/pm_v1_5_contracts/v5_4_factorial_outcome_oracle_learning_v1.json"
OUT = ROOT / "outputs/pm_v1_5_v5_4_source_prefix_locked_authoring_v2_20260810"


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    contract = json.loads(CONTRACT.read_text())
    if contract["current_authorization"].get("only_authorized_authoring_revision") != "source-prefix-locked current-user-turn-only V2":
        raise RuntimeError("source-prefix-locked V2 is not the sole authorized authoring revision")
    v1 = _jsonl(V1_PACKET)
    assignments = {str(row["pair_id"]): row for row in _jsonl(V1_ASSIGNMENT)}
    packet = []
    prefix_lengths = Counter()
    for item in v1:
        dialogue = list(item["anchor_visible_dialogue_for_tone_and_world_fidelity"])
        if not dialogue or dialogue[-1]["role"] != "user":
            raise RuntimeError(f"{item['pair_id']} public anchor does not end in current user")
        prefix = dialogue[:-1]
        assignment = assignments[str(item["pair_id"])]
        packet.append({
            "protocol": PROTOCOL,
            "pair_id": item["pair_id"],
            "semantic_family_id": item["semantic_family_id"],
            "component": item["component"],
            "assigned_author_endpoint": item["assigned_author_endpoint"],
            "source_dataset": item["source_dataset"],
            "exact_public_source_visible_prefix_locked": prefix,
            "source_prefix_lock_attested": True,
            "original_current_user_turn_for_world_and_tone_only": dialogue[-1]["content"],
            "frozen_candidate": item["frozen_candidate"],
            "frozen_candidate_text": item["frozen_candidate_text"],
            "variant_A_private_instruction": item["variant_role_A_private_author_instruction"],
            "variant_B_private_instruction": item["variant_role_B_private_author_instruction"],
            "output_task": {
                "variant_A_current_user_turn": "Return one natural user turn continuing the exact locked prefix and satisfying private role A.",
                "variant_B_current_user_turn": "Return one natural user turn continuing the exact locked prefix and satisfying private role B.",
                "minimal_pair": "Reuse the same syntactic frame, user, entity, topic, goal wording, tone, and approximate length. Change only the specific response-need, redundancy, or boundary factor named by the private roles.",
            },
            "machine_surface_gates": {
                "each_turn_words": "8-80",
                "word_length_ratio_max": 1.5,
                "normalized_character_similarity_min": 0.25,
                "exact_turns_must_differ": True,
                "source_prefix_must_be_byte_unchanged": True,
                "candidate_full_text_copy_forbidden": True,
                "scaffold_and_assignment_terms_forbidden": True,
            },
            "construction_assignment_is_value_gold": False,
            "response_effect_quality_risk_function_oracle_visible": False,
            "actual_rank1_recomputation_required_after_authoring": True,
            "development_only": True,
        })
        prefix_lengths[len(prefix)] += 1
        if assignment["exclude_from_pm_features_generator_and_effect_judges"] is not True:
            raise RuntimeError("private assignment exclusion changed")
    checks = {
        "48_pairs": len(packet) == 48,
        "48_unique_ids": len({row["pair_id"] for row in packet}) == 48,
        "12_per_component": Counter(row["component"] for row in packet) == Counter({"MP": 12, "MS": 12, "ME": 12, "RS": 12}),
        "24_per_author": Counter(row["assigned_author_endpoint"] for row in packet) == Counter({"anthropic_claude_haiku_4_5": 24, "openai_gpt_5_mini": 24}),
        "all_prefixes_materialized_from_anchor_slice": all(row["source_prefix_lock_attested"] for row in packet),
        "no_generated_assistant_field": all(set(row["output_task"]) == {"variant_A_current_user_turn", "variant_B_current_user_turn", "minimal_pair"} for row in packet),
        "all_outcomes_hidden": all(not row["response_effect_quality_risk_function_oracle_visible"] for row in packet),
    }
    if not all(checks.values()):
        raise RuntimeError(f"V2 authoring plan checks failed: {checks}")
    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "source_prefix_locked_authoring_packet_private.jsonl", packet)
    write_jsonl(OUT / "construction_assignment_private_do_not_join_to_pm_features.jsonl", _jsonl(V1_ASSIGNMENT))
    report = {
        "protocol": PROTOCOL,
        "status": "SOURCE_PREFIX_LOCKED_V2_PLAN_COMPLETE_ZERO_API",
        "checks": checks,
        "pairs": len(packet),
        "planned_variants": 2 * len(packet),
        "prefix_turn_count_distribution": dict(prefix_lengths),
        "v1_packet_sha256": sha256_file(V1_PACKET),
        "v1_assignment_sha256": sha256_file(V1_ASSIGNMENT),
        "contract_sha256": sha256_file(CONTRACT),
        "generated_assistant_turns": 0,
        "response_effect_or_judge_calls": 0,
        "api_calls": 0,
    }
    write_json(OUT / "source_prefix_locked_v2_plan_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
