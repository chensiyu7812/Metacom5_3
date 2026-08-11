#!/usr/bin/env python3
"""Materialize the current evidence snapshot for Rank-1 and OFF accounting.

This is a derived, zero-API report.  Candidate absence is reported as a
structural OFF lower bound, the 576 paired-arm allocation is explicitly kept
separate from policy behavior, and no final learned ON/OFF rate is fabricated
while all four heads remain unqualified.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, write_json  # noqa: E402


PROTOCOL = "pm-v1.5-v5.3-semantic-off-accounting-snapshot-v1"
BACKBONE = ROOT / "outputs/pm_v1_5_v5_3_public_backbone_audit_20260809/audit.json"
FORMAL = ROOT / "outputs/pm_v1_5_v5_3_public_formal_oof_20260809/formal_oof_report.json"
CALIBRATION = ROOT / "outputs/pm_v1_5_v5_3_dual_reviewer_calibration_20260810"
CONTRACT = ROOT / "data/pm_v1_5_contracts/v5_3_semantic_coverage_off_accounting_v1.json"
OUT = ROOT / "outputs/pm_v1_5_v5_3_semantic_off_accounting_20260810"


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _rate(numerator: int, denominator: int) -> float:
    return numerator / denominator


def main() -> None:
    backbone = _json(BACKBONE)
    formal = _json(FORMAL)
    support = backbone["candidate_support_lower_bound"]
    total = int(support["states_total"])
    prior = int(support["states_with_at_least_one_completed_prior_session"])

    components: dict[str, Any] = {}
    for component in ("MP", "MS", "ME"):
        present = int(support[component]["preliminary_actual_rank1_states"])
        components[component] = {
            "all_seeker_turns": {
                "denominator": total,
                "rank1_present": present,
                "candidate_availability_rate": _rate(present, total),
                "structural_off_lower_bound": _rate(total - present, total),
            },
            "states_with_completed_prior_session": {
                "denominator": prior,
                "rank1_present": present,
                "candidate_availability_rate": _rate(present, prior),
                "structural_off_lower_bound": _rate(prior - present, prior),
            },
            "semantic_off_rate": "NOT_MEASURED",
            "final_policy_on_rate": "NOT_AVAILABLE",
        }

    review_a = _jsonl(CALIBRATION / "reviewer_A_completed.jsonl")
    review_b = _jsonl(CALIBRATION / "reviewer_B_completed.jsonl")
    by_id_a = {str(row["calibration_id"]): row for row in review_a}
    by_id_b = {str(row["calibration_id"]): row for row in review_b}
    if len(by_id_a) != len(review_a) or len(by_id_b) != len(review_b):
        raise RuntimeError("duplicate calibration_id in reviewer ledger")
    if set(by_id_a) != set(by_id_b):
        raise RuntimeError("calibration reviewer identity sets differ")
    aligned = [(by_id_a[key], by_id_b[key]) for key in sorted(by_id_a)]
    candidate_pairs = Counter(
        (left["candidate_truth"], right["candidate_truth"])
        for left, right in aligned
    )
    boundary_pairs = Counter(
        (lrep["owner_time_boundary_correct"], rrep["owner_time_boundary_correct"])
        for left, right in aligned
        for replicate_id in sorted(str(row["replicate_id"]) for row in left["replicates"])
        for lrep in [next(row for row in left["replicates"] if str(row["replicate_id"]) == replicate_id)]
        for rrep in [next(row for row in right["replicates"] if str(row["replicate_id"]) == replicate_id)]
    )

    report = {
        "protocol": PROTOCOL,
        "status": "ACCOUNTING_DEFINITION_READY_FINAL_LEARNED_POLICY_RATE_UNAVAILABLE",
        "grain": {
            "candidate_snapshot": "EvoEmo seeker turn x component",
            "calibration": "64 selected group candidates and 192 ON replicates",
            "formal_effect": "576 selected group x paired experimental arm; not a population-policy sample",
        },
        "rank1": {
            "definition": "the exact top-scored structurally legal candidate frozen before action/outcome; not gold or oracle",
            "all_seeker_turns": total,
            "states_with_completed_prior_session": prior,
            "components": components,
            "all_three_memory_rank1_present": {
                "count": int(support["states_with_preliminary_rank1_for_MP_MS_ME"]),
                "rate_all_turns": _rate(
                    int(support["states_with_preliminary_rank1_for_MP_MS_ME"]), total
                ),
            },
        },
        "paired_effect_arm_allocation": {
            "groups": 576,
            "replicates_per_group": 3,
            "on_replies": 1728,
            "off_replies": 1728,
            "off_rate": 0.5,
            "policy_interpretation_forbidden": True,
        },
        "current_learned_policy": {
            "passed_heads": formal["passed_heads"],
            "failed_heads": formal["failed_heads"],
            "external_arm_authorized": False,
            "mechanical_all_failed_action": "M0+R0",
            "transparent_rule_substitution_inside_learned_arm": False,
            "natural_action_distribution": "NOT_AVAILABLE",
        },
        "memory_misuse_calibration_evidence_not_population_prevalence": {
            "candidate_pair_counts": {
                f"A:{left}|B:{right}": count
                for (left, right), count in sorted(candidate_pairs.items())
            },
            "owner_time_boundary_pair_counts": {
                f"A:{left}|B:{right}": count
                for (left, right), count in sorted(boundary_pairs.items())
            },
            "both_candidate_applicable": candidate_pairs[("VALID_APPLICABLE", "VALID_APPLICABLE")],
            "both_candidate_invalid_wrong_owner_time_event": candidate_pairs[("INVALID_WRONG_OWNER_TIME_EVENT", "INVALID_WRONG_OWNER_TIME_EVENT")],
            "both_owner_time_boundary_yes": boundary_pairs[("YES", "YES")],
            "both_owner_time_boundary_no": boundary_pairs[("NO", "NO")],
            "warning": "the calibration sample is stratified and reviewer agreement failed; these counts establish risk, not a natural misuse rate",
        },
        "required_next": [
            "pass role-decomposed measurement calibration",
            "freeze machine-executable OOD and low-confidence abstention",
            "materialize one four-component trace per final policy state before outcomes open",
            "report conditional ON and OFF reasons, not one global OFF rate",
        ],
        "source_hashes": {
            "backbone": sha256_file(BACKBONE),
            "formal_oof": sha256_file(FORMAL),
            "reviewer_A": sha256_file(CALIBRATION / "reviewer_A_completed.jsonl"),
            "reviewer_B": sha256_file(CALIBRATION / "reviewer_B_completed.jsonl"),
            "contract": sha256_file(CONTRACT),
        },
        "api_calls": 0,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
