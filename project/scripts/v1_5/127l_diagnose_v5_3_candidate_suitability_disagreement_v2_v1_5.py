#!/usr/bin/env python3
"""Diagnose candidate-only V2 disagreement without opening any outcome."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import stable_hex, write_json  # noqa: E402


PROTOCOL = "pm-v1.5-v5.3-candidate-suitability-disagreement-diagnosis-v2"
DIR = ROOT / "outputs/pm_v1_5_v5_3_role_decomposed_calibration_v2_20260810"


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _projection(label: str) -> str:
    if label == "VALID_APPLICABLE":
        return "OPEN_ELIGIBLE"
    if label in {"VALID_REDUNDANT", "VALID_NOT_USEFUL"}:
        return "DO_NOT_OPEN"
    if label == "INVALID_WRONG_OWNER_TIME_EVENT":
        return "INVALID"
    return "UNRESOLVED"


def main() -> None:
    packet = {str(row["calibration_id"]): row for row in _jsonl(DIR / "candidate_suitability_packet_blind.jsonl")}
    audit = {str(row["calibration_id"]): row for row in _jsonl(DIR / "selection_audit_outcome_blind.jsonl")}
    a = {str(row["calibration_id"]): row for row in _jsonl(DIR / "candidate_reviewer_A_completed.jsonl")}
    b = {str(row["calibration_id"]): row for row in _jsonl(DIR / "candidate_reviewer_B_completed.jsonl")}
    if not (set(packet) == set(audit) == set(a) == set(b)) or len(packet) != 64:
        raise RuntimeError("complete aligned candidate-only evidence required")

    segments: dict[str, Counter[str]] = defaultdict(Counter)
    disagreement_types: Counter[str] = Counter()
    examples: list[dict[str, Any]] = []
    for calibration_id in sorted(packet):
        item = packet[calibration_id]
        meta = audit[calibration_id]
        left = str(a[calibration_id]["candidate_truth"])
        right = str(b[calibration_id]["candidate_truth"])
        pleft, pright = _projection(left), _projection(right)
        keys = (
            "ALL",
            f"COMPONENT:{item['component']}",
            f"TYPE:{item['component']}:{item['candidate']['candidate_type']}",
            f"DIAGNOSTIC:{meta['selection_diagnostic_stratum_not_gold']}",
        )
        for key in keys:
            segments[key][f"A:{left}"] += 1
            segments[key][f"B:{right}"] += 1
            segments[key][f"PAIR:{pleft}|{pright}"] += 1
        if pleft != pright:
            disagreement_types[f"{pleft}|{pright}"] += 1
            examples.append({
                "calibration_id": calibration_id,
                "component": item["component"],
                "candidate_type": item["candidate"]["candidate_type"],
                "selection_diagnostic_not_gold": meta["selection_diagnostic_stratum_not_gold"],
                "candidate_text": item["candidate"]["text"],
                "recent_dialogue": item["visible_dialogue"][-5:],
                "reviewer_A": {"label": left, "projection": pleft, "rationale": a[calibration_id]["rationale"]},
                "reviewer_B": {"label": right, "projection": pright, "rationale": b[calibration_id]["rationale"]},
            })
    examples.sort(key=lambda row: stable_hex(PROTOCOL, row["calibration_id"], n=24))

    report = {
        "protocol": PROTOCOL,
        "status": "ATOMIC_CANDIDATE_AXES_REQUIRED_COMPOSITE_SUITABILITY_LABEL_INVALID",
        "private_outcome_key_read": False,
        "groups": 64,
        "projection_disagreement_groups": len(examples),
        "projection_disagreement_types": dict(disagreement_types),
        "segments": {key: dict(value) for key, value in segments.items()},
        "representative_disagreements": examples[:16],
        "root_causes": [
            {
                "id": "STRUCTURAL_AND_SEMANTIC_CONFLATION",
                "finding": "one label asks the reviewer to decide owner/time/event validity, current relevance, redundancy, and response usefulness at once",
                "repair": "machine-verifiable owner/time/version remains a separate structural fact; semantic reviewers never override it without explicit conflicting evidence"
            },
            {
                "id": "POSSIBLE_VERSUS_INCREMENTAL_APPLICABILITY",
                "finding": "Reviewer B tends to call a topically usable candidate applicable, while Reviewer A asks whether it adds a nonredundant response contribution",
                "repair": "separate current-event relevance, contribution already present, and response-act change into atomic axes before deterministic projection"
            },
            {
                "id": "UNVERIFIABLE_PRIOR_FACT_SCOPE",
                "finding": "the packet supplies a typed prior candidate but not its literal source lineage; reviewers sometimes treat absence from current dialogue as invalid and sometimes as legitimate memory",
                "repair": "show a verified source span and strict-past metadata to validity review, but keep it hidden from quality preference and runtime PM labels"
            },
            {
                "id": "NATURAL_PANEL_SUPPORT_ASYMMETRY",
                "finding": "pre-treatment open-like diagnostics are absent for MP and scarce for MS/ME, while RS has few consensus DO_NOT_OPEN cases",
                "repair": "use this V2 packet only as development evidence; freeze a new V3 confirmation after atomic-axis rubric and support quotas are defined without paired outcomes"
            }
        ],
        "next_measurement_object": {
            "machine_structural_validity": "owner/time/version/source lineage",
            "semantic_axes": [
                "SAME_CURRENT_ENTITY_EVENT_GOAL: YES/NO/UNRESOLVED",
                "SPECIFIC_CONTRIBUTION_ALREADY_VISIBLE: YES/NO/UNRESOLVED",
                "CANDIDATE_CAN_CHANGE_RESPONSE_ACT_OR_CONTENT: YES/NO/UNRESOLVED",
                "CURRENT_BOUNDARY_PERMITS_COMPONENT: YES/NO/UNRESOLVED"
            ],
            "projection": "OPEN_ELIGIBLE only when structural validity passes, same-event/goal=YES, already-visible=NO, can-change=YES, and boundary-permits=YES; any semantic UNRESOLVED abstains OFF",
            "forbidden": "a single free-form VALID_APPLICABLE judgment as gold"
        },
        "api_calls": 0,
    }
    write_json(DIR / "candidate_disagreement_diagnostics.json", report)
    print(json.dumps({
        "status": report["status"],
        "projection_disagreement_groups": report["projection_disagreement_groups"],
        "projection_disagreement_types": report["projection_disagreement_types"],
        "root_cause_ids": [row["id"] for row in report["root_causes"]],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
