#!/usr/bin/env python3
"""Materialize one outcome-blind EvoEmo external-corpus treatment stress test.

This is deliberately exploratory rather than formal external confirmation.
It selects one previously ungenerated state per EvoEmo owner from a frozen
opportunity-enriched slice (learned RS ON, learned MS ON, fixed-eligible MP),
then compiles five same-state/same-seed V4 arms: always-off, full, and one
full-minus-component arm for RS, MP, and MS.  No API call is made here.
"""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import sys
from typing import Any

import joblib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import canonical_json, read_json, read_jsonl, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402
from metacom_pm.text import dialogue_text  # noqa: E402
from metacom_pm.v1_5_component_general_v3 import V3Candidate, build_component_general_plan_v3  # noqa: E402
from metacom_pm.v1_5_mp_profile_delta_templates_v1 import mp_realization_template  # noqa: E402
from metacom_pm.v1_5_ms_pre_decision import ms_candidate_or_none  # noqa: E402
from metacom_pm.v1_5_ms_same_stack_feasibility import SameStackGeneratorOutput  # noqa: E402
from metacom_pm.v1_5_response_program_v4 import response_generation_messages_v4  # noqa: E402
from metacom_pm.v1_5_rs_v4_card_retrieval import retrieve as rs_retrieve  # noqa: E402
from metacom_pm.v1_5_strategy_rag_repair import repaired_observable_opportunity_flags  # noqa: E402
from metacom_pm.v1_5b_policy_runtime import compile_component_bits  # noqa: E402


DESIGN = ROOT / "data/pm_v1_5_contracts/paper1_external_treatment_stress_test_design_v1.json"
STATES = ROOT / "outputs/pm_v1_5_paper1_p1_public_surface/evoemo_states_unlabeled.jsonl"
CANDIDATES = ROOT / "outputs/pm_v1_5_paper1_p1_public_surface/evoemo_candidates_unlabeled.jsonl"
RANK1 = ROOT / "outputs/pm_v1_5_paper1_p1b_actual_rank1/actual_rank1_unlabeled.jsonl"
DIAGNOSTICS = ROOT / "outputs/pm_v1_5_paper1_v3_g3_candidate_surface_audit_20260811/candidate_surface_diagnostics_unlabeled.jsonl"
MS_MODEL = ROOT / "outputs/pm_v1_5_paper1_ms_source_annotated_consensus_full_fit_20260812/ms_source_annotated_suitability_model.joblib"
MS_THRESHOLDS = ROOT / "outputs/pm_v1_5_paper1_ms_outer_train_abstention_calibration_20260812/ms_head_abstention_thresholds.json"
RS_MODEL = ROOT / "outputs/pm_v1_5_same_bank_rs_opportunity_router_fit_v1/rs_opportunity_router.joblib"
RS_REPORT = ROOT / "outputs/pm_v1_5_same_bank_rs_opportunity_router_fit_v1/fit_report.json"
RS_CARDS = ROOT / "outputs/pm_v1_5_paper1_rs_strategy_card_llm_audit_qualified_bank_20260812/strategy_cards_v4_llm_audit_qualified_only.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_external_treatment_stress_test_preflight_20260813"

CURRENT_GOAL = "Respond supportively to the latest visible seeker turn. Advance its immediate emotional-support goal without inventing facts, overloading the reply, or assuming a past fact is still current."
SELECTION_SALT = "PAPER1_EXTERNAL_TREATMENT_STRESS_TEST_V1_OWNER_UNIQUE"
GENERATOR = "meta/llama-3.1-8b-instruct"
GENERATOR_USD_CAP = 0.0
TEMPERATURE = 0.2
MAX_OUTPUT_TOKENS = 400
SEED = 20260813

MS_MEANING_CUE = "Interpret the single strictly past user-owned source as a tentative continuity cue; do not treat it as current or quote it."
MS_ALLOWED_CHANGE = "Use the past fact only when it adds a specific, relevant, non-conflicting continuity cue; otherwise leave it unused."
MS_FORBIDDEN = "Do not copy the user's first-person wording, assume the past remains true, infer a trait or cause, or expose a memory record."


def stable_hex(*values: object, length: int = 24) -> str:
    return hashlib.sha256("\x1f".join(map(str, values)).encode()).hexdigest()[:length]


def consumed_generation_state_ids() -> tuple[set[str], list[str]]:
    """Exclude every state already sent to a generator in repository evidence.

    The filename classes intentionally target execution outputs, not candidate
    surfaces or manifests, so merely materializing a public state never makes
    it consumed.
    """

    patterns = (
        "**/*generator*results*.jsonl",
        "**/*generation*results*.jsonl",
        "**/*generation*outcomes*.jsonl",
        "**/*response*core*outcomes*.jsonl",
        "**/*response*raw*outcomes*.jsonl",
        "**/*generator_arm_results*.jsonl",
    )
    paths = sorted({path for pattern in patterns for path in (ROOT / "outputs").glob(pattern)})
    consumed: set[str] = set()
    used_paths: list[str] = []
    for path in paths:
        found = False
        for row in read_jsonl(path):
            state_id = row.get("state_id")
            if isinstance(state_id, str) and state_id.startswith("evo::"):
                consumed.add(state_id)
                found = True
        if found:
            used_paths.append(str(path.relative_to(ROOT)))
    return consumed, used_paths


def ms_feature_vector(row: dict[str, Any]) -> list[list[float]]:
    return [[
        float(row["selection_score"]),
        float(row["top1_top2_margin"]),
        math.log1p(int(row["candidate_age_sessions"])),
        math.log1p(int(row["candidate_word_count"])),
        math.log1p(int(row["strict_past_pool_count"])),
        float(bool(row["low_information_rank1"])),
        float(bool(row["exact_or_containment_current_echo"])),
    ]]


def bits(*, mp: bool, ms: bool, rs: bool) -> dict[str, bool]:
    return {"MP": mp, "MS": ms, "ME": False, "RS": rs}


def main() -> None:
    if OUT.exists():
        raise RuntimeError("external treatment stress-test preflight already exists; refusing overwrite")
    design = read_json(DESIGN)
    if design["status"] != "ACTIVE_ZERO_API_EXPLORATORY_DESIGN_NO_LIVE_EXECUTION_AUTHORITY":
        raise RuntimeError("external diagnostic design is not in zero-API proposal state")

    states = {row["state_id"]: row for row in read_jsonl(STATES)}
    candidates = {row["candidate_id"]: row for row in read_jsonl(CANDIDATES)}
    rank1_by_state: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in read_jsonl(RANK1):
        if row["dataset"] == "EvoEmo":
            rank1_by_state[row["state_id"]][row["component"]] = row
    diagnostics = {
        (row["state_id"], row["component"]): row
        for row in read_jsonl(DIAGNOSTICS)
    }
    ms_model = joblib.load(MS_MODEL)
    ms_thresholds = read_json(MS_THRESHOLDS)
    rs_model = joblib.load(RS_MODEL)
    rs_feature_names = read_json(RS_REPORT)["feature_names"]
    rs_cards = read_jsonl(RS_CARDS)
    if len(rs_cards) != 79:
        raise RuntimeError("frozen qualified RS card denominator drifted")

    consumed, consumed_paths = consumed_generation_state_ids()
    eligible_by_owner: dict[str, list[dict[str, Any]]] = defaultdict(list)
    exclusions: dict[str, int] = defaultdict(int)
    for state_id, state in states.items():
        if state_id in consumed:
            exclusions["previously_generated"] += 1
            continue
        ranked = rank1_by_state.get(state_id, {})
        mp_rank = ranked.get("MP")
        ms_rank = ranked.get("MS")
        if not mp_rank or not mp_rank.get("candidate_present"):
            exclusions["mp_candidate_absent"] += 1
            continue
        if not ms_rank or not ms_rank.get("candidate_present"):
            exclusions["ms_candidate_absent"] += 1
            continue
        ms_diag = diagnostics.get((state_id, "MS"))
        if ms_diag is None:
            exclusions["ms_diagnostic_absent"] += 1
            continue
        ms_probability = float(ms_model.predict_proba(ms_feature_vector(ms_diag))[0, 1])
        if ms_probability < float(ms_thresholds["on_min"]):
            exclusions["ms_not_learned_on"] += 1
            continue
        flags = repaired_observable_opportunity_flags(
            current_user_text=state["current_user_text"],
            visible_dialogue=state["visible_current_session_dialogue"],
        )
        rs_vector = [[int(bool(flags[name])) for name in rs_feature_names]]
        rs_probability = float(rs_model.predict_proba(rs_vector)[0, 1])
        if rs_probability < 0.5:
            exclusions["rs_not_learned_on"] += 1
            continue
        rs_retrieval = rs_retrieve(
            recent_dialogue=state["visible_current_session_dialogue"],
            qualified_cards=rs_cards,
        )
        if rs_retrieval.selected_card is None:
            exclusions["rs_card_absent"] += 1
            continue
        mp_candidate = candidates.get(mp_rank["actual_rank1_id"])
        ms_candidate = candidates.get(ms_rank["actual_rank1_id"])
        if mp_candidate is None or ms_candidate is None:
            exclusions["candidate_join_failure"] += 1
            continue
        owner = state["runtime_owner_key"]
        if mp_candidate["runtime_owner_key"] != owner or ms_candidate["runtime_owner_key"] != owner:
            exclusions["owner_failure"] += 1
            continue
        if not (int(mp_candidate["available_after_session_index"]) < int(state["source_session_index"])):
            exclusions["mp_time_failure"] += 1
            continue
        if not (int(ms_candidate["available_after_session_index"]) < int(state["source_session_index"])):
            exclusions["ms_time_failure"] += 1
            continue
        eligible_by_owner[owner].append({
            "state": state,
            "mp_rank": mp_rank,
            "mp_candidate": mp_candidate,
            "ms_rank": ms_rank,
            "ms_candidate": ms_candidate,
            "ms_probability": ms_probability,
            "rs_probability": rs_probability,
            "rs_card": rs_retrieval.selected_card,
            "rs_score": rs_retrieval.selected_score,
        })

    owners = sorted({state["runtime_owner_key"] for state in states.values()})
    missing_owners = [owner for owner in owners if not eligible_by_owner.get(owner)]
    if len(owners) != 18 or missing_owners:
        raise RuntimeError(f"need all 18 owners with an eligible ungenerated state; missing={missing_owners}")

    selected = []
    for owner in owners:
        bucket = sorted(
            eligible_by_owner[owner],
            key=lambda row: stable_hex(SELECTION_SALT, row["state"]["state_id"]),
        )
        selected.append(bucket[0])

    schema = SameStackGeneratorOutput.model_json_schema()
    cases: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    arm_bits = {
        "always_off": bits(mp=False, ms=False, rs=False),
        "full": bits(mp=True, ms=True, rs=True),
        "minus_RS": bits(mp=True, ms=True, rs=False),
        "minus_MP": bits(mp=False, ms=True, rs=True),
        "minus_MS": bits(mp=True, ms=False, rs=True),
    }
    for row in selected:
        state = row["state"]
        owner = state["runtime_owner_key"]
        state_id = state["state_id"]
        case_id = "extstress_" + stable_hex(state_id)
        mp_row = row["mp_candidate"]
        ms_row = row["ms_candidate"]
        mp_template = mp_realization_template(mp_row["profile_field"])
        mp_candidate = V3Candidate(
            component="MP",
            evidence_id=mp_row["candidate_id"],
            meaning_cue=mp_template.meaning_cue,
            exact_source=mp_row["literal_text"],
            owner_id=owner,
            time_status="STRICTLY_PAST",
            allowed_response_change=mp_template.allowed_response_change,
            forbidden_inference=mp_template.forbidden_inference,
        )
        ms_candidate = ms_candidate_or_none(
            pre_decision="USE",
            evidence_id=ms_row["candidate_id"],
            meaning_cue=MS_MEANING_CUE,
            exact_source=ms_row["literal_text"],
            owner_id=owner,
            allowed_response_change=MS_ALLOWED_CHANGE,
            forbidden_inference=MS_FORBIDDEN,
        )
        if ms_candidate is None:  # pragma: no cover - literal USE above.
            raise RuntimeError("MS learned-ON state unexpectedly compiled to None")
        card = row["rs_card"]
        rs_candidate = V3Candidate(
            component="RS",
            evidence_id=str(card["card_id"]),
            meaning_cue=f"strategy_family={card.get('strategy_family')}; {card.get('prompt_guidance', '')}",
            exact_source=str(card.get("retrieval_text") or card.get("support_move") or ""),
            owner_id=None,
            time_status="CURRENT_CARD",
            allowed_response_change="Add or sharpen one bounded strategy move only when it improves the present reply.",
            forbidden_inference=str(card.get("when_not_to_use") or "Do not replace current-turn grounding or the R0 foundation."),
        )
        candidate_map = {"MP": mp_candidate, "MS": ms_candidate, "ME": None, "RS": rs_candidate}
        context = dialogue_text(state["visible_current_session_dialogue"])
        seed = SEED + int(stable_hex("seed", state_id, length=8), 16) % 100000
        case = {
            "protocol": "pm-v1.5-paper1-external-treatment-stress-test-case-v1",
            "case_id": case_id,
            "state_id": state_id,
            "runtime_owner_key": owner,
            "split_group_key": state["split_group_key"],
            "selection": {
                "outcome_blind": True,
                "previously_generated": False,
                "learned_rs_probability": row["rs_probability"],
                "learned_ms_probability": row["ms_probability"],
                "mp_policy": "fixed_eligible_rank1",
            },
            "candidate_ids": {"MP": mp_row["candidate_id"], "MS": ms_row["candidate_id"], "RS": card["card_id"]},
            "mp_profile_field": mp_row["profile_field"],
            "authorized_sources_private": {"MP": mp_row["literal_text"], "MS": ms_row["literal_text"], "RS": rs_candidate.exact_source},
            "arms": list(arm_bits),
            "seed": seed,
        }
        cases.append(case)
        for arm, requested_bits in arm_bits.items():
            action_id = compile_component_bits(requested_bits)
            plan = build_component_general_plan_v3(
                requested_action_id=action_id,
                current_user_id=owner,
                candidates=candidate_map,
            )
            messages = response_generation_messages_v4(
                current_context=context,
                current_goal=CURRENT_GOAL,
                plan=plan,
            )
            calls.append({
                "protocol": "pm-v1.5-paper1-external-treatment-stress-test-call-v1",
                "physical_call_id": f"{case_id}::{arm}",
                "case_id": case_id,
                "state_id": state_id,
                "runtime_owner_key": owner,
                "arm": arm,
                "requested_action_id": action_id,
                "messages": messages,
                "messages_sha256": sha256_text(canonical_json(messages)),
                "response_schema": schema,
                "response_schema_sha256": sha256_text(canonical_json(schema)),
                "seed": seed,
                "temperature": TEMPERATURE,
                "max_output_tokens": MAX_OUTPUT_TOKENS,
                "generator": GENERATOR,
                "plan_accounting": {
                    "requested_action_id": plan.accounting.requested_action_id,
                    "structurally_eligible_action_id": plan.accounting.structurally_eligible_action_id,
                    "jointly_planned_action_id": plan.accounting.jointly_planned_action_id,
                },
            })

    checks = {
        "exact_18_states": len(cases) == 18,
        "one_state_per_owner": len({case["runtime_owner_key"] for case in cases}) == len(cases),
        "no_previously_generated_state": all(case["state_id"] not in consumed for case in cases),
        "exact_5_arms_per_state": len(calls) == 90 and all(sum(call["case_id"] == case["case_id"] for call in calls) == 5 for case in cases),
        "same_seed_within_state": all(len({call["seed"] for call in calls if call["case_id"] == case["case_id"]}) == 1 for case in cases),
        "all_requested_equal_structurally_eligible_and_jointly_planned": all(
            call["requested_action_id"] == call["plan_accounting"]["structurally_eligible_action_id"] == call["plan_accounting"]["jointly_planned_action_id"]
            for call in calls
        ),
        "all_full_arms_are_mp_ms_rs": all(call["requested_action_id"] == "MPMS+RS" for call in calls if call["arm"] == "full"),
        "full_context_used": all(len(states[case["state_id"]]["visible_current_session_dialogue"]) > 0 for case in cases),
        "zero_api_zero_fit": True,
    }
    if not all(checks.values()):
        raise RuntimeError(f"external treatment stress-test preflight checks failed: {checks}")

    identity_payload = {
        "protocol": "pm-v1.5-paper1-external-treatment-stress-test-run-identity-v1",
        "design_sha256": sha256_file(DESIGN),
        "case_ids": [case["case_id"] for case in cases],
        "call_ids": [call["physical_call_id"] for call in calls],
        "message_hashes": [call["messages_sha256"] for call in calls],
        "schema_sha256": sha256_text(canonical_json(schema)),
        "generator": GENERATOR,
        "temperature": TEMPERATURE,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
    }
    run_identity = sha256_text(canonical_json(identity_payload))

    OUT.mkdir(parents=True)
    cases_path = OUT / "cases_private.jsonl"
    calls_path = OUT / "call_plan_private.jsonl"
    write_jsonl(cases_path, cases)
    write_jsonl(calls_path, calls)
    report = {
        "protocol": "pm-v1.5-paper1-external-treatment-stress-test-preflight-v1",
        "status": "PASS_EXACT_18_OWNER_90_CALL_EXPLORATORY_PROPOSAL_HUMAN_APPROVAL_REQUIRED",
        "run_identity": run_identity,
        "scope_label": "development-informed external-corpus opportunity-enriched treatment diagnostic; not formal learned-PM confirmation",
        "states": len(cases),
        "owners": len({case["runtime_owner_key"] for case in cases}),
        "arms_per_state": list(arm_bits),
        "logical_generator_calls": len(calls),
        "maximum_physical_attempts": len(calls) * 2,
        "generator": GENERATOR,
        "estimated_generator_cost_usd": 0.0,
        "proposed_generator_usd_cap": GENERATOR_USD_CAP,
        "checks": checks,
        "selection": {
            "salt": SELECTION_SALT,
            "eligible_counts_by_owner": {owner: len(eligible_by_owner[owner]) for owner in owners},
            "exclusion_counts": dict(sorted(exclusions.items())),
            "consumed_generation_state_count": len(consumed),
            "consumed_generation_paths": consumed_paths,
            "response_or_judge_outcomes_read_for_selection": False,
        },
        "planned_judging_after_generation": {
            "quality_pairs": 72,
            "source_aware_absolute_risk_replies": 90,
            "secondary_function_subset": "6 frozen cases per component (18 calls total), selected before opening replies",
            "estimated_judge_cost_usd": 1.93,
            "proposed_judge_cap_usd": 2.4,
            "judge_execution_requires_separate_identity_and_explicit_approval": True,
        },
        "artifacts": {
            "design": {"path": str(DESIGN.relative_to(ROOT)), "sha256": sha256_file(DESIGN)},
            "cases": {"path": str(cases_path.relative_to(ROOT)), "sha256": sha256_file(cases_path)},
            "call_plan": {"path": str(calls_path.relative_to(ROOT)), "sha256": sha256_file(calls_path)},
        },
        "input_hashes": {
            str(path.relative_to(ROOT)): sha256_file(path)
            for path in (STATES, CANDIDATES, RANK1, DIAGNOSTICS, MS_MODEL, MS_THRESHOLDS, RS_MODEL, RS_REPORT, RS_CARDS)
        },
        "authorization": {"api_calls": 0, "generator_calls": 0, "judge_calls": 0, "fits": 0},
        "next": "Present this exact generator run identity and $0 cap for explicit approval; only then bind an execution phase and run the 90 calls.",
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
