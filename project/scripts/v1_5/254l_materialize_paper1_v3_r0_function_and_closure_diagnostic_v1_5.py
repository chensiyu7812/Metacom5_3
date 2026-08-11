#!/usr/bin/env python3
"""Materialize the frozen zero-API R0 Function and closure-routing diagnostics."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "outputs/pm_v1_5_paper1_v3_rs_ms_same_stack_baseline_plan_20260811/policy_actions_private.jsonl"
FUNCTION_PACKET = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_measurement_packet_20260811/function_packet_blind.jsonl"
MAPPING = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_measurement_packet_20260811/private_mapping.jsonl"
RESPONSES = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_trace_recovery_20260811/recovered_first_response_results_private.jsonl"
CASES = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_qualification_preflight_v3_20260811/qualification_cases_private.jsonl"
PI = ROOT / "outputs/pm_v1_5_paper1_v3_rs_ms_two_human_freeze_20260811/human_B_raw_frozen.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_r0_function_closure_diagnostic_20260811"

CLOSURE = {
    "evo::p13::esc1198::seeker_turn::25": "plan formed + anger reduced + repeated thanks",
    "evo::p1::p1_conv_1::seeker_turn::25": "feels lighter + plan to seek support + repeated thanks",
}


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def stable_id(prefix: str, value: str) -> str:
    return f"{prefix}_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]}"


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in records), encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    policy = rows(POLICY)
    functions = {x["blind_item_id"]: x for x in rows(FUNCTION_PACKET)}
    mapping = rows(MAPPING)
    response_by_call = {x["physical_call_id"]: x for x in rows(RESPONSES)}
    case_by_state = {x["state_id"]: x for x in rows(CASES)}
    pi = json.loads(PI.read_text(encoding="utf-8"))["answers"]

    r0_policy = {
        x["state_id"]: x
        for x in policy
        if x["policy"] == "learned_ms_r0_slice" and x["ms_selected_on"]
    }
    rs_mapping = {x["state_id"]: x for x in mapping if x["rs_condition"] == "RS"}

    blind_function: list[dict] = []
    private_function: list[dict] = []
    for state_id in sorted(r0_policy):
        selected = r0_policy[state_id]
        original_id = selected["function_blind_item_id_if_ms_on"]
        source_item = functions[original_id]
        response = response_by_call[selected["selected_physical_call_id"]]
        blind_id = stable_id("msr0func", state_id)
        blind_function.append(
            {
                "protocol": "pm-v1.5-paper1-v3-ms-r0-existing-arm-function-blind-item-v1",
                "blind_item_id": blind_id,
                "visible_current_dialogue": source_item["visible_current_dialogue"],
                "strictly_past_user_owned_source": source_item["strictly_past_user_owned_source"],
                "response": response["final_reply"],
                "component_minimum": source_item["component_minimum"],
                "decision": source_item["decision"],
                "annotation": {
                    "label": "",
                    "source_evidence_quote": "",
                    "response_evidence_quote": "",
                    "boundary_event_quote": "",
                    "rationale": "",
                },
            }
        )
        rs_item_id = rs_mapping[state_id]["function_blind_item_id"]
        source_availability = pi[rs_item_id]["source_availability"]
        private_function.append(
            {
                "protocol": "pm-v1.5-paper1-v3-ms-r0-existing-arm-function-private-key-v1",
                "blind_item_id": blind_id,
                "state_id": state_id,
                "split_group_key": selected["split_group_key"],
                "qualification_case_id": selected["qualification_case_id"],
                "existing_physical_call_id": selected["selected_physical_call_id"],
                "requested_action": "MS+R0",
                "generator_claimed_MS": bool(response["generator_claimed"]["MS"]),
                "PI_source_availability_from_matched_RS_slice": source_availability,
                "matched_RS_function_item_id": rs_item_id,
                "formal_R0_function_label": None,
            }
        )

    closure_blind: list[dict] = []
    closure_private: list[dict] = []
    policy_by_key = {(x["state_id"], x["policy"]): x for x in policy}
    for state_id, signal in sorted(CLOSURE.items()):
        r0 = policy_by_key[(state_id, "always_off")]
        rs = policy_by_key[(state_id, "rs_only")]
        r0_reply = response_by_call[r0["selected_physical_call_id"]]["final_reply"]
        rs_reply = response_by_call[rs["selected_physical_call_id"]]["final_reply"]
        present_r0_as_a = int(hashlib.sha256(state_id.encode("utf-8")).hexdigest(), 16) % 2 == 0
        response_a, action_a = (r0_reply, "M0+R0") if present_r0_as_a else (rs_reply, "M0+RS")
        response_b, action_b = (rs_reply, "M0+RS") if present_r0_as_a else (r0_reply, "M0+R0")
        blind_id = stable_id("closureq", state_id)
        closure_blind.append(
            {
                "protocol": "pm-v1.5-paper1-v3-closure-routing-existing-arm-quality-blind-item-v1",
                "blind_item_id": blind_id,
                "visible_current_dialogue": case_by_state[state_id]["current_context"],
                "response_A": response_a,
                "response_B": response_b,
                "decision": {
                    "label": ["A_BETTER", "B_BETTER", "EQUIVALENT", "UNRESOLVED"],
                    "material_rule": "Prefer one arm only when it better matches the current support phase. For explicit relief plus closure, reward acknowledging improvement, gentle closure, low response burden, and a future-open option; do not reward continuing the topic merely because it asks an open question.",
                    "equivalent_rule": "Use EQUIVALENT when both responses are similarly phase-appropriate or when differences are cosmetic/mixed without a material net direction.",
                    "required_evidence": "Quote one exact span from each response and give one concise current-phase contrast reason.",
                    "do_not_score": ["memory use", "resource Function", "Cost", "length alone", "style alone"],
                },
                "annotation": {"label": "", "quote_A": "", "quote_B": "", "contrast_reason": ""},
            }
        )
        closure_private.append(
            {
                "protocol": "pm-v1.5-paper1-v3-closure-routing-existing-arm-quality-private-key-v1",
                "blind_item_id": blind_id,
                "state_id": state_id,
                "split_group_key": case_by_state[state_id]["split_group_key"],
                "preidentified_closure_signal": signal,
                "response_A_action": action_a,
                "response_B_action": action_b,
                "M0_R0_existing_physical_call_id": r0["selected_physical_call_id"],
                "M0_RS_existing_physical_call_id": rs["selected_physical_call_id"],
                "formal_quality_label": None,
            }
        )

    write_jsonl(OUT / "r0_function_blind.jsonl", blind_function)
    write_jsonl(OUT / "r0_function_private_key.jsonl", private_function)
    write_jsonl(OUT / "closure_quality_blind.jsonl", closure_blind)
    write_jsonl(OUT / "closure_quality_private_key.jsonl", closure_private)

    claimed = sum(x["generator_claimed_MS"] for x in private_function)
    usable = sum(x["PI_source_availability_from_matched_RS_slice"] == "USABLE" for x in private_function)
    report = {
        "protocol": "pm-v1.5-paper1-v3-r0-function-closure-zero-api-diagnostic-v1",
        "date": "2026-08-11",
        "status": "ZERO_API_EXISTING_ARM_DIAGNOSTIC_PACKETS_READY_LABELS_PENDING",
        "r0_function": {
            "cases": len(blind_function),
            "connected_groups": len({x["split_group_key"] for x in private_function}),
            "requested_action": "MS+R0",
            "matched_learned_MS_ON_states": len(r0_policy),
            "PI_matched_source_usable": usable,
            "generator_claimed_MS": claimed,
            "generator_reported_nonuse": len(private_function) - claimed,
            "formal_source_aware_Function": "PENDING_PI_REVIEW",
            "interpretation_rule": {
                "any_verified_function": "RS crowd-out contributed to the RS-slice failure, but the size and repeatability still require reporting.",
                "zero_verified_function": "RS crowd-out is insufficient as the explanation; candidate-specific semantic planning and generator realization remain failed or missing.",
            },
        },
        "closure_routing": {
            "cases": len(closure_blind),
            "actions": ["M0+R0", "M0+RS"],
            "formal_quality_direction": "PENDING_PI_REVIEW",
            "kept_separate_from_MS_function": True,
        },
        "provenance": {
            "all_responses_preexisting": True,
            "new_API_calls": 0,
            "new_responses_generated": 0,
            "PM_refit": False,
            "threshold_change": False,
            "training_labels_created": 0,
        },
    }
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
