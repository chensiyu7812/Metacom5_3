from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_v3_g4a_packet_materialization_phase_v1.json"
DEFAULT_OUTPUT = ROOT / "outputs/pm_v1_5_paper1_v3_g4a_packet_phase_validation_20260811/report.json"


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    path.relative_to(ROOT.resolve())
    return path


def validate() -> dict[str, Any]:
    phase = _read(PHASE)
    inputs = {row["role"]: row for row in phase["input_bindings"]}
    design = _read(_resolve(inputs["g4_design"]["path"]))
    design_report = _read(_resolve(inputs["g4_design_validation"]["path"]))
    authorization = phase["authorization"]
    selection = phase["selection_contract"]
    controls = phase["fresh_controls"]
    checks = {
        "protocol_status_and_parent_frozen": phase["protocol"]
        == "pm-v1.5-paper1-v3-g4a-packet-materialization-phase-v1"
        and phase["status"]
        == "G4A_ZERO_API_NONEXCLUSIVE_PACKET_AND_FRESH_CONTROLS_AUTHORIZED_ONCE"
        and len(phase["promoted_from_authority_sha256"]) == 64,
        "all_input_hashes_match": all(
            _sha(_resolve(row["path"])) == row["sha256"]
            for row in phase["input_bindings"]
        ),
        "validated_design_is_exact_parent": design_report["status"]
        == "G4_NONEXCLUSIVE_SUITABILITY_DESIGN_PASS_G4A_PACKET_PHASE_MAY_BE_DESIGNED"
        and design["status"]
        == "G4_ZERO_API_DESIGN_FROZEN_PACKET_MATERIALIZATION_NOT_AUTHORIZED",
        "selection_denominator_exact": selection
        == {
            "MP": 204,
            "MS": 204,
            "ME": 99,
            "total": 507,
            "same_state_cross_component_allowed": True,
            "all_three_shared_state_groups_required": 14,
            "within_component_duplicate_case_forbidden": True,
            "proxy_flags_are_sampling_only": True,
            "suitability_labels_remain_null": True,
        },
        "selection_matches_design": selection["MP"]
        == design["packet_capacity"]["MP"]["planned_cases"]
        and selection["MS"] == design["packet_capacity"]["MS"]["planned_cases"]
        and selection["ME"] == design["packet_capacity"]["ME"]["planned_cases"]
        and selection["total"] == design["packet_capacity"]["total_planned_cases"],
        "fresh_controls_match_design": controls["per_component"] == 12
        and controls["total"] == 36
        and controls["per_component_distribution"]
        == {"SUITABLE": 5, "NOT_SUITABLE": 5, "SEMANTIC_ABSTAIN": 2}
        and controls["must_not_reuse_old_p2b_control_or_public_case"] is True,
        "only_zero_api_materialization_authorized": all(
            authorization[key] is True
            for key in (
                "read_bound_inputs",
                "packet_materialization",
                "fresh_control_materialization",
                "private_key_materialization",
                "json_and_html_report",
            )
        )
        and all(
            authorization[key] is False
            for key in (
                "reviewer_calls",
                "human_label_collection",
                "suitability_label_creation",
                "pm_fit",
                "generator_calls",
                "paid_execution",
                "baseline_execution",
                "external_execution",
                "overwrite_successful_output",
            )
        ),
        "blinding_is_nonexclusive_but_link_hidden": phase["blinding_contract"][
            "same_state_cross_component_link_not_visible"
        ]
        is True
        and phase["blinding_contract"]["private_case_key_not_in_public_payload"]
        is True
        and selection["same_state_cross_component_allowed"] is True,
        "new_paths_do_not_touch_old_p2": all(
            "p2a_suitability_packet" not in path and "suitability_review.py" not in path
            for path in phase["allowed_new_paths"]
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "protocol": "pm-v1.5-paper1-v3-g4a-packet-phase-validation-v1",
        "status": (
            "G4A_PACKET_PHASE_PASS_ZERO_API_MATERIALIZATION_MAY_BE_AUTHORIZED"
            if not failed
            else "G4A_PACKET_PHASE_FAIL_CLOSED"
        ),
        "checks": checks,
        "failed_checks": failed,
        "hashes": {
            "phase_sha256": _sha(PHASE),
            "parent_authority_sha256": phase["promoted_from_authority_sha256"],
            "g4_design_sha256": _sha(_resolve(inputs["g4_design"]["path"])),
        },
        "api_calls": 0,
        "labels_created": 0,
        "pm_fit": False,
        "packet_materialization_authorized_by_phase": True,
        "reviewer_execution_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = validate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    if report["failed_checks"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
