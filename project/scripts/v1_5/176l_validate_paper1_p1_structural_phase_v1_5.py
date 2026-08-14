from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = ROOT / "data" / "pm_v1_5_contracts" / "active_method_authority_v1.json"
PHASE = (
    ROOT
    / "data"
    / "pm_v1_5_contracts"
    / "paper1_p1_structural_materialization_phase_v1.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "outputs"
    / "pm_v1_5_paper1_p1_structural_phase_preflight_20260810"
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
    active = authority["active_method"]
    paid = _read(_resolve(authority["paid_execution_guard"]["central_release_path"]))
    current = authority["current_phase"]
    phase_hash = _sha(PHASE)
    prepromotion = (
        current["id"] == "P0_ZERO_API_CLAIM_LABEL_VERSION_FREEZE"
        and _sha(AUTHORITY) == phase["parent_authority_sha256"]
    )
    promoted = (
        current["id"] == "P1_PUBLIC_SOURCE_AND_CANONICAL_GROUP_MATERIALIZATION"
        and current.get("promoted_from_authority_sha256")
        == phase["parent_authority_sha256"]
        and current.get("active_phase_manifest", {}).get("sha256") == phase_hash
    )
    expected_authorization = {
        "structural_surface_materialization": True,
        "actual_rank1_materialization": False,
        "api_calls": False,
        "response_generation": False,
        "label_creation": False,
        "pm_training": False,
        "baseline_execution": False,
        "external_outcome_scoring": False,
        "paid_execution": False,
    }
    evidence_valid = True
    evidence_statuses: dict[str, str] = {}
    for binding in phase["preflight_evidence"]:
        path = _resolve(binding["path"])
        report = _read(path)
        evidence_statuses[binding["path"]] = str(report.get("status"))
        evidence_valid = evidence_valid and _sha(path) == binding["sha256"]
        evidence_valid = evidence_valid and report.get("status") == binding[
            "required_status"
        ]
    implementations_valid = all(
        _sha(_resolve(binding["path"])) == binding["sha256"]
        for binding in phase["implementation_bindings"]
    )
    candidate = phase["p1_candidate_manifest"]
    checks = {
        "phase_protocol_and_status": phase["protocol"]
        == "pm-v1.5-paper1-p1-structural-materialization-phase-v1"
        and phase["status"] == "P1_ACTIVE_ZERO_API_STRUCTURAL_MATERIALIZATION",
        "authority_transition_is_valid": prepromotion or promoted,
        "method_and_contract_match": phase["method_id"] == active["method_id"]
        and phase["active_contract_sha256"] == active["contract_sha256"]
        and phase["active_method_amendment_sha256"]
        == active["method_amendment_sha256"],
        "candidate_manifest_hash_matches": _sha(_resolve(candidate["path"]))
        == candidate["sha256"],
        "implementation_hashes_match": implementations_valid,
        "preflight_evidence_matches": evidence_valid,
        "authorization_is_structural_only": phase["authorization"]
        == expected_authorization,
        "paid_release_is_false": paid.get("paid_execution_authorized") is False,
        "outputs_are_separate": phase["outputs"]["public_dir"]
        != phase["outputs"]["private_dir"],
        "phase_has_zero_calls": phase["api_calls_for_phase_manifest"] == 0,
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "protocol": "pm-v1.5-paper1-p1-structural-phase-validation-v1",
        "status": (
            "P1_STRUCTURAL_PHASE_PREFLIGHT_PASS"
            if not failed and prepromotion
            else "P1_STRUCTURAL_PHASE_ACTIVE_PASS"
            if not failed and promoted
            else "P1_STRUCTURAL_PHASE_FAIL_CLOSED"
        ),
        "checks": checks,
        "failed_checks": failed,
        "transition_state": "PREPROMOTION" if prepromotion else "PROMOTED" if promoted else "INVALID",
        "phase_manifest_sha256": phase_hash,
        "authority_sha256": _sha(AUTHORITY),
        "evidence_statuses": evidence_statuses,
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
