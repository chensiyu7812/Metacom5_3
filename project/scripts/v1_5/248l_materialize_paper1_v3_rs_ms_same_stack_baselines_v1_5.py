#!/usr/bin/env python3
"""Materialize bounded RS+MS baselines from the existing 16x4 response panel."""

from __future__ import annotations

from collections import Counter
import json
import math
from pathlib import Path
import sys

import joblib


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import canonical_json, sha256_file, write_json, write_jsonl  # noqa: E402
from metacom_pm.text import estimate_tokens  # noqa: E402
from metacom_pm.v1_5_ms_rs_same_stack_baselines import (  # noqa: E402
    ACTIONS,
    action_for,
    choose_cost_matched_fixed,
    choose_on_rate_matched_random,
    transparent_ms_on,
)


CASES = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_qualification_preflight_v3_20260811/qualification_cases_private.jsonl"
CALLS = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_qualification_preflight_v3_20260811/physical_call_plan_private.jsonl"
RESULTS = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_trace_recovery_20260811/recovered_first_response_results_private.jsonl"
LABELS = ROOT / "outputs/pm_v1_5_paper1_v3_ms_single_teacher_label_freeze_20260811/ms_teacher_labels.jsonl"
MODEL = ROOT / "outputs/pm_v1_5_paper1_v3_ms_atomic_teacher_full_fit_20260811/ms_atomic_suitability_model.joblib"
FUNCTION_REVIEWS = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_function_gpt_id_repair_continuation_20260811/reviews.jsonl"
PRIVATE_MAPPING = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_measurement_packet_20260811/private_mapping.jsonl"
QUALITY_PACKET = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_measurement_packet_20260811/quality_packet_blind.jsonl"
RISK_PACKET = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_measurement_packet_20260811/risk_packet_blind.jsonl"
FUNCTION_PACKET = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_measurement_packet_20260811/function_packet_blind.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_rs_ms_same_stack_baseline_plan_20260811"
THRESHOLD = 0.5
RANDOM_SEED = "paper1-v3-rs-ms-matched-random-20260811"


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def feature_vector(row: dict) -> list[float]:
    return [
        float(row["selection_score"]),
        float(row["top1_top2_margin"]),
        math.log1p(int(row["candidate_age_sessions"])),
        math.log1p(int(row["candidate_word_count"])),
        math.log1p(int(row["strict_past_pool_count"])),
        int(bool(row["low_information_rank1"])),
        int(bool(row["exact_or_containment_current_echo"])),
    ]


def main() -> None:
    if OUT.exists():
        raise RuntimeError("baseline plan output exists; refusing overwrite")
    cases = rows(CASES)
    calls = rows(CALLS)
    results = rows(RESULTS)
    labels = {row["case_key"]: row for row in rows(LABELS)}
    model = joblib.load(MODEL)
    result_by_key = {(row["qualification_case_id"], row["requested_action_id"]): row for row in results}
    call_by_key = {(row["qualification_case_id"], row["requested_action_id"]): row for row in calls}
    if len(cases) != 16 or len(calls) != 64 or len(results) != 64:
        raise RuntimeError("expected the frozen 16-state by four-action panel")
    if any(set(action for case_id, action in result_by_key if case_id == case["qualification_case_id"]) != set(ACTIONS) for case in cases):
        raise RuntimeError("one or more states lack a complete four-arm response panel")

    state_ids = [case["state_id"] for case in cases]
    case_by_state = {case["state_id"]: case for case in cases}
    probabilities = {}
    learned_ms_on = {}
    transparent_on = {}
    estimated_costs = {}
    for case in cases:
        label = labels[case["case_key"]]
        probability = float(model.predict_proba([feature_vector(label)])[0, 1])
        probabilities[case["state_id"]] = probability
        learned_ms_on[case["state_id"]] = probability >= THRESHOLD
        transparent_on[case["state_id"]] = transparent_ms_on(
            low_information_rank1=bool(label["low_information_rank1"]),
            current_echo=bool(label["exact_or_containment_current_echo"]),
        )
        for action in ACTIONS:
            call = call_by_key[(case["qualification_case_id"], action)]
            estimated_costs[(case["state_id"], action)] = estimate_tokens(canonical_json(call["messages"]))

    learned_rs_ms = {state: action_for(ms_on=learned_ms_on[state], rs_on=True) for state in state_ids}
    learned_ms_r0 = {state: action_for(ms_on=learned_ms_on[state], rs_on=False) for state in state_ids}
    transparent = {state: action_for(ms_on=transparent_on[state], rs_on=True) for state in state_ids}
    cost_match = choose_cost_matched_fixed(
        state_ids=state_ids,
        learned_actions=learned_rs_ms,
        estimated_input_tokens=estimated_costs,
    )
    matched_random = choose_on_rate_matched_random(
        state_ids=state_ids,
        learned_ms_on=learned_ms_on,
        estimated_input_tokens=estimated_costs,
        seed=RANDOM_SEED,
    )
    fixed_cost_policy_name = (
        "cost_matched_fixed" if cost_match["qualified_at_5_percent"]
        else "closest_cost_fixed_unqualified"
    )
    policies = {
        "always_off": {state: "M0+R0" for state in state_ids},
        "rs_only": {state: "M0+RS" for state in state_ids},
        "fixed_high_rs_ms": {state: "MS+RS" for state in state_ids},
        "transparent_rs_ms": transparent,
        "rs_fixed_on_plus_learned_ms": learned_rs_ms,
        "learned_ms_r0_slice": learned_ms_r0,
        fixed_cost_policy_name: {state: cost_match["action"] for state in state_ids},
        "cost_and_on_rate_matched_random_rs": matched_random["actions"],
    }

    accepted_function = {
        row["blind_item_id"]: row
        for row in rows(FUNCTION_REVIEWS)
        if row.get("stage") == "PUBLIC"
    }
    mapping = rows(PRIVATE_MAPPING)
    function_key = {
        (row["state_id"], row["on_action"]): row["function_blind_item_id"]
        for row in mapping
    }
    plan_rows = []
    for state in state_ids:
        case = case_by_state[state]
        label = labels[case["case_key"]]
        for policy, action_by_state in policies.items():
            action = action_by_state[state]
            result = result_by_key[(case["qualification_case_id"], action)]
            function_id = function_key.get((state, action))
            function = accepted_function.get(function_id or "")
            plan_rows.append({
                "protocol": "pm-v1.5-paper1-v3-rs-ms-same-stack-policy-binding-v1",
                "policy": policy,
                "state_id": state,
                "qualification_case_id": case["qualification_case_id"],
                "split_group_key": case["split_group_key"],
                "selected_action": action,
                "selected_physical_call_id": result["physical_call_id"],
                "selected_response_is_existing": True,
                "estimated_input_tokens": estimated_costs[(state, action)],
                "ms_probability": probabilities[state],
                "ms_threshold": THRESHOLD,
                "ms_selected_on": action.startswith("MS+"),
                "rs_selected_on": action.endswith("+RS"),
                "transparent_ms_on": transparent_on[state],
                "teacher_class_private_development_only": case["qualification_class"],
                "negative_stratum_private": case["negative_stratum"],
                "function_blind_item_id_if_ms_on": function_id,
                "accepted_proxy_function_label": function.get("label") if function else None,
                "accepted_proxy_function_available": function is not None,
            })

    policy_summary = []
    for policy, action_by_state in policies.items():
        selected = [row for row in plan_rows if row["policy"] == policy]
        function_rows = [row for row in selected if row["accepted_proxy_function_available"]]
        policy_summary.append({
            "policy": policy,
            "states": 16,
            "action_counts": dict(Counter(action_by_state.values())),
            "ms_on": sum(action.startswith("MS+") for action in action_by_state.values()),
            "rs_on": sum(action.endswith("+RS") for action in action_by_state.values()),
            "total_estimated_input_tokens": sum(row["estimated_input_tokens"] for row in selected),
            "mean_estimated_input_tokens": sum(row["estimated_input_tokens"] for row in selected) / 16,
            "accepted_proxy_function_coverage": len(function_rows),
            "accepted_proxy_function_labels": dict(Counter(row["accepted_proxy_function_label"] for row in function_rows)),
        })

    learned_teacher = Counter()
    for case in cases:
        predicted = learned_ms_on[case["state_id"]]
        teacher = case["qualification_class"] == "TEACHER_SUITABLE"
        learned_teacher[(teacher, predicted)] += 1
    differing_primary = [
        state for state in state_ids if learned_rs_ms[state] != policies["rs_only"][state]
    ]
    differing_fixed = [
        state for state in state_ids if learned_rs_ms[state] != policies["fixed_high_rs_ms"][state]
    ]
    differing_random = [
        state for state in state_ids if learned_rs_ms[state] != policies["cost_and_on_rate_matched_random_rs"][state]
    ]
    report = {
        "protocol": "pm-v1.5-paper1-v3-rs-ms-same-stack-baseline-plan-v1",
        "status": "ZERO_API_BASELINE_ACTIONS_MATERIALIZED_EXISTING_RESPONSES_ONLY_FORMAL_OUTCOMES_NOT_YET_SCORED",
        "scientific_question": "Does the frozen learned atomic-MS gate add value over RS-only when both policies reuse the same V3 response stack?",
        "scope_correction": {
            "valid_name": "RS fixed ON plus learned MS",
            "invalid_name": "jointly learned RS+MS deployment policy",
            "reason": "The carried RS result has grouped-OOF PASS evidence but the active method did not create a matching full-fit RS checkpoint for these EvoEmo states.",
            "primary_incremental_contrast": "rs_fixed_on_plus_learned_ms versus rs_only",
            "interaction_diagnostic": "learned_ms_r0_slice versus always_off, compared descriptively with the RS-on slice",
        },
        "panel": {
            "states": 16,
            "connected_groups": 8,
            "existing_physical_responses": 64,
            "new_generator_calls": 0,
            "all_four_actions_per_state": True,
            "actions": list(ACTIONS),
        },
        "frozen_ms": {
            "threshold": THRESHOLD,
            "predicted_on": sum(learned_ms_on.values()),
            "predicted_off": 16 - sum(learned_ms_on.values()),
            "qualification_sample_teacher_cross_tab_development_only": {
                "teacher_suitable_predicted_on": learned_teacher[(True, True)],
                "teacher_suitable_predicted_off": learned_teacher[(True, False)],
                "teacher_not_suitable_predicted_on": learned_teacher[(False, True)],
                "teacher_not_suitable_predicted_off": learned_teacher[(False, False)],
            },
            "not_an_external_or_oof_metric": True,
        },
        "transparent_rule": {
            "definition": "MS ON iff actual Rank-1 is neither low-information nor an exact/containment current echo",
            "semantic_suitability_not_claimed": True,
            "predicted_on": sum(transparent_on.values()),
        },
        "policies": policy_summary,
        "matched_controls": {
            "cost_matched_fixed": cost_match,
            "cost_and_on_rate_matched_random_rs": {key: value for key, value in matched_random.items() if key not in {"ms_on", "actions"}},
        },
        "minimal_measurement": {
            "learned_vs_rs_only_nonalias_states": len(differing_primary),
            "learned_vs_fixed_high_nonalias_states": len(differing_fixed),
            "learned_vs_matched_random_nonalias_states": len(differing_random),
            "unique_rs_slice_ms_on_off_pairs_needed_for_all_primary_comparisons": 16,
            "existing_quality_packet_can_be_reused": True,
            "existing_risk_packet_can_be_reused": True,
            "accepted_proxy_function_is_development_only": True,
        },
        "current_interpretability": {
            "function": "partial development proxy may be joined where available",
            "quality": "not yet scored",
            "risk": "not yet scored",
            "cost": "fully deterministic and reported",
            "baseline_winner_can_be_declared_now": False,
        },
        "decision": "PROCEED_TO_ONE_BLIND_RS_SLICE_OUTCOME_MEASUREMENT_WITHOUT_NEW_GENERATION_OR_REFIT",
        "source_hashes": {
            "cases": sha256_file(CASES),
            "calls": sha256_file(CALLS),
            "recovered_results": sha256_file(RESULTS),
            "teacher_labels": sha256_file(LABELS),
            "ms_checkpoint": sha256_file(MODEL),
            "accepted_function_reviews": sha256_file(FUNCTION_REVIEWS),
            "private_mapping": sha256_file(PRIVATE_MAPPING),
            "quality_packet": sha256_file(QUALITY_PACKET),
            "risk_packet": sha256_file(RISK_PACKET),
            "function_packet": sha256_file(FUNCTION_PACKET),
        },
        "api_calls": 0,
        "pm_fits": 0,
        "responses_generated": 0,
        "next": "FREEZE_AND_RUN_MINIMAL_BLIND_16_PAIR_RS_SLICE_QUALITY_RISK_FUNCTION_MEASUREMENT",
    }
    OUT.mkdir(parents=True)
    write_jsonl(OUT / "policy_actions_private.jsonl", plan_rows)
    rs_mapping = [row for row in mapping if row["rs_condition"] == "RS"]
    quality_ids = {row["quality_blind_item_id"] for row in rs_mapping}
    risk_ids = {
        item
        for row in rs_mapping
        for item in (row["risk_A_blind_item_id"], row["risk_B_blind_item_id"])
    }
    function_ids = {row["function_blind_item_id"] for row in rs_mapping}
    quality_blind = [row for row in rows(QUALITY_PACKET) if row["blind_item_id"] in quality_ids]
    risk_blind = [row for row in rows(RISK_PACKET) if row["blind_item_id"] in risk_ids]
    function_blind = [row for row in rows(FUNCTION_PACKET) if row["blind_item_id"] in function_ids]
    if (len(quality_blind), len(risk_blind), len(function_blind)) != (16, 32, 16):
        raise RuntimeError("minimal RS-slice blind packet denominator drifted")
    write_jsonl(OUT / "quality_rs_slice_blind.jsonl", quality_blind)
    write_jsonl(OUT / "risk_rs_slice_blind.jsonl", risk_blind)
    write_jsonl(OUT / "function_ms_rs_blind.jsonl", function_blind)
    report["measurement_artifacts"] = {
        "quality_16_pairs": {
            "path": str((OUT / "quality_rs_slice_blind.jsonl").relative_to(ROOT)),
            "sha256": sha256_file(OUT / "quality_rs_slice_blind.jsonl"),
        },
        "risk_32_absolute_arms": {
            "path": str((OUT / "risk_rs_slice_blind.jsonl").relative_to(ROOT)),
            "sha256": sha256_file(OUT / "risk_rs_slice_blind.jsonl"),
        },
        "function_16_ms_rs_responses": {
            "path": str((OUT / "function_ms_rs_blind.jsonl").relative_to(ROOT)),
            "sha256": sha256_file(OUT / "function_ms_rs_blind.jsonl"),
        },
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
