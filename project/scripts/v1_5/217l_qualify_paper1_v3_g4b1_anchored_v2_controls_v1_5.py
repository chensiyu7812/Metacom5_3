#!/usr/bin/env python3
"""Qualify frozen G4B1 anchored V2 primary decisions after gold opens."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, write_json  # noqa: E402
from metacom_pm.v1_5_g4b_nonexclusive_suitability_review import qualify_control_decisions  # noqa: E402


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_v3_g4b1_anchored_v2_qualification_phase_v1.json"
FREEZE = ROOT / "outputs/pm_v1_5_paper1_v3_g4b1_anchored_v2_primary_decision_freeze_20260811"
GOLD = ROOT / "outputs/pm_v1_5_paper1_v3_g4b1_anchored_v2_controls_private_20260811/control_gold_key.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_g4b1_anchored_v2_qualification_20260811"


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    if OUT.exists():
        raise RuntimeError("anchored V2 qualification output exists; refusing overwrite")
    authority = read(AUTHORITY)
    current = authority["active_v3_phase"]
    if current["id"] != "G4B1_ANCHORED_V2_CONTROL_QUALIFICATION":
        raise RuntimeError("anchored V2 qualification is not active")
    binding = current["active_phase_manifest"]
    if binding["path"] != str(PHASE.relative_to(ROOT)) or binding["sha256"] != sha256_file(PHASE):
        raise RuntimeError("anchored V2 qualification phase binding drifted")
    phase = read(PHASE)
    for bound in [*phase["input_bindings"], *phase["implementation_bindings"]]:
        if sha256_file(ROOT / bound["path"]) != bound["sha256"]:
            raise RuntimeError(f"qualification input drifted: {bound['path']}")
    freeze_report = read(FREEZE / "report.json")
    if freeze_report["status"] != "G4B1_V2_PRIMARY_DECISIONS_72_FROZEN_ONE_AUX_REASON_INVALID_GOLD_MAY_BE_OPENED_SEPARATELY":
        raise RuntimeError("72 primary decisions were not frozen before gold")
    gold = rows(GOLD)
    observed_by_reviewer = {
        "REVIEWER_A": rows(FREEZE / "reviewer_a_primary_decisions.jsonl"),
        "REVIEWER_B": rows(FREEZE / "reviewer_b_primary_decisions.jsonl"),
    }
    projected: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for truth in gold:
        for reviewer, suffix in (("REVIEWER_A", "a"), ("REVIEWER_B", "b")):
            projected[(reviewer, truth["component"])].append(
                {**truth, "review_item_id": truth[f"reviewer_{suffix}_item_id"]}
            )
    results = {}
    for reviewer, observed in observed_by_reviewer.items():
        results[reviewer] = {}
        for component in ("MP", "MS", "ME"):
            ids = {row["review_item_id"] for row in projected[(reviewer, component)]}
            results[reviewer][component] = qualify_control_decisions(
                [row for row in observed if row["review_item_id"] in ids],
                projected[(reviewer, component)],
            )
    eligible = [
        component for component in ("MP", "MS", "ME")
        if all(results[reviewer][component]["status"] == "QUALIFIED" for reviewer in results)
    ]
    report = {
        "protocol": "pm-v1.5-paper1-v3-g4b1-anchored-v2-qualification-report-v1",
        "status": (
            "G4B1_ANCHORED_V2_QUALIFICATION_PASS_PUBLIC_REVIEW_MAY_BE_DESIGNED"
            if eligible
            else "G4B1_ANCHORED_V2_QUALIFICATION_FAIL_NO_THIRD_INSTRUMENT_LOOP"
        ),
        "reviewer_component_results": results,
        "eligible_components": eligible,
        "fixed_off_components": [c for c in ("MP", "MS", "ME") if c not in eligible],
        "v1_failure_remains_frozen": True,
        "v2_is_final_llm_instrument_wave": True,
        "one_auxiliary_reason_invalid_was_not_repaired": True,
        "raw_primary_decisions_changed": False,
        "gold_first_opened_after_72_primary_decisions_froze": True,
        "public_reviews_labels_fit_generator": 0,
        "api_calls": 0,
        "next_gate": (
            "G4B2_PUBLIC_DUAL_REVIEW_FOR_ELIGIBLE_COMPONENTS_ONLY"
            if eligible
            else "CLOSE_FAILED_LLM_LABEL_COMPONENTS_OR_SEPARATELY_PREREGISTER_NON_LLM_ANNOTATION"
        ),
    }
    OUT.mkdir(parents=True)
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
