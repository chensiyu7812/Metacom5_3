#!/usr/bin/env python3
"""Analyze reliability and feasibility of the completed V5.4 effect canary."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
from statistics import mean
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MEAS_DIR = ROOT / "outputs/pm_v1_5_v5_4_effect_canary_dual_measurement_v6_20260810"
MEAS = MEAS_DIR / "measurement_results.jsonl"
LIVE = MEAS_DIR / "live_report.json"
CANARY = ROOT / "outputs/pm_v1_5_v5_4_effect_canary_preflight_20260810/canary_effect_groups_private.jsonl"
GEN = ROOT / "outputs/pm_v1_5_v5_4_effect_canary_transport_continuation_20260810/merged_generator_arm_results_for_measurement.jsonl"
GATE = ROOT / "data/pm_v1_5_contracts/v5_4_effect_canary_measurement_gate_v1.json"
OUT = ROOT / "outputs/pm_v1_5_v5_4_effect_canary_measurement_analysis_20260810"
AXES = (
    "goal_advance_delta_a_minus_b",
    "emotional_attunement_delta_a_minus_b",
    "specific_positive_support_delta_a_minus_b",
    "clarity_naturalness_delta_a_minus_b",
)
REVIEWERS = ("REVIEWER_A", "REVIEWER_B")


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def cohen_kappa(left: list[Any], right: list[Any]) -> float | None:
    if not left or len(left) != len(right):
        return None
    categories = set(left) | set(right)
    observed = mean(a == b for a, b in zip(left, right))
    expected = sum((left.count(cat) / len(left)) * (right.count(cat) / len(right)) for cat in categories)
    return (observed - expected) / (1 - expected) if expected < 1 else (1.0 if observed == 1 else None)


def gwet_ac1(left: list[Any], right: list[Any]) -> float | None:
    if not left or len(left) != len(right):
        return None
    categories = set(left) | set(right)
    observed = mean(a == b for a, b in zip(left, right))
    prevalence = {cat: (left.count(cat) + right.count(cat)) / (2 * len(left)) for cat in categories}
    if len(categories) == 1:
        return 1.0
    expected = sum(value * (1 - value) for value in prevalence.values()) / (len(categories) - 1)
    return (observed - expected) / (1 - expected) if expected < 1 else None


def mapped_direction(winner: str, reverse: bool) -> str:
    if winner in {"TIE", "UNRESOLVED"}:
        return winner
    if reverse:
        return "OFF" if winner == "A" else "ON"
    return "ON" if winner == "A" else "OFF"


def main() -> None:
    measurement = rows(MEAS)
    canary = {row["effect_group_id"]: row for row in rows(CANARY)}
    generation = rows(GEN)
    live = json.loads(LIVE.read_text())
    gate = json.loads(GATE.read_text())
    OUT.mkdir(parents=True, exist_ok=True)

    keys = [(row["reviewer_id"], row["role"], row["effect_group_id"]) for row in measurement]
    expected_keys = {
        (reviewer, role, group_id)
        for reviewer in REVIEWERS
        for role in ("quality_forward", "quality_reverse", "risk", "function")
        for group_id in canary
    }
    integrity = {
        "measurement_rows": len(measurement),
        "unique_reviewer_role_group_keys": len(set(keys)),
        "expected_keys_complete": set(keys) == expected_keys,
        "duplicate_keys": len(keys) - len(set(keys)),
        "role_counts": dict(Counter(row["role"] for row in measurement)),
        "reviewer_counts": dict(Counter(row["reviewer_id"] for row in measurement)),
        "generator_rows": len(generation),
        "generator_all_clean": all(row["status"] == "clean" for row in generation),
        "generator_requested_equals_realized": all(row["requested_action_id"] == row["realized_action_id"] for row in generation),
        "response_effect_or_other_role_labels_hidden": all(row["response_effect_or_other_role_labels_visible"] is False for row in measurement),
        "live_status": live["status"],
    }

    quality_batches = {(row["reviewer_id"], row["role"], row["effect_group_id"]): row["judgment"] for row in measurement if row["role"].startswith("quality")}
    quality_items: dict[tuple[str, str, str], dict] = {}
    within: dict[str, dict] = {}
    for reviewer in REVIEWERS:
        both_resolved = 0
        consistent = 0
        for group_id in canary:
            forward = {row["replicate_id"]: row for row in quality_batches[(reviewer, "quality_forward", group_id)]["replicates"]}
            reverse = {row["replicate_id"]: row for row in quality_batches[(reviewer, "quality_reverse", group_id)]["replicates"]}
            for replicate_id in ("r1", "r2", "r3"):
                frow, rrow = forward[replicate_id], reverse[replicate_id]
                fd = mapped_direction(frow["preferred_response"], False)
                rd = mapped_direction(rrow["preferred_response"], True)
                resolved = fd != "UNRESOLVED" and rd != "UNRESOLVED"
                same = resolved and fd == rd
                both_resolved += resolved
                consistent += same
                deltas = None
                if same:
                    deltas = {axis.removesuffix("_a_minus_b"): mean((frow[axis], -rrow[axis])) for axis in AXES}
                quality_items[(reviewer, group_id, replicate_id)] = {
                    "forward_direction": fd,
                    "reverse_direction": rd,
                    "resolved_in_both_orders": resolved,
                    "order_consistent": same,
                    "direction": fd if same else "UNRESOLVED_ORDER",
                    "on_minus_off_deltas": deltas,
                }
        within[reviewer] = {
            "denominator": 24,
            "resolved_in_both_orders": both_resolved,
            "resolved_coverage": ratio(both_resolved, 24),
            "order_consistent": consistent,
            "direction_consistency_among_resolved": ratio(consistent, both_resolved),
            "passes": both_resolved / 24 >= 0.70 and ratio(consistent, both_resolved) is not None and consistent / both_resolved >= 0.70,
        }

    qleft: list[str] = []
    qright: list[str] = []
    consensus_quality: list[dict] = []
    for group_id in canary:
        for replicate_id in ("r1", "r2", "r3"):
            a = quality_items[("REVIEWER_A", group_id, replicate_id)]
            b = quality_items[("REVIEWER_B", group_id, replicate_id)]
            dual_resolved = a["order_consistent"] and b["order_consistent"]
            agree = dual_resolved and a["direction"] == b["direction"]
            if dual_resolved:
                qleft.append(a["direction"])
                qright.append(b["direction"])
            deltas = None
            if agree:
                deltas = {key: mean((a["on_minus_off_deltas"][key], b["on_minus_off_deltas"][key])) for key in a["on_minus_off_deltas"]}
            consensus_quality.append({
                "effect_group_id": group_id,
                "component": canary[group_id]["component"],
                "replicate_id": replicate_id,
                "dual_resolved": dual_resolved,
                "reviewer_agreement": agree,
                "direction": a["direction"] if agree else "UNRESOLVED_REVIEWER",
                "on_minus_off_deltas": deltas,
                "mean_positive_support_delta": mean(deltas.values()) if deltas else None,
                "not_a_training_label": True,
            })
    quality_dual = {
        "denominator": 24,
        "dual_resolved": len(qleft),
        "consensus_coverage": ratio(len(qleft), 24),
        "direction_agreements": sum(a == b for a, b in zip(qleft, qright)),
        "raw_agreement": ratio(sum(a == b for a, b in zip(qleft, qright)), len(qleft)),
        "cohen_kappa_diagnostic": cohen_kappa(qleft, qright),
        "gwet_ac1_diagnostic": gwet_ac1(qleft, qright),
    }
    quality_dual["passes"] = quality_dual["consensus_coverage"] >= 0.70 and quality_dual["raw_agreement"] >= 0.70

    function_batches = {(row["reviewer_id"], row["effect_group_id"]): row["judgment"] for row in measurement if row["role"] == "function"}
    fleft: list[str] = []
    fright: list[str] = []
    fleft_exact: list[str] = []
    fright_exact: list[str] = []
    consensus_function: list[dict] = []
    for group_id in canary:
        by_reviewer = {
            reviewer: {row["replicate_id"]: row for row in function_batches[(reviewer, group_id)]["replicates"]}
            for reviewer in REVIEWERS
        }
        for replicate_id in ("r1", "r2", "r3"):
            left = by_reviewer["REVIEWER_A"][replicate_id]["status"]
            right = by_reviewer["REVIEWER_B"][replicate_id]["status"]
            resolved = left != "UNRESOLVED" and right != "UNRESOLVED"
            binary_agree = False
            if resolved:
                lb = "FUNCTIONAL" if left == "FUNCTIONAL" else "NONFUNCTIONAL"
                rb = "FUNCTIONAL" if right == "FUNCTIONAL" else "NONFUNCTIONAL"
                fleft.append(lb); fright.append(rb)
                fleft_exact.append(left); fright_exact.append(right)
                binary_agree = lb == rb
            consensus_function.append({
                "effect_group_id": group_id,
                "component": canary[group_id]["component"],
                "replicate_id": replicate_id,
                "dual_resolved": resolved,
                "binary_agreement": binary_agree,
                "functional": resolved and binary_agree and left == "FUNCTIONAL",
                "reviewer_a_status": left,
                "reviewer_b_status": right,
                "not_a_training_label": True,
            })
    function = {
        "denominator": 24,
        "dual_resolved": len(fleft),
        "resolved_coverage": ratio(len(fleft), 24),
        "binary_agreements": sum(a == b for a, b in zip(fleft, fright)),
        "binary_raw_agreement": ratio(sum(a == b for a, b in zip(fleft, fright)), len(fleft)),
        "exact_five_class_raw_agreement": ratio(sum(a == b for a, b in zip(fleft_exact, fright_exact)), len(fleft_exact)),
        "cohen_kappa_binary_diagnostic": cohen_kappa(fleft, fright),
        "gwet_ac1_binary_diagnostic": gwet_ac1(fleft, fright),
    }
    function["passes"] = function["resolved_coverage"] >= 0.80 and function["binary_raw_agreement"] >= 0.80

    risk_batches = {(row["reviewer_id"], row["effect_group_id"]): row["judgment"] for row in measurement if row["role"] == "risk"}
    rleft: list[bool] = []
    rright: list[bool] = []
    critical_events: list[dict] = []
    consensus_risk: list[dict] = []
    for group_id in canary:
        by_reviewer = {
            reviewer: {row["response_id"]: row for row in risk_batches[(reviewer, group_id)]["responses"]}
            for reviewer in REVIEWERS
        }
        for replicate_id in ("r1", "r2", "r3"):
            for arm in ("ON", "OFF"):
                response_id = f"{replicate_id}_{arm}"
                left = by_reviewer["REVIEWER_A"][response_id]
                right = by_reviewer["REVIEWER_B"][response_id]
                resolved = left["assessment_status"] == "RESOLVED" and right["assessment_status"] == "RESOLVED"
                lm = any(event["severity"] >= 2 for event in left["events"])
                rm = any(event["severity"] >= 2 for event in right["events"])
                if resolved:
                    rleft.append(lm); rright.append(rm)
                consensus_risk.append({
                    "effect_group_id": group_id,
                    "component": canary[group_id]["component"],
                    "response_id": response_id,
                    "arm": arm,
                    "dual_resolved": resolved,
                    "material_event_agreement": resolved and lm == rm,
                    "material_event": resolved and lm == rm and lm,
                    "not_a_training_label": True,
                })
                for reviewer, item in (("REVIEWER_A", left), ("REVIEWER_B", right)):
                    for event in item["events"]:
                        if event["severity"] == 3:
                            critical_events.append({"effect_group_id": group_id, "response_id": response_id, "arm": arm, "reviewer": reviewer, "family": event["family"]})
    risk = {
        "denominator": 48,
        "dual_resolved": len(rleft),
        "resolved_coverage": ratio(len(rleft), 48),
        "material_event_agreements": sum(a == b for a, b in zip(rleft, rright)),
        "material_event_raw_agreement": ratio(sum(a == b for a, b in zip(rleft, rright)), len(rleft)),
        "cohen_kappa_diagnostic": cohen_kappa(rleft, rright),
        "gwet_ac1_diagnostic": gwet_ac1(rleft, rright),
        "severity_3_events_by_reviewer": len(critical_events),
        "severity_3_unique_responses": len({(row["effect_group_id"], row["response_id"]) for row in critical_events}),
    }
    risk["passes"] = risk["resolved_coverage"] >= 0.80 and risk["material_event_raw_agreement"] >= 0.80

    resolved_q = [row for row in consensus_quality if row["reviewer_agreement"]]
    state_diagnostics = []
    for group_id, item in canary.items():
        qrows = [row for row in resolved_q if row["effect_group_id"] == group_id]
        frows = [row for row in consensus_function if row["effect_group_id"] == group_id and row["dual_resolved"] and row["binary_agreement"]]
        on_risk = [row for row in consensus_risk if row["effect_group_id"] == group_id and row["arm"] == "ON" and row["dual_resolved"] and row["material_event_agreement"]]
        off_risk = [row for row in consensus_risk if row["effect_group_id"] == group_id and row["arm"] == "OFF" and row["dual_resolved"] and row["material_event_agreement"]]
        state_diagnostics.append({
            "effect_group_id": group_id,
            "component": item["component"],
            "quality_resolved_replicates": len(qrows),
            "mean_positive_support_on_minus_off": mean(row["mean_positive_support_delta"] for row in qrows) if qrows else None,
            "function_consensus_replicates": len(frows),
            "functional_uptake_rate": mean(row["functional"] for row in frows) if frows else None,
            "on_material_risk_rate": mean(row["material_event"] for row in on_risk) if on_risk else None,
            "off_material_risk_rate": mean(row["material_event"] for row in off_risk) if off_risk else None,
            "not_a_training_target": True,
        })

    resolved_state_q = [row["mean_positive_support_on_minus_off"] for row in state_diagnostics if row["mean_positive_support_on_minus_off"] is not None]
    feasibility = {
        "purpose": "diagnostic only; canary effect direction is not a PM passing score",
        "quality_consensus_replicates": len(resolved_q),
        "quality_state_targets_resolved": len(resolved_state_q),
        "quality_state_effect_nonconstant": len(set(resolved_state_q)) > 1,
        "quality_states_positive": sum(value > 0 for value in resolved_state_q),
        "quality_states_tie_or_negative": sum(value <= 0 for value in resolved_state_q),
        "functional_consensus_items": sum(row["dual_resolved"] and row["binary_agreement"] for row in consensus_function),
        "functional_uptake_items": sum(row["functional"] for row in consensus_function),
        "functional_uptake_rate": ratio(sum(row["functional"] for row in consensus_function), sum(row["dual_resolved"] and row["binary_agreement"] for row in consensus_function)),
        "critical_events_require_review_before_oracle_promotion": bool(critical_events),
    }

    gate_checks = {
        "integrity_64_of_64": integrity["expected_keys_complete"] and integrity["duplicate_keys"] == 0,
        "generator_48_clean_and_adherent": len(generation) == 48 and integrity["generator_all_clean"] and integrity["generator_requested_equals_realized"],
        "reviewer_a_quality_ab_ba": within["REVIEWER_A"]["passes"],
        "reviewer_b_quality_ab_ba": within["REVIEWER_B"]["passes"],
        "dual_quality": quality_dual["passes"],
        "dual_function": function["passes"],
        "dual_risk": risk["passes"],
    }
    measurement_pass = all(gate_checks.values())
    report = {
        "protocol": "pm-v1.5-v5.4-effect-canary-measurement-analysis-v1",
        "status": "MEASUREMENT_CANARY_PASS_EFFECT_FEASIBILITY_MAY_BE_INTERPRETED" if measurement_pass else "MEASUREMENT_CANARY_FAIL_NO_EFFECT_TARGETS",
        "gate_contract": gate["protocol"],
        "integrity": integrity,
        "quality_within_reviewer": within,
        "quality_between_reviewers": quality_dual,
        "function_between_reviewers": function,
        "risk_between_reviewers": risk,
        "critical_events": critical_events,
        "effect_feasibility_diagnostic": feasibility,
        "gate_checks": gate_checks,
        "measurement_pass": measurement_pass,
        "pm_has_learned": False,
        "final_pm_pass_evaluated": False,
        "remaining_88_live_calls_authorized": False,
        "reason_remaining_88_not_authorized": "A separate cost cap and execution manifest is required even if measurement passes.",
    }
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    with (OUT / "canary_state_diagnostics_not_training_targets.jsonl").open("w") as handle:
        for row in state_diagnostics:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    with (OUT / "resolved_quality_replicates_not_training_labels.jsonl").open("w") as handle:
        for row in consensus_quality:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
