#!/usr/bin/env python3
"""Open control gold only after both reviewers' results are frozen."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, write_json  # noqa: E402
from metacom_pm.v1_5_g4b_nonexclusive_suitability_review import (  # noqa: E402
    qualify_control_decisions,
)


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_v3_g4b1_control_qualification_phase_v1.json"
REVIEWS = ROOT / "outputs/pm_v1_5_paper1_v3_g4b_reviews_20260811"
GOLD = ROOT / "outputs/pm_v1_5_paper1_v3_g4a_packet_v2_private_20260811/control_gold_key.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_g4b1_control_qualification_20260811"
REVIEWERS = {
    "REVIEWER_A": "reviewer_a_controls_reviews.jsonl",
    "REVIEWER_B": "reviewer_b_controls_reviews.jsonl",
}


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> None:
    if OUT.exists():
        raise RuntimeError("G4B1 qualification output exists; refusing overwrite")
    authority = read(AUTHORITY)
    current = authority["active_v3_phase"]
    if current["id"] != "G4B1_CONTROL_QUALIFICATION":
        raise RuntimeError("G4B1 control qualification is not active")
    binding = current["active_phase_manifest"]
    if (
        binding["path"] != str(PHASE.relative_to(ROOT))
        or binding["sha256"] != sha256_file(PHASE)
    ):
        raise RuntimeError("G4B1 qualification phase binding drifted")
    phase = read(PHASE)
    for bound in [*phase["input_bindings"], *phase["implementation_bindings"]]:
        if sha256_file(ROOT / bound["path"]) != bound["sha256"]:
            raise RuntimeError(f"bound artifact drifted: {bound['path']}")

    live = read(REVIEWS / "controls_live_report.json")
    if live["status"] != "G4B_CONTROL_REVIEWS_COMPLETE":
        raise RuntimeError("both reviewers must freeze all 72 controls first")
    gold = rows(GOLD)
    if len(gold) != 36:
        raise RuntimeError("control gold denominator drifted")

    gold_by_reviewer_component: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for truth in gold:
        for reviewer_id, suffix in (("REVIEWER_A", "a"), ("REVIEWER_B", "b")):
            gold_by_reviewer_component[(reviewer_id, truth["component"])].append(
                {
                    **truth,
                    "review_item_id": truth[f"reviewer_{suffix}_item_id"],
                }
            )

    results: dict[str, Any] = {}
    for reviewer_id, filename in REVIEWERS.items():
        reviewer_rows = rows(REVIEWS / filename)
        results[reviewer_id] = {}
        for component in ("MP", "MS", "ME"):
            component_ids = {
                row["review_item_id"]
                for row in gold_by_reviewer_component[(reviewer_id, component)]
            }
            observed = [
                row for row in reviewer_rows if row["review_item_id"] in component_ids
            ]
            results[reviewer_id][component] = qualify_control_decisions(
                observed, gold_by_reviewer_component[(reviewer_id, component)]
            )

    eligible = [
        component
        for component in ("MP", "MS", "ME")
        if all(
            results[reviewer][component]["status"] == "QUALIFIED"
            for reviewer in REVIEWERS
        )
    ]
    fixed_off = [component for component in ("MP", "MS", "ME") if component not in eligible]
    status = (
        "G4B1_CONTROL_QUALIFICATION_PASS_PUBLIC_PHASE_MAY_BE_DESIGNED"
        if eligible
        else "G4B1_CONTROL_QUALIFICATION_FAIL_NO_MEMORY_PUBLIC_REVIEW"
    )
    report = {
        "protocol": "pm-v1.5-paper1-v3-g4b1-control-qualification-report-v1",
        "status": status,
        "reviewer_component_results": results,
        "eligible_components": eligible,
        "fixed_off_components": fixed_off,
        "component_independent": True,
        "one_component_failure_does_not_disable_other_components": True,
        "gold_first_opened_after_all_control_results_frozen": True,
        "gold_did_not_enter_provider_prompt_or_execution_runner": True,
        "no_gate_control_codebook_or_prompt_change_after_results": True,
        "public_reviews_created": 0,
        "training_labels_created": 0,
        "api_calls": 0,
        "next_gate": (
            "G4B2_PUBLIC_DUAL_REVIEW_PHASE_DESIGN_FOR_ELIGIBLE_COMPONENTS"
            if eligible
            else "MEMORY_HEAD_CONTROL_FAILURE_CLOSEOUT_OR_PREDECLARED_REPLACEMENT_REVIEWER"
        ),
    }
    OUT.mkdir(parents=True)
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
