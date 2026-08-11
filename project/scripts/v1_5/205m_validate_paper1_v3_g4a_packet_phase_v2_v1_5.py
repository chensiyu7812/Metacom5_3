from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_v3_g4a_packet_materialization_phase_v2.json"
DEFAULT_OUTPUT = ROOT / "outputs/pm_v1_5_paper1_v3_g4a_packet_phase_v2_validation_20260811/report.json"


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
    supersedes = phase["supersedes"]
    carry = phase["carry_invariants"]
    delta = phase["control_delta"]
    authorization = phase["authorization"]
    checks = {
        "protocol_status_parent": phase["protocol"]
        == "pm-v1.5-paper1-v3-g4a-packet-materialization-phase-v2"
        and phase["status"]
        == "G4A_V2_ZERO_API_CONTROL_REPAIR_AND_PACKET_REMATERIALIZATION_AUTHORIZED_ONCE"
        and phase["promoted_from_authority_sha256"]
        == "89afda8fc0e6dad0cbae0cf9878d4a66d572cb61185ab914418297c25fe633a7",
        "superseded_v1_evidence_hashes_match": _sha(_resolve(supersedes["phase_path"]))
        == supersedes["phase_sha256"]
        and _sha(_resolve(supersedes["v1_report_path"]))
        == supersedes["v1_report_sha256"]
        and _sha(_resolve(supersedes["semantic_audit_path"]))
        == supersedes["semantic_audit_sha256"]
        and supersedes["v1_reviewer_execution"] == 0
        and supersedes["v1_labels_created"] == 0
        and supersedes["v1_outputs_immutable"] is True,
        "all_input_and_implementation_hashes_match": all(
            _sha(_resolve(row["path"])) == row["sha256"]
            for row in phase["input_bindings"]
        )
        and _sha(_resolve(phase["implementation_binding"]["path"]))
        == phase["implementation_binding"]["sha256"],
        "public_case_carry_exact": carry
        == {
            "reviewer_a_packet_sha256": "be66ff89ad3c3a1857ebc4d87bb1cb20113214021b6d4aac335ff5699974b9e8",
            "reviewer_b_packet_sha256": "68ca51000c7bdfc5b0463436c1be9b492eaa5257501d5f2f7374f4123a7c77c2",
            "private_case_key_sha256": "e34556683a85925eecbf58de9ebff2b4e74a7ebc986d3f7d53acf3a77041348c",
            "public_cases": 507,
            "MP": 204,
            "MS": 204,
            "ME": 99,
            "all_three_shared_groups": 14,
        },
        "exact_six_control_delta": delta["total_controls"] == 36
        and delta["unchanged_surfaces"] == 30
        and delta["changed_surfaces"] == 6
        and delta["changed_MP_positive"] == 5
        and delta["changed_ME_negative"] == 1
        and delta["four_axis_fields_forbidden"] is True,
        "new_output_paths_do_not_overwrite_v1": phase["outputs"]["public_dir"]
        != "outputs/pm_v1_5_paper1_v3_g4a_packet_20260811"
        and phase["outputs"]["private_dir"]
        != "outputs/pm_v1_5_paper1_v3_g4a_packet_private_20260811",
        "only_zero_api_repair_authorized": all(
            authorization[key] is True
            for key in (
                "packet_rematerialization_in_new_paths",
                "fresh_control_repair",
                "private_key_rematerialization",
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
                "overwrite_v1_or_v2_output",
            )
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "protocol": "pm-v1.5-paper1-v3-g4a-packet-phase-v2-validation-v1",
        "status": (
            "G4A_V2_PACKET_PHASE_PASS_ZERO_API_REMATERIALIZATION_MAY_BE_AUTHORIZED"
            if not failed
            else "G4A_V2_PACKET_PHASE_FAIL_CLOSED"
        ),
        "checks": checks,
        "failed_checks": failed,
        "hashes": {
            "phase_sha256": _sha(PHASE),
            "parent_authority_sha256": phase["promoted_from_authority_sha256"],
            "semantic_audit_sha256": _sha(_resolve(supersedes["semantic_audit_path"])),
        },
        "api_calls": 0,
        "reviewer_calls": 0,
        "labels_created": 0,
        "pm_fit": False,
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
