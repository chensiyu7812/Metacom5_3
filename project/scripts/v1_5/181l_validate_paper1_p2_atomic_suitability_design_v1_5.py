from __future__ import annotations

from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
DESIGN = (
    ROOT
    / "data/pm_v1_5_contracts"
    / "paper1_p2_atomic_suitability_design_candidate_v1.json"
)
OUT = (
    ROOT
    / "outputs/pm_v1_5_paper1_p2_atomic_suitability_design_20260810"
    / "report.json"
)


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    path.relative_to(ROOT.resolve())
    return path


def validate() -> dict[str, Any]:
    authority = _read(AUTHORITY)
    design = _read(DESIGN)
    contract = _read(_resolve(authority["active_method"]["contract_path"]))
    rank1 = _jsonl(_resolve(design["rank1_input"]["path"]))
    audit = _read(_resolve(design["rank1_input"]["required_final_audit"]["path"]))
    present_groups: dict[str, set[str]] = {
        component: {
            str(row["split_group_key"])
            for row in rank1
            if row["component"] == component and row["candidate_present"]
        }
        for component in ("MP", "MS", "ME", "RS")
    }
    component_present = Counter(
        str(row["component"]) for row in rank1 if row["candidate_present"]
    )
    expected_auth = {
        "real_packet_materialization": False,
        "reviewer_calls": False,
        "label_creation": False,
        "response_generation": False,
        "pm_training": False,
        "baseline_execution": False,
        "external_outcome_scoring": False,
        "paid_execution": False,
    }
    contract_suitability = contract["measurement_qualification"]["suitability"]
    gates = design["qualification_gates_per_component"]
    checks = {
        "design_protocol_and_zero_api_status": design["protocol"]
        == "pm-v1.5-paper1-p2-atomic-bounded-suitability-design-candidate-v1"
        and design["status"] == "ZERO_API_DESIGN_CANDIDATE_NO_REAL_LABELS_AUTHORIZED",
        "designed_under_current_completed_p1b_authority": design[
            "parent_authority_sha256"
        ]
        == _sha(AUTHORITY)
        and authority["current_phase"]["id"]
        == "P1B_ACTUAL_RANK1_COMPLETE_P2_LABEL_DESIGN_PENDING",
        "active_method_hashes_match": design["method_id"]
        == authority["active_method"]["method_id"]
        and design["active_contract_sha256"]
        == authority["active_method"]["contract_sha256"]
        and design["active_method_amendment_sha256"]
        == authority["active_method"]["method_amendment_sha256"],
        "rank1_and_audit_hashes_match": _sha(
            _resolve(design["rank1_input"]["path"])
        )
        == design["rank1_input"]["sha256"]
        and _sha(_resolve(design["rank1_input"]["required_final_audit"]["path"]))
        == design["rank1_input"]["required_final_audit"]["sha256"]
        and audit["status"]
        == design["rank1_input"]["required_final_audit"]["status"],
        "measurement_implementation_hash_matches": _sha(
            _resolve(design["measurement_implementation"]["path"])
        )
        == design["measurement_implementation"]["sha256"],
        "exact_four_axes_are_frozen": list(design["axes"])
        == [
            "current_target_fit",
            "specific_increment_available",
            "component_minimum_possible_now",
            "current_boundary_permits",
        ],
        "all_four_component_minima_are_explicit": set(design["component_minima"])
        == {"MP", "MS", "ME", "RS"},
        "packet_denominator_is_consistent": sum(
            int(row["items"])
            for row in design["qualification_packet_design"].values()
            if isinstance(row, dict) and "items" in row
        )
        == design["qualification_packet_design"]["total_items"]
        == 132,
        "source_group_support_matches_design": len(present_groups["MP"]) == 17
        and len(present_groups["MS"]) == 17
        and len(present_groups["ME"]) == 15
        and len(present_groups["RS"]) >= 36,
        "rank1_present_counts_match_completed_audit": component_present
        == Counter({"RS": 22913, "MS": 4442, "MP": 846, "ME": 417}),
        "qualification_gates_match_active_contract": gates[
            "per_axis_raw_agreement_min"
        ]
        == contract_suitability["per_axis_raw_agreement_min"]
        and gates["per_axis_gwet_ac1_min"]
        == contract_suitability["per_axis_chance_adjusted_agreement_min"]
        and gates["derived_raw_agreement_min"]
        == contract_suitability["derived_decision_raw_agreement_min"]
        and gates["resolved_coverage_min"]
        == contract_suitability["resolved_coverage_min"]
        and gates["consensus_suitable_independent_groups_min"]
        == contract_suitability["per_component_min_suitable_independent_groups"]
        and gates["consensus_not_suitable_independent_groups_min"]
        == contract_suitability[
            "per_component_min_not_suitable_independent_groups"
        ],
        "suitability_is_not_quality_or_safe_yield": design[
            "safe_functional_yield_separation"
        ]["not_present_in_this_packet"]
        is True
        and "overall response quality"
        in design["review_surface"]["forbidden_scales"],
        "no_real_execution_authorized": design["authorization"] == expected_auth,
        "no_labels_responses_training_or_outcomes": design["api_calls_for_design"]
        == 0
        and design["labels_created"] == 0
        and design["responses_generated"] == 0
        and design["pm_trained"] is False
        and design["external_outcomes_read"] is False
        and all(row["suitability_label"] is None for row in rank1),
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "protocol": "pm-v1.5-paper1-p2-atomic-suitability-design-validation-v1",
        "status": (
            "P2_ATOMIC_SUITABILITY_DESIGN_PASS_PACKET_PHASE_MAY_BE_DESIGNED"
            if not failed
            else "P2_ATOMIC_SUITABILITY_DESIGN_FAIL_CLOSED"
        ),
        "checks": checks,
        "failed_checks": failed,
        "design_sha256": _sha(DESIGN),
        "authority_sha256": _sha(AUTHORITY),
        "source_support": {
            component: {
                "candidate_present_rows": component_present[component],
                "canonical_groups": len(present_groups[component]),
            }
            for component in ("MP", "MS", "ME", "RS")
        },
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
