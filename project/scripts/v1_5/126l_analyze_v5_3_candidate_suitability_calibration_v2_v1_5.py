#!/usr/bin/env python3
"""Freeze and analyze the candidate-only role without opening outcomes."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402


PROTOCOL = "pm-v1.5-v5.3-role-decomposed-calibration-v2"
DIR = ROOT / "outputs/pm_v1_5_v5_3_role_decomposed_calibration_v2_20260810"
PACKET = DIR / "candidate_suitability_packet_blind.jsonl"
AUDIT = DIR / "selection_audit_outcome_blind.jsonl"
REVIEW_A = DIR / "candidate_reviewer_A_completed.jsonl"
REVIEW_B = DIR / "candidate_reviewer_B_completed.jsonl"
FREEZE = DIR / "candidate_reviews_freeze_private_key_still_closed.json"
ALLOWED = {
    "VALID_APPLICABLE", "VALID_REDUNDANT", "VALID_NOT_USEFUL",
    "INVALID_WRONG_OWNER_TIME_EVENT", "UNRESOLVED",
}


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _validate(path: Path, reviewer_id: str, packet: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    rows = _jsonl(path)
    by_id = {str(row.get("calibration_id")): row for row in rows}
    if len(rows) != len(by_id) or set(by_id) != set(packet):
        raise ValueError(f"{reviewer_id} identity mismatch")
    for calibration_id, row in by_id.items():
        if row.get("protocol") != PROTOCOL or row.get("reviewer_id") != reviewer_id:
            raise ValueError(f"{reviewer_id}:{calibration_id} protocol/reviewer mismatch")
        if row.get("candidate_truth") not in ALLOWED:
            raise ValueError(f"{reviewer_id}:{calibration_id} invalid candidate truth")
        options = {turn["evidence_id"]: turn["text"] for turn in packet[calibration_id]["visible_dialogue"]}
        evidence = row.get("current_evidence") or []
        if not 1 <= len(evidence) <= 3:
            raise ValueError(f"{reviewer_id}:{calibration_id} current evidence count")
        for item in evidence:
            if options.get(item.get("evidence_id")) != item.get("text"):
                raise ValueError(f"{reviewer_id}:{calibration_id} current evidence binding")
        candidate = row.get("candidate_evidence") or {}
        if candidate.get("evidence_id") != "CANDIDATE_TEXT" or candidate.get("text") != packet[calibration_id]["candidate"]["text"]:
            raise ValueError(f"{reviewer_id}:{calibration_id} candidate evidence binding")
    return by_id


def _agreement(left: Iterable[str], right: Iterable[str]) -> dict[str, Any]:
    a, b = list(left), list(right)
    labels = sorted(set(a) | set(b))
    observed = sum(x == y for x, y in zip(a, b)) / len(a)
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[label] / len(a) * cb[label] / len(b) for label in labels)
    kappa = None if expected >= 1 else (observed - expected) / (1 - expected)
    return {
        "n": len(a), "labels": labels, "raw_agreement": observed,
        "cohen_kappa": kappa, "reviewer_A_counts": dict(ca), "reviewer_B_counts": dict(cb),
    }


def main() -> None:
    packet_rows = _jsonl(PACKET)
    packet = {str(row["calibration_id"]): row for row in packet_rows}
    audit = {str(row["calibration_id"]): row for row in _jsonl(AUDIT)}
    if len(packet) != 64 or set(packet) != set(audit):
        raise RuntimeError("frozen packet/audit mismatch")
    a = _validate(REVIEW_A, "REVIEWER_A", packet)
    b = _validate(REVIEW_B, "REVIEWER_B", packet)
    freeze = {
        "protocol": PROTOCOL,
        "status": "BOTH_CANDIDATE_REVIEWS_SCHEMA_VALID_AND_HASH_FROZEN_PRIVATE_KEY_STILL_CLOSED",
        "packet_sha256": sha256_file(PACKET),
        "selection_audit_sha256": sha256_file(AUDIT),
        "reviewer_A_sha256": sha256_file(REVIEW_A),
        "reviewer_B_sha256": sha256_file(REVIEW_B),
        "private_key_read": False,
    }
    if FREEZE.exists() and json.loads(FREEZE.read_text()) != freeze:
        raise RuntimeError("existing candidate freeze differs")
    if not FREEZE.exists():
        write_json(FREEZE, freeze)

    ids = [str(row["calibration_id"]) for row in packet_rows]
    exact = _agreement((a[key]["candidate_truth"] for key in ids), (b[key]["candidate_truth"] for key in ids))
    projection = {
        "VALID_APPLICABLE": "OPEN_ELIGIBLE",
        "VALID_REDUNDANT": "DO_NOT_OPEN",
        "VALID_NOT_USEFUL": "DO_NOT_OPEN",
        "INVALID_WRONG_OWNER_TIME_EVENT": "INVALID",
        "UNRESOLVED": "UNRESOLVED",
    }
    projected = _agreement(
        (projection[a[key]["candidate_truth"]] for key in ids),
        (projection[b[key]["candidate_truth"]] for key in ids),
    )
    consensus = []
    counts_by_component: dict[str, Counter[str]] = defaultdict(Counter)
    clusters_by_component_label: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for calibration_id in ids:
        left, right = a[calibration_id]["candidate_truth"], b[calibration_id]["candidate_truth"]
        label = projection[left] if left == right else "DISAGREE"
        component = str(packet[calibration_id]["component"])
        counts_by_component[component][label] += 1
        if label != "DISAGREE":
            clusters_by_component_label[component][label].add(str(audit[calibration_id]["independent_cluster_hash"]))
        consensus.append({
            "protocol": PROTOCOL,
            "calibration_id": calibration_id,
            "component": component,
            "candidate_truth_A": left,
            "candidate_truth_B": right,
            "consensus_projection": label,
            "eligible_for_later_roles": label == "OPEN_ELIGIBLE",
        })

    measurement_gate = (
        projected["raw_agreement"] >= 0.80
        and projected["cohen_kappa"] is not None
        and projected["cohen_kappa"] >= 0.60
    )
    development_support = {
        component: {
            "consensus_counts": dict(counts_by_component[component]),
            "independent_cluster_counts": {
                label: len(values) for label, values in clusters_by_component_label[component].items()
            },
            "has_at_least_3_open_and_3_do_not_open_for_development": (
                counts_by_component[component]["OPEN_ELIGIBLE"] >= 3
                and counts_by_component[component]["DO_NOT_OPEN"] >= 3
            ),
        }
        for component in ("MP", "MS", "ME", "RS")
    }
    support_gate = all(row["has_at_least_3_open_and_3_do_not_open_for_development"] for row in development_support.values())
    continue_roles = measurement_gate and support_gate
    write_jsonl(DIR / "candidate_consensus_private_outcome_still_closed.jsonl", consensus)
    report = {
        "protocol": PROTOCOL,
        "status": "CANDIDATE_PREFLIGHT_PASS_CONTINUE_ROLES" if continue_roles else "CANDIDATE_PREFLIGHT_FAIL_STOP_BEFORE_OTHER_ROLES",
        "private_key_read": False,
        "exact_five_label_agreement": exact,
        "decision_projection_agreement": projected,
        "measurement_gate": measurement_gate,
        "development_bidirectional_support": development_support,
        "development_support_gate": support_gate,
        "continue_function_quality_risk_roles": continue_roles,
        "eligible_group_count_for_later_roles": sum(row["eligible_for_later_roles"] for row in consensus),
        "formal_training_support_not_established": True,
        "formal_training_still_requires_12_independent_clusters_on_both_decision_sides_per_head": True,
        "api_calls_by_analysis": 0,
    }
    write_json(DIR / "candidate_agreement_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
