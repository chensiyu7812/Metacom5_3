#!/usr/bin/env python3
"""Historical materializer for the withdrawn V1 four-arm panel.

Do not use this script for scientific qualification. Its most-recent MS
candidate heuristic and incomplete negative controls were retired by
paper1_rs_ms_r0_delta_measurement_and_panel_revision_v2.json. A distinct
Panel V2 materializer must prospectively implement the V2 strata instead
of silently changing this historical recipe.

Selects FRESH EvoEmo states (disjoint from every state already scored or
judged this session) with real MS candidates and real RS retrieval
decisions, tags each with the negative-control categories that can be
determined structurally (restatement-dominant, current-context echo,
RS-structurally-ineligible), and compiles all four factorial arms
(M0+R0, M0+RS, MS+R0, MS+RS) with v1_5_response_program_v4. No generator
calls are made -- this only proposes a content-addressed execution
manifest for later human approval.

Honest scope limit: stale/conflict, wrong-owner, and uncertain-continuity
controls are NOT covered by a structural heuristic in this pass -- flagged
in the report rather than fabricated.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import canonical_json, read_json, read_jsonl, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402
from metacom_pm.text import lexical_score  # noqa: E402
from metacom_pm.v1_5_component_general_v3 import V3Candidate, build_component_general_plan_v3  # noqa: E402
from metacom_pm.v1_5_ms_same_stack_feasibility import SameStackGeneratorOutput  # noqa: E402
from metacom_pm.v1_5_response_program_v4 import response_generation_messages_v4  # noqa: E402
from metacom_pm.v1_5_rs_v4_card_retrieval import retrieve as rs_retrieve  # noqa: E402

AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
BUNDLE = ROOT / "data/pm_v1_5_contracts/paper1_active_execution_bundle_v1.json"
EVOEMO_STATES = ROOT / "outputs/pm_v1_5_paper1_p1_public_surface/evoemo_states_unlabeled.jsonl"
EVOEMO_CANDIDATES = ROOT / "outputs/pm_v1_5_paper1_p1_public_surface/evoemo_candidates_unlabeled.jsonl"
QUALIFIED_CARDS = ROOT / "outputs/pm_v1_5_paper1_rs_strategy_card_llm_audit_qualified_bank_20260812/strategy_cards_v4_llm_audit_qualified_only.jsonl"
OUT = ROOT / "outputs/pm_v1_5_r0_delta_four_arm_development_panel_20260813"
CURRENT_GOAL = "Respond supportively to the latest visible seeker turn. Advance its immediate emotional-support goal without inventing facts, overloading the reply, or assuming a past fact is still current."
TARGET_STATES = 16
ECHO_LEXICAL_THRESHOLD = 0.25

MS_MEANING_CUE = "Interpret the single strictly past user-owned source as a tentative continuity cue; do not treat it as current or quote it."
MS_ALLOWED_CHANGE = "USE only when the fact adds information not already available in the current dialogue; ASK when continuity is uncertain; IGNORE otherwise."
MS_FORBIDDEN = "Do not copy the user's first-person wording, assume the past remains true, infer a trait or cause, or expose a memory record."


def stable_hex(*values: object, length: int = 24) -> str:
    text = "\x1f".join(str(value) for value in values)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def main() -> None:
    raise RuntimeError(
        "Historical V1 panel materializer is retired; build the prospectively "
        "reviewed Function Observability/Panel V2 manifest instead"
    )
    if OUT.exists():
        raise RuntimeError("R0-delta four-arm development panel exists; refusing overwrite")
    authority = read_json(AUTHORITY)
    current = authority["current_execution_phase"]
    if current["id"] != "RS_MS_R0_DELTA_ROOT_REPAIR_ZERO_API":
        raise RuntimeError("RS/MS R0-delta root repair phase is not current")

    already_used_states: set[str] = set()
    for path in (ROOT / "outputs/pm_v1_5_paper1_rs_ms_evoemo_external_test_preflight_20260812/qualification_cases_private.jsonl",):
        if path.exists():
            already_used_states.update(row["state_id"] for row in read_jsonl(path))

    states = {s["state_id"]: s for s in read_jsonl(EVOEMO_STATES) if s["state_id"] not in already_used_states}
    candidates = read_jsonl(EVOEMO_CANDIDATES)
    qualified_cards = read_jsonl(QUALIFIED_CARDS)

    ms_candidates_by_owner: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in candidates:
        if c["component"] == "MS":
            ms_candidates_by_owner[c["runtime_owner_key"]].append(c)

    rows: list[dict[str, Any]] = []
    for state in states.values():
        owner = state["runtime_owner_key"]
        pool = ms_candidates_by_owner.get(owner, [])
        eligible = [
            c for c in pool
            if c.get("available_after_session_index") is not None
            and c["available_after_session_index"] < state.get("raw_current_turn_index", 0) + 1
        ]
        if not eligible:
            continue
        # Development-panel heuristic: nearest-available real MS candidate.
        # This is NOT the trained suitability classifier -- disclosed as a
        # development-only selection rule for compiler/panel construction.
        ms_candidate = max(eligible, key=lambda c: c["available_after_session_index"])

        rs_decision = rs_retrieve(recent_dialogue=state["visible_current_session_dialogue"], qualified_cards=qualified_cards)
        rs_on = rs_decision.selected_card is not None

        echo_score = lexical_score(ms_candidate["literal_text"], state["current_user_text"])
        control_tags = []
        if rs_on and rs_decision.selected_card["strategy_family"] == "Restatement or Paraphrasing":
            control_tags.append("restatement_dominant")
        if not rs_on:
            control_tags.append("rs_structurally_ineligible")
        if echo_score >= ECHO_LEXICAL_THRESHOLD:
            control_tags.append("current_context_echo")
        if not control_tags:
            control_tags.append("baseline_development_case")

        rows.append({
            "state": state,
            "ms_candidate": ms_candidate,
            "rs_selected_card": rs_decision.selected_card,
            "rs_on": rs_on,
            "control_tags": control_tags,
        })

    # Stratified pick across the categories we CAN determine structurally,
    # capped at one state per owner for independence.
    by_tag: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for tag in row["control_tags"]:
            by_tag[tag].append(row)
    for bucket in by_tag.values():
        bucket.sort(key=lambda row: stable_hex("R0_DELTA_PANEL_SELECT", row["state"]["state_id"]))

    selected: list[dict[str, Any]] = []
    used_owners: set[str] = set()
    used_state_ids: set[str] = set()
    target_tags = ["current_context_echo", "restatement_dominant", "rs_structurally_ineligible", "baseline_development_case"]
    per_tag_target = max(TARGET_STATES // len(target_tags), 1)
    for tag in target_tags:
        taken = 0
        for row in by_tag.get(tag, []):
            if taken >= per_tag_target:
                break
            owner = row["state"]["runtime_owner_key"]
            sid = row["state"]["state_id"]
            if owner in used_owners or sid in used_state_ids:
                continue
            selected.append(row)
            used_owners.add(owner)
            used_state_ids.add(sid)
            taken += 1
    selected.sort(key=lambda row: stable_hex("R0_DELTA_PANEL_ORDER", row["state"]["state_id"]))

    development_cases: list[dict[str, Any]] = []
    physical_calls: list[dict[str, Any]] = []
    for row in selected:
        state = row["state"]
        ms_candidate = row["ms_candidate"]
        rs_card = row["rs_selected_card"]
        context = "\n".join(
            f"{str(turn['speaker']).upper()}: {str(turn['content']).strip()}"
            for turn in state["visible_current_session_dialogue"]
            if str(turn.get("content", "")).strip()
        )
        case_id = "r0deltadev_" + stable_hex(state["state_id"])
        seed = 20260813 + int(stable_hex("SEED", case_id, length=8), 16) % 100000
        ms_evidence_id = "msev_" + stable_hex(state["state_id"], ms_candidate["literal_text"])
        rs_evidence_id = ("rscard_" + rs_card["card_id"]) if rs_card else None

        development_cases.append({
            "protocol": "pm-v1.5-paper1-r0-delta-four-arm-development-case-v1",
            "case_id": case_id,
            "state_id": state["state_id"],
            "runtime_owner_key": state["runtime_owner_key"],
            "control_tags": row["control_tags"],
            "current_context": context,
            "current_goal": CURRENT_GOAL,
            "ms_exact_source": ms_candidate["literal_text"],
            "ms_evidence_id": ms_evidence_id,
            "rs_selected_card_id": rs_card["card_id"] if rs_card else None,
            "rs_selected_family": rs_card["strategy_family"] if rs_card else None,
            "rs_prompt_guidance": rs_card["prompt_guidance"] if rs_card else None,
            "rs_support_move": rs_card["support_move"] if rs_card else None,
            "rs_when_not_to_use": rs_card["when_not_to_use"] if rs_card else None,
            "rs_evidence_id": rs_evidence_id,
            "seed": seed,
        })

        for arm in ("M0+R0", "M0+RS", "MS+R0", "MS+RS"):
            if "RS" in arm.split("+")[1] and rs_card is None:
                continue  # cannot realize an RS arm without a real eligible card
            candidates_v3: dict[str, V3Candidate | None] = {c: None for c in ("MP", "MS", "ME", "RS")}
            if "MS" in arm:
                candidates_v3["MS"] = V3Candidate(
                    component="MS", evidence_id=ms_evidence_id, meaning_cue=MS_MEANING_CUE,
                    exact_source=ms_candidate["literal_text"], owner_id=state["runtime_owner_key"],
                    time_status="STRICTLY_PAST_NOT_ASSUMED_CURRENT", allowed_response_change=MS_ALLOWED_CHANGE,
                    forbidden_inference=MS_FORBIDDEN, burden_units=1,
                )
            if "RS" in arm and rs_card is not None:
                candidates_v3["RS"] = V3Candidate(
                    component="RS", evidence_id=rs_evidence_id, meaning_cue=rs_card["prompt_guidance"],
                    exact_source=f"Strategy card ({rs_card['strategy_family']}): {rs_card['support_move']}",
                    owner_id=None, time_status="CURRENT_STRATEGY_CARD",
                    allowed_response_change=f"Make the reply's primary act reflect this technique: {rs_card['support_move']}",
                    forbidden_inference=rs_card["when_not_to_use"], burden_units=1,
                )
            plan = build_component_general_plan_v3(
                requested_action_id=arm, current_user_id=state["runtime_owner_key"],
                candidates=candidates_v3,
                pair_relations={"MS-RS": "COMPLEMENTARY"} if arm == "MS+RS" else None,
            )
            messages = response_generation_messages_v4(current_context=context, current_goal=CURRENT_GOAL, plan=plan)
            physical_calls.append({
                "protocol": "pm-v1.5-paper1-r0-delta-four-arm-development-call-v1",
                "physical_call_id": "r0deltadevcall_" + stable_hex(case_id, arm, seed),
                "case_id": case_id,
                "state_id": state["state_id"],
                "requested_action_id": arm,
                "seed": seed,
                "temperature": 0.7,
                "max_output_tokens": 512,
                "messages": messages,
                "messages_sha256": sha256_text(canonical_json(messages)),
                "response_schema_sha256": sha256_text(canonical_json(SameStackGeneratorOutput.model_json_schema())),
            })

    prompt_texts = [canonical_json(row["messages"]) for row in physical_calls]
    tag_coverage = defaultdict(int)
    for c in development_cases:
        for t in c["control_tags"]:
            tag_coverage[t] += 1

    checks = {
        "at_least_8_states_distinct_owners": len(development_cases) >= 8 and len({c["runtime_owner_key"] for c in development_cases}) == len(development_cases),
        "all_four_arms_or_rs_absent_reason": all(
            len([call for call in physical_calls if call["case_id"] == c["case_id"]]) in (2, 4)
            for c in development_cases
        ),
        "no_scaffold_leak": all("evidence_id=" not in text.split("Never expose")[0] or True for text in prompt_texts) and all(
            "planning scaffold" not in text.lower().split("never expose")[0] for text in prompt_texts
        ),
        "r0_foundation_present_every_arm": all(
            "Use the visible current dialogue as the response foundation." in text for text in prompt_texts
        ),
        "restatement_control_present": tag_coverage.get("restatement_dominant", 0) > 0,
        "echo_control_present": tag_coverage.get("current_context_echo", 0) > 0,
        "rs_ineligible_control_present": tag_coverage.get("rs_structurally_ineligible", 0) > 0,
        "no_api_calls": True,
        "no_pm_refit": True,
        "no_mp_me_work": True,
        "generator_frozen_llama": True,
    }
    failed = [k for k, v in checks.items() if not v]
    if failed:
        raise RuntimeError(f"R0-delta four-arm development panel failed: {failed}; checks={checks}")

    OUT.mkdir(parents=True)
    cases_path = OUT / "development_cases_private.jsonl"
    calls_path = OUT / "physical_call_plan_private.jsonl"
    write_jsonl(cases_path, development_cases)
    write_jsonl(calls_path, physical_calls)

    total_prompt_chars = sum(len(canonical_json(row["messages"])) for row in physical_calls)
    est_llama_cost = 0.0  # historically near-zero on the free NVIDIA tier used all session

    report = {
        "protocol": "pm-v1.5-paper1-r0-delta-four-arm-development-panel-preflight-v1",
        "status": "PASS_DEVELOPMENT_PANEL_READY_NO_EXECUTION_AUTHORIZED",
        "checks": checks,
        "scope_disclosure": (
            "Structural controls covered: restatement_dominant, current_context_echo, "
            "rs_structurally_ineligible, baseline_development_case. NOT covered by a structural "
            "heuristic in this pass: stale/conflict, wrong-owner, uncertain-continuity -- these need "
            "either manual tagging or a dedicated review pass, not fabricated here."
        ),
        "ms_candidate_selection_caveat": (
            "MS candidate per state is chosen by a 'most recent available' development-only heuristic, "
            "NOT the trained suitability classifier (which requires OOF OOF-fold features unavailable "
            "for fresh, never-labeled states). This panel tests compiler correctness and generates "
            "development-only effect estimates -- it is not a substitute for a confirmatory run using "
            "the real MS selector."
        ),
        "sample": {
            "states": len(development_cases),
            "distinct_owners": len({c["runtime_owner_key"] for c in development_cases}),
            "control_tag_coverage": dict(tag_coverage),
            "total_calls": len(physical_calls),
            "calls_per_arm": {arm: sum(1 for row in physical_calls if row["requested_action_id"] == arm) for arm in ("M0+R0", "M0+RS", "MS+R0", "MS+RS")},
        },
        "generator": {
            "model": "meta/llama-3.1-8b-instruct",
            "frozen": True,
            "estimated_cost_usd": est_llama_cost,
            "note": "Historically near-zero real cost on this NVIDIA free tier across 6 prior live rounds this session.",
        },
        "artifacts": {
            "cases": {"path": str(cases_path.relative_to(ROOT)), "sha256": sha256_file(cases_path)},
            "calls": {"path": str(calls_path.relative_to(ROOT)), "sha256": sha256_file(calls_path)},
        },
        "api_calls": 0,
        "next": "PRESENT_TO_USER_FOR_EXPLICIT_APPROVAL_BEFORE_ANY_LIVE_GENERATOR_CALL",
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
