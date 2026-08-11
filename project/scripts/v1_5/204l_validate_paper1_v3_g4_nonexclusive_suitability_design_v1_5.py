from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DESIGN = ROOT / "data/pm_v1_5_contracts/paper1_v3_g4_nonexclusive_suitability_design_v1.json"
DEFAULT_OUTPUT = (
    ROOT
    / "outputs/pm_v1_5_paper1_v3_g4_nonexclusive_suitability_design_20260811/report.json"
)


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    path.relative_to(ROOT.resolve())
    return path


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def validate() -> dict[str, Any]:
    design = _read(DESIGN)
    upstream = design["upstream"]
    phase_path = _resolve(upstream["g3_phase"]["path"])
    report_path = _resolve(upstream["g3_report"]["path"])
    diagnostics_path = _resolve(upstream["g3_diagnostics"]["path"])
    report = _read(report_path)
    rows = _jsonl(diagnostics_path)
    present = [row for row in rows if row["candidate_present"]]

    by_component_group: dict[str, Counter[str]] = defaultdict(Counter)
    by_state: dict[str, set[str]] = defaultdict(set)
    me_candidate_ids: set[str] = set()
    for row in present:
        component = str(row["component"])
        by_component_group[component][str(row["split_group_key"])] += 1
        by_state[str(row["state_id"])].add(component)
        if component == "ME":
            me_candidate_ids.add(str(row["actual_rank1_id"]))
    all_three_groups = {
        next(
            str(row["split_group_key"])
            for row in present
            if row["state_id"] == state_id
        )
        for state_id, components in by_state.items()
        if components == {"MP", "MS", "ME"}
    }

    mp_flags = sum(
        bool(row.get("exact_profile_value_already_visible"))
        for row in present
        if row["component"] == "MP"
    )
    ms_low = sum(
        bool(row.get("low_information_rank1"))
        for row in present
        if row["component"] == "MS"
    )
    ms_echo = sum(
        bool(row.get("exact_or_containment_current_echo"))
        for row in present
        if row["component"] == "MS"
    )
    me_capped_capacity = sum(
        min(7, count) for count in by_component_group["ME"].values()
    )

    unit = design["scientific_unit"]
    instrument = design["review_instrument"]
    capacity = design["packet_capacity"]
    qualification = design["reviewer_qualification"]
    freeze = design["pre_adjudication_and_label_freeze"]
    authorization = design["authorization"]
    checks = {
        "protocol_and_design_only_status": design["protocol"]
        == "pm-v1.5-paper1-v3-g4-nonexclusive-suitability-design-v1"
        and design["status"]
        == "G4_ZERO_API_DESIGN_FROZEN_PACKET_MATERIALIZATION_NOT_AUTHORIZED",
        "upstream_hashes_and_status_match": _sha(phase_path)
        == upstream["g3_phase"]["sha256"]
        and _sha(report_path) == upstream["g3_report"]["sha256"]
        and report["status"] == upstream["g3_report"]["required_status"]
        and _sha(diagnostics_path) == upstream["g3_diagnostics"]["sha256"]
        and len(rows) == upstream["g3_diagnostics"]["rows"],
        "diagnostics_are_unlabeled": upstream["g3_diagnostics"]["labels_created"] == 0
        and all(row.get("suitability_label") is None for row in rows),
        "decision_grain_is_nonexclusive": unit["nonexclusive"] is True
        and unit["same_state_may_enter_multiple_component_packets"] is True
        and unit["same_state_may_receive_suitable_for_all_present_components"] is True
        and unit["one_of_k_softmax_winner_take_all_forbidden"] is True
        and unit["at_most_one_positive_memory_forbidden"] is True,
        "exact_three_class_decision": unit["primary_decision_values"]
        == ["SUITABLE", "NOT_SUITABLE", "SEMANTIC_ABSTAIN"],
        "checklist_does_not_recreate_four_labels": instrument[
            "one_primary_decision_only"
        ]
        is True
        and len(instrument["checklist_is_attestation_not_four_labels"]) == 4
        and instrument["per_axis_yes_no_unknown_outputs_forbidden"] is True
        and instrument["per_axis_accuracy_kappa_or_gate_forbidden"] is True,
        "mp_capacity_supported": capacity["MP"]["planned_cases"] == 204
        and capacity["MP"]["per_group_target"] == 12
        and len(by_component_group["MP"]) == 17
        and min(by_component_group["MP"].values()) >= 12
        and mp_flags == 12,
        "ms_capacity_supported": capacity["MS"]["planned_cases"] == 204
        and capacity["MS"]["per_group_target"] == 12
        and len(by_component_group["MS"]) == 17
        and min(by_component_group["MS"].values()) >= 12
        and ms_low == 21
        and ms_echo == 32,
        "me_capacity_is_sparse_but_supported": capacity["ME"]["planned_cases"] == 99
        and capacity["ME"]["per_group_cap"] == 7
        and len(by_component_group["ME"]) == 15
        and len(me_candidate_ids) == 23
        and me_capped_capacity == 99,
        "packet_denominator_exact": capacity["total_planned_cases"]
        == capacity["MP"]["planned_cases"]
        + capacity["MS"]["planned_cases"]
        + capacity["ME"]["planned_cases"]
        == 507,
        "all_three_co_presence_is_preserved": len(all_three_groups) == 14
        and "14 groups" in capacity["co_presence_requirement"]
        and "three separate review cases" in capacity["co_presence_requirement"],
        "component_specific_anchors_exist": set(design["component_anchors"])
        == {"MP", "MS", "ME"}
        and all(
            design["component_anchors"][component]["suitable_reason_codes"]
            and design["component_anchors"][component]["not_suitable_reason_codes"]
            for component in ("MP", "MS", "ME")
        ),
        "reviewer_qualification_is_component_specific": qualification[
            "reviewer_count"
        ]
        == 2
        and qualification["held_out_controls_per_component"] == 12
        and qualification["control_composition_per_component"]
        == {"SUITABLE": 5, "NOT_SUITABLE": 5, "SEMANTIC_ABSTAIN": 2}
        and qualification["component_specific_gate"][
            "exact_three_class_accuracy_min"
        ]
        >= 10 / 12
        and qualification["llm_reviewer_must_never_be_called_human"] is True,
        "agreement_precedes_adjudication": freeze[
            "agreement_is_computed_before_any_adjudication"
        ]
        is True
        and freeze["primary_training_label_rule"].startswith("Only exact")
        and "never rewrites pre-adjudication agreement" in freeze["adjudication"],
        "minimum_training_capacity_is_bidirectional": freeze[
            "minimum_resolved_training_capacity"
        ]["MP"]
        == {"total": 128, "each_class": 32, "groups_overall": 17, "groups_per_class": 8}
        and freeze["minimum_resolved_training_capacity"]["MS"]
        == {"total": 128, "each_class": 32, "groups_overall": 17, "groups_per_class": 8}
        and freeze["minimum_resolved_training_capacity"]["ME"]
        == {"total": 60, "each_class": 15, "groups_overall": 12, "groups_per_class": 6},
        "same_cases_cannot_be_repaired_after_results": freeze[
            "one_review_wave_only"
        ]
        is True
        and "no threshold, sample, reason-code or codebook edits"
        in freeze["head_failure_behavior"],
        "review_payload_forbids_future_and_outcomes": {
            "future supporter reply",
            "summary",
            "observation",
            "event outcome or future event",
            "QA answer or evidence",
            "generator response or outcome",
            "quality, risk, function or cost outcome",
            "PM prediction",
            "fold or dataset split",
        }.issubset(set(design["blinding_and_leakage"]["forbidden_everywhere_in_review_payload"])),
        "all_execution_authorities_false": all(value is False for value in authorization.values()),
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "protocol": "pm-v1.5-paper1-v3-g4-nonexclusive-suitability-design-validation-v1",
        "status": (
            "G4_NONEXCLUSIVE_SUITABILITY_DESIGN_PASS_G4A_PACKET_PHASE_MAY_BE_DESIGNED"
            if not failed
            else "G4_NONEXCLUSIVE_SUITABILITY_DESIGN_FAIL_CLOSED"
        ),
        "checks": checks,
        "failed_checks": failed,
        "observed_capacity": {
            "MP_groups": len(by_component_group["MP"]),
            "MP_min_rows_per_group": min(by_component_group["MP"].values()),
            "MP_current_redundancy_flags": mp_flags,
            "MS_groups": len(by_component_group["MS"]),
            "MS_min_rows_per_group": min(by_component_group["MS"].values()),
            "MS_low_information": ms_low,
            "MS_current_echo": ms_echo,
            "ME_groups": len(by_component_group["ME"]),
            "ME_unique_candidates": len(me_candidate_ids),
            "ME_cap7_capacity": me_capped_capacity,
            "all_three_co_present_groups": len(all_three_groups),
        },
        "hashes": {
            "design_sha256": _sha(DESIGN),
            "promoted_from_authority_sha256": design[
                "promoted_from_authority_sha256"
            ],
            "g3_report_sha256": _sha(report_path),
            "g3_diagnostics_sha256": _sha(diagnostics_path),
        },
        "api_calls": 0,
        "reviewer_calls": 0,
        "labels_created": 0,
        "pm_fit": False,
        "packet_materialization_authorized": False,
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
