#!/usr/bin/env python3
"""Materialize eight frozen oracle-plan MS+R0 calls without calling an API."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import canonical_json, read_json, read_jsonl, sha256_file, sha256_text, stable_hex, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_component_general_v3 import V3Candidate, build_component_general_plan_v3  # noqa: E402
from metacom_pm.v1_5_ms_same_stack_feasibility import SameStackGeneratorOutput  # noqa: E402
from metacom_pm.v1_5_response_program_v3 import response_generation_messages_v3  # noqa: E402


CONTRACT = ROOT / "data/pm_v1_5_contracts/paper1_semantic_adapter_ablation_v1.json"
ORACLE = ROOT / "data/pm_v1_5_contracts/paper1_ms_oracle_semantic_plans_v1.json"
CASES = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_qualification_preflight_v3_20260811/qualification_cases_private.jsonl"
CONFIG = ROOT / "configs/paper1_ms_oracle_plan_upper_bound_execution_v1.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_ms_oracle_plan_upper_bound_preflight_20260811"


def build_plan(case: dict, oracle: dict):
    meaning = (
        f"support_phase={oracle['support_phase']}; immediate_goal={oracle['immediate_goal']}; "
        f"candidate_increment={oracle['candidate_increment']}; "
        f"resource_disposition={oracle['oracle_disposition']}; "
        f"entity_link_status={oracle['entity_link_status']}"
    )
    allowed = oracle["good_use"] + " " + oracle["nonuse_condition"]
    forbidden = (
        oracle["forbidden_focus_shift"]
        + " Do not copy the source, assume it remains current, or expose this planning scaffold."
    )
    candidate = V3Candidate(
        component="MS",
        evidence_id=case["evidence_id"],
        meaning_cue=meaning,
        exact_source=case["exact_source"],
        owner_id=case["runtime_owner_key"],
        time_status="STRICTLY_PAST_NOT_ASSUMED_CURRENT",
        allowed_response_change=allowed,
        forbidden_inference=forbidden,
        burden_units=1,
    )
    return build_component_general_plan_v3(
        requested_action_id="MS+R0",
        current_user_id=case["runtime_owner_key"],
        candidates={"MP": None, "MS": candidate, "ME": None, "RS": None},
    )


def main() -> None:
    contract = read_json(CONTRACT)
    if contract["authority"]["api_calls_authorized"] != 0:
        raise RuntimeError("zero-API parent contract drifted")
    cases = {
        row["qualification_case_id"]: row
        for row in read_jsonl(CASES)
        if row["qualification_class"] == "TEACHER_SUITABLE"
    }
    oracle = {row["qualification_case_id"]: row for row in read_json(ORACLE)["plans"]}
    if len(cases) != len(oracle) or set(cases) != set(oracle) or len(cases) != 8:
        raise RuntimeError("oracle/case set drifted")
    schema = SameStackGeneratorOutput.model_json_schema()
    calls = []
    for case_id in sorted(cases):
        case = cases[case_id]
        plan = build_plan(case, oracle[case_id])
        messages = response_generation_messages_v3(
            current_context=case["current_context"],
            current_goal=case["current_goal"],
            plan=plan,
        )
        calls.append({
            "protocol": "pm-v1.5-paper1-ms-oracle-plan-upper-bound-call-v1",
            "physical_call_id": "msoracle_" + stable_hex(case_id, case["seed"], "ORACLE_PLAN_MS_R0_V1", n=24),
            "qualification_case_id": case_id,
            "state_id": case["state_id"],
            "split_group_key": case["split_group_key"],
            "runtime_owner_key": case["runtime_owner_key"],
            "evidence_id": case["evidence_id"],
            "oracle_disposition_private": oracle[case_id]["oracle_disposition"],
            "requested_action_id": "MS+R0",
            "seed": case["seed"],
            "temperature": 0.7,
            "max_output_tokens": 512,
            "messages": messages,
            "messages_sha256": sha256_text(canonical_json(messages)),
            "response_schema": schema,
            "response_schema_sha256": sha256_text(canonical_json(schema)),
        })
    prompt_texts = [canonical_json(row["messages"]) for row in calls]
    checks = {
        "exact_eight_calls": len(calls) == 8,
        "six_use_two_safe_nonuse": sum(row["oracle_disposition_private"] == "USE_IF_NATURAL" for row in calls) == 6 and sum(row["oracle_disposition_private"] == "SAFE_NONUSE" for row in calls) == 2,
        "one_ms_r0_call_per_state": len({row["state_id"] for row in calls}) == 8 and {row["requested_action_id"] for row in calls} == {"MS+R0"},
        "frozen_seed_reused": all(row["seed"] == cases[row["qualification_case_id"]]["seed"] for row in calls),
        "candidate_specific_fields_visible": all(all(term in text for term in ("support_phase=", "immediate_goal=", "candidate_increment=", "resource_disposition=", "entity_link_status=")) for text in prompt_texts),
        "safe_nonuse_visible": all("Leave the memory unused" in text for text in prompt_texts),
        "literal_splice_forbidden": all("Literal mention and lexical overlap are not required" in text and "Use this exact prior-user statement" not in text for text in prompt_texts),
        "response_schema_frozen": len({row["response_schema_sha256"] for row in calls}) == 1,
        "teacher_label_not_provider_visible": all("TEACHER_SUITABLE" not in text for text in prompt_texts),
        "zero_api": True,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError("oracle call preflight failed: " + ", ".join(failed))
    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "physical_call_plan_private.jsonl", calls)
    report = {
        "protocol": "pm-v1.5-paper1-ms-oracle-plan-upper-bound-preflight-v1",
        "status": "ZERO_API_PREFLIGHT_PASS_LIVE_PHASE_MAY_BE_HASH_BOUND",
        "checks": checks,
        "calls": 8,
        "parent_commit": "7eb23a6e0cc749ae866202e681b007fd3e0789a1",
        "bindings": {
            "contract": {"path": str(CONTRACT.relative_to(ROOT)), "sha256": sha256_file(CONTRACT)},
            "oracle": {"path": str(ORACLE.relative_to(ROOT)), "sha256": sha256_file(ORACLE)},
            "cases": {"path": str(CASES.relative_to(ROOT)), "sha256": sha256_file(CASES)},
            "config": {"path": str(CONFIG.relative_to(ROOT)), "sha256": sha256_file(CONFIG)},
            "call_plan": {"path": str((OUT / "physical_call_plan_private.jsonl").relative_to(ROOT)), "sha256": sha256_file(OUT / "physical_call_plan_private.jsonl")},
        },
        "api_calls": 0,
        "pm_fits": 0,
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
