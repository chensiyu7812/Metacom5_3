#!/usr/bin/env python3
"""Continue only V5.4 canary calls that never received a valid completion."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import runpy
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from metacom_pm.api import make_client  # noqa: E402
from metacom_pm.config import endpoint_from_config, load_config  # noqa: E402
from metacom_pm.io import sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_typed_resource_adapter import TypedResourceCandidate  # noqa: E402
from metacom_pm.v1_5_v5_3_typed_response_program import (  # noqa: E402
    RewritePolicy, build_typed_response_program, evidence_aware_generation_messages,
    execute_typed_response,
)

PROTOCOL = "pm-v1.5-v5.4-effect-canary-transport-continuation-v1"
BASE = ROOT / "outputs/pm_v1_5_v5_4_effect_canary_generation_20260810"
CANARY = ROOT / "outputs/pm_v1_5_v5_4_effect_canary_preflight_20260810/canary_effect_groups_private.jsonl"
OUT = ROOT / "outputs/pm_v1_5_v5_4_effect_canary_transport_continuation_20260810"


def rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    base_report = json.loads((BASE / "report.json").read_text())
    base_rows = rows(BASE / "generator_arm_results.jsonl")
    raw = rows(BASE / "raw_provider_attempts_before_guard.jsonl")
    canary = {row["effect_group_id"]: row for row in rows(CANARY)}
    success_calls = {row["call_id"] for row in raw if row["succeeded"]}
    eligible = [row for row in base_rows if row["call_id"] not in success_calls]
    if base_report["status"] != "CANARY_GENERATION_COMPLETE_MEASUREMENT_MAY_RUN" or len(eligible) != 7:
        raise RuntimeError("expected exactly seven no-completion transport calls")
    if any(not row["first_pass_errors"] or "HTTP 429" not in row["first_pass_errors"][0] for row in eligible):
        raise RuntimeError("continuation contains a non-transport failure")
    freeze = {
        "protocol": PROTOCOL,
        "status": "TRANSPORT_CONTINUATION_FROZEN_SEVEN_NO_COMPLETION_CALLS",
        "eligible_calls": len(eligible),
        "selection": "no successful provider completion exists in the immutable raw-attempt ledger",
        "state_arm_seed_prompt_change": False,
        "valid_base_response_repeated": False,
        "base_report_sha256": sha256_file(BASE / "report.json"),
        "base_results_sha256": sha256_file(BASE / "generator_arm_results.jsonl"),
        "base_raw_sha256": sha256_file(BASE / "raw_provider_attempts_before_guard.jsonl"),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    write_json(OUT / "freeze.json", freeze)

    legacy = runpy.run_path(str(ROOT / "scripts/v1_5/159l_run_v5_4_effect_canary_generation_v1_5.py"))
    schema = legacy["GeneratorSchema"]
    wrapper_type = legacy["RawPersistingClient"]
    context = legacy["context"]
    aliases = legacy["aliases_by_owner"]()
    config = load_config(ROOT / "configs/experiment.yaml")
    client = make_client(endpoint_from_config(config, "generator"))
    completed = {row["original_call_id"]: row for row in rows(OUT / "continuation_results.jsonl")}
    raw_rows = {f"existing:{index}": row for index, row in enumerate(rows(OUT / "raw_provider_attempts_before_guard.jsonl"))}
    try:
        for index, old in enumerate(eligible, start=1):
            if old["call_id"] in completed:
                continue
            plan = canary[old["effect_group_id"]]
            candidate = TypedResourceCandidate(**plan["actual_rank1_candidate"])
            on = old["arm"] == "ON"
            program = build_typed_response_program(
                requested_action_id=plan["on_action_id"] if on else plan["off_action_id"],
                current_goal="Respond supportively to the latest user message using only visible authorized information.",
                current_user_id=plan["current_owner_id"],
                candidates={plan["component"]: candidate} if on else {},
                expected_execution_candidate_ids={plan["component"]: candidate.resource_id} if on else {},
                current_user_known_aliases=aliases.get(plan["current_owner_id"], ()),
            )
            continuation_key = old["call_id"] + ":transport_continuation_v1"
            wrapper = wrapper_type(client, call_key=continuation_key, seed=int(old["seed"]), raw_rows=raw_rows, out_dir=OUT)
            execution = execute_typed_response(
                wrapper, schema,
                evidence_aware_generation_messages(current_context=context(plan), program=program),
                program, rewrite_policy=RewritePolicy.DETERMINISTIC_FALLBACK,
            )
            completed[old["call_id"]] = {
                "protocol": PROTOCOL, "original_call_id": old["call_id"],
                "continuation_call_id": continuation_key,
                "effect_group_id": old["effect_group_id"], "state_id": old["state_id"],
                "component": old["component"], "seed": old["seed"], "arm": old["arm"],
                "requested_action_id": execution.requested_action_id,
                "realized_action_id": execution.realized_action_id,
                "status": execution.status,
                "first_pass_errors": list(execution.first_pass_errors),
                "final_guard_errors": list(execution.final_guard_errors),
                "final_reply": execution.response.reply if execution.response else None,
                "final_used_evidence_ids": list(execution.used_evidence_ids),
                "reported_used_evidence_ids": list(execution.reported_used_evidence_ids),
                "raw_provider_reply_persisted_before_guard": any(row.get("call_id") == continuation_key for row in raw_rows.values()),
                "replaces_only_no_completion_transport_fallback": True,
            }
            write_jsonl(OUT / "continuation_results.jsonl", list(completed.values()))
            print(f"transport continuation {index}/7 status={execution.status}", flush=True)
    finally:
        client.close()

    merged = {row["call_id"]: dict(row) for row in base_rows}
    for original_id, row in completed.items():
        if row["status"] == "clean":
            target = merged[original_id]
            target.update({
                "realized_action_id": row["realized_action_id"], "status": row["status"],
                "first_pass_errors": row["first_pass_errors"], "final_guard_errors": row["final_guard_errors"],
                "final_reply": row["final_reply"], "final_used_evidence_ids": row["final_used_evidence_ids"],
                "reported_used_evidence_ids": row["reported_used_evidence_ids"],
                "raw_provider_reply_persisted_before_guard": row["raw_provider_reply_persisted_before_guard"],
                "transport_continuation_call_id": row["continuation_call_id"],
                "original_no_completion_fallback_preserved_in_base": True,
            })
    merged_rows = list(merged.values())
    write_jsonl(OUT / "merged_generator_arm_results_for_measurement.jsonl", merged_rows)
    report = {
        "protocol": PROTOCOL,
        "status": "TRANSPORT_CONTINUATION_COMPLETE_MEASUREMENT_READY" if len(completed) == 7 and all(row["status"] == "clean" for row in completed.values()) else "TRANSPORT_CONTINUATION_INCOMPLETE_NO_MEASUREMENT",
        "continued": len(completed),
        "continuation_status_counts": dict(Counter(row["status"] for row in completed.values())),
        "merged_status_counts": dict(Counter(row["status"] for row in merged_rows)),
        "merged_requested_realized_exact": sum(row["requested_action_id"] == row["realized_action_id"] for row in merged_rows),
        "valid_base_calls_repeated": 0,
        "state_arm_seed_prompt_changed": False,
        "response_effect_judged": False,
        "merged_sha256": sha256_file(OUT / "merged_generator_arm_results_for_measurement.jsonl"),
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
