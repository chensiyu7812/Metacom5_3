#!/usr/bin/env python3
"""Freeze P2B raw agreement and component qualification before adjudication."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_paper1_suitability import (  # noqa: E402
    SUITABILITY_AXES,
    component_qualification,
)


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_p2b_dual_reviewer_suitability_phase_v1.json"
REVIEWS = ROOT / "outputs/pm_v1_5_paper1_p2b_dual_reviews_20260810"
CASE_KEY = ROOT / "outputs/pm_v1_5_paper1_p2a_suitability_packet_private/private_case_key.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_p2b_pre_adjudication_20260810"
PRIVATE = ROOT / "outputs/pm_v1_5_paper1_p2b_pre_adjudication_private_20260810"


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    if OUT.exists() or PRIVATE.exists():
        raise RuntimeError("P2B pre-adjudication output exists; refusing overwrite")
    authority = read(AUTHORITY)
    current = authority["current_phase"]
    if current["id"] != "P2B_DUAL_REVIEWER_SUITABILITY_QUALIFICATION":
        raise RuntimeError("P2B is not active")
    if current["active_phase_manifest"]["sha256"] != sha256_file(PHASE):
        raise RuntimeError("P2B phase hash is not authority-bound")
    live = read(REVIEWS / "public_live_report.json")
    if live["status"] != "PUBLIC_REVIEWS_COMPLETE_AWAITING_PRE_ADJUDICATION_ANALYSIS":
        raise RuntimeError("public reviews are not complete")
    control = read(REVIEWS / "control_qualification_report.json")
    if control["status"] != "CONTROL_PASS_PUBLIC_MAY_RUN":
        raise RuntimeError("control qualification did not pass")
    eligible = set(control["eligible_components"])
    reviewer_a = {row["review_item_id"]: row for row in rows(REVIEWS / "reviewer_a_public_reviews.jsonl")}
    reviewer_b = {row["review_item_id"]: row for row in rows(REVIEWS / "reviewer_b_public_reviews.jsonl")}
    paired_by_component: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for key in rows(CASE_KEY):
        component = key["component"]
        if component not in eligible:
            continue
        aid = key["reviewer_a_item_id"]
        bid = key["reviewer_b_item_id"]
        if aid not in reviewer_a or bid not in reviewer_b:
            raise RuntimeError(f"missing frozen review pair for {key['case_key']}")
        a = reviewer_a[aid]
        b = reviewer_b[bid]
        paired_by_component[component].append(
            {
                "case_key": key["case_key"],
                "state_id": key["state_id"],
                "split_group_key": key["split_group_key"],
                "component": component,
                "reviewer_a_axes": {axis: a["axes"][axis]["decision"] for axis in SUITABILITY_AXES},
                "reviewer_b_axes": {axis: b["axes"][axis]["decision"] for axis in SUITABILITY_AXES},
                "reviewer_a_derived": a["derived_suitability"],
                "reviewer_b_derived": b["derived_suitability"],
            }
        )
    qualifications: dict[str, Any] = {}
    all_pairs: list[dict[str, Any]] = []
    for component in ("MP", "MS", "ME", "RS"):
        if component not in eligible:
            qualifications[component] = {
                "status": "FAILED_FIXED_OFF",
                "failed_checks": ["reviewer_control_ineligible"],
                "pre_adjudication_only": True,
            }
            continue
        pairs = paired_by_component[component]
        qualifications[component] = component_qualification(pairs)
        all_pairs.extend(pairs)
    passed = [component for component, result in qualifications.items() if result["status"] == "QUALIFIED"]
    primary = "RS" in passed and any(component in passed for component in ("MP", "MS", "ME"))
    PRIVATE.mkdir(parents=True)
    pair_path = PRIVATE / "paired_raw_judgments.jsonl"
    write_jsonl(pair_path, all_pairs)
    report = {
        "protocol": "pm-v1.5-paper1-p2b-pre-adjudication-qualification-report-v1",
        "status": "P2B_MEASUREMENT_QUALIFIED_ADJUDICATION_MAY_BE_DESIGNED" if primary else "P2B_MEASUREMENT_FAILED_PRIMARY_FIXED_OFF_CLOSEOUT",
        "component_qualification": qualifications,
        "qualified_components": passed,
        "fixed_off_components": [component for component in ("MP", "MS", "ME", "RS") if component not in passed],
        "paper1_primary_head_surface_feasible": primary,
        "raw_agreement_frozen_before_adjudication": True,
        "adjudication_has_not_occurred": True,
        "paired_raw_judgments": {"path": str(pair_path.relative_to(ROOT)), "sha256": sha256_file(pair_path), "rows": len(all_pairs)},
        "no_gate_change_append_or_prompt_rewrite": True,
        "api_calls": 0,
        "responses_safe_yield_pm_baselines_external_outcomes": 0,
    }
    OUT.mkdir(parents=True)
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
