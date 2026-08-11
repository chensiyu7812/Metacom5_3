#!/usr/bin/env python3
"""Outcome-blind diagnosis of the failed V5.4 construction-fidelity gate.

This script does not adjudicate failed pairs into passes.  It preserves the
frozen V1 result, quantifies the prevalence-sensitive reliability diagnostic,
and separates instrument, construction, retrieval-anchor, and identifiability
faults so a new version can be authored and reviewed from scratch.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402


PROTOCOL = "pm-v1.5-v5.4-fidelity-failure-diagnosis-v1"
DIR = ROOT / "outputs/pm_v1_5_v5_4_fidelity_review_20260810"
PACKET = DIR / "fidelity_packet_private_assignment_outcome_blind.jsonl"
REVIEW_A = DIR / "fidelity_REVIEWER_A.jsonl"
REVIEW_B = DIR / "fidelity_REVIEWER_B.jsonl"
REPORT = DIR / "fidelity_agreement_report.json"
OUT = ROOT / "outputs/pm_v1_5_v5_4_fidelity_failure_diagnosis_20260810"

TRI_FIELDS = (
    "world_fidelity_A", "world_fidelity_B", "dialogue_coherence_A",
    "dialogue_coherence_B", "assignment_fidelity_A", "assignment_fidelity_B",
    "single_axis_minimality",
)
EVENT_FIELDS = ("unsupported_critical_fact", "response_or_scaffold_leak")


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _projection(row: dict) -> str:
    if any(row[field] == "FAIL" for field in TRI_FIELDS):
        return "FAIL"
    if any(row[field] == "PRESENT" for field in EVENT_FIELDS):
        return "FAIL"
    if any(row[field] == "UNRESOLVED" for field in TRI_FIELDS + EVENT_FIELDS):
        return "UNRESOLVED"
    return "PASS"


def _gwet_ac1(left: list[str], right: list[str]) -> dict:
    """Gwet AC1 for two raters and nominal categories.

    AC1 is reported only as a diagnosis of the prevalence-sensitive kappa
    result.  It cannot retroactively qualify the already-frozen V1 gate.
    """

    if len(left) != len(right) or not left:
        raise ValueError("paired non-empty judgments required")
    labels = sorted(set(left) | set(right))
    n = len(left)
    observed = sum(a == b for a, b in zip(left, right)) / n
    pooled = Counter(left + right)
    proportions = {label: pooled[label] / (2 * n) for label in labels}
    if len(labels) == 1:
        chance = 0.0
    else:
        chance = sum(p * (1.0 - p) for p in proportions.values()) / (len(labels) - 1)
    ac1 = None if chance >= 1.0 else (observed - chance) / (1.0 - chance)
    return {
        "n": n,
        "labels": labels,
        "observed_agreement": observed,
        "pooled_label_proportions": proportions,
        "chance_agreement_ac1": chance,
        "gwet_ac1": ac1,
        "diagnostic_only_not_v1_requalification": True,
    }


PAIR_FINDINGS = {
    "v54pair_6e69431f599f398fb688": {
        "fault_classes": ["INSTRUMENT_TRUSTED_CANDIDATE_MISREAD", "PAIR_MINIMALITY_NEEDS_REWRITE"],
        "disposition": "REWRITE_PAIR_OUTCOME_BLIND",
        "evidence": "The candidate explicitly contains the James falling-out; one reviewer treated it as invented. A/B also differ in advice request and goal framing.",
    },
    "v54pair_7be2c6ebe0472124d49b": {
        "fault_classes": ["UNSUPPORTED_SPECIFICITY_IN_AUTHORED_TURN"],
        "disposition": "REWRITE_PAIR_OUTCOME_BLIND",
        "evidence": "Defensive and dismissive strengthen the trusted candidate's merely mixed responses.",
    },
    "v54pair_895cae31a6323f54dae0": {
        "fault_classes": ["RANK1_ANCHOR_SEMANTIC_MISMATCH", "INSTRUMENT_CANDIDATE_OMISSION_MISREAD"],
        "disposition": "REPLACE_ANCHOR_BEFORE_REAUTHORING",
        "evidence": "The frozen friend-blocking MS candidate is unrelated to the sleep current state. Candidate omission is not itself world-fidelity failure, but the anchor cannot identify useful candidate semantics.",
    },
    "v54pair_a3b976319022626ea576": {
        "fault_classes": ["RS_ROLE_CONFUSION", "NONIDENTIFIABLE_PREFIX_FIXED_ASSIGNMENT"],
        "disposition": "REAUTHOR_UNDER_REPLACEMENT_RS_LOW_MODE",
        "evidence": "A current user turn cannot establish that an assistant move already occurred in an unchanged shared prefix, and variant B asks an assistant-style invitation.",
    },
    "v54pair_c396058a2104aacba5c7": {
        "fault_classes": ["INSTRUMENT_ASSISTANT_MOVE_ROLE_MISREAD", "PAIR_MINIMALITY_NEEDS_REWRITE"],
        "disposition": "REWRITE_PAIR_OUTCOME_BLIND",
        "evidence": "The user turn should create or remove opportunity for the assistant move; it must not itself execute the paraphrase-check card.",
    },
    "v54pair_ca496f2e4be2a5b4c651": {
        "fault_classes": ["UNSUPPORTED_ACTION_DETAIL_AND_RESULT", "INSTRUMENT_TRUSTED_CANDIDATE_MISREAD"],
        "disposition": "REPLACE_OR_REWRITE_ANCHOR_PAIR_OUTCOME_BLIND",
        "evidence": "About boundaries and it did not go well are not entailed by the trusted candidate, which contains an attempt but no topic or result.",
    },
    "v54pair_d9477ca079a7deb5f81e": {
        "fault_classes": ["UNSUPPORTED_SPECIFICITY_IN_AUTHORED_TURN", "INSTRUMENT_TRUSTED_CANDIDATE_MISREAD"],
        "disposition": "REWRITE_PAIR_OUTCOME_BLIND",
        "evidence": "David's move is trusted, but routines already feeling different is an added result not in the trusted sources.",
    },
    "v54pair_ed3ba9503845141955d5": {
        "fault_classes": ["INSTRUMENT_VARIANT_CONTENT_MISREAD", "PAIR_MINIMALITY_NEEDS_REWRITE"],
        "disposition": "REWRITE_PAIR_OUTCOME_BLIND",
        "evidence": "One rationale assigns drinking-relapse wording to variant A even though neither variant says it; the pair also shifts from general endurance to professional-help intent.",
    },
    "v54pair_ee69bdcfbd339a26eac5": {
        "fault_classes": ["TEMPORAL_AND_ENTITY_REWRITE", "INSTRUMENT_TRUSTED_CANDIDATE_MISREAD"],
        "disposition": "REPLACE_ANCHOR_BEFORE_REAUTHORING",
        "evidence": "Father/material-things/two-years-ago is rewritten as recent generic family tension over money, changing entity, content, and time.",
    },
}


def main() -> None:
    packet_rows = _rows(PACKET)
    packet = {row["pair_id"]: row for row in packet_rows}
    review_a = {row["pair_id"]: row for row in _rows(REVIEW_A)}
    review_b = {row["pair_id"]: row for row in _rows(REVIEW_B)}
    frozen = json.loads(REPORT.read_text())
    if frozen.get("status") != "FIDELITY_GATE_FAIL_NO_PROMOTION":
        raise RuntimeError("diagnosis is only valid for the frozen failed V1 gate")
    if not (set(packet) == set(review_a) == set(review_b)):
        raise RuntimeError("review identities differ")

    ordered_ids = [row["pair_id"] for row in packet_rows]
    left = [_projection(review_a[pair_id]) for pair_id in ordered_ids]
    right = [_projection(review_b[pair_id]) for pair_id in ordered_ids]
    ac1 = _gwet_ac1(left, right)

    nonpass = set(frozen["nonpass_or_disagreement_pair_ids"])
    if set(PAIR_FINDINGS) != nonpass:
        raise RuntimeError("pair diagnosis does not cover exactly the frozen non-pass set")

    rs_nonidentifiable = sorted(
        row["pair_id"]
        for row in packet_rows
        if row["component"] == "RS" and row.get("low_mode") == "MOVE_ALREADY_PERFORMED"
    )
    if len(rs_nonidentifiable) != 6:
        raise RuntimeError("expected exactly six prefix-fixed RS assignment defects")

    finding_rows = []
    for pair_id in sorted(PAIR_FINDINGS):
        finding = PAIR_FINDINGS[pair_id]
        finding_rows.append({
            "protocol": PROTOCOL,
            "pair_id": pair_id,
            "component": packet[pair_id]["component"],
            "projection_A": _projection(review_a[pair_id]),
            "projection_B": _projection(review_b[pair_id]),
            **finding,
            "paired_response_or_effect_outcome_read": False,
            "current_v1_pair_promoted": False,
        })

    class_counts = Counter(
        fault
        for row in finding_rows
        for fault in row["fault_classes"]
    )
    report = {
        "protocol": PROTOCOL,
        "status": "ROOT_CAUSES_FROZEN_V1_REMAINS_FAILED",
        "v1_gate_status_unchanged": frozen["status"],
        "diagnosis": {
            "not_global_semantic_collapse": True,
            "dual_consensus_pass_pairs": frozen["consensus_pass_total"],
            "total_pairs": len(packet_rows),
            "raw_agreement": frozen["projection_agreement"]["raw_agreement"],
            "cohen_kappa": frozen["projection_agreement"]["cohen_kappa"],
            "gwet_ac1": ac1,
            "interpretation": "High raw agreement with low kappa is partly a prevalence effect, while concrete construction and identifiability defects still independently block promotion.",
        },
        "root_cause_class_counts_nonexclusive": dict(sorted(class_counts.items())),
        "prefix_fixed_rs_move_already_performed_pair_ids": rs_nonidentifiable,
        "prefix_fixed_rs_assignment_identifiable": False,
        "required_repair": {
            "instrument": "Trusted evidence is the union of locked prefix, original public current turn, and verified prior candidate. Candidate omission or current irrelevance is never world-fidelity failure; relevance belongs to Rank-1 diagnostics.",
            "rs_assignment": "Replace MOVE_ALREADY_PERFORMED with a factor the authored current user turn can actually manipulate, such as present need versus explicit resolution/decline/redundancy, while treating the assistant move as a prospective response action.",
            "data": "Replace or rewrite every listed pair without reading outcomes, then run a newly versioned full-panel dual review.",
            "reliability": "Freeze raw agreement plus Gwet AC1 before the fresh review. Do not retroactively substitute AC1 into V1.",
        },
        "downstream_authorization": {
            "outcome_blind_repair": True,
            "rank1_diagnostic": True,
            "effect_calls": False,
            "pm_training": False,
        },
        "private_paired_outcome_key_read": False,
        "api_calls": 0,
        "source_hashes": {
            "packet": sha256_file(PACKET),
            "review_A": sha256_file(REVIEW_A),
            "review_B": sha256_file(REVIEW_B),
            "v1_report": sha256_file(REPORT),
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "pair_root_causes_outcome_blind.jsonl", finding_rows)
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
