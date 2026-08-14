#!/usr/bin/env python3
"""Validate, freeze, and analyze two independent V5.3 calibration reviews.

The private outcome key is not read until both reviewer ledgers are complete,
schema-valid, excerpt-grounded, identity-complete, and hash-frozen.  The script
fails closed on the currently distributed blank templates.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402


PROTOCOL = "pm-v1.5-v5.3-dual-reviewer-calibration-v1"
DIR = ROOT / "outputs/pm_v1_5_v5_3_dual_reviewer_calibration_20260810"
PACKET = DIR / "review_packet_blind.jsonl"
REVIEW_A = DIR / "reviewer_A_completed.jsonl"
REVIEW_B = DIR / "reviewer_B_completed.jsonl"
PRIVATE = DIR / "private_outcome_key_do_not_open_until_both_reviews_freeze.jsonl"
FREEZE = DIR / "dual_review_freeze_before_private_key_open.json"

CANDIDATE = {
    "VALID_APPLICABLE",
    "VALID_REDUNDANT",
    "VALID_NOT_USEFUL",
    "INVALID_WRONG_OWNER_TIME_EVENT",
    "UNRESOLVED",
}
FUNCTION = {
    "FUNCTIONAL",
    "SURFACE_ECHO_ONLY",
    "NOT_USED_FINAL",
    "BOUNDARY_FAILURE",
    "UNRESOLVED",
}
YES_NO_UNKNOWN = {"YES", "NO", "UNRESOLVED"}
GUARD = {"TRUE_ACCEPT", "FALSE_ACCEPT", "UNRESOLVED"}
PREFERENCE = {"ON_BETTER", "OFF_BETTER", "TIE", "UNRESOLVED"}
RISK_ATTRIBUTION = {"SAFE", "UNSAFE", "UNRESOLVED"}
RISK_EVENTS = {
    "WRONG_OWNER",
    "FUTURE_OR_PRIVATE_FABRICATION",
    "EXPLICIT_BOUNDARY_VIOLATION",
    "EXCESSIVE_DIRECTIVENESS_OR_BURDEN",
}


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _literal_or_empty(excerpt: str, surface: str, field: str) -> None:
    if excerpt and excerpt not in surface:
        raise ValueError(f"{field} is not a literal packet excerpt: {excerpt!r}")


def _require(value: str, allowed: set[str], field: str) -> None:
    if value not in allowed:
        raise ValueError(f"{field} must be one of {sorted(allowed)}; got {value!r}")


def _validate_review(
    *, reviewer: str, rows: list[dict[str, Any]], packet: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    packet_by_id = {str(row["calibration_id"]): row for row in packet}
    review_by_id = {str(row.get("calibration_id")): row for row in rows}
    if len(rows) != len(review_by_id):
        raise ValueError(f"{reviewer} has duplicate calibration_id")
    if set(review_by_id) != set(packet_by_id):
        raise ValueError(f"{reviewer} calibration identities do not match packet")

    for calibration_id, judgment in review_by_id.items():
        item = packet_by_id[calibration_id]
        if judgment.get("protocol") != PROTOCOL:
            raise ValueError(f"{reviewer}:{calibration_id} protocol mismatch")
        if judgment.get("reviewer_id") != reviewer:
            raise ValueError(f"{reviewer}:{calibration_id} reviewer_id mismatch")
        _require(str(judgment.get("candidate_truth")), CANDIDATE, "candidate_truth")
        dialogue_surface = "\n".join(
            str(row["content"]) for row in item["visible_dialogue"]
        )
        candidate = item["verified_past_panel"]
        candidate_surface = str(candidate["candidate_text"]) + "\n" + json.dumps(
            candidate["typed_candidate"], ensure_ascii=False, sort_keys=True
        )
        current_excerpt = str(judgment.get("candidate_current_evidence_excerpt") or "")
        resource_excerpt = str(judgment.get("candidate_resource_evidence_excerpt") or "")
        _literal_or_empty(current_excerpt, dialogue_surface, "candidate_current_evidence_excerpt")
        _literal_or_empty(resource_excerpt, candidate_surface, "candidate_resource_evidence_excerpt")
        if judgment["candidate_truth"] == "VALID_APPLICABLE" and (
            not current_excerpt or not resource_excerpt
        ):
            raise ValueError(f"{reviewer}:{calibration_id} applicable candidate needs two excerpts")

        packet_rep = {str(row["replicate_id"]): row for row in item["replicates"]}
        judged_rep = {
            str(row.get("replicate_id")): row for row in judgment.get("replicates") or []
        }
        if len(judged_rep) != 3 or set(judged_rep) != set(packet_rep):
            raise ValueError(f"{reviewer}:{calibration_id} replicate identity mismatch")
        for replicate_id, rep in judged_rep.items():
            source = packet_rep[replicate_id]
            _require(str(rep.get("functional_execution")), FUNCTION, "functional_execution")
            _require(
                str(rep.get("owner_time_boundary_correct")),
                YES_NO_UNKNOWN,
                "owner_time_boundary_correct",
            )
            _require(str(rep.get("guard_acceptance")), GUARD, "guard_acceptance")
            _require(str(rep.get("response_preference")), PREFERENCE, "response_preference")
            _require(
                str(rep.get("resource_risk_attribution")),
                RISK_ATTRIBUTION,
                "resource_risk_attribution",
            )
            for arm in ("on_absolute_risk_events", "off_absolute_risk_events"):
                values = rep.get(arm)
                if not isinstance(values, list) or len(values) != len(set(values)):
                    raise ValueError(f"{reviewer}:{calibration_id}:{arm} invalid list")
                if not set(values).issubset(RISK_EVENTS):
                    raise ValueError(f"{reviewer}:{calibration_id}:{arm} invalid event")
            contribution = str(rep.get("candidate_contribution_excerpt") or "")
            response = str(rep.get("on_response_excerpt") or "")
            _literal_or_empty(contribution, candidate_surface, "candidate_contribution_excerpt")
            _literal_or_empty(response, str(source["on_reply"]), "on_response_excerpt")
            if rep["functional_execution"] == "FUNCTIONAL" and (
                not contribution
                or not response
                or rep["owner_time_boundary_correct"] != "YES"
            ):
                raise ValueError(
                    f"{reviewer}:{calibration_id}:{replicate_id} FUNCTIONAL lacks binding"
                )
    return review_by_id


def _agreement(left: Iterable[str], right: Iterable[str]) -> dict[str, Any]:
    a = list(left)
    b = list(right)
    if len(a) != len(b) or not a:
        raise ValueError("agreement vectors must be nonempty and equal length")
    labels = sorted(set(a) | set(b))
    observed = sum(x == y for x, y in zip(a, b)) / len(a)
    left_counts = Counter(a)
    right_counts = Counter(b)
    expected = sum(
        left_counts[label] / len(a) * right_counts[label] / len(b)
        for label in labels
    )
    kappa = None if expected >= 1.0 else (observed - expected) / (1.0 - expected)
    return {
        "n": len(a),
        "labels": labels,
        "raw_agreement": observed,
        "cohen_kappa": kappa,
        "left_counts": dict(left_counts),
        "right_counts": dict(right_counts),
    }


def _passes(metric: dict[str, Any], *, raw: float, kappa: float) -> bool:
    return (
        metric["raw_agreement"] >= raw
        and metric["cohen_kappa"] is not None
        and metric["cohen_kappa"] >= kappa
    )


def main() -> None:
    packet = _jsonl(PACKET)
    if len(packet) != 64 or len({row["calibration_id"] for row in packet}) != 64:
        raise RuntimeError("frozen 64-group packet required")
    review_a = _validate_review(
        reviewer="REVIEWER_A", rows=_jsonl(REVIEW_A), packet=packet
    )
    review_b = _validate_review(
        reviewer="REVIEWER_B", rows=_jsonl(REVIEW_B), packet=packet
    )

    freeze = {
        "protocol": PROTOCOL,
        "status": "BOTH_REVIEWS_VALIDATED_AND_FROZEN_BEFORE_PRIVATE_KEY_OPEN",
        "groups": 64,
        "packet_sha256": sha256_file(PACKET),
        "reviewer_A_sha256": sha256_file(REVIEW_A),
        "reviewer_B_sha256": sha256_file(REVIEW_B),
        "private_key_read_before_freeze": False,
        "api_calls_by_analysis": 0,
    }
    if FREEZE.exists():
        if json.loads(FREEZE.read_text()) != freeze:
            raise RuntimeError("existing review freeze differs; refuse overwrite")
    else:
        write_json(FREEZE, freeze)

    # Only after the durable review freeze exists may the historical key open.
    private = _jsonl(PRIVATE)
    if len(private) != 64:
        raise RuntimeError("private key identity count mismatch")

    ordered_ids = [str(row["calibration_id"]) for row in packet]
    candidate_a = [
        "CLEAR" if review_a[key]["candidate_truth"] == "VALID_APPLICABLE" else "NONCLEAR"
        for key in ordered_ids
    ]
    candidate_b = [
        "CLEAR" if review_b[key]["candidate_truth"] == "VALID_APPLICABLE" else "NONCLEAR"
        for key in ordered_ids
    ]
    function_a: list[str] = []
    function_b: list[str] = []
    preference_a: list[str] = []
    preference_b: list[str] = []
    risk_a: list[str] = []
    risk_b: list[str] = []
    disagreements: list[dict[str, Any]] = []
    packet_by_id = {str(row["calibration_id"]): row for row in packet}

    for calibration_id in ordered_ids:
        left = review_a[calibration_id]
        right = review_b[calibration_id]
        left_rep = {str(row["replicate_id"]): row for row in left["replicates"]}
        right_rep = {str(row["replicate_id"]): row for row in right["replicates"]}
        group_disagrees = left["candidate_truth"] != right["candidate_truth"]
        for replicate_id in sorted(left_rep):
            lrep = left_rep[replicate_id]
            rrep = right_rep[replicate_id]
            function_a.append(
                "QUALIFIED" if lrep["functional_execution"] == "FUNCTIONAL" else "NONQUALIFIED"
            )
            function_b.append(
                "QUALIFIED" if rrep["functional_execution"] == "FUNCTIONAL" else "NONQUALIFIED"
            )
            preference_a.append(str(lrep["response_preference"]))
            preference_b.append(str(rrep["response_preference"]))
            risk_a.append(str(lrep["resource_risk_attribution"]))
            risk_b.append(str(rrep["resource_risk_attribution"]))
            group_disagrees = group_disagrees or any(
                lrep[field] != rrep[field]
                for field in (
                    "functional_execution",
                    "response_preference",
                    "resource_risk_attribution",
                    "guard_acceptance",
                )
            )
        if group_disagrees:
            disagreements.append(
                {
                    "protocol": PROTOCOL,
                    "calibration_id": calibration_id,
                    "blind_packet": packet_by_id[calibration_id],
                    "reviewer_A": left,
                    "reviewer_B": right,
                    "adjudication": {},
                }
            )

    metrics = {
        "candidate_clear_applicability": _agreement(candidate_a, candidate_b),
        "functional_qualified": _agreement(function_a, function_b),
        "response_preference_direction": _agreement(preference_a, preference_b),
        "risk_attribution_diagnostic": _agreement(risk_a, risk_b),
    }
    gates = {
        "candidate_clear_applicability": _passes(
            metrics["candidate_clear_applicability"], raw=0.80, kappa=0.60
        ),
        "functional_qualified": _passes(
            metrics["functional_qualified"], raw=0.80, kappa=0.60
        ),
        "response_preference_direction": _passes(
            metrics["response_preference_direction"], raw=0.70, kappa=0.40
        ),
    }
    report = {
        "protocol": PROTOCOL,
        "status": (
            "MEASUREMENT_AGREEMENT_PASS_ADJUDICATION_AND_LABEL_SUPPORT_PENDING"
            if all(gates.values())
            else "MEASUREMENT_AGREEMENT_FAIL_NO_TRAINING"
        ),
        "metrics": metrics,
        "gates": gates,
        "all_primary_gates_pass": all(gates.values()),
        "disagreement_groups": len(disagreements),
        "private_key_opened_only_after_review_freeze": True,
        "training_authorized": False,
        "next_required": (
            "adjudicate disagreements, then audit clean bidirectional independent-cluster support"
            if all(gates.values())
            else "repair the measurement rubric/judge and freeze a new named calibration sample"
        ),
        "api_calls_by_analysis": 0,
    }
    write_jsonl(DIR / "adjudication_packet.jsonl", disagreements)
    write_json(DIR / "agreement_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
