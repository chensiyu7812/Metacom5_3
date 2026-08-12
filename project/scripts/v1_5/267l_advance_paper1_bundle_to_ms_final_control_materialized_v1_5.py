#!/usr/bin/env python3
"""Advance the single active-execution-bundle pointer past fresh MS control materialization.

This does not authorize review calls, reannotation, labels, fits, or generator
calls. It only records that the one permitted fresh-control materialization +
independent zero-API construct audit (266l) is done and PASS, and repoints
paper1_active_execution_bundle_v1.json / active_method_authority_v1.json so no
runner or future session can infer currency from filenames or chronology
instead of this pointer.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
BUNDLE = ROOT / "data/pm_v1_5_contracts/paper1_active_execution_bundle_v1.json"
DESIGN = ROOT / "data/pm_v1_5_contracts/paper1_ms_final_control_construct_repair_design_v1.json"
LEDGER = ROOT / "docs/PM_V1_TO_V1_5_GLOBAL_FAILURE_LEDGER_ZH.md"
MATERIALIZE_SCRIPT = ROOT / "scripts/v1_5/266l_materialize_paper1_ms_final_control_repair_v1_5.py"
MATERIALIZATION_REPORT = ROOT / "outputs/pm_v1_5_paper1_ms_final_control_repair_20260812/report.json"
CONTROLS = ROOT / "outputs/pm_v1_5_paper1_ms_final_control_repair_20260812/final_control_repair_controls_blind.jsonl"
CLOSEOUT_OUT = ROOT / "data/pm_v1_5_contracts/paper1_ms_final_control_repair_materialization_closeout_v1.json"

EXPECTED_MATERIALIZATION_STATUS = "ZERO_API_FRESH_CONTROLS_MATERIALIZED_LOCAL_CONSTRUCT_AUDIT_PASS_REVIEW_CALLS_NOT_YET_AUTHORIZED"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    if CLOSEOUT_OUT.exists():
        raise RuntimeError("closeout already exists; refuse overwrite")
    materialization = read(MATERIALIZATION_REPORT)
    if materialization["status"] != EXPECTED_MATERIALIZATION_STATUS:
        raise RuntimeError("266l materialization report is not in the expected PASS state")
    if materialization["counts"]["items"] != 12 or materialization["counts"]["distribution"] != {
        "NOT_SUITABLE": 5,
        "SUITABLE": 5,
        "SEMANTIC_ABSTAIN": 2,
    }:
        raise RuntimeError("materialization counts/distribution drifted from expected 5/5/2")
    if materialization["api_calls"] != 0 or materialization["training_labels_created_or_changed"] != 0 or materialization["fits"] != 0:
        raise RuntimeError("materialization spent API/label/fit budget; refuse to advance silently")

    authority = read(AUTHORITY)
    bundle = read(BUNDLE)
    current = authority["current_execution_phase"]
    alias = authority["active_v3_phase"]
    expected_bundle_binding = {"path": str(BUNDLE.relative_to(ROOT)), "sha256": sha(BUNDLE)}
    if current["id"] != "MS_SOURCE_ANNOTATED_CONTROL_REPAIR_DESIGN":
        raise RuntimeError("authority current phase is not the pre-materialization design phase; refuse to guess")
    if current["active_phase_manifest"] != expected_bundle_binding:
        raise RuntimeError("authority does not point at the current bundle hash; refuse to advance on drifted state")
    if alias.get("compatibility_alias_of") != "current_execution_phase" or alias["active_phase_manifest"] != expected_bundle_binding:
        raise RuntimeError("authority compatibility alias drifted from current_execution_phase")

    closeout = {
        "protocol": "pm-v1.5-paper1-ms-final-control-repair-materialization-closeout-v1",
        "date": "2026-08-12",
        "status": "FRESH_CONTROLS_MATERIALIZED_LOCAL_AUDIT_PASS_REVIEW_CALLS_NOT_YET_AUTHORIZED",
        "method_version": bundle["method"]["base_method_id"],
        "experiment_revision": bundle["git"]["allowed_experiment_revision"],
        "executed_script": {
            "path": str(MATERIALIZE_SCRIPT.relative_to(ROOT)),
            "sha256": sha(MATERIALIZE_SCRIPT),
        },
        "design": {
            "path": str(DESIGN.relative_to(ROOT)),
            "sha256": sha(DESIGN),
        },
        "artifacts": [
            {
                "role": "controls_blind",
                "path": str(CONTROLS.relative_to(ROOT)),
                "sha256": sha(CONTROLS),
            },
            {
                "role": "materialization_report",
                "path": str(MATERIALIZATION_REPORT.relative_to(ROOT)),
                "sha256": sha(MATERIALIZATION_REPORT),
                "required_status": EXPECTED_MATERIALIZATION_STATUS,
            },
            {
                "role": "global_failure_ledger",
                "path": str(LEDGER.relative_to(ROOT)),
                "sha256": sha(LEDGER),
            },
        ],
        "observed": {
            "items": 12,
            "distribution": {"SUITABLE": 5, "NOT_SUITABLE": 5, "SEMANTIC_ABSTAIN": 2},
            "families_covered": 11,
            "max_content_overlap_jaccard_vs_retired_12": materialization["max_content_overlap_jaccard"]["vs_retired_12"],
            "max_content_overlap_jaccard_vs_public_201": materialization["max_content_overlap_jaccard"]["vs_public_201"],
            "api_calls": 0,
            "training_labels_created_or_changed": 0,
            "fits": 0,
        },
        "construct_repairs_verified": materialization["construct_repairs_verified"],
        "authorization": {
            "fresh_control_materialization": True,
            "review_calls": False,
            "public_201_reannotation": False,
            "training_label_change": False,
            "pm_fit_or_threshold_change": False,
            "generator_calls": False,
            "MP_or_ME_work": False,
            "baseline_or_external_calls": False,
        },
        "invariants": {
            "content_disjoint_from_retired_and_public_201": True,
            "sixteen_actions_unchanged": True,
            "no_single_memory_cap": True,
            "retired_identity_not_reused": True,
            "one_new_reviewer_identity_required_for_next_qualification": True,
        },
        "next_gate": materialization["next_gate"],
    }
    write_json(CLOSEOUT_OUT, closeout)
    closeout_binding = {"path": str(CLOSEOUT_OUT.relative_to(ROOT)), "sha256": sha(CLOSEOUT_OUT)}

    new_files = []
    for row in bundle["files"]:
        if row["role"] == "parent_current_phase_closeout":
            new_files.append({**row, "path": closeout_binding["path"], "sha256": closeout_binding["sha256"]})
        else:
            new_files.append(row)
    new_files.append({
        "role": "ms_final_control_materialization_and_audit_report",
        "path": str(MATERIALIZATION_REPORT.relative_to(ROOT)),
        "sha256": sha(MATERIALIZATION_REPORT),
    })

    bundle["current_phase"] = {
        "id": "MS_FINAL_CONTROL_REPAIR_MATERIALIZED_AUDIT_PASS",
        "status": "FRESH_CONTROLS_MATERIALIZED_LOCAL_AUDIT_PASS_REVIEW_CALLS_NOT_YET_AUTHORIZED",
        "parent_phase": closeout_binding,
        "next_scientific_action": (
            "Authorize and run the fresh-identity 24-call qualification (12 items x GPT-5.6 + Gemini) exactly "
            "once against these 12 fresh controls. This is the last permitted MS control-construct check; on "
            "failure the pre-registered fallback is to retire the MS label route and proceed with MP/ME only."
        ),
        "authorization": {
            "api_calls": 0,
            "training_labels": 0,
            "diagnostic_fits": 0,
            "generator_calls": 0,
            "external_execution": False,
        },
    }
    bundle["files"] = new_files
    write_json(BUNDLE, bundle)
    new_bundle_binding = {"path": str(BUNDLE.relative_to(ROOT)), "sha256": sha(BUNDLE)}

    for phase_key in ("current_execution_phase", "active_v3_phase"):
        phase = authority[phase_key]
        phase["id"] = bundle["current_phase"]["id"]
        phase["status"] = bundle["current_phase"]["status"]
        phase["active_phase_manifest"] = new_bundle_binding
        if phase_key == "current_execution_phase":
            phase["scope"] = (
                "Fresh MS control materialization and its independent zero-API construct audit are complete "
                "and PASS. Next work is authorizing and running the fresh-identity 24-call qualification only. "
                "No 201-item reannotation, labels, fits, generator, MP/ME execution, baseline, or external work."
            )
        phase["api_calls_authorized"] = 0
        phase["training_labels_authorized"] = 0
        phase["diagnostic_fits_authorized"] = 0
    authority["status"] = "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_MS_FINAL_CONTROL_MATERIALIZED_AUDIT_PASS"
    write_json(AUTHORITY, authority)

    print(json.dumps({
        "protocol": "pm-v1.5-paper1-bundle-advance-report-v1",
        "status": "ADVANCED_TO_MS_FINAL_CONTROL_REPAIR_MATERIALIZED_AUDIT_PASS",
        "closeout": closeout_binding,
        "bundle": new_bundle_binding,
        "api_calls": 0,
        "training_labels": 0,
        "fits": 0,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
