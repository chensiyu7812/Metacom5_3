#!/usr/bin/env python3
"""Analyze the frozen semantic audit after opening its private outcome key."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import sys
from typing import Any, Iterable

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, write_json  # noqa: E402


AUDIT_DIR = ROOT / "outputs/pm_v1_5_v5_3_blind_semantic_audit_20260809"
REVIEW = AUDIT_DIR / "review_judgments_frozen.jsonl"
FREEZE = AUDIT_DIR / "review_freeze.json"
KEY = AUDIT_DIR / "private_outcome_key_do_not_open_until_review.jsonl"
PACKET = AUDIT_DIR / "review_packet_blind.jsonl"
COMPONENTS = ("MP", "MS", "ME", "RS")
PREFERENCE_VALUE = {"ON_BETTER": 1, "OFF_BETTER": -1, "TIE": 0}
QUALIFIED_USE = {"FUNCTIONAL_USE"}
NONQUALIFIED_USE = {"SURFACE_ECHO_ONLY", "NOT_USED", "BOUNDARY_VIOLATION"}


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _sign(value: float) -> str:
    return "positive" if value > 0 else "negative" if value < 0 else "tie"


def _mean(values: Iterable[float]) -> float | None:
    rows = list(values)
    return float(np.mean(rows)) if rows else None


def main() -> None:
    freeze = json.loads(FREEZE.read_text())
    if freeze["status"] != "REVIEW_FROZEN_BEFORE_OUTCOME_KEY_OPEN":
        raise RuntimeError("review freeze is missing")
    if sha256_file(REVIEW) != freeze["review_judgments_sha256"]:
        raise RuntimeError("review changed after freeze")
    if sha256_file(PACKET) != freeze["review_packet_sha256"]:
        raise RuntimeError("blind packet changed after freeze")

    review_rows = _jsonl(REVIEW)
    key_rows = _jsonl(KEY)
    packet_rows = _jsonl(PACKET)
    review_by_id = {row["audit_id"]: row for row in review_rows}
    key_by_id = {row["audit_id"]: row for row in key_rows}
    packet_by_id = {row["audit_id"]: row for row in packet_rows}
    if not (
        len(review_rows) == len(review_by_id) == 32
        and len(key_rows) == len(key_by_id) == 32
        and len(packet_rows) == len(packet_by_id) == 32
    ):
        raise RuntimeError("audit_id must be unique at the 32-group grain")
    if set(review_by_id) != set(key_by_id) or set(review_by_id) != set(packet_by_id):
        raise RuntimeError("review, key, and packet IDs differ")

    relevance = Counter()
    relevance_by_component = {component: Counter() for component in COMPONENTS}
    relevance_by_stratum: dict[str, Counter[str]] = defaultdict(Counter)
    functional = Counter()
    preference = Counter()
    original_function = Counter()
    function_confusion = Counter()
    function_by_component: dict[str, Counter[str]] = {component: Counter() for component in COMPONENTS}
    preference_by_component: dict[str, Counter[str]] = {component: Counter() for component in COMPONENTS}
    relevance_effects: dict[str, list[float]] = defaultdict(list)
    group_sign_confusion = Counter()
    group_rows = []
    original_used_on_nonqualified_examples = []

    for audit_id in sorted(review_by_id):
        review = review_by_id[audit_id]
        key = key_by_id[audit_id]
        packet = packet_by_id[audit_id]
        component = str(key["component"])
        relevance_label = str(review["candidate_relevance"])
        relevance[relevance_label] += 1
        relevance_by_component[component][relevance_label] += 1
        relevance_by_stratum[str(key["sampling_stratum"])][relevance_label] += 1
        relevance_effects[relevance_label].append(float(key["original_q_effect"]))

        original_f = {
            str(row["replicate_id"]): str(row["use_status"])
            for row in key["original_function_labels"]["replicates"]
        }
        manual_values = []
        qualified_count = 0
        boundary_count = 0
        reviewable_function_count = 0
        replicate_ids = [str(row["replicate_id"]) for row in review["replicates"]]
        if sorted(replicate_ids) != ["r1", "r2", "r3"]:
            raise RuntimeError("each audit group must contain r1/r2/r3 exactly once")
        for replicate in review["replicates"]:
            replicate_id = str(replicate["replicate_id"])
            use = str(replicate["functional_use"])
            pref = str(replicate["response_preference"])
            functional[use] += 1
            function_by_component[component][use] += 1
            preference[pref] += 1
            preference_by_component[component][pref] += 1
            original = original_f[replicate_id]
            original_function[original] += 1
            if use != "UNREVIEWABLE_RAW_REPLY_MISSING":
                reviewable_function_count += 1
                manual_binary = "USED" if use in QUALIFIED_USE else "NOT_QUALIFIED_USE"
                function_confusion[f"manual_{manual_binary}__original_{original}"] += 1
                if manual_binary == "NOT_QUALIFIED_USE" and original == "USED" and len(original_used_on_nonqualified_examples) < 12:
                    generated = next(
                        row for row in packet["replicates"] if row["replicate_id"] == replicate_id
                    )
                    original_used_on_nonqualified_examples.append(
                        {
                            "audit_id": audit_id,
                            "component": component,
                            "candidate_relevance": relevance_label,
                            "manual_function": use,
                            "original_function": original,
                            "candidate_text": packet["candidate_text"],
                            "on_reply": generated["on_reply"],
                        }
                    )
            qualified_count += int(use in QUALIFIED_USE)
            boundary_count += int(use == "BOUNDARY_VIOLATION")
            if pref in PREFERENCE_VALUE:
                manual_values.append(PREFERENCE_VALUE[pref])

        manual_mean = float(np.mean(manual_values)) if manual_values else 0.0
        manual_sign = _sign(manual_mean)
        original_effect = float(key["original_q_effect"])
        original_sign = _sign(original_effect)
        group_sign_confusion[f"manual_{manual_sign}__original_{original_sign}"] += 1
        group_rows.append(
            {
                "audit_id": audit_id,
                "component": component,
                "candidate_type": key["candidate_type"],
                "sampling_stratum": key["sampling_stratum"],
                "candidate_relevance": relevance_label,
                "qualified_function_replicates": qualified_count,
                "boundary_violation_replicates": boundary_count,
                "reviewable_function_replicates": reviewable_function_count,
                "manual_preference_mean": manual_mean,
                "manual_preference_sign": manual_sign,
                "original_q_effect": original_effect,
                "original_q_sign": original_sign,
                "clean_semantic_value_candidate": (
                    relevance_label == "CLEARLY_APPLICABLE"
                    and qualified_count >= 2
                    and boundary_count == 0
                    and reviewable_function_count == 3
                ),
            }
        )

    reviewable_function = sum(function_confusion.values())
    original_used_nonqualified = sum(
        count for key, count in function_confusion.items()
        if key.startswith("manual_NOT_QUALIFIED_USE") and key.endswith("original_USED")
    )
    original_not_used_qualified = sum(
        count for key, count in function_confusion.items()
        if key.startswith("manual_USED") and key.endswith("original_NOT_USED")
    )
    group_sign_agree = sum(
        count for key, count in group_sign_confusion.items()
        if key.split("__")[0].replace("manual_", "")
        == key.split("__")[1].replace("original_", "")
    )
    clean_semantic = [row for row in group_rows if row["clean_semantic_value_candidate"]]
    report = {
        "protocol": "pm-v1.5-v5.3-blind-semantic-audit-analysis-v1",
        "status": "SINGLE_REVIEWER_SEMANTIC_AUDIT_COMPLETE_NOT_CONFIRMATORY",
        "data_quality_checks": {
            "review_packet_32_unique_groups": True,
            "private_key_32_unique_groups": True,
            "review_32_unique_groups": True,
            "three_unique_replicates_per_group": True,
            "freeze_hashes_match": True,
            "complete_join_coverage": True,
        },
        "groups": len(group_rows),
        "replicates": sum(functional.values()),
        "candidate_relevance": {
            "overall": dict(relevance),
            "by_component": {key: dict(value) for key, value in relevance_by_component.items()},
            "by_hidden_sampling_stratum": {
                key: dict(value) for key, value in sorted(relevance_by_stratum.items())
            },
            "original_q_effect_mean_by_relevance": {
                key: _mean(value) for key, value in sorted(relevance_effects.items())
            },
        },
        "functional_use": {
            "manual_counts": dict(functional),
            "manual_by_component": {key: dict(value) for key, value in function_by_component.items()},
            "original_judge_counts_in_sample": dict(original_function),
            "reviewable_replicates": reviewable_function,
            "manual_vs_original_confusion": dict(function_confusion),
            "original_used_but_manual_nonqualified_count": original_used_nonqualified,
            "original_used_but_manual_nonqualified_rate": (
                original_used_nonqualified / reviewable_function if reviewable_function else None
            ),
            "original_not_used_but_manual_qualified_count": original_not_used_qualified,
            "examples": original_used_on_nonqualified_examples,
        },
        "response_preference": {
            "manual_counts": dict(preference),
            "manual_by_component": {key: dict(value) for key, value in preference_by_component.items()},
            "group_sign_confusion": dict(group_sign_confusion),
            "group_sign_agreement_count": group_sign_agree,
            "group_sign_agreement_rate": group_sign_agree / len(group_rows),
        },
        "clean_semantic_value_subset": {
            "definition": (
                "candidate CLEARLY_APPLICABLE; all three raw/final replies reviewable; at least "
                "two FUNCTIONAL_USE; zero BOUNDARY_VIOLATION"
            ),
            "groups": len(clean_semantic),
            "by_component": dict(Counter(row["component"] for row in clean_semantic)),
            "manual_preference_signs": dict(Counter(row["manual_preference_sign"] for row in clean_semantic)),
            "rows": clean_semantic,
        },
        "group_rows": group_rows,
        "interpretation": [
            "The sample is outcome-stratified and intentionally not prevalence-weighted.",
            "One outcome-hidden Codex reviewer is a forensic diagnostic, not independent human confirmation.",
            "Candidate applicability, functional realization, and final response preference are empirically different variables.",
            "A positive final-response preference without qualified candidate use cannot supervise semantic component opening.",
        ],
        "source_hashes": {
            "review_freeze": sha256_file(FREEZE),
            "review": sha256_file(REVIEW),
            "private_key": sha256_file(KEY),
            "blind_packet": sha256_file(PACKET),
        },
        "api_calls": 0,
    }
    write_json(AUDIT_DIR / "analysis.json", report)
    print(
        json.dumps(
            {
                "relevance": report["candidate_relevance"]["overall"],
                "function_confusion": report["functional_use"]["manual_vs_original_confusion"],
                "preference_sign_agreement": report["response_preference"]["group_sign_agreement_rate"],
                "clean_semantic_groups": report["clean_semantic_value_subset"]["groups"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
