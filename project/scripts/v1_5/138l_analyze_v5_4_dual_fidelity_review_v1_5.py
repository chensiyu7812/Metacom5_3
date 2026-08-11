#!/usr/bin/env python3
"""Freeze and analyze the dual construction-fidelity reviews."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402

PROTOCOL = "pm-v1.5-v5.4-dual-fidelity-review-v1"
DIR = ROOT / "outputs/pm_v1_5_v5_4_fidelity_review_20260810"
PACKET = DIR / "fidelity_packet_private_assignment_outcome_blind.jsonl"
A_PATH = DIR / "fidelity_REVIEWER_A.jsonl"; B_PATH = DIR / "fidelity_REVIEWER_B.jsonl"
TRI_FIELDS = ("world_fidelity_A", "world_fidelity_B", "dialogue_coherence_A", "dialogue_coherence_B", "assignment_fidelity_A", "assignment_fidelity_B", "single_axis_minimality")
EVENT_FIELDS = ("unsupported_critical_fact", "response_or_scaffold_leak")


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def project(row: dict) -> str:
    if any(row[field] == "FAIL" for field in TRI_FIELDS) or any(row[field] == "PRESENT" for field in EVENT_FIELDS): return "FAIL"
    if any(row[field] == "UNRESOLVED" for field in TRI_FIELDS + EVENT_FIELDS): return "UNRESOLVED"
    return "PASS"


def agreement(left: list[str], right: list[str]) -> dict:
    n = len(left); ca, cb = Counter(left), Counter(right); labels = sorted(set(left) | set(right)); raw = sum(a == b for a, b in zip(left, right)) / n; expected = sum(ca[label] / n * cb[label] / n for label in labels); kappa = None if expected >= 1 else (raw - expected) / (1 - expected)
    return {"n": n, "labels": labels, "raw_agreement": raw, "cohen_kappa": kappa, "reviewer_A_counts": dict(ca), "reviewer_B_counts": dict(cb)}


def main() -> None:
    packet_rows = rows(PACKET); packet = {row["pair_id"]: row for row in packet_rows}; a = {row["pair_id"]: row for row in rows(A_PATH)}; b = {row["pair_id"]: row for row in rows(B_PATH)}
    if len(a) != 48 or len(b) != 48 or set(a) != set(packet) or set(b) != set(packet): raise RuntimeError("fidelity review identity incomplete")
    for reviewer, data in (("REVIEWER_A", a), ("REVIEWER_B", b)):
        for pair_id, row in data.items():
            if row.get("protocol") != PROTOCOL or row.get("reviewer_id") != reviewer: raise RuntimeError(f"{reviewer}:{pair_id} protocol mismatch")
    ids = [row["pair_id"] for row in packet_rows]; pa = [project(a[key]) for key in ids]; pb = [project(b[key]) for key in ids]; projected = agreement(pa, pb)
    field_agreement = {field: agreement([a[key][field] for key in ids], [b[key][field] for key in ids]) for field in TRI_FIELDS + EVENT_FIELDS}
    consensus_rows = []; pass_by_component = Counter(); unresolved = []; any_critical = []; dual_critical = []; dual_scaffold = []
    for key, left, right in zip(ids, pa, pb):
        component = packet[key]["component"]; consensus = left if left == right else "DISAGREE"
        if consensus == "PASS": pass_by_component[component] += 1
        if consensus != "PASS": unresolved.append(key)
        if a[key]["unsupported_critical_fact"] == "PRESENT" or b[key]["unsupported_critical_fact"] == "PRESENT": any_critical.append(key)
        if a[key]["unsupported_critical_fact"] == b[key]["unsupported_critical_fact"] == "PRESENT": dual_critical.append(key)
        if a[key]["response_or_scaffold_leak"] == b[key]["response_or_scaffold_leak"] == "PRESENT": dual_scaffold.append(key)
        consensus_rows.append({"protocol": PROTOCOL, "pair_id": key, "component": component, "projection_A": left, "projection_B": right, "consensus_projection": consensus, "single_reviewer_critical_flag": key in any_critical})
    gates = {"transport_complete": len(a) == len(b) == 48, "projection_raw_agreement": projected["raw_agreement"] >= .80, "projection_kappa": projected["cohen_kappa"] is not None and projected["cohen_kappa"] >= .60, "consensus_pass_total": sum(pass_by_component.values()) >= 42, "consensus_pass_each_component": all(pass_by_component[c] >= 10 for c in ("MP", "MS", "ME", "RS")), "dual_consensus_critical_zero": not dual_critical, "dual_consensus_scaffold_zero": not dual_scaffold, "single_reviewer_critical_flags_resolved": not any_critical}
    passed = all(gates.values())
    freeze = {"protocol": PROTOCOL, "status": "FIDELITY_REVIEWS_HASH_FROZEN_OUTCOME_CLOSED", "packet_sha256": sha256_file(PACKET), "reviewer_A_sha256": sha256_file(A_PATH), "reviewer_B_sha256": sha256_file(B_PATH), "private_paired_outcome_key_read": False}; write_json(DIR / "fidelity_review_freeze.json", freeze)
    write_jsonl(DIR / "fidelity_consensus_outcome_blind.jsonl", consensus_rows)
    report = {"protocol": PROTOCOL, "status": "FIDELITY_GATE_PASS_RANK1_PROMOTION_ALLOWED" if passed else "FIDELITY_GATE_FAIL_NO_PROMOTION", "projection_agreement": projected, "field_agreement": field_agreement, "consensus_pass_total": sum(pass_by_component.values()), "consensus_pass_by_component": dict(pass_by_component), "nonpass_or_disagreement_pair_ids": unresolved, "single_reviewer_critical_flag_pair_ids": any_critical, "dual_critical_pair_ids": dual_critical, "dual_scaffold_pair_ids": dual_scaffold, "gates": gates, "all_gates_pass": passed, "rank1_promotion_allowed": passed, "representation_test_authorized": False, "response_effect_calls_authorized": False, "pm_training_authorized": False, "private_paired_outcome_key_read": False, "api_calls_by_analysis": 0}
    write_json(DIR / "fidelity_agreement_report.json", report); print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
