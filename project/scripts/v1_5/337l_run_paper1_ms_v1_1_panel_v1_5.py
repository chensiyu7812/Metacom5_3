#!/usr/bin/env python3
"""Execute the exact hash-bound 30-call MS Panel V1.1 (336l output)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.api import RetryableProviderError, make_client  # noqa: E402
from metacom_pm.config import endpoint_from_config, load_config  # noqa: E402
from metacom_pm.io import canonical_json, read_json, read_jsonl, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402
from metacom_pm.paid_run_release import require_paid_run_release  # noqa: E402
from metacom_pm.text import dialogue_text  # noqa: E402
from metacom_pm.v1_5_component_general_v3 import V3Candidate, build_component_general_plan_v3  # noqa: E402
from metacom_pm.v1_5_ms_pre_decision import ms_candidate_or_none  # noqa: E402
from metacom_pm.v1_5_ms_same_stack_feasibility import SameStackGeneratorOutput  # noqa: E402
from metacom_pm.v1_5_response_program_v4 import response_generation_messages_v4  # noqa: E402
from metacom_pm.v1_5_rs_v4_card_retrieval import retrieve as rs_retrieve  # noqa: E402

PROTOCOL = "pm-v1.5-paper1-ms-v1-1-panel-live-v1"
STAGE = "paper1_ms_v1_1_panel_v1"
STAGE_ID = "MS_V1_1_PANEL_EXECUTION"
AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
BUNDLE = ROOT / "data/pm_v1_5_contracts/paper1_active_execution_bundle_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_ms_v1_1_panel_execution_phase_v1.json"
CONFIG = ROOT / "configs/paper1_ms_v1_1_panel_execution_v1.json"
CASES = ROOT / "outputs/pm_v1_5_paper1_ms_v1_1_panel_20260813/development_cases_private.jsonl"
EVOEMO_STATES = ROOT / "outputs/pm_v1_5_paper1_p1_public_surface/evoemo_states_unlabeled.jsonl"
EVOEMO_CANDIDATES = ROOT / "outputs/pm_v1_5_paper1_p1_public_surface/evoemo_candidates_unlabeled.jsonl"
QUALIFIED_CARDS = ROOT / "outputs/pm_v1_5_paper1_rs_strategy_card_llm_audit_qualified_bank_20260812/strategy_cards_v4_llm_audit_qualified_only.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_ms_v1_1_panel_live_20260813"
CURRENT_GOAL = "Respond supportively to the latest visible seeker turn. Advance its immediate emotional-support goal without inventing facts, overloading the reply, or assuming a past fact is still current."
USD_CAP = 0.0

MS_MEANING_CUE = "Interpret the single strictly past user-owned source as a tentative continuity cue; do not treat it as current or quote it."
MS_ALLOWED_CHANGE = "USE only when the fact adds information not already available in the current dialogue; ASK when continuity is uncertain; IGNORE otherwise."
MS_FORBIDDEN = "Do not copy the user's first-person wording, assume the past remains true, infer a trait or cause, or expose a memory record."


def require_authority() -> dict[str, Any]:
    authority = read_json(AUTHORITY)
    bundle = read_json(BUNDLE)
    current = authority["current_execution_phase"]
    expected_bundle = {"path": str(BUNDLE.relative_to(ROOT)), "sha256": sha256_file(BUNDLE)}
    if current["id"] != STAGE_ID or current["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("MS V1.1 panel execution is not current")
    if bundle["current_phase"]["id"] != STAGE_ID:
        raise RuntimeError("bundle does not point at this execution phase")
    phase = read_json(PHASE)
    for binding in phase["input_bindings"] + phase["implementation_bindings"]:
        if sha256_file(ROOT / binding["path"]) != binding["sha256"]:
            raise RuntimeError(f"bound input drifted: {binding['role']}")
    return phase


def rebuild_calls(cases, states_by_id, ms_candidates, qualified_cards):
    calls = []
    for case in cases:
        state = states_by_id[case["state_id"]]
        owner = case["runtime_owner_key"]
        full_context = dialogue_text(state["visible_current_session_dialogue"])
        ms_row = ms_candidates.get(case.get("ms_exact_source_id"))
        ms_row = None
        for row in ms_candidates.values():
            if row["runtime_owner_key"] == owner and row["literal_text"] == case["ms_exact_source"]:
                ms_row = row
                break
        ms_candidate = None
        if ms_row is not None:
            ms_candidate = ms_candidate_or_none(
                pre_decision=case["pre_decision"], evidence_id=ms_row["candidate_id"],
                meaning_cue=MS_MEANING_CUE, exact_source=ms_row["literal_text"], owner_id=owner,
                allowed_response_change=MS_ALLOWED_CHANGE, forbidden_inference=MS_FORBIDDEN,
            )
        rs_decision = rs_retrieve(recent_dialogue=state["visible_current_session_dialogue"], qualified_cards=qualified_cards)
        rs_candidate = None
        if rs_decision.status == "retrieved_top1":
            card = rs_decision.selected_card
            rs_candidate = V3Candidate(
                component="RS", evidence_id=str(card["card_id"]), meaning_cue=f"strategy_family={card.get('strategy_family')}",
                exact_source=str(card.get("retrieval_text", "")), owner_id=None, time_status="CURRENT_CARD",
                allowed_response_change="Add or sharpen one bounded strategy move only when it improves the present reply.",
                forbidden_inference="Do not let the card replace current-turn grounding or the R0 foundation.",
            )

        arms: dict[str, list[dict[str, str]]] = {}
        m0_plan = build_component_general_plan_v3(requested_action_id="M0+R0", current_user_id=owner, candidates={"MP": None, "MS": None, "ME": None, "RS": None})
        arms["M0+R0"] = response_generation_messages_v4(current_context=full_context, current_goal=CURRENT_GOAL, plan=m0_plan)
        if ms_candidate is not None:
            ms_plan = build_component_general_plan_v3(requested_action_id="MS+R0", current_user_id=owner, candidates={"MP": None, "MS": ms_candidate, "ME": None, "RS": None})
            arms["MS+R0"] = response_generation_messages_v4(current_context=full_context, current_goal=CURRENT_GOAL, plan=ms_plan)
        if rs_candidate is not None:
            rs_plan = build_component_general_plan_v3(requested_action_id="M0+RS", current_user_id=owner, candidates={"MP": None, "MS": None, "ME": None, "RS": rs_candidate})
            arms["M0+RS"] = response_generation_messages_v4(current_context=full_context, current_goal=CURRENT_GOAL, plan=rs_plan)
            if ms_candidate is not None:
                joint_plan = build_component_general_plan_v3(requested_action_id="MS+RS", current_user_id=owner, candidates={"MP": None, "MS": ms_candidate, "ME": None, "RS": rs_candidate})
                arms["MS+RS"] = response_generation_messages_v4(current_context=full_context, current_goal=CURRENT_GOAL, plan=joint_plan)

        for arm_name, messages in arms.items():
            if arm_name not in case["arms_present"]:
                continue
            calls.append({
                "physical_call_id": f"{case['case_id']}::{arm_name}", "case_id": case["case_id"],
                "state_id": case["state_id"], "arm": arm_name, "messages": messages,
                "messages_sha256": sha256_text(canonical_json(messages)),
                "temperature": 0.2, "max_output_tokens": 400, "seed": 7,
            })
    return calls


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--run-identity")
    parser.add_argument("--accept-usd-cap", type=float)
    args = parser.parse_args()
    phase = require_authority()

    cases = read_jsonl(CASES)
    states_by_id = {row["state_id"]: row for row in read_jsonl(EVOEMO_STATES)}
    ms_candidates = {row["candidate_id"]: row for row in read_jsonl(EVOEMO_CANDIDATES) if row["component"] == "MS"}
    qualified_cards = read_jsonl(QUALIFIED_CARDS)
    calls = rebuild_calls(cases, states_by_id, ms_candidates, qualified_cards)
    if len(calls) != 30:
        raise RuntimeError(f"exact 30-call plan required, got {len(calls)}")

    dry = {"protocol": PROTOCOL, "status": "LIVE_READY_EXACT_30_MS_V1_1_CALLS", "logical_calls": len(calls),
           "absolute_usd_cap": USD_CAP, "run_identity": phase["execution"]["run_identity"], "api_calls": 0}
    print(json.dumps(dry, ensure_ascii=False, indent=2), flush=True)
    if not args.live:
        return
    if args.run_identity != phase["execution"]["run_identity"]:
        raise RuntimeError("run identity does not match live phase")
    if args.accept_usd_cap != USD_CAP:
        raise RuntimeError(f"must accept exact frozen cap {USD_CAP:g}")
    require_paid_run_release(read_json(CONFIG), config_path=CONFIG, stage=STAGE, run=True, run_identity=args.run_identity)

    OUT.mkdir(parents=True, exist_ok=True)
    completed = {row["physical_call_id"]: row for row in read_jsonl(OUT / "generator_results_private.jsonl")} if (OUT / "generator_results_private.jsonl").exists() else {}
    raw_records = {row["physical_call_id"]: row for row in read_jsonl(OUT / "raw_provider_attempts_before_guard.jsonl")} if (OUT / "raw_provider_attempts_before_guard.jsonl").exists() else {}
    config = load_config(CONFIG)
    client = make_client(endpoint_from_config(config, "generator"))
    for call in sorted(calls, key=lambda row: row["physical_call_id"]):
        if call["physical_call_id"] in completed:
            continue
        last_error: Exception | None = None
        for attempt in (1, 2):
            try:
                result, parsed = client.chat(call["messages"], temperature=call["temperature"], max_tokens=call["max_output_tokens"], seed=call["seed"], response_schema=SameStackGeneratorOutput, retries=1)
                raw_records[call["physical_call_id"]] = {"protocol": PROTOCOL, "physical_call_id": call["physical_call_id"], "attempt": attempt,
                    "succeeded": parsed is not None, "request_hash": result.request_hash, "usage": result.usage, "latency_ms": result.latency_ms,
                    "finish_reason": result.normalized_finish_reason, "raw_text_before_guard": result.text, "raw_response_before_guard": result.raw_response,
                    "parsed_before_guard": parsed.model_dump(mode="json") if parsed is not None else None,
                    "error": None if parsed is not None else "provider returned no schema-valid output"}
                write_jsonl(OUT / "raw_provider_attempts_before_guard.jsonl", list(raw_records.values()))
                if parsed is None:
                    last_error = RuntimeError("no schema-valid output")
                    continue
                completed[call["physical_call_id"]] = {"protocol": PROTOCOL, "physical_call_id": call["physical_call_id"], "case_id": call["case_id"],
                    "state_id": call["state_id"], "arm": call["arm"], "messages_sha256": call["messages_sha256"], "reply": parsed.reply,
                    "used_evidence_ids": list(parsed.used_evidence_ids), "realized_response_act": parsed.realized_response_act,
                    "provider_usage": result.usage, "provider_latency_ms": result.latency_ms, "provider_finish_reason": result.normalized_finish_reason}
                write_jsonl(OUT / "generator_results_private.jsonl", list(completed.values()))
                print(f"MS v1.1 panel {len(completed)}/30", flush=True)
                last_error = None
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                retryable = isinstance(exc, RetryableProviderError)
                raw_records[call["physical_call_id"]] = {"protocol": PROTOCOL, "physical_call_id": call["physical_call_id"], "attempt": attempt, "succeeded": False, "error": f"{type(exc).__name__}: {exc}"}
                write_jsonl(OUT / "raw_provider_attempts_before_guard.jsonl", list(raw_records.values()))
                if not retryable or attempt == 2:
                    break
        if call["physical_call_id"] not in completed and last_error is not None:
            print(f"FAILED {call['physical_call_id']}: {last_error}", flush=True)

    summary = {"protocol": PROTOCOL, "status": f"LIVE_COMPLETE_{len(completed)}_OF_30", "run_identity": phase["execution"]["run_identity"],
               "completed": len(completed), "total": 30, "output_directory": str(OUT.relative_to(ROOT))}
    write_json(OUT / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
