#!/usr/bin/env python3
"""Freeze and analyze atomic semantic suitability development reviews."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402


PROTOCOL = "pm-v1.5-v5.3-atomic-semantic-suitability-development-v1"
DIR = ROOT / "outputs/pm_v1_5_v5_3_role_decomposed_calibration_v2_20260810"
PACKET = DIR / "candidate_suitability_packet_blind.jsonl"
AUDIT = DIR / "selection_audit_outcome_blind.jsonl"
A_PATH = DIR / "atomic_semantic_reviewer_A_completed.jsonl"
B_PATH = DIR / "atomic_semantic_reviewer_B_completed.jsonl"
FREEZE = DIR / "atomic_semantic_reviews_freeze_private_outcome_closed.json"
FIELDS = (
    "current_goal_entity_fit", "specific_contribution_already_visible",
    "component_function_can_change_response", "current_boundary_permits_component",
)


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _agreement(a: Iterable[str], b: Iterable[str]) -> dict[str, Any]:
    left, right = list(a), list(b)
    labels = sorted(set(left) | set(right)); n = len(left)
    observed = sum(x == y for x, y in zip(left, right)) / n
    ca, cb = Counter(left), Counter(right)
    expected = sum(ca[label] / n * cb[label] / n for label in labels)
    kappa = None if expected >= 1 else (observed - expected) / (1 - expected)
    return {"n": n, "labels": labels, "raw_agreement": observed, "cohen_kappa": kappa, "reviewer_A_counts": dict(ca), "reviewer_B_counts": dict(cb)}


def _project(row: dict[str, Any]) -> str:
    values = {field: str(row[field]["label"]) for field in FIELDS}
    if (
        values["current_goal_entity_fit"] == "NO"
        or values["specific_contribution_already_visible"] == "YES"
        or values["component_function_can_change_response"] == "NO"
        or values["current_boundary_permits_component"] == "NO"
    ):
        return "DO_NOT_OPEN"
    if values == {
        "current_goal_entity_fit": "YES",
        "specific_contribution_already_visible": "NO",
        "component_function_can_change_response": "YES",
        "current_boundary_permits_component": "YES",
    }:
        return "OPEN_ELIGIBLE"
    return "ABSTAIN"


def _validate(path: Path, reviewer: str, packet: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    rows = _jsonl(path); by_id = {str(row["calibration_id"]): row for row in rows}
    if len(rows) != len(by_id) or not set(by_id).issubset(set(packet)):
        raise ValueError(f"{reviewer} identity mismatch")
    for key, row in by_id.items():
        if row.get("protocol") != PROTOCOL or row.get("reviewer_id") != reviewer:
            raise ValueError(f"{reviewer}:{key} protocol mismatch")
        turns = {turn["evidence_id"]: turn["text"] for turn in packet[key]["visible_dialogue"]}
        for field in FIELDS:
            if row[field]["label"] not in {"YES", "NO", "UNRESOLVED"}:
                raise ValueError(f"{reviewer}:{key}:{field} label")
            evidence = row[field]["current_evidence"]
            if turns.get(evidence.get("evidence_id")) != evidence.get("text"):
                raise ValueError(f"{reviewer}:{key}:{field} evidence")
        if row["candidate_evidence"] != {"evidence_id": "CANDIDATE_TEXT", "text": packet[key]["candidate"]["text"]}:
            raise ValueError(f"{reviewer}:{key} candidate evidence")
    return by_id


def main() -> None:
    packet_rows = _jsonl(PACKET); packet = {str(row["calibration_id"]): row for row in packet_rows}
    audit = {str(row["calibration_id"]): row for row in _jsonl(AUDIT)}
    a = _validate(A_PATH, "REVIEWER_A", packet); b = _validate(B_PATH, "REVIEWER_B", packet)
    completeness = {
        "packet_n": len(packet),
        "reviewer_A_n": len(a),
        "reviewer_B_n": len(b),
        "common_n": len(set(a) & set(b)),
        "reviewer_A_missing_ids": sorted(set(packet) - set(a)),
        "reviewer_B_missing_ids": sorted(set(packet) - set(b)),
    }
    completeness_gate = completeness["reviewer_A_n"] == completeness["reviewer_B_n"] == completeness["packet_n"]
    freeze = {
        "protocol": PROTOCOL,
        "status": "ATOMIC_AVAILABLE_REVIEWS_VALIDATED_AND_HASH_FROZEN_PRIVATE_OUTCOME_CLOSED",
        "packet_sha256": sha256_file(PACKET), "audit_sha256": sha256_file(AUDIT),
        "reviewer_A_sha256": sha256_file(A_PATH), "reviewer_B_sha256": sha256_file(B_PATH),
        "review_completeness": completeness,
        "transport_completeness_gate": completeness_gate,
        "private_outcome_key_read": False,
    }
    if FREEZE.exists() and json.loads(FREEZE.read_text()) != freeze:
        raise RuntimeError("existing atomic freeze differs")
    if not FREEZE.exists(): write_json(FREEZE, freeze)
    ids = [str(row["calibration_id"]) for row in packet_rows if str(row["calibration_id"]) in a and str(row["calibration_id"]) in b]
    axes = {field: _agreement((a[key][field]["label"] for key in ids), (b[key][field]["label"] for key in ids)) for field in FIELDS}
    projection = _agreement((_project(a[key]) for key in ids), (_project(b[key]) for key in ids))
    axis_gates = {field: metric["raw_agreement"] >= .80 and metric["cohen_kappa"] is not None and metric["cohen_kappa"] >= .60 for field, metric in axes.items()}
    projection_gate = projection["raw_agreement"] >= .80 and projection["cohen_kappa"] is not None and projection["cohen_kappa"] >= .60
    counts: dict[str, Counter[str]] = defaultdict(Counter); clusters: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set)); rows = []
    for key in ids:
        left, right = _project(a[key]), _project(b[key]); component = str(packet[key]["component"])
        consensus = left if left == right else "DISAGREE"
        counts[component][consensus] += 1
        if consensus != "DISAGREE": clusters[component][consensus].add(str(audit[key]["independent_cluster_hash"]))
        rows.append({"protocol": PROTOCOL, "calibration_id": key, "component": component, "projection_A": left, "projection_B": right, "consensus_projection": consensus})
    support = {component: {"counts": dict(counts[component]), "cluster_counts": {label: len(values) for label, values in clusters[component].items()}, "pass_3_each": counts[component]["OPEN_ELIGIBLE"] >= 3 and counts[component]["DO_NOT_OPEN"] >= 3} for component in ("MP", "MS", "ME", "RS")}
    support_gate = all(value["pass_3_each"] for value in support.values())
    passed = completeness_gate and all(axis_gates.values()) and projection_gate and support_gate
    write_jsonl(DIR / "atomic_semantic_consensus_private_outcome_closed.jsonl", rows)
    report = {
        "protocol": PROTOCOL,
        "status": "ATOMIC_DEVELOPMENT_PASS_FREEZE_FRESH_CONFIRMATION" if passed else "ATOMIC_DEVELOPMENT_FAIL_NO_CONFIRMATION",
        "private_outcome_key_read": False,
        "review_completeness": completeness,
        "transport_completeness_gate": completeness_gate,
        "axis_agreement": axes, "axis_gates": axis_gates,
        "projection_agreement": projection, "projection_gate": projection_gate,
        "component_bidirectional_support": support, "support_gate": support_gate,
        "all_development_gates_pass": passed,
        "confirmation_authorized": passed,
        "function_quality_risk_roles_authorized": False,
        "pm_training_authorized": False,
        "api_calls_by_analysis": 0,
    }
    write_json(DIR / "atomic_semantic_development_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
