#!/usr/bin/env python3
"""Materialize (zero-API) the RS-only ESConv external test, mirroring the
RS+MS EvoEmo external test (299l) methodology exactly, for a genuinely
comparable second track.

ESConv is single-session (memory_available is {ME:false,MP:false,MS:false}
for every real state -- structurally confirmed, not assumed), so only RS
ever applies: baseline M0 vs routed RS, 2 actions, not 16. RS's opportunity
router was originally trained on ESConv data itself (confirmed via
fit_report.json training_rows_audit.jsonl source_dialogue_id values), so
this is zero new training -- feature extraction + inference only.

Same instrument choices as the EvoEmo round for fair comparability:
v1_5_component_general_v3 + v1_5_response_program_v3 generation stack,
v1_5_rs_v4_card_retrieval.retrieve() for Step2 card selection, same-state
same-seed M0 baseline pairing for every routed call.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import canonical_json, read_json, read_jsonl, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_component_general_v3 import (  # noqa: E402
    V3Candidate,
    all_sixteen_action_ids,
    build_component_general_plan_v3,
)
from metacom_pm.v1_5_ms_same_stack_feasibility import SameStackGeneratorOutput  # noqa: E402
from metacom_pm.v1_5_response_program_v3 import response_generation_messages_v3  # noqa: E402
from metacom_pm.v1_5_rs_v4_card_retrieval import retrieve as rs_retrieve  # noqa: E402
from metacom_pm.v1_5b_policy_runtime import compile_component_bits  # noqa: E402

AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
BUNDLE = ROOT / "data/pm_v1_5_contracts/paper1_active_execution_bundle_v1.json"
ESCONV_STATES = ROOT / "outputs/pm_v1_5_paper1_p1_public_surface/esconv_states_unlabeled.jsonl"
QUALIFIED_CARDS = ROOT / "outputs/pm_v1_5_paper1_rs_strategy_card_llm_audit_qualified_bank_20260812/strategy_cards_v4_llm_audit_qualified_only.jsonl"
RELEASE_MANIFEST = ROOT / "outputs/pm_v1_5_paid_run_release.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_rs_esconv_external_test_preflight_20260812"
CURRENT_GOAL = "Respond supportively to the latest visible seeker turn. Advance its immediate emotional-support goal without inventing facts, overloading the reply, or assuming a past fact is still current."
MAX_PER_DIALOGUE = 1
TARGET_STATES = 36


def stable_hex(*values: object, length: int = 24) -> str:
    text = "\x1f".join(str(value) for value in values)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def main() -> None:
    if OUT.exists():
        raise RuntimeError("RS ESConv external test preflight exists; refusing overwrite")
    authority = read_json(AUTHORITY)
    current = authority["current_execution_phase"]
    alias = authority["active_v3_phase"]
    expected_bundle = {"path": str(BUNDLE.relative_to(ROOT)), "sha256": sha256_file(BUNDLE)}
    if current["id"] != "RS_RESTATEMENT_WARM_CLOSE_QUALITY_GAIN_TRADED_FOR_DOUBLED_HALLUCINATION_RISK_MP_NEXT" or current["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("warm-close rerisk phase is not the current execution phase")
    if alias.get("compatibility_alias_of") != "current_execution_phase" or alias["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("authority compatibility alias drifted")

    all_states = read_jsonl(ESCONV_STATES)
    test_states = [s for s in all_states if s["split"] == "test"]
    qualified_cards = read_jsonl(QUALIFIED_CARDS)
    if len(qualified_cards) != 79:
        raise RuntimeError("frozen 79-card qualified pool denominator drifted")
    if not all(not any(s["memory_available"].values()) for s in test_states):
        raise RuntimeError("ESConv memory_available is not structurally all-false; MP/MS/ME assumption violated")

    enriched: list[dict[str, Any]] = []
    for state in test_states:
        rs_decision = rs_retrieve(recent_dialogue=state["visible_dialogue"], qualified_cards=qualified_cards)
        rs_d = "ON" if rs_decision.selected_card is not None else "OFF"
        enriched.append({"state": state, "rs_decision": rs_d, "rs_selected_card": rs_decision.selected_card, "rs_selected_score": rs_decision.selected_score})

    cells: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in enriched:
        cells[row["rs_decision"]].append(row)
    for bucket in cells.values():
        bucket.sort(key=lambda row: stable_hex("ESCONV_EXT_TEST_SELECT", row["state"]["state_id"]))

    cell_targets = {"OFF": TARGET_STATES // 3, "ON": TARGET_STATES - TARGET_STATES // 3}
    selected: list[dict[str, Any]] = []
    dialogue_counts: dict[str, int] = defaultdict(int)
    for cell, target in cell_targets.items():
        taken = 0
        for row in cells.get(cell, []):
            if taken >= target:
                break
            dialogue_id = row["state"]["dialogue_id"]
            if dialogue_counts[dialogue_id] >= MAX_PER_DIALOGUE:
                continue
            selected.append(row)
            dialogue_counts[dialogue_id] += 1
            taken += 1
    selected.sort(key=lambda row: stable_hex("ESCONV_EXT_TEST_ORDER", row["state"]["state_id"]))

    qualification_cases: list[dict[str, Any]] = []
    physical_calls: list[dict[str, Any]] = []
    for row in selected:
        state = row["state"]
        case_id = "rsesconvext_" + stable_hex(state["state_id"])
        seed = 20260812 + int(stable_hex("SEED", case_id, length=8), 16) % 100000
        context = "\n".join(
            f"{str(turn['speaker']).upper()}: {str(turn['content']).strip()}"
            for turn in state["visible_dialogue"]
            if str(turn.get("content", "")).strip()
        )
        routed_rs_on = row["rs_decision"] == "ON"
        selected_card = row["rs_selected_card"]
        rs_evidence_id = ("rscard_" + selected_card["card_id"]) if selected_card else None
        routed_bits = {"MP": False, "MS": False, "ME": False, "RS": routed_rs_on}
        routed_action = compile_component_bits(routed_bits)
        baseline_action = "M0+R0"
        qualification_cases.append({
            "protocol": "pm-v1.5-paper1-rs-esconv-external-test-case-v1",
            "case_id": case_id,
            "state_id": state["state_id"],
            "dialogue_id": state["dialogue_id"],
            "runtime_owner_key": state["runtime_owner_key"],
            "split_group_key": state["split_group_key"],
            "rs_decision": row["rs_decision"],
            "rs_selected_card_id": selected_card["card_id"] if selected_card else None,
            "rs_selected_family": selected_card["strategy_family"] if selected_card else None,
            "rs_selected_score": row["rs_selected_score"],
            "rs_evidence_id": rs_evidence_id,
            "routed_action_id": routed_action,
            "baseline_action_id": baseline_action,
            "current_context": context,
            "current_goal": CURRENT_GOAL,
            "rs_prompt_guidance": selected_card["prompt_guidance"] if (routed_rs_on and selected_card) else None,
            "rs_support_move": selected_card["support_move"] if (routed_rs_on and selected_card) else None,
            "rs_when_not_to_use": selected_card["when_not_to_use"] if (routed_rs_on and selected_card) else None,
            "seed": seed,
        })
        actions_to_call = (baseline_action, routed_action) if routed_action != baseline_action else (baseline_action,)
        for action in actions_to_call:
            is_routed_call = action == routed_action and action != baseline_action
            candidates: dict[str, V3Candidate | None] = {c: None for c in ("MP", "MS", "ME", "RS")}
            if is_routed_call and routed_rs_on and selected_card:
                candidates["RS"] = V3Candidate(
                    component="RS",
                    evidence_id=rs_evidence_id,
                    meaning_cue=selected_card["prompt_guidance"],
                    exact_source=f"Strategy card ({selected_card['strategy_family']}): {selected_card['support_move']}",
                    owner_id=None,
                    time_status="CURRENT_STRATEGY_CARD",
                    allowed_response_change=f"Make the reply's primary act reflect this technique: {selected_card['support_move']}",
                    forbidden_inference=selected_card["when_not_to_use"],
                    burden_units=1,
                )
            plan = build_component_general_plan_v3(
                requested_action_id=action,
                current_user_id=state["runtime_owner_key"],
                candidates=candidates,
                pair_relations=None,
            )
            messages = response_generation_messages_v3(current_context=context, current_goal=CURRENT_GOAL, plan=plan)
            physical_calls.append({
                "protocol": "pm-v1.5-paper1-rs-esconv-external-test-call-v1",
                "physical_call_id": "rsesconvcall_" + stable_hex(case_id, action, seed),
                "case_id": case_id,
                "state_id": state["state_id"],
                "dialogue_id": state["dialogue_id"],
                "runtime_owner_key": state["runtime_owner_key"],
                "requested_action_id": action,
                "is_baseline": action == baseline_action,
                "is_routed": is_routed_call,
                "seed": seed,
                "temperature": 0.7,
                "max_output_tokens": 512,
                "messages": messages,
                "messages_sha256": sha256_text(canonical_json(messages)),
                "response_schema": SameStackGeneratorOutput.model_json_schema(),
                "response_schema_sha256": sha256_text(canonical_json(SameStackGeneratorOutput.model_json_schema())),
                "plan_accounting": {
                    "requested_action_id": plan.accounting.requested_action_id,
                    "structurally_eligible_action_id": plan.accounting.structurally_eligible_action_id,
                    "jointly_planned_action_id": plan.accounting.jointly_planned_action_id,
                },
            })

    by_case = defaultdict(list)
    for row in physical_calls:
        by_case[row["case_id"]].append(row)
    prompt_texts = [canonical_json(row["messages"]) for row in physical_calls]
    cell_coverage = Counter(row["rs_decision"] for row in qualification_cases)
    checks = {
        "at_least_24_states_distinct_dialogues": len(qualification_cases) >= 24 and all(c <= MAX_PER_DIALOGUE for c in Counter(row["dialogue_id"] for row in qualification_cases).values()),
        "every_state_has_a_baseline_call": all(any(row["is_baseline"] for row in calls) for calls in by_case.values()),
        "routed_call_present_only_when_action_differs_from_baseline": all(
            (case["routed_action_id"] != case["baseline_action_id"]) == any(row["is_routed"] for row in by_case[case["case_id"]])
            for case in qualification_cases
        ),
        "same_seed_within_state": all(len({row["seed"] for row in calls}) == 1 for calls in by_case.values()),
        "visible_context_ends_with_seeker": all(row["current_context"].splitlines()[-1].startswith("SEEKER:") for row in qualification_cases if row["current_context"].splitlines()),
        "no_mp_ms_me_ever_planned": all(
            call["plan_accounting"]["jointly_planned_action_id"] in ("M0+R0", "M0+RS")
            for call in physical_calls
        ),
        "v3_meaning_absorption_prompt_only": all("Literal mention and lexical overlap are not required" in text for text in prompt_texts),
        "safe_nonuse_instruction_present": all("leave it unused and still produce a safe current-context-grounded reply" in text for text in prompt_texts),
        "no_one_memory_cap_and_global_16_actions_unchanged": len(all_sixteen_action_ids()) == 16,
        "rs_score_never_provider_visible": all((c["rs_selected_score"] is None or str(round(c["rs_selected_score"], 4)) not in text) for c in qualification_cases for text in prompt_texts),
        "response_schema_frozen": len({row["response_schema_sha256"] for row in physical_calls}) == 1,
        "cell_coverage_both_present": cell_coverage.get("ON", 0) > 0 and cell_coverage.get("OFF", 0) > 0,
        "no_api_calls": True,
        "no_pm_refit": True,
        "no_mp_ms_me_training_work": True,
    }
    failed = [name for name, passed in checks.items() if not passed]

    run_identity = sha256_text(
        canonical_json({
            "stage": "paper1_rs_esconv_external_test_v1",
            "call_plan": [row["physical_call_id"] for row in physical_calls],
            "call_plan_messages_sha256": [row["messages_sha256"] for row in physical_calls],
        })
    )
    release_manifest = read_json(RELEASE_MANIFEST)
    consumed_identities = {
        str(record.get("approval_identity") or record.get("run_identity") or "")
        for record in [
            *(release_manifest.get("stage_consumptions") or {}).values(),
            *(release_manifest.get("prior_stage_attempts_history") or []),
            *(release_manifest.get("stage_consumptions_history") or []),
        ]
        if isinstance(record, dict)
    }
    if run_identity in consumed_identities or run_identity in (release_manifest.get("stage_approvals") or {}).values():
        failed.append("run_identity_not_previously_consumed_or_pending")

    if failed:
        raise RuntimeError(f"RS ESConv external test preflight failed: {failed}; checks={checks}")

    OUT.mkdir(parents=True)
    cases_path = OUT / "qualification_cases_private.jsonl"
    calls_path = OUT / "physical_call_plan_private.jsonl"
    write_jsonl(cases_path, qualification_cases)
    write_jsonl(calls_path, physical_calls)

    report = {
        "protocol": "pm-v1.5-paper1-rs-esconv-external-test-preflight-v1",
        "status": "PASS_EXTERNAL_TEST_PROPOSAL_READY_HUMAN_APPROVAL_REQUIRED_BEFORE_ANY_API_CALL",
        "checks": checks,
        "sample": {
            "states": len(qualification_cases),
            "distinct_dialogues": len({row["dialogue_id"] for row in qualification_cases}),
            "cell_coverage_rs": dict(cell_coverage),
            "baseline_calls": sum(1 for row in physical_calls if row["is_baseline"]),
            "routed_calls": sum(1 for row in physical_calls if row["is_routed"]),
            "total_calls": len(physical_calls),
            "distinct_rs_cards_used": len({c["rs_selected_card_id"] for c in qualification_cases if c["rs_selected_card_id"]}),
        },
        "note": "RS-only (MP/MS/ME structurally unavailable in single-session ESConv, memory_available all-false confirmed on every real state, not assumed). Same V3 generation stack, same RS Step1+Step2 pipeline, same instrument choices as the EvoEmo external test, for a genuinely comparable second track.",
        "proposed_authorization": {
            "stage": "paper1_rs_esconv_external_test_v1",
            "run_identity": run_identity,
        },
        "artifacts": {
            "cases": {"path": str(cases_path.relative_to(ROOT)), "sha256": sha256_file(cases_path)},
            "calls": {"path": str(calls_path.relative_to(ROOT)), "sha256": sha256_file(calls_path)},
        },
        "api_calls": 0,
        "pm_fits": 0,
        "next": "PROPOSE_RUN_IDENTITY_AND_COST_CAP_FOR_HUMAN_APPROVAL",
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
