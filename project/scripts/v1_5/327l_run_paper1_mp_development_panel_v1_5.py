#!/usr/bin/env python3
"""Execute the exact hash-bound 19-call MP development panel (325l output)."""

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
from metacom_pm.v1_5_component_general_v3 import V3Candidate, build_component_general_plan_v3  # noqa: E402
from metacom_pm.v1_5_mp_profile_delta_templates_v1 import mp_realization_template  # noqa: E402
from metacom_pm.v1_5_ms_same_stack_feasibility import SameStackGeneratorOutput  # noqa: E402
from metacom_pm.v1_5_response_program_v4 import response_generation_messages_v4  # noqa: E402

PROTOCOL = "pm-v1.5-paper1-mp-development-panel-live-v1"
STAGE = "paper1_mp_development_panel_v1"
AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
BUNDLE = ROOT / "data/pm_v1_5_contracts/paper1_active_execution_bundle_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_mp_development_panel_execution_phase_v1.json"
CONFIG = ROOT / "configs/paper1_mp_development_panel_execution_v1.json"
CASES = ROOT / "outputs/pm_v1_5_paper1_mp_development_panel_20260813/development_cases_private.jsonl"
EVOEMO_STATES = ROOT / "outputs/pm_v1_5_paper1_p1_public_surface/evoemo_states_unlabeled.jsonl"
EVOEMO_CANDIDATES = ROOT / "outputs/pm_v1_5_paper1_p1_public_surface/evoemo_candidates_unlabeled.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_mp_development_panel_live_20260813"
CURRENT_GOAL = "Respond supportively to the latest visible seeker turn. Advance its immediate emotional-support goal without inventing facts, overloading the reply, or assuming a past fact is still current."
USD_CAP = 0.0
STAGE_ID = "MP_DEVELOPMENT_PANEL_EXECUTION"


def _compact(value: object) -> str:
    return " ".join(str(value or "").split())


def require_authority() -> dict[str, Any]:
    authority = read_json(AUTHORITY)
    bundle = read_json(BUNDLE)
    current = authority["current_execution_phase"]
    expected_bundle = {"path": str(BUNDLE.relative_to(ROOT)), "sha256": sha256_file(BUNDLE)}
    if current["id"] != STAGE_ID or current["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("MP development panel execution is not current")
    if bundle["current_phase"]["id"] != STAGE_ID:
        raise RuntimeError("bundle does not point at this execution phase")
    phase = read_json(PHASE)
    for binding in phase["input_bindings"]:
        if sha256_file(ROOT / binding["path"]) != binding["sha256"]:
            raise RuntimeError(f"bound input drifted: {binding['role']}")
    return phase


def build_messages(case: dict[str, Any], arm: str, states_by_id, ms_ignore, cand_by_owner_field) -> list[dict[str, str]]:
    state = states_by_id[case["state_id"]]
    owner = case["runtime_owner_key"]
    current_context = _compact(state["current_user_text"])
    candidates: dict[str, V3Candidate | None] = {"MP": None, "MS": None, "ME": None, "RS": None}
    if arm == "MP+R0" and case["profile_field"]:
        template = mp_realization_template(case["profile_field"])
        candidate_row = cand_by_owner_field[(owner, case["profile_field"])]
        candidates["MP"] = V3Candidate(
            component="MP",
            evidence_id=candidate_row["candidate_id"],
            meaning_cue=template.meaning_cue,
            exact_source=candidate_row["literal_text"],
            owner_id=owner,
            time_status="STRICTLY_PAST",
            allowed_response_change=template.allowed_response_change,
            forbidden_inference=template.forbidden_inference,
        )
    action = "MP+R0" if arm == "MP+R0" else "M0+R0"
    plan = build_component_general_plan_v3(
        requested_action_id=action, current_user_id=owner, candidates=candidates
    )
    return response_generation_messages_v4(current_context=current_context, current_goal=CURRENT_GOAL, plan=plan)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--run-identity")
    parser.add_argument("--accept-usd-cap", type=float)
    args = parser.parse_args()
    phase = require_authority()

    cases = read_jsonl(CASES)
    states_by_id = {row["state_id"]: row for row in read_jsonl(EVOEMO_STATES)}
    cand_by_owner_field: dict[tuple[str, str], Any] = {}
    for row in read_jsonl(EVOEMO_CANDIDATES):
        if row["component"] == "MP":
            cand_by_owner_field[(row["runtime_owner_key"], row["profile_field"])] = row

    calls: list[dict[str, Any]] = []
    for case in cases:
        for arm in case["arms_present"]:
            messages = build_messages(case, arm, states_by_id, None, cand_by_owner_field)
            calls.append(
                {
                    "physical_call_id": f"{case['case_id']}::{arm}",
                    "case_id": case["case_id"],
                    "state_id": case["state_id"],
                    "arm": arm,
                    "messages": messages,
                    "messages_sha256": sha256_text(canonical_json(messages)),
                    "temperature": 0.2,
                    "max_output_tokens": 400,
                    "seed": 7,
                }
            )
    if len(calls) != 19:
        raise RuntimeError(f"exact 19-call plan required, got {len(calls)}")

    dry = {
        "protocol": PROTOCOL,
        "status": "LIVE_READY_EXACT_19_MP_DEVELOPMENT_PANEL_CALLS",
        "logical_calls": len(calls),
        "absolute_usd_cap": USD_CAP,
        "run_identity": phase["execution"]["run_identity"],
        "api_calls": 0,
    }
    print(json.dumps(dry, ensure_ascii=False, indent=2), flush=True)
    if not args.live:
        return
    if args.run_identity != phase["execution"]["run_identity"]:
        raise RuntimeError("run identity does not match live phase")
    if args.accept_usd_cap != USD_CAP:
        raise RuntimeError(f"must accept exact frozen cap {USD_CAP:g}")
    require_paid_run_release(read_json(CONFIG), config_path=CONFIG, stage=STAGE, run=True, run_identity=args.run_identity)

    OUT.mkdir(parents=True, exist_ok=True)
    completed = (
        {row["physical_call_id"]: row for row in read_jsonl(OUT / "generator_results_private.jsonl")}
        if (OUT / "generator_results_private.jsonl").exists()
        else {}
    )
    raw_records = (
        {row["physical_call_id"]: row for row in read_jsonl(OUT / "raw_provider_attempts_before_guard.jsonl")}
        if (OUT / "raw_provider_attempts_before_guard.jsonl").exists()
        else {}
    )
    config = load_config(CONFIG)
    client = make_client(endpoint_from_config(config, "generator"))
    for call in sorted(calls, key=lambda row: row["physical_call_id"]):
        if call["physical_call_id"] in completed:
            continue
        last_error: Exception | None = None
        for attempt in (1, 2):
            try:
                result, parsed = client.chat(
                    call["messages"],
                    temperature=call["temperature"],
                    max_tokens=call["max_output_tokens"],
                    seed=call["seed"],
                    response_schema=SameStackGeneratorOutput,
                    retries=1,
                )
                raw_records[call["physical_call_id"]] = {
                    "protocol": PROTOCOL,
                    "physical_call_id": call["physical_call_id"],
                    "attempt": attempt,
                    "succeeded": parsed is not None,
                    "request_hash": result.request_hash,
                    "usage": result.usage,
                    "latency_ms": result.latency_ms,
                    "finish_reason": result.normalized_finish_reason,
                    "raw_text_before_guard": result.text,
                    "raw_response_before_guard": result.raw_response,
                    "parsed_before_guard": parsed.model_dump(mode="json") if parsed is not None else None,
                    "error": None if parsed is not None else "provider returned no schema-valid output",
                }
                write_jsonl(OUT / "raw_provider_attempts_before_guard.jsonl", list(raw_records.values()))
                if parsed is None:
                    last_error = RuntimeError("no schema-valid output")
                    continue
                completed[call["physical_call_id"]] = {
                    "protocol": PROTOCOL,
                    "physical_call_id": call["physical_call_id"],
                    "case_id": call["case_id"],
                    "state_id": call["state_id"],
                    "arm": call["arm"],
                    "messages_sha256": call["messages_sha256"],
                    "reply": parsed.reply,
                    "used_evidence_ids": list(parsed.used_evidence_ids),
                    "realized_response_act": parsed.realized_response_act,
                    "provider_usage": result.usage,
                    "provider_latency_ms": result.latency_ms,
                    "provider_finish_reason": result.normalized_finish_reason,
                }
                write_jsonl(OUT / "generator_results_private.jsonl", list(completed.values()))
                print(f"MP development panel {len(completed)}/19", flush=True)
                last_error = None
                break
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                retryable = isinstance(exc, RetryableProviderError)
                raw_records[call["physical_call_id"]] = {
                    "protocol": PROTOCOL,
                    "physical_call_id": call["physical_call_id"],
                    "attempt": attempt,
                    "succeeded": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
                write_jsonl(OUT / "raw_provider_attempts_before_guard.jsonl", list(raw_records.values()))
                if not retryable or attempt == 2:
                    break
        if call["physical_call_id"] not in completed and last_error is not None:
            print(f"FAILED {call['physical_call_id']}: {last_error}", flush=True)

    summary = {
        "protocol": PROTOCOL,
        "status": f"LIVE_COMPLETE_{len(completed)}_OF_19",
        "run_identity": phase["execution"]["run_identity"],
        "completed": len(completed),
        "total": 19,
        "output_directory": str(OUT.relative_to(ROOT)),
    }
    write_json(OUT / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
