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
    / "paper1_p2a_suitability_packet_materialization_phase_v1.json"
)
OUT = (
    ROOT
    / "outputs/pm_v1_5_paper1_p2a_suitability_packet_phase_preflight_20260810"
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
    prepromotion = (
        current["id"] == "P1B_ACTUAL_RANK1_COMPLETE_P2_LABEL_DESIGN_PENDING"
        and _sha(AUTHORITY) == phase["parent_authority_sha256"]
    )
    promoted = (
        current["id"] == "P2A_SUITABILITY_QUALIFICATION_PACKET_MATERIALIZATION"
        and current.get("promoted_from_authority_sha256")
        == phase["parent_authority_sha256"]
        and current.get("active_phase_manifest", {}).get("sha256") == _sha(PHASE)
    )
    expected_auth = {
        "qualification_packet_materialization": True,
        "reviewer_calls": False,
        "label_creation": False,
        "response_generation": False,
        "pm_training": False,
        "baseline_execution": False,
        "external_outcome_scoring": False,
        "paid_execution": False,
    }
    checks = {
        "phase_protocol_and_status": phase["protocol"]
        == "pm-v1.5-paper1-p2a-suitability-packet-materialization-phase-v1"
        and phase["status"] == "P2A_ACTIVE_ZERO_API_PACKET_ONLY",
        "authority_transition_is_valid": prepromotion or promoted,
        "method_hashes_match": phase["method_id"]
        == authority["active_method"]["method_id"]
        and phase["active_contract_sha256"]
        == authority["active_method"]["contract_sha256"]
        and phase["active_method_amendment_sha256"]
        == authority["active_method"]["method_amendment_sha256"],
        "all_inputs_match": all(
            _sha(_resolve(row["path"])) == row["sha256"]
            for row in phase["input_bindings"]
        ),
        "all_implementations_match": all(
            _sha(_resolve(row["path"])) == row["sha256"]
            for row in phase["implementation_bindings"]
        ),
        "authorization_is_packet_only": phase["authorization"] == expected_auth,
        "outputs_physically_separate": phase["outputs"]["public_dir"]
        != phase["outputs"]["private_dir"],
        "paid_release_false": _read(
            _resolve(authority["paid_execution_guard"]["central_release_path"])
        ).get("paid_execution_authorized")
        is False,
        "zero_calls": phase["api_calls_for_phase_manifest"] == 0,
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "protocol": "pm-v1.5-paper1-p2a-suitability-packet-phase-validation-v1",
        "status": (
            "P2A_PACKET_PHASE_PREFLIGHT_PASS"
            if not failed and prepromotion
            else "P2A_PACKET_PHASE_ACTIVE_PASS"
            if not failed and promoted
            else "P2A_PACKET_PHASE_FAIL_CLOSED"
        ),
        "checks": checks,
        "failed_checks": failed,
        "transition_state": "PREPROMOTION" if prepromotion else "PROMOTED" if promoted else "INVALID",
        "phase_manifest_sha256": _sha(PHASE),
        "authority_sha256": _sha(AUTHORITY),
        "api_calls": 0,
        "labels_created": 0,
        "responses_generated": 0,
        "pm_trained": False,
        "external_outcomes_read": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUT)
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
