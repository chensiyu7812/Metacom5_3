#!/usr/bin/env python3
"""Analyze fresh V4 fidelity V2 with frozen raw-agreement and AC1 gates."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402

PROTOCOL = "pm-v1.5-v5.4-v4-dual-fidelity-v2"
DIR = ROOT / "outputs/pm_v1_5_v5_4_v4_fidelity_v2_20260810"
PACKET = DIR / "fidelity_v2_packet_private_assignment_outcome_blind.jsonl"
A = DIR / "fidelity_v2_REVIEWER_A.jsonl"
B = DIR / "fidelity_v2_REVIEWER_B.jsonl"
TRI = ("world_fidelity_A", "world_fidelity_B", "dialogue_coherence_A", "dialogue_coherence_B", "assignment_fidelity_A", "assignment_fidelity_B", "single_axis_minimality")
EVENT = ("unsupported_critical_fact", "response_or_scaffold_leak")


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def projection(row: dict) -> str:
    if any(row[field] == "FAIL" for field in TRI) or any(row[field] == "PRESENT" for field in EVENT):
        return "FAIL"
    if any(row[field] == "UNRESOLVED" for field in TRI + EVENT):
        return "UNRESOLVED"
    return "PASS"


def agreement(left: list[str], right: list[str]) -> dict:
    n = len(left)
    labels = sorted(set(left) | set(right))
    observed = sum(a == b for a, b in zip(left, right)) / n
    ca, cb = Counter(left), Counter(right)
    expected_kappa = sum(ca[label] / n * cb[label] / n for label in labels)
    kappa = None if expected_kappa >= 1 else (observed - expected_kappa) / (1 - expected_kappa)
    pooled = Counter(left + right)
    proportions = {label: pooled[label] / (2 * n) for label in labels}
    expected_ac1 = 0.0 if len(labels) == 1 else sum(p * (1 - p) for p in proportions.values()) / (len(labels) - 1)
    ac1 = None if expected_ac1 >= 1 else (observed - expected_ac1) / (1 - expected_ac1)
    return {"n": n, "labels": labels, "raw_agreement": observed, "cohen_kappa_diagnostic": kappa, "gwet_ac1": ac1, "reviewer_A_counts": dict(ca), "reviewer_B_counts": dict(cb)}


def main() -> None:
    packet_rows = rows(PACKET)
    packet = {row["pair_id"]: row for row in packet_rows}
    a = {row["pair_id"]: row for row in rows(A)}
    b = {row["pair_id"]: row for row in rows(B)}
    if len(a) != 48 or len(b) != 48 or set(a) != set(packet) or set(b) != set(packet):
        raise RuntimeError("fidelity V2 identities incomplete")
    ids = [row["pair_id"] for row in packet_rows]
    pa = [projection(a[pair_id]) for pair_id in ids]
    pb = [projection(b[pair_id]) for pair_id in ids]
    reliability = agreement(pa, pb)
    pass_by_component = Counter()
    nonpass = []
    any_critical = []
    scaffold = []
    consensus_rows = []
    for pair_id, left, right in zip(ids, pa, pb):
        component = packet[pair_id]["component"]
        consensus = left if left == right else "DISAGREE"
        if consensus == "PASS":
            pass_by_component[component] += 1
        else:
            nonpass.append(pair_id)
        if a[pair_id]["unsupported_critical_fact"] == "PRESENT" or b[pair_id]["unsupported_critical_fact"] == "PRESENT":
            any_critical.append(pair_id)
        if a[pair_id]["response_or_scaffold_leak"] == "PRESENT" or b[pair_id]["response_or_scaffold_leak"] == "PRESENT":
            scaffold.append(pair_id)
        consensus_rows.append({"protocol": PROTOCOL, "pair_id": pair_id, "component": component, "projection_A": left, "projection_B": right, "consensus": consensus})
    gates = {
        "complete": len(a) == len(b) == 48,
        "raw_agreement": reliability["raw_agreement"] >= 0.80,
        "gwet_ac1": reliability["gwet_ac1"] is not None and reliability["gwet_ac1"] >= 0.60,
        "consensus_pass_total": sum(pass_by_component.values()) >= 42,
        "consensus_pass_each_component": all(pass_by_component[component] >= 10 for component in ("MP", "MS", "ME", "RS")),
        "single_or_dual_critical_zero": not any_critical,
        "single_or_dual_scaffold_zero": not scaffold,
    }
    passed = all(gates.values())
    report = {
        "protocol": PROTOCOL,
        "status": "V4_FIDELITY_V2_PASS_REPRESENTATION_GATE_MAY_BE_MATERIALIZED" if passed else "V4_FIDELITY_V2_FAIL_NO_REPRESENTATION_OR_EFFECT",
        "reliability": reliability,
        "consensus_pass_total": sum(pass_by_component.values()),
        "consensus_pass_by_component": dict(pass_by_component),
        "nonpass_or_disagreement_pair_ids": nonpass,
        "critical_pair_ids": any_critical,
        "scaffold_pair_ids": scaffold,
        "gates": gates,
        "all_gates_pass": passed,
        "bounded_observability_materialization_authorized": passed,
        "response_effect_calls_authorized": False,
        "pm_training_authorized": False,
        "response_or_outcome_read": False,
        "api_calls": 0,
        "hashes": {"packet": sha256_file(PACKET), "review_A": sha256_file(A), "review_B": sha256_file(B)},
    }
    write_jsonl(DIR / "fidelity_v2_consensus_outcome_blind.jsonl", consensus_rows)
    write_json(DIR / "fidelity_v2_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
