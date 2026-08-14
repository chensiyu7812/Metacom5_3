from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
PHASE = (
    ROOT
    / "data/pm_v1_5_contracts"
    / "paper1_p1b_actual_rank1_materialization_phase_v1.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "outputs/pm_v1_5_paper1_p1b_actual_rank1_phase_preflight_20260810"
    / "report.json"
)


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    path.relative_to(ROOT.resolve())
    return path


def validate() -> dict[str, Any]:
    authority = _read(AUTHORITY)
    phase = _read(PHASE)
    current = authority["current_phase"]
    active = authority["active_method"]
    phase_hash = _sha(PHASE)
    prepromotion = (
        current["id"] == "P1_STRUCTURAL_SURFACE_COMPLETE_P1B_PENDING"
        and _sha(AUTHORITY) == phase["parent_authority_sha256"]
    )
    promoted = (
        current["id"] == "P1B_ACTUAL_RANK1_MATERIALIZATION"
        and current.get("promoted_from_authority_sha256")
        == phase["parent_authority_sha256"]
        and current.get("active_phase_manifest", {}).get("sha256") == phase_hash
    )
    expected_authorization = {
        "structural_surface_materialization": False,
        "actual_rank1_materialization": True,
        "api_calls": False,
        "response_generation": False,
        "label_creation": False,
        "pm_training": False,
        "baseline_execution": False,
        "external_outcome_scoring": False,
        "paid_execution": False,
    }
    input_hashes_match = all(
        _sha(_resolve(binding["path"])) == binding["sha256"]
        for binding in phase["input_bindings"]
    )
    implementation_hashes_match = all(
        _sha(_resolve(binding["path"])) == binding["sha256"]
        for binding in phase["implementation_bindings"]
    )
    evidence_match = all(
        _sha(_resolve(binding["path"])) == binding["sha256"]
        and _read(_resolve(binding["path"])).get("status")
        == binding["required_status"]
        for binding in phase["preflight_evidence"]
    )
    paid = _read(_resolve(authority["paid_execution_guard"]["central_release_path"]))
    snapshot = Path(phase["local_semantic_encoder"]["snapshot_path"])
    checks = {
        "phase_protocol_and_status": phase["protocol"]
        == "pm-v1.5-paper1-p1b-actual-rank1-materialization-phase-v1"
        and phase["status"] == "P1B_ACTIVE_ZERO_API_ACTUAL_RANK1",
        "authority_transition_is_valid": prepromotion or promoted,
        "method_and_contract_match": phase["method_id"] == active["method_id"]
        and phase["active_contract_sha256"] == active["contract_sha256"]
        and phase["active_method_amendment_sha256"]
        == active["method_amendment_sha256"],
        "input_hashes_match": input_hashes_match,
        "implementation_hashes_match": implementation_hashes_match,
        "preflight_evidence_matches": evidence_match,
        "authorization_is_rank1_only": phase["authorization"]
        == expected_authorization,
        "semantic_snapshot_is_local_directory": snapshot.is_dir(),
        "semantic_snapshot_hash_is_frozen": phase["local_semantic_encoder"][
            "snapshot_tree_sha256"
        ]
        == "f0384ec76e05ff5439dd455f7d65ea523bd90c6273c106cfe9c3629a867b80ba",
        "paid_release_is_false": paid.get("paid_execution_authorized") is False,
        "phase_has_zero_calls": phase["api_calls_for_phase_manifest"] == 0,
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "protocol": "pm-v1.5-paper1-p1b-actual-rank1-phase-validation-v1",
        "status": (
            "P1B_ACTUAL_RANK1_PHASE_PREFLIGHT_PASS"
            if not failed and prepromotion
            else "P1B_ACTUAL_RANK1_PHASE_ACTIVE_PASS"
            if not failed and promoted
            else "P1B_ACTUAL_RANK1_PHASE_FAIL_CLOSED"
        ),
        "checks": checks,
        "failed_checks": failed,
        "transition_state": (
            "PREPROMOTION" if prepromotion else "PROMOTED" if promoted else "INVALID"
        ),
        "phase_manifest_sha256": phase_hash,
        "authority_sha256": _sha(AUTHORITY),
        "authorization": phase["authorization"],
        "api_calls": 0,
        "responses_generated": 0,
        "labels_created": 0,
        "pm_trained": False,
        "external_outcomes_read": False,
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
