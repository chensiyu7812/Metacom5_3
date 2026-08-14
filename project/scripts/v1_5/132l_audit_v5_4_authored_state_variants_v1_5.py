#!/usr/bin/env python3
"""Materialize unlabeled runtime variants and machine-audit V5.4 authoring."""

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


PROTOCOL = "pm-v1.5-v5.4-authored-state-variant-machine-audit-v1"
DIR = ROOT / "outputs/pm_v1_5_v5_4_state_variant_authoring_20260810"
AUTHORED = DIR / "authored_pairs_outcome_blind.jsonl"
PACKET = DIR / "authoring_packet_private.jsonl"
ASSIGNMENT = DIR / "construction_assignment_private_do_not_join_to_pm_features.jsonl"
RUNTIME = DIR / "runtime_visible_variants_unlabeled.jsonl"
COMPONENTS = ("MP", "MS", "ME", "RS")
SCAFFOLD = ("low_opportunity", "incremental:", "candidate_text", "resource_id", "construction assignment", "oracle action")


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _normalized(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", text.lower()))


def _ngrams(text: str, n: int = 8) -> set[tuple[str, ...]]:
    tokens = _normalized(text).split()
    return {tuple(tokens[i:i+n]) for i in range(max(0, len(tokens) - n + 1))}


def main() -> None:
    authored = _jsonl(AUTHORED)
    packet = {str(row["pair_id"]): row for row in _jsonl(PACKET)}
    private_assignments = {str(row["pair_id"]): row for row in _jsonl(ASSIGNMENT)}
    if len(authored) != len({row["pair_id"] for row in authored}):
        raise RuntimeError("duplicate authored pair ids")
    runtime_rows = []
    surfaces: list[tuple[str, str]] = []
    pair_metrics = []
    source_assistant = {
        _normalized(turn["content"])
        for item in packet.values()
        for turn in item["anchor_visible_dialogue_for_tone_and_world_fidelity"]
        if turn["role"] == "assistant"
    }
    source_assistant_8grams = set().union(*(_ngrams(text) for text in source_assistant)) if source_assistant else set()
    copied_source_assistant_exact = []
    copied_source_assistant_8gram = []
    scaffold_leaks = []
    candidate_exact_copies = []
    for row in authored:
        pair_id = str(row["pair_id"]); item = packet[pair_id]
        prefix = row["shared_prefix"]
        assistant_text = str(prefix[-1]["content"])
        if _normalized(assistant_text) in source_assistant:
            copied_source_assistant_exact.append(pair_id)
        if _ngrams(assistant_text) & source_assistant_8grams:
            copied_source_assistant_8gram.append(pair_id)
        a = str(row["variant_A_current_user_turn"]); b = str(row["variant_B_current_user_turn"])
        combined = " ".join(turn["content"] for turn in prefix) + " " + a + " " + b
        if any(token in combined.lower() for token in SCAFFOLD):
            scaffold_leaks.append(pair_id)
        if _normalized(str(row["frozen_candidate_text"])) in _normalized(combined):
            candidate_exact_copies.append(pair_id)
        ratio = SequenceMatcher(None, _normalized(a), _normalized(b)).ratio()
        length_ratio = max(len(a.split()), len(b.split())) / max(1, min(len(a.split()), len(b.split())))
        pair_metrics.append({"pair_id": pair_id, "component": row["component_private_lineage"], "character_similarity": ratio, "word_length_ratio": length_ratio})
        for variant_name, current_text in (("A", a), ("B", b)):
            runtime_rows.append({
                "protocol": PROTOCOL,
                "variant_id": pair_id + "_" + variant_name.lower(),
                "pair_id": pair_id,
                "semantic_family_id": row["semantic_family_id"],
                "source_dataset": row["source_dataset"],
                "component": row["component_private_lineage"],
                "visible_dialogue": prefix + [{"role": "user", "content": current_text}],
                "current_user_text": current_text,
                "frozen_source_candidate": row["frozen_candidate"],
                "frozen_source_candidate_text": row["frozen_candidate_text"],
                "construction_assignment_present": False,
                "effect_quality_risk_function_oracle_outcome_present": False,
                "actual_rank1_recomputation_status": "PENDING",
                "independent_fidelity_review_status": "PENDING",
            })
            surfaces.append((pair_id + "_" + variant_name.lower(), _normalized(" ".join(turn["content"] for turn in prefix) + " " + current_text)))
    duplicate_groups: dict[str, list[str]] = {}
    for variant_id, surface in surfaces:
        duplicate_groups.setdefault(surface, []).append(variant_id)
    exact_duplicates = [ids for ids in duplicate_groups.values() if len(ids) > 1]
    counts = Counter(row["component_private_lineage"] for row in authored)
    author_counts = Counter((row["component_private_lineage"], row["assigned_author_endpoint"]) for row in authored)
    checks = {
        "authored_pair_ids_are_plan_subset": set(row["pair_id"] for row in authored).issubset(packet),
        "private_assignment_ids_cover_plan": set(private_assignments) == set(packet),
        "runtime_has_two_rows_per_completed_pair": len(runtime_rows) == 2 * len(authored),
        "runtime_assignment_fields_absent": all("variant_A_assignment" not in row and "low_mode" not in row for row in runtime_rows),
        "runtime_outcome_fields_absent": all(not row["effect_quality_risk_function_oracle_outcome_present"] for row in runtime_rows),
        "exact_variant_duplicates_zero": not exact_duplicates,
        "scaffold_leaks_zero": not scaffold_leaks,
        "candidate_full_text_copies_zero": not candidate_exact_copies,
        "source_assistant_exact_copies_zero": not copied_source_assistant_exact,
        "all_pairs_character_similarity_at_least_0_20": all(row["character_similarity"] >= 0.20 for row in pair_metrics),
        "all_pairs_word_length_ratio_at_most_2": all(row["word_length_ratio"] <= 2.0 for row in pair_metrics),
        "minimum_12_families_each_component": all(counts[component] >= 12 for component in COMPONENTS),
    }
    hard_checks = {key: value for key, value in checks.items() if key != "minimum_12_families_each_component"}
    if not all(hard_checks.values()):
        status = "MACHINE_AUDIT_FAIL"
    elif not checks["minimum_12_families_each_component"]:
        status = "MACHINE_AUDIT_PASS_SUPPORT_INCOMPLETE_NO_FIDELITY_PROMOTION"
    else:
        status = "MACHINE_AUDIT_PASS_AWAITING_INDEPENDENT_FIDELITY_AND_RANK1"
    write_jsonl(RUNTIME, runtime_rows)
    report = {
        "protocol": PROTOCOL,
        "status": status,
        "completed_pairs": len(authored),
        "runtime_variants": len(runtime_rows),
        "component_pairs": dict(counts),
        "component_author_pairs": {f"{component}:{author}": count for (component, author), count in author_counts.items()},
        "checks": checks,
        "exact_duplicate_groups": exact_duplicates,
        "scaffold_leak_pair_ids": scaffold_leaks,
        "candidate_exact_copy_pair_ids": candidate_exact_copies,
        "source_assistant_exact_copy_pair_ids": copied_source_assistant_exact,
        "source_assistant_8gram_review_pair_ids": sorted(set(copied_source_assistant_8gram)),
        "pair_similarity": pair_metrics,
        "assignment_joined_to_runtime_rows": False,
        "actual_rank1_recomputed": False,
        "independent_fidelity_review_run": False,
        "response_effect_or_judge_calls": 0,
        "private_paired_outcome_key_read": False,
        "authored_sha256": sha256_file(AUTHORED),
        "runtime_sha256": sha256_file(RUNTIME),
    }
    write_json(DIR / "authored_variant_machine_audit_report.json", report)
    print(json.dumps({key: report[key] for key in ("status", "completed_pairs", "runtime_variants", "component_pairs", "checks")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
