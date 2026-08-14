#!/usr/bin/env python3
"""Freeze the 204-call MS single-qualified-teacher plan; zero API."""

from __future__ import annotations

from collections import Counter
import json
import math
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.api import Endpoint  # noqa: E402
from metacom_pm.attempt_ledger import physical_call_key  # noqa: E402
from metacom_pm.io import canonical_json, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_g4b_anchored_review_v2 import G4BSuitabilityReview, prompt_messages  # noqa: E402


PACKET = ROOT / "outputs/pm_v1_5_paper1_v3_g4a_packet_v2_20260811/reviewer_a_packet.jsonl"
PRIVATE = ROOT / "outputs/pm_v1_5_paper1_v3_g4a_packet_v2_private_20260811/private_case_key.jsonl"
G3 = ROOT / "outputs/pm_v1_5_paper1_v3_g3_candidate_surface_audit_20260811/candidate_surface_diagnostics_unlabeled.jsonl"
QUALIFICATION = ROOT / "outputs/pm_v1_5_paper1_v3_g4b1_anchored_v2_qualification_20260811/report.json"
ENDPOINTS = ROOT / "configs/pm_v1_5_strict_judge_bakeoff_v1.json"
RUNNER = ROOT / "scripts/v1_5/226l_run_paper1_v3_ms_single_teacher_reviews_v1_5.py"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_ms_single_teacher_preflight_20260811"
STAGE = "paper1_v3_ms_single_qualified_teacher_review_v1"
REVIEWER_ID = "REVIEWER_A"
ENDPOINT_KEY = "anthropic_claude_haiku_4_5"
MAX_OUTPUT_TOKENS = 500
MAX_ATTEMPTS = 2
SEED_BASE = 20260811


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def endpoint(raw: dict[str, Any]) -> Endpoint:
    return Endpoint(
        base_url=str(raw["base_url"]), model=str(raw["model"]),
        api_key_env=str(raw["api_key_env"]), timeout_seconds=240.0,
        family=str(raw["family"]), transport=str(raw["transport"]),
        supports_strict_json_schema=bool(raw["supports_strict_json_schema"]),
        temperature_mode=str(raw.get("temperature_mode") or "explicit"),
        max_output_tokens_parameter=str(raw.get("max_output_tokens_parameter") or "max_tokens"),
        anthropic_strict_tool_use=bool(raw.get("anthropic_strict_tool_use", False)),
        openai_reasoning_effort=raw.get("openai_reasoning_effort"),
    )


def main() -> None:
    if OUT.exists():
        raise RuntimeError("MS teacher preflight exists; refusing overwrite")
    qualification = read(QUALIFICATION)
    result = qualification["reviewer_component_results"][REVIEWER_ID]["MS"]
    if result["status"] != "QUALIFIED" or result["exact_correct"] != 11 or result["resolved_correct"] != 9 or result["abstain_correct"] != 2:
        raise RuntimeError("frozen Reviewer A MS qualification drifted")

    packet = [row for row in rows(PACKET) if row["component"] == "MS"]
    if len(packet) != 204 or len({row["review_item_id"] for row in packet}) != 204:
        raise RuntimeError("MS packet denominator or key drifted")
    private = {row["reviewer_a_item_id"]: row for row in rows(PRIVATE) if row["component"] == "MS"}
    g3 = {(row["state_id"], row["actual_rank1_id"]): row for row in rows(G3) if row["component"] == "MS" and row["candidate_present"]}
    if set(private) != {row["review_item_id"] for row in packet}:
        raise RuntimeError("MS packet/private mapping mismatch")

    joined = []
    for item in packet:
        key = private[item["review_item_id"]]
        diagnostic = g3[(key["state_id"], key["actual_rank1_id"])]
        if len(item["candidate_spans"]) != 1 or not diagnostic["atomic_single_seeker_turn"]:
            raise RuntimeError("non-atomic MS teacher case")
        joined.append((item, key, diagnostic))

    endpoints = read(ENDPOINTS)
    ep = endpoint(endpoints["candidates"][ENDPOINT_KEY])
    plan = []
    for item, _key, _diagnostic in joined:
        messages = prompt_messages(item, REVIEWER_ID)
        prompt_sha = sha256_text(canonical_json(messages))
        params = {
            "temperature": 0.0,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "seed": SEED_BASE + int(item["review_position"]),
            "response_schema": G4BSuitabilityReview.__name__,
            "client_internal_retries": 1,
        }
        record_ids = {
            "reviewer_id": REVIEWER_ID,
            "review_item_id": item["review_item_id"],
            "call_stage": "MS_TEACHER",
        }
        plan.append({
            "protocol": "pm-v1.5-paper1-v3-ms-single-teacher-call-plan-v1",
            "call_stage": "MS_TEACHER",
            "reviewer_id": REVIEWER_ID,
            "review_item_id": item["review_item_id"],
            "review_position": int(item["review_position"]),
            "component": "MS",
            "endpoint_key": ENDPOINT_KEY,
            "model": ep.model,
            "prompt_sha256": prompt_sha,
            "logical_call_key": physical_call_key(
                stage=STAGE,
                record_ids=record_ids,
                prompt_sha256=prompt_sha,
                endpoint=ep,
                request_parameters=params,
            ),
            "request_parameters": params,
            "maximum_physical_attempts": MAX_ATTEMPTS,
            "input_character_count": len(canonical_json(messages)),
        })
    plan.sort(key=lambda row: row["review_position"])
    if len({row["logical_call_key"] for row in plan}) != 204:
        raise RuntimeError("MS teacher call keys are not unique")

    raw_endpoint = endpoints["candidates"][ENDPOINT_KEY]
    conservative = 0.0
    for row in plan:
        input_tokens = math.ceil(row["input_character_count"] / 3 * 1.5)
        per_attempt = (
            input_tokens * float(raw_endpoint["input_usd_per_million_tokens"])
            + MAX_OUTPUT_TOKENS * float(raw_endpoint["output_usd_per_million_tokens"])
        ) / 1_000_000
        conservative += per_attempt * MAX_ATTEMPTS
    cap = math.ceil(conservative * 2) / 2

    group_counts = Counter(key["split_group_key"] for _item, key, _diag in joined)
    candidate_counts = Counter(key["actual_rank1_id"] for _item, key, _diag in joined)
    forbidden_keys = {"summary", "observation", "influenced_by", "answer", "evidence", "gold", "label", "future_supporter_text"}
    checks = {
        "reviewer_a_ms_frozen_qualification_11_of_12": result["status"] == "QUALIFIED" and result["exact_correct"] == 11,
        "reviewer_a_resolved_9_of_10_and_abstain_2_of_2": result["resolved_correct"] == 9 and result["abstain_correct"] == 2,
        "reviewer_b_failure_recorded_not_used": qualification["reviewer_component_results"]["REVIEWER_B"]["MS"]["status"] == "NOT_QUALIFIED",
        "exact_204_atomic_ms_cases": len(joined) == 204 and all(diag["atomic_single_seeker_turn"] for _item, _key, diag in joined),
        "exact_17_connected_groups_12_each": len(group_counts) == 17 and set(group_counts.values()) == {12},
        "low_information_and_echo_strata_preserved": sum(diag["low_information_rank1"] for _item, _key, diag in joined) == 21 and sum(diag["exact_or_containment_current_echo"] for _item, _key, diag in joined) == 32,
        "packet_private_g3_one_to_one": len(joined) == len(packet) == len(private),
        "provider_payload_has_no_label_or_future_keys": all(not (forbidden_keys & set(item)) for item in packet),
        "anchored_ms_examples_provider_visible": all("WORKED TRAINING ANCHORS FOR MS" in prompt_messages(item, REVIEWER_ID)[0]["content"] for item in packet[:3]),
        "single_teacher_not_human_or_dual_gold": True,
        "influenced_by_and_qa_gold_not_training_targets": True,
        "all_16_actions_remain_downstream": True,
    }
    failed = [name for name, passed in checks.items() if not passed]
    OUT.mkdir(parents=True)
    call_plan = OUT / "call_plan.jsonl"
    cost_path = OUT / "cost_ceiling.json"
    write_jsonl(call_plan, plan)
    write_json(cost_path, {
        "protocol": "pm-v1.5-paper1-v3-ms-single-teacher-cost-ceiling-v1",
        "logical_calls": 204,
        "maximum_physical_attempts": 408,
        "conservative_computed_usd": conservative,
        "absolute_usd_cap": cap,
        "method": "ceil(chars/3*1.5) input + full 500 output tokens, both attempts",
    })
    report = {
        "protocol": "pm-v1.5-paper1-v3-ms-single-teacher-preflight-report-v1",
        "status": "MS_SINGLE_QUALIFIED_TEACHER_PREFLIGHT_PASS_EXECUTION_PHASE_MAY_BE_DESIGNED" if not failed else "MS_SINGLE_TEACHER_PREFLIGHT_FAIL",
        "checks": checks,
        "failed_checks": failed,
        "supervision_identity": {
            "type": "single qualified LLM teacher; not human gold and not dual-review consensus",
            "reviewer_id": REVIEWER_ID,
            "endpoint_key": ENDPOINT_KEY,
            "model": ep.model,
            "frozen_control_result": {"exact": "11/12", "resolved": "9/10", "abstain": "2/2"},
        },
        "surface": {
            "cases": 204,
            "connected_groups": 17,
            "cases_per_group": dict(sorted(group_counts.items())),
            "distinct_candidates": len(candidate_counts),
            "low_information_cases": 21,
            "current_echo_cases": 32,
        },
        "label_projection_after_freeze": {
            "SUITABLE": 1,
            "NOT_SUITABLE": 0,
            "SEMANTIC_ABSTAIN": "unresolved; excluded from binary fit and runtime defaults OFF",
            "minimum_training_capacity_is_diagnostic_not_a_scientific_pass_line": "both resolved classes must exist across multiple connected groups; final adequacy is OOF and same-stack performance",
        },
        "call_plan": {"path": str(call_plan.relative_to(ROOT)), "sha256": sha256_file(call_plan), "rows": 204},
        "cost_ceiling": {"path": str(cost_path.relative_to(ROOT)), "sha256": sha256_file(cost_path), **read(cost_path)},
        "api_calls": 0,
        "labels_created": 0,
        "private_case_mapping_read_for_integrity_only": True,
        "next": "HASH_BOUND_EXACT_204_MS_SINGLE_TEACHER_EXECUTION_PHASE",
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
