#!/usr/bin/env python3
"""Freeze V2 primary decisions before gold, preserving auxiliary invalidity."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_g4b_nonexclusive_suitability_review import G4BSuitabilityReview  # noqa: E402


REVIEWS = ROOT / "outputs/pm_v1_5_paper1_v3_g4b1_anchored_v2_reviews_20260811"
PACKET = ROOT / "outputs/pm_v1_5_paper1_v3_g4b1_anchored_v2_controls_20260811"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_g4b1_anchored_v2_primary_decision_freeze_20260811"


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    if OUT.exists():
        raise RuntimeError("V2 primary-decision freeze exists; refusing overwrite")
    raw = rows(REVIEWS / "raw_physical_attempts.jsonl")
    ledger = rows(REVIEWS / "physical_attempt_ledger.jsonl")
    failed = [row for row in ledger if row.get("event") == "FAILED"]
    if len(raw) != 72 or len(failed) != 1:
        raise RuntimeError("expected 72 raw attempts and exactly one terminal auxiliary failure")
    terminal = failed[0]
    if terminal.get("error") != "ValueError: reason_code_not_allowed_for_decision_and_component":
        raise RuntimeError("failure is not the frozen auxiliary reason-code case")
    item_id = terminal["record_ids"]["review_item_id"]
    raw_row = next(row for row in raw if row["review_item_id"] == item_id)
    parsed = G4BSuitabilityReview.model_validate_json(raw_row["provider_text"])
    packet_item = next(
        row
        for row in rows(PACKET / "reviewer_a_controls.jsonl")
        if row["review_item_id"] == item_id
    )
    payload = parsed.model_dump(mode="json")
    allowed_visible = {row["span_id"] for row in packet_item["visible_spans"]}
    allowed_candidate = {row["span_id"] for row in packet_item["candidate_spans"]}
    if payload["review_item_id"] != item_id:
        raise RuntimeError("salvage item identity mismatch")
    if not payload["visible_span_ids"] or not set(payload["visible_span_ids"]) <= allowed_visible:
        raise RuntimeError("salvage visible evidence invalid")
    if not payload["candidate_span_ids"] or not set(payload["candidate_span_ids"]) <= allowed_candidate:
        raise RuntimeError("salvage candidate evidence invalid")
    if payload["checklist_attested"] != "ALL_FOUR_CONSIDERED":
        raise RuntimeError("salvage checklist invalid")
    if payload["primary_reason_code"] in packet_item["decision_contract"][
        {"SUITABLE": "suitable_reason_codes", "NOT_SUITABLE": "not_suitable_reason_codes", "SEMANTIC_ABSTAIN": "abstain_reason_codes"}[payload["decision"]]
    ]:
        raise RuntimeError("salvage case unexpectedly has an allowed auxiliary reason")

    merged = {}
    for reviewer, filename in (
        ("REVIEWER_A", "reviewer_a_controls_reviews.jsonl"),
        ("REVIEWER_B", "reviewer_b_controls_reviews.jsonl"),
    ):
        for row in rows(REVIEWS / filename):
            merged[row["review_item_id"]] = {
                **row,
                "primary_decision_status": "FULL_REVIEW_VALID",
                "auxiliary_reason_valid": True,
            }
    merged[item_id] = {
        **payload,
        "protocol": "pm-v1.5-paper1-v3-g4b1-v2-primary-decision-with-invalid-auxiliary-v1",
        "reviewer_id": "REVIEWER_A",
        "component": packet_item["component"],
        "call_stage": "CONTROL",
        "endpoint_key": terminal["metadata"]["endpoint_key"],
        "model": terminal["metadata"]["model"],
        "review_position": packet_item["review_position"],
        "primary_decision_status": "VALID_PRIMARY_DECISION_AUXILIARY_REASON_INVALID",
        "auxiliary_reason_valid": False,
        "auxiliary_reason_error": "reason_code_not_allowed_for_decision_and_component",
        "raw_attempt_key": terminal["attempt_key"],
        "not_retried_or_repaired": True,
    }
    if len(merged) != 72:
        raise RuntimeError(f"primary-decision freeze denominator drifted: {len(merged)}")
    OUT.mkdir(parents=True)
    for reviewer, stem in (("REVIEWER_A", "reviewer_a"), ("REVIEWER_B", "reviewer_b")):
        selected = sorted(
            (row for row in merged.values() if row["reviewer_id"] == reviewer),
            key=lambda row: row["review_position"],
        )
        if len(selected) != 36:
            raise RuntimeError(f"{reviewer} primary-decision denominator drifted")
        write_jsonl(OUT / f"{stem}_primary_decisions.jsonl", selected)
    report = {
        "protocol": "pm-v1.5-paper1-v3-g4b1-v2-primary-decision-freeze-v1",
        "status": "G4B1_V2_PRIMARY_DECISIONS_72_FROZEN_ONE_AUX_REASON_INVALID_GOLD_MAY_BE_OPENED_SEPARATELY",
        "valid_primary_decisions": 72,
        "full_valid_reviews": 71,
        "auxiliary_reason_invalid": 1,
        "decision_evidence_identity_checklist_valid_in_aux_case": True,
        "raw_decision_changed": False,
        "reason_repaired": False,
        "api_retry": 0,
        "gold_access": False,
        "critical_boundary_behavior": "qualification fails the critical-boundary-reason check if the private gold later identifies this case as critical",
        "reviewer_a": {"path": str((OUT / "reviewer_a_primary_decisions.jsonl").relative_to(ROOT)), "sha256": sha256_file(OUT / "reviewer_a_primary_decisions.jsonl")},
        "reviewer_b": {"path": str((OUT / "reviewer_b_primary_decisions.jsonl").relative_to(ROOT)), "sha256": sha256_file(OUT / "reviewer_b_primary_decisions.jsonl")},
        "training_labels_or_fit": 0,
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
