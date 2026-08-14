#!/usr/bin/env python3
"""Materialize (zero-API) a larger, real-card-selection RS+MS EvoEmo external
test, superseding the 6-state mechanism-only pilot (291l/292l).

Differences from the earlier pilot:
  - Real RS Step2 card selection (v1_5_rs_v4_card_retrieval.retrieve() over
    the 79 LLM-audit-qualified V4 cards) instead of one fixed generic card.
  - Larger, broader sample (up to 2 states per owner across all 17 owners in
    the MS-labeled pool, ~34 states) instead of 6, for more statistical
    weight -- this is still a mechanism/qualitative test, not a formal blind
    quality measurement, and is reported as such.
  - Same-state/same-seed M0+R0 baseline pairing preserved for every routed
    call, per established practice this session.

MP and ME are forced OFF via candidate=None (the project's own established
ablation-arm pattern), since neither was trained this session.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import joblib

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
OOF_PREDICTIONS = ROOT / "outputs/pm_v1_5_paper1_ms_source_annotated_consensus_logo_oof_20260812/oof_predictions.jsonl"
MS_THRESHOLDS = ROOT / "outputs/pm_v1_5_paper1_ms_outer_train_abstention_calibration_20260812/ms_head_abstention_thresholds.json"
EVOEMO_STATES = ROOT / "outputs/pm_v1_5_paper1_p1_public_surface/evoemo_states_unlabeled.jsonl"
EVOEMO_CANDIDATES = ROOT / "outputs/pm_v1_5_paper1_p1_public_surface/evoemo_candidates_unlabeled.jsonl"
QUALIFIED_CARDS = ROOT / "outputs/pm_v1_5_paper1_rs_strategy_card_llm_audit_qualified_bank_20260812/strategy_cards_v4_llm_audit_qualified_only.jsonl"
RELEASE_MANIFEST = ROOT / "outputs/pm_v1_5_paid_run_release.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_rs_ms_evoemo_external_test_preflight_20260812"
CURRENT_GOAL = "Respond supportively to the latest visible seeker turn. Advance its immediate emotional-support goal without inventing facts, overloading the reply, or assuming a past fact is still current."

MS_MEANING_CUE = (
    "Interpret the single strictly past user-owned source supplied below as a "
    "tentative continuity cue; do not treat it as current or quote it."
)
MS_ALLOWED_CHANGE = "If it materially helps, use the past meaning to acknowledge continuity or ask a more informed current-oriented question."
MS_FORBIDDEN = "Do not copy the user's first-person wording, assume the past remains true, infer a trait or cause, or expose a memory record."

MAX_PER_OWNER = 2


def stable_hex(*values: object, length: int = 24) -> str:
    text = "\x1f".join(str(value) for value in values)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def main() -> None:
    if OUT.exists():
        raise RuntimeError("RS+MS EvoEmo external test preflight exists; refusing overwrite")
    authority = read_json(AUTHORITY)
    current = authority["current_execution_phase"]
    alias = authority["active_v3_phase"]
    expected_bundle = {"path": str(BUNDLE.relative_to(ROOT)), "sha256": sha256_file(BUNDLE)}
    if current["id"] != "RS_STEP2_CARD_RETRIEVAL_BUILT_AND_VALIDATED_MP_NEXT" or current["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("RS-step2-card-retrieval-built phase is not the current execution phase")
    if alias.get("compatibility_alias_of") != "current_execution_phase" or alias["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("authority compatibility alias drifted")

    ms_thresholds = read_json(MS_THRESHOLDS)
    ms_predictions = read_jsonl(OOF_PREDICTIONS)
    evoemo_states = {row["state_id"]: row for row in read_jsonl(EVOEMO_STATES)}
    evoemo_candidates = {row["candidate_id"]: row for row in read_jsonl(EVOEMO_CANDIDATES)}
    qualified_cards = read_jsonl(QUALIFIED_CARDS)
    if len(qualified_cards) != 79:
        raise RuntimeError("frozen 79-card qualified pool denominator drifted")

    def ms_decision(probability: float) -> str:
        if probability >= ms_thresholds["on_min"]:
            return "ON"
        if probability <= ms_thresholds["off_max"]:
            return "OFF"
        return "UNCERTAIN"

    enriched: list[dict[str, Any]] = []
    for row in ms_predictions:
        state = evoemo_states.get(row["state_id"])
        candidate = evoemo_candidates.get(row["actual_rank1_id"])
        if state is None or candidate is None:
            continue
        ms_p = float(row["primary_probability"])
        ms_d = ms_decision(ms_p)
        rs_decision = rs_retrieve(recent_dialogue=state["visible_current_session_dialogue"], qualified_cards=qualified_cards)
        rs_d = "ON" if rs_decision.selected_card is not None else "OFF"
        enriched.append({
            "state": state,
            "candidate": candidate,
            "ms_probability": ms_p,
            "ms_decision": ms_d,
            "rs_decision": rs_d,
            "rs_selected_card": rs_decision.selected_card,
            "rs_selected_score": rs_decision.selected_score,
            "consensus_label": row["consensus_label"],
        })

    cells: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in enriched:
        cells[(row["ms_decision"], row["rs_decision"])].append(row)
    for bucket in cells.values():
        bucket.sort(key=lambda row: stable_hex("EXT_TEST_SELECT", row["state"]["state_id"]))

    target_cells = (("ON", "ON"), ("ON", "OFF"), ("OFF", "ON"), ("OFF", "OFF"), ("UNCERTAIN", "ON"), ("UNCERTAIN", "OFF"))
    selected: list[dict[str, Any]] = []
    owner_counts: dict[str, int] = defaultdict(int)
    for cell in target_cells:
        for row in cells.get(cell, []):
            owner = row["state"]["runtime_owner_key"]
            if owner_counts[owner] >= MAX_PER_OWNER:
                continue
            selected.append(row)
            owner_counts[owner] += 1
    selected.sort(key=lambda row: stable_hex("EXT_TEST_ORDER", row["state"]["state_id"]))

    qualification_cases: list[dict[str, Any]] = []
    physical_calls: list[dict[str, Any]] = []
    for row in selected:
        state = row["state"]
        candidate = row["candidate"]
        case_id = "rsmsext_" + stable_hex(state["state_id"])
        ms_evidence_id = "msev_" + stable_hex(state["state_id"], candidate["literal_text"])
        seed = 20260812 + int(stable_hex("SEED", case_id, length=8), 16) % 100000
        context = "\n".join(
            f"{str(turn['speaker']).upper()}: {str(turn['content']).strip()}"
            for turn in state["visible_current_session_dialogue"]
            if str(turn.get("content", "")).strip()
        )
        routed_ms_on = row["ms_decision"] == "ON"
        routed_rs_on = row["rs_decision"] == "ON"
        selected_card = row["rs_selected_card"]
        rs_evidence_id = ("rscard_" + selected_card["card_id"]) if selected_card else None
        routed_bits = {"MP": False, "MS": routed_ms_on, "ME": False, "RS": routed_rs_on}
        routed_action = compile_component_bits(routed_bits)
        baseline_action = "M0+R0"
        qualification_cases.append({
            "protocol": "pm-v1.5-paper1-rs-ms-evoemo-external-test-case-v1",
            "case_id": case_id,
            "state_id": state["state_id"],
            "runtime_owner_key": state["runtime_owner_key"],
            "split_group_key": state["split_group_key"],
            "ms_probability": row["ms_probability"],
            "ms_decision": row["ms_decision"],
            "rs_decision": row["rs_decision"],
            "rs_selected_card_id": selected_card["card_id"] if selected_card else None,
            "rs_selected_family": selected_card["strategy_family"] if selected_card else None,
            "rs_selected_score": row["rs_selected_score"],
            "consensus_label_private": row["consensus_label"],
            "routed_action_id": routed_action,
            "baseline_action_id": baseline_action,
            "current_context": context,
            "current_goal": CURRENT_GOAL,
            "ms_exact_source": candidate["literal_text"] if routed_ms_on else None,
            "ms_evidence_id": ms_evidence_id,
            "rs_prompt_guidance": selected_card["prompt_guidance"] if (routed_rs_on and selected_card) else None,
            "rs_support_move": selected_card["support_move"] if (routed_rs_on and selected_card) else None,
            "rs_when_not_to_use": selected_card["when_not_to_use"] if (routed_rs_on and selected_card) else None,
            "rs_evidence_id": rs_evidence_id,
            "seed": seed,
        })
        actions_to_call = (baseline_action, routed_action) if routed_action != baseline_action else (baseline_action,)
        for action in actions_to_call:
            is_routed_call = action == routed_action and action != baseline_action
            candidates: dict[str, V3Candidate | None] = {component: None for component in ("MP", "MS", "ME", "RS")}
            if is_routed_call and routed_ms_on:
                candidates["MS"] = V3Candidate(
                    component="MS",
                    evidence_id=ms_evidence_id,
                    meaning_cue=MS_MEANING_CUE,
                    exact_source=candidate["literal_text"],
                    owner_id=state["runtime_owner_key"],
                    time_status="STRICTLY_PAST_NOT_ASSUMED_CURRENT",
                    allowed_response_change=MS_ALLOWED_CHANGE,
                    forbidden_inference=MS_FORBIDDEN,
                    burden_units=1,
                )
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
                pair_relations={"MS-RS": "COMPLEMENTARY"} if is_routed_call and routed_ms_on and routed_rs_on else None,
            )
            messages = response_generation_messages_v3(
                current_context=context,
                current_goal=CURRENT_GOAL,
                plan=plan,
            )
            physical_calls.append({
                "protocol": "pm-v1.5-paper1-rs-ms-evoemo-external-test-call-v1",
                "physical_call_id": "rsmsextcall_" + stable_hex(case_id, action, seed),
                "case_id": case_id,
                "state_id": state["state_id"],
                "split_group_key": state["split_group_key"],
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
    cell_coverage = Counter((row["ms_decision"], row["rs_decision"]) for row in qualification_cases)
    checks = {
        "at_least_24_states_distinct_owners_bounded": len(qualification_cases) >= 24 and all(c <= MAX_PER_OWNER for c in Counter(row["runtime_owner_key"] for row in qualification_cases).values()),
        "every_state_has_a_baseline_call": all(any(row["is_baseline"] for row in calls) for calls in by_case.values()),
        "routed_call_present_only_when_action_differs_from_baseline": all(
            (case["routed_action_id"] != case["baseline_action_id"]) == any(row["is_routed"] for row in by_case[case["case_id"]])
            for case in qualification_cases
        ),
        "same_seed_within_state": all(len({row["seed"] for row in calls}) == 1 for calls in by_case.values()),
        "visible_context_ends_with_seeker": all(row["current_context"].splitlines()[-1].startswith("SEEKER:") for row in qualification_cases if row["current_context"].splitlines()),
        "v3_meaning_absorption_prompt_only": all("Literal mention and lexical overlap are not required" in text and "Use this exact prior-user statement" not in text for text in prompt_texts),
        "safe_nonuse_instruction_present": all("leave it unused and still produce a safe current-context-grounded reply" in text for text in prompt_texts),
        "no_one_memory_cap_and_global_16_actions_unchanged": len(all_sixteen_action_ids()) == 16,
        "ms_probability_never_provider_visible": all(str(round(c["ms_probability"], 6)) not in text for c in qualification_cases for text in prompt_texts),
        "rs_score_never_provider_visible": all((c["rs_selected_score"] is None or str(round(c["rs_selected_score"], 4)) not in text) for c in qualification_cases for text in prompt_texts),
        "response_schema_frozen": len({row["response_schema_sha256"] for row in physical_calls}) == 1,
        "no_api_calls": True,
        "no_pm_refit": True,
        "no_mp_or_me_training_work": True,
    }
    failed = [name for name, passed in checks.items() if not passed]

    run_identity = sha256_text(
        canonical_json({
            "stage": "paper1_rs_ms_evoemo_external_test_v1",
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
    already_approved_for_this_stage = (release_manifest.get("stage_approvals") or {}).get("paper1_rs_ms_evoemo_external_test_v1")
    if run_identity in consumed_identities:
        failed.append("run_identity_not_previously_consumed_or_pending")
    elif run_identity in (release_manifest.get("stage_approvals") or {}).values() and run_identity != already_approved_for_this_stage:
        failed.append("run_identity_not_previously_consumed_or_pending")

    if failed:
        raise RuntimeError(f"RS+MS EvoEmo external test preflight failed: {failed}; checks={checks}")

    OUT.mkdir(parents=True)
    cases_path = OUT / "qualification_cases_private.jsonl"
    calls_path = OUT / "physical_call_plan_private.jsonl"
    write_jsonl(cases_path, qualification_cases)
    write_jsonl(calls_path, physical_calls)
    report = {
        "protocol": "pm-v1.5-paper1-rs-ms-evoemo-external-test-preflight-v1",
        "status": "PASS_EXTERNAL_TEST_PROPOSAL_READY_HUMAN_APPROVAL_REQUIRED_BEFORE_ANY_API_CALL",
        "checks": checks,
        "sample": {
            "states": len(qualification_cases),
            "cell_coverage_ms_rs": {f"{a}|{b}": c for (a, b), c in cell_coverage.items()},
            "baseline_calls": sum(row["is_baseline"] for row in physical_calls),
            "routed_calls": sum(row["is_routed"] for row in physical_calls),
            "total_calls": len(physical_calls),
            "distinct_rs_cards_used": len({c["rs_selected_card_id"] for c in qualification_cases if c["rs_selected_card_id"]}),
        },
        "generator": {
            "config": "configs/paper1_rs_ms_evoemo_external_test_execution_v1.json",
            "model": "meta/llama-3.1-8b-instruct",
            "temperature": 0.7,
            "max_output_tokens": 512,
            "paired_seed_per_state": True,
            "planned_physical_calls": len(physical_calls),
            "maximum_transport_attempts_per_call": 2,
        },
        "measurement_plan": {
            "immediate": ["structured completion", "guard status", "no internal-label/scaffold leak", "no unauthorized evidence ID"],
            "paired_baseline_comparison": (
                "Every routed call has a same-state same-seed M0+R0 baseline call. This is "
                "still a mechanism/qualitative external test, not a formal blind quality/risk/"
                "function measurement -- that would need a follow-up blind pairwise judging "
                "step (234l pattern) before any quantified 'RS+MS helps' claim."
            ),
            "generator_claimed_used_evidence_is_not_function_gold": True,
        },
        "artifacts": {
            "cases": {"path": str(cases_path.relative_to(ROOT)), "sha256": sha256_file(cases_path)},
            "calls": {"path": str(calls_path.relative_to(ROOT)), "sha256": sha256_file(calls_path)},
        },
        "proposed_authorization": {
            "stage": "paper1_rs_ms_evoemo_external_test_v1",
            "run_identity": run_identity,
        },
        "source_hashes": {
            "authority": sha256_file(AUTHORITY),
            "bundle": sha256_file(BUNDLE),
            "ms_thresholds": sha256_file(MS_THRESHOLDS),
            "qualified_cards": sha256_file(QUALIFIED_CARDS),
            "response_program_v3": sha256_file(ROOT / "src/metacom_pm/v1_5_response_program_v3.py"),
            "component_general_v3": sha256_file(ROOT / "src/metacom_pm/v1_5_component_general_v3.py"),
            "rs_v4_card_retrieval": sha256_file(ROOT / "src/metacom_pm/v1_5_rs_v4_card_retrieval.py"),
        },
        "api_calls": 0,
        "pm_fits": 0,
        "live_execution_authorized_by_this_report": False,
        "next": "PROPOSE_RUN_IDENTITY_AND_COST_CAP_FOR_HUMAN_APPROVAL",
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
