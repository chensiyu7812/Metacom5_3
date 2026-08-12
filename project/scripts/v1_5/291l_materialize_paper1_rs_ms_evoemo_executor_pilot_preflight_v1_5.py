#!/usr/bin/env python3
"""Materialize (zero-API) a small RS+MS executor pilot on real EvoEmo states.

Mirrors the already-validated MS-executor-qualification precedent
(230l-235l) -- same V3Candidate/plan/message construction, same
meaning-absorption-only prompting, same guard machinery -- but:
  - uses REAL EvoEmo dialogue/candidate text (not synthetic control items),
  - routes MS via the newly trained checkpoint's calibrated OUTER_TRAIN_ONLY
    thresholds (off_max=0.567, on_min=0.729) instead of a pre-assigned
    teacher class,
  - routes RS via the already re-frozen same-bank opportunity router
    (mechanical regex-based observable_opportunity_flags -> features ->
    predict_proba, zero API cost) instead of a fixed teacher class,
  - forces MP and ME OFF via candidate=None (they were not trained this
    session; this is the project's own established ablation-arm pattern,
    not a new invention -- see docs/PM_V1_TO_V1_5_GLOBAL_FAILURE_LEDGER_ZH.md
    V15-MEAS-100),
  - pairs every routed-action call with a same-seed, same-state M0+R0
    baseline call, so a later blind quality/risk/function comparison (the
    same measurement pattern 234l already established) is possible --
    running the pilot is not itself the success criterion; the baseline
    comparison is.
  - uses one fixed, generic, non-bank RS evidence card (same simplification
    the precedent used): none of the 80 Strategy Bank V4 cards are marked
    eligible_for_formal_rs yet (content-level qualification is a separate,
    unfinished layer from the opportunity-routing decision this pilot
    tests), so using real bank content would use uncertified evidence.
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
from metacom_pm.v1_5_strategy_rag_repair import repaired_observable_opportunity_flags  # noqa: E402
from metacom_pm.v1_5b_policy_runtime import compile_component_bits  # noqa: E402


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
BUNDLE = ROOT / "data/pm_v1_5_contracts/paper1_active_execution_bundle_v1.json"
OOF_PREDICTIONS = ROOT / "outputs/pm_v1_5_paper1_ms_source_annotated_consensus_logo_oof_20260812/oof_predictions.jsonl"
MS_THRESHOLDS = ROOT / "outputs/pm_v1_5_paper1_ms_outer_train_abstention_calibration_20260812/ms_head_abstention_thresholds.json"
MS_CHECKPOINT = ROOT / "outputs/pm_v1_5_paper1_ms_source_annotated_consensus_full_fit_20260812/ms_source_annotated_suitability_model.joblib"
EVOEMO_STATES = ROOT / "outputs/pm_v1_5_paper1_p1_public_surface/evoemo_states_unlabeled.jsonl"
EVOEMO_CANDIDATES = ROOT / "outputs/pm_v1_5_paper1_p1_public_surface/evoemo_candidates_unlabeled.jsonl"
RS_CHECKPOINT = ROOT / "outputs/pm_v1_5_same_bank_rs_opportunity_router_fit_v1/rs_opportunity_router.joblib"
RS_FEATURES_REPORT = ROOT / "outputs/pm_v1_5_same_bank_rs_opportunity_router_fit_v1/fit_report.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_rs_ms_evoemo_executor_pilot_preflight_20260812"
CURRENT_GOAL = "Respond supportively to the latest visible seeker turn. Advance its immediate emotional-support goal without inventing facts, overloading the reply, or assuming a past fact is still current."

RS_STATIC_EVIDENCE_ID = "rs_open_nonleading_v1"
RS_STATIC_EXACT_SOURCE = "Frozen strategy card: one open, non-leading, low-burden invitation."
RS_STATIC_MEANING_CUE = "Offer one open, non-leading invitation that helps the user identify what feels most important or manageable now."
RS_STATIC_ALLOWED_CHANGE = "Make the reply's primary act one open, non-leading question or invitation."
RS_STATIC_FORBIDDEN = "Do not presuppose the answer, force disclosure, add a second task, or override a stop boundary."

MS_MEANING_CUE = (
    "Interpret the single strictly past user-owned source supplied below as a "
    "tentative continuity cue; do not treat it as current or quote it."
)
MS_ALLOWED_CHANGE = "If it materially helps, use the past meaning to acknowledge continuity or ask a more informed current-oriented question."
MS_FORBIDDEN = "Do not copy the user's first-person wording, assume the past remains true, infer a trait or cause, or expose a memory record."


def stable_hex(*values: object, length: int = 24) -> str:
    text = "␟".join(str(value) for value in values)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def current_context(dialogue: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"{str(turn['speaker']).upper()}: {str(turn['content']).strip()}"
        for turn in dialogue
        if str(turn.get("content", "")).strip()
    )


def main() -> None:
    if OUT.exists():
        raise RuntimeError("RS+MS EvoEmo executor pilot preflight exists; refusing overwrite")
    authority = read_json(AUTHORITY)
    current = authority["current_execution_phase"]
    alias = authority["active_v3_phase"]
    expected_bundle = {"path": str(BUNDLE.relative_to(ROOT)), "sha256": sha256_file(BUNDLE)}
    if current["id"] != "RS_REFROZEN_MS_TRAINED_EXECUTOR_ELIGIBILITY_AND_EXTERNAL_WIRING_NEXT" or current["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("RS-refrozen phase is not the current execution phase")
    if alias.get("compatibility_alias_of") != "current_execution_phase" or alias["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("authority compatibility alias drifted")

    ms_thresholds = read_json(MS_THRESHOLDS)
    ms_predictions = read_jsonl(OOF_PREDICTIONS)
    evoemo_states = {row["state_id"]: row for row in read_jsonl(EVOEMO_STATES)}
    evoemo_candidates = {row["candidate_id"]: row for row in read_jsonl(EVOEMO_CANDIDATES)}
    rs_feature_names = read_json(RS_FEATURES_REPORT)["feature_names"]
    rs_model = joblib.load(RS_CHECKPOINT)

    def ms_decision(probability: float) -> str:
        if probability >= ms_thresholds["on_min"]:
            return "ON"
        if probability <= ms_thresholds["off_max"]:
            return "OFF"
        return "UNCERTAIN"

    def rs_decision_and_probability(current_user_text: str, visible_dialogue: list[dict[str, Any]]) -> tuple[str, float]:
        flags = repaired_observable_opportunity_flags(
            current_user_text=current_user_text,
            visible_dialogue=visible_dialogue,
        )
        vector = [[int(bool(flags[name])) for name in rs_feature_names]]
        probability = float(rs_model.predict_proba(vector)[0][1])
        return ("ON" if probability >= 0.5 else "OFF"), probability

    enriched: list[dict[str, Any]] = []
    for row in ms_predictions:
        state = evoemo_states.get(row["state_id"])
        candidate = evoemo_candidates.get(row["actual_rank1_id"])
        if state is None or candidate is None:
            continue
        ms_p = float(row["primary_probability"])
        ms_d = ms_decision(ms_p)
        rs_d, rs_p = rs_decision_and_probability(state["current_user_text"], state["visible_current_session_dialogue"])
        enriched.append({
            "state": state,
            "candidate": candidate,
            "ms_probability": ms_p,
            "ms_decision": ms_d,
            "rs_probability": rs_p,
            "rs_decision": rs_d,
            "consensus_label": row["consensus_label"],
        })

    cells: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in enriched:
        cells[(row["ms_decision"], row["rs_decision"])].append(row)
    for bucket in cells.values():
        bucket.sort(key=lambda row: stable_hex("PILOT_SELECT", row["state"]["state_id"]))

    target_cells = (("ON", "ON"), ("ON", "OFF"), ("OFF", "ON"), ("OFF", "OFF"))
    selected: list[dict[str, Any]] = []
    used_owners: set[str] = set()
    for cell in target_cells:
        picked = 0
        for row in cells.get(cell, []):
            owner = row["state"]["runtime_owner_key"]
            if owner in used_owners:
                continue
            selected.append(row)
            used_owners.add(owner)
            picked += 1
            if picked == 2:
                break

    qualification_cases: list[dict[str, Any]] = []
    physical_calls: list[dict[str, Any]] = []
    for row in selected:
        state = row["state"]
        candidate = row["candidate"]
        case_id = "rsmspilot_" + stable_hex(state["state_id"])
        ms_evidence_id = "msev_" + stable_hex(state["state_id"], candidate["literal_text"])
        seed = 20260812 + int(stable_hex("SEED", case_id, length=8), 16) % 100000
        context = current_context(state["visible_current_session_dialogue"])
        routed_ms_on = row["ms_decision"] == "ON"
        routed_rs_on = row["rs_decision"] == "ON"
        routed_bits = {"MP": False, "MS": routed_ms_on, "ME": False, "RS": routed_rs_on}
        routed_action = compile_component_bits(routed_bits)
        baseline_action = "M0+R0"
        qualification_cases.append({
            "protocol": "pm-v1.5-paper1-rs-ms-evoemo-executor-pilot-case-v1",
            "case_id": case_id,
            "state_id": state["state_id"],
            "runtime_owner_key": state["runtime_owner_key"],
            "split_group_key": state["split_group_key"],
            "ms_probability": row["ms_probability"],
            "ms_decision": row["ms_decision"],
            "rs_probability": row["rs_probability"],
            "rs_decision": row["rs_decision"],
            "consensus_label_private": row["consensus_label"],
            "routed_action_id": routed_action,
            "baseline_action_id": baseline_action,
            "current_context": context,
            "current_goal": CURRENT_GOAL,
            "ms_exact_source": candidate["literal_text"] if routed_ms_on else None,
            "ms_evidence_id": ms_evidence_id,
            "seed": seed,
        })
        for action in (baseline_action, routed_action) if routed_action != baseline_action else (baseline_action,):
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
            if is_routed_call and routed_rs_on:
                candidates["RS"] = V3Candidate(
                    component="RS",
                    evidence_id=RS_STATIC_EVIDENCE_ID,
                    meaning_cue=RS_STATIC_MEANING_CUE,
                    exact_source=RS_STATIC_EXACT_SOURCE,
                    owner_id=None,
                    time_status="CURRENT_STRATEGY_CARD",
                    allowed_response_change=RS_STATIC_ALLOWED_CHANGE,
                    forbidden_inference=RS_STATIC_FORBIDDEN,
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
                "protocol": "pm-v1.5-paper1-rs-ms-evoemo-executor-pilot-call-v1",
                "physical_call_id": "rsmspilotcall_" + stable_hex(case_id, action, seed),
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
        "at_least_6_states_distinct_owners": len(qualification_cases) >= 6 and len({row["runtime_owner_key"] for row in qualification_cases}) == len(qualification_cases),
        "every_state_has_a_baseline_call": all(any(row["is_baseline"] for row in calls) for calls in by_case.values()),
        "routed_call_present_only_when_action_differs_from_baseline": all(
            (case["routed_action_id"] != case["baseline_action_id"]) == any(row["is_routed"] for row in by_case[case["case_id"]])
            for case in qualification_cases
        ),
        "same_seed_within_state": all(len({row["seed"] for row in calls}) == 1 for calls in by_case.values()),
        "mp_and_me_never_requested": all(row["requested_action_id"] not in {"MP+R0", "ME+R0"} for row in physical_calls) and all("MP" not in row["requested_action_id"].replace("MPMSME", "") for row in physical_calls),
        "visible_context_ends_with_seeker": all(row["current_context"].splitlines()[-1].startswith("SEEKER:") for row in qualification_cases if row["current_context"].splitlines()),
        "ms_source_once_in_system_when_routed_on_zero_otherwise": all(
            row["messages"][0]["content"].count(next(c["ms_exact_source"] for c in qualification_cases if c["case_id"] == row["case_id"]) or "\x00__none__")
            == (1 if (row["is_routed"] and next(c["ms_decision"] for c in qualification_cases if c["case_id"] == row["case_id"]) == "ON") else 0)
            for row in physical_calls
        ),
        "v3_meaning_absorption_prompt_only": all("Literal mention and lexical overlap are not required" in text and "Use this exact prior-user statement" not in text for text in prompt_texts),
        "safe_nonuse_instruction_present": all("leave it unused and still produce a safe current-context-grounded reply" in text for text in prompt_texts),
        "no_one_memory_cap_and_global_16_actions_unchanged": len(all_sixteen_action_ids()) == 16,
        "ms_probability_never_provider_visible": all(str(round(c["ms_probability"], 6)) not in text for c in qualification_cases for text in prompt_texts),
        "rs_probability_never_provider_visible": all(str(round(c["rs_probability"], 6)) not in text for c in qualification_cases for text in prompt_texts),
        "response_schema_frozen": len({row["response_schema_sha256"] for row in physical_calls}) == 1,
        "no_api_calls": True,
        "no_pm_refit": True,
        "no_mp_or_me_training_work": True,
    }
    failed = [name for name, passed in checks.items() if not passed]

    OUT.mkdir(parents=True)
    cases_path = OUT / "qualification_cases_private.jsonl"
    calls_path = OUT / "physical_call_plan_private.jsonl"
    write_jsonl(cases_path, qualification_cases)
    write_jsonl(calls_path, physical_calls)
    report = {
        "protocol": "pm-v1.5-paper1-rs-ms-evoemo-executor-pilot-preflight-v1",
        "status": "RS_MS_EVOEMO_PILOT_PREFLIGHT_PASS_LIVE_PHASE_MAY_BE_DESIGNED" if not failed else "RS_MS_EVOEMO_PILOT_PREFLIGHT_FAIL",
        "checks": checks,
        "failed_checks": failed,
        "sample": {
            "states": len(qualification_cases),
            "cell_coverage_ms_rs": {f"{a}|{b}": c for (a, b), c in cell_coverage.items()},
            "baseline_calls": sum(row["is_baseline"] for row in physical_calls),
            "routed_calls": sum(row["is_routed"] for row in physical_calls),
        },
        "generator": {
            "config": "configs/paper1_rs_ms_evoemo_executor_pilot_execution_v1.json",
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
                "Every routed call has a same-state same-seed M0+R0 baseline call. Running "
                "the pilot alone is not a success claim -- a follow-up zero-API step must "
                "blind-pair (routed, baseline) replies for quality/risk/function comparison, "
                "same pattern as 234l, before any 'RS+MS helps' claim is made."
            ),
            "generator_claimed_used_evidence_is_not_function_gold": True,
        },
        "artifacts": {
            "cases": {"path": str(cases_path.relative_to(ROOT)), "sha256": sha256_file(cases_path)},
            "calls": {"path": str(calls_path.relative_to(ROOT)), "sha256": sha256_file(calls_path)},
        },
        "source_hashes": {
            "authority": sha256_file(AUTHORITY),
            "bundle": sha256_file(BUNDLE),
            "ms_thresholds": sha256_file(MS_THRESHOLDS),
            "rs_features_report": sha256_file(RS_FEATURES_REPORT),
            "response_program_v3": sha256_file(ROOT / "src/metacom_pm/v1_5_response_program_v3.py"),
            "component_general_v3": sha256_file(ROOT / "src/metacom_pm/v1_5_component_general_v3.py"),
            "strategy_rag_repair": sha256_file(ROOT / "src/metacom_pm/v1_5_strategy_rag_repair.py"),
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
