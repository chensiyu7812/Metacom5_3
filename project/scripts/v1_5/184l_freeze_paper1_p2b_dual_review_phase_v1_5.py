#!/usr/bin/env python3
"""Freeze the zero-API P2B control, call plan, budget, and phase candidate."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random
import sys
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import canonical_json, sha256_file  # noqa: E402
from metacom_pm.v1_5_paper1_suitability_review import (  # noqa: E402
    build_reviewer_controls,
    prompt_messages,
)


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
DESIGN = ROOT / "data/pm_v1_5_contracts/paper1_p2_atomic_suitability_design_candidate_v1.json"
ENDPOINTS = ROOT / "configs/pm_v1_5_strict_judge_bakeoff_v1.json"
PACKET_DIR = ROOT / "outputs/pm_v1_5_paper1_p2a_suitability_packet"
PRIVATE_P2A = ROOT / "outputs/pm_v1_5_paper1_p2a_suitability_packet_private/private_case_key.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_p2b_dual_review_freeze_20260810"
PRIVATE = ROOT / "outputs/pm_v1_5_paper1_p2b_dual_review_freeze_private_20260810"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_p2b_dual_reviewer_suitability_phase_v1.json"
REVIEWERS = (
    ("REVIEWER_A", "anthropic_claude_haiku_4_5", "reviewer_a_packet_unlabeled.jsonl"),
    ("REVIEWER_B", "openai_gpt_5_mini", "reviewer_b_packet_unlabeled.jsonl"),
)
MAX_OUTPUT_TOKENS = 900
MAX_ATTEMPTS_PER_CALL = 2
USD_CAP = 6.0


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def write_jsonl(path: Path, values: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(canonical_json(dict(value)) + "\n" for value in values))


def rel(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT.resolve()))


def binding(path: Path, role: str) -> dict[str, Any]:
    return {"role": role, "path": rel(path), "sha256": sha256_file(path)}


def call_key(stage: str, reviewer: str, item_id: str) -> str:
    return "p2b_" + hashlib.sha256(
        f"paper1-p2b-v1:{stage}:{reviewer}:{item_id}".encode()
    ).hexdigest()[:24]


def main() -> None:
    if OUT.exists() or PRIVATE.exists() or PHASE.exists():
        raise RuntimeError("P2B freeze output already exists; refusing overwrite")
    authority = read(AUTHORITY)
    if authority["current_phase"]["id"] != "P2A_PACKET_COMPLETE_P2B_REVIEW_PENDING":
        raise RuntimeError("active authority is not at the P2B design boundary")
    parent_authority_sha = sha256_file(AUTHORITY)
    if parent_authority_sha != "79bb9066e07f5fdba8241cca32da8180381e5af51e1828b503ea62c3d89220e9":
        raise RuntimeError("unexpected parent authority drift")
    design = read(DESIGN)
    endpoint_config = read(ENDPOINTS)
    controls, gold = build_reviewer_controls()
    control_a = list(controls)
    control_b = list(controls)
    random.Random(202608101).shuffle(control_a)
    random.Random(202608102).shuffle(control_b)
    control_a_path = OUT / "reviewer_a_controls_unlabeled.jsonl"
    control_b_path = OUT / "reviewer_b_controls_unlabeled.jsonl"
    gold_path = PRIVATE / "control_gold_key.jsonl"
    write_jsonl(control_a_path, control_a)
    write_jsonl(control_b_path, control_b)
    write_jsonl(gold_path, gold)

    plan: list[dict[str, Any]] = []
    cost_by_reviewer: dict[str, dict[str, Any]] = {}
    for reviewer, endpoint_key, packet_name in REVIEWERS:
        endpoint = endpoint_config["candidates"][endpoint_key]
        packet_path = PACKET_DIR / packet_name
        packet = rows(packet_path)
        reviewer_controls = control_a if reviewer == "REVIEWER_A" else control_b
        surfaces = [("CONTROL", item) for item in reviewer_controls] + [
            ("PUBLIC", item) for item in packet
        ]
        chars = 0
        for ordinal, (stage, item) in enumerate(surfaces, 1):
            messages = prompt_messages(item, reviewer)
            prompt_sha = hashlib.sha256(canonical_json(messages).encode()).hexdigest()
            chars += len(canonical_json(messages))
            plan.append(
                {
                    "ordinal": ordinal,
                    "reviewer_id": reviewer,
                    "endpoint_key": endpoint_key,
                    "model": endpoint["model"],
                    "call_stage": stage,
                    "review_item_id": item["review_item_id"],
                    "call_key": call_key(stage, reviewer, item["review_item_id"]),
                    "prompt_sha256": prompt_sha,
                    "max_output_tokens": MAX_OUTPUT_TOKENS,
                    "maximum_physical_attempts": MAX_ATTEMPTS_PER_CALL,
                }
            )
        input_tokens = int(chars / 4 * 1.5)
        output_tokens = len(surfaces) * MAX_OUTPUT_TOKENS
        one_pass = (
            input_tokens * float(endpoint["input_usd_per_million_tokens"])
            + output_tokens * float(endpoint["output_usd_per_million_tokens"])
        ) / 1_000_000
        cost_by_reviewer[reviewer] = {
            "endpoint_key": endpoint_key,
            "model": endpoint["model"],
            "logical_calls": len(surfaces),
            "input_token_upper_proxy": input_tokens,
            "output_token_upper_proxy": output_tokens,
            "two_attempt_usd_upper_proxy": 2 * one_pass,
        }
    plan_path = OUT / "call_plan.jsonl"
    write_jsonl(plan_path, plan)
    total_upper = sum(row["two_attempt_usd_upper_proxy"] for row in cost_by_reviewer.values())
    cost = {
        "protocol": "pm-v1.5-paper1-p2b-cost-ceiling-v1",
        "reviewers": cost_by_reviewer,
        "total_two_attempt_usd_upper_proxy": total_upper,
        "absolute_usd_cap": USD_CAP,
        "within_cap": total_upper <= USD_CAP,
        "cost_is_transport_budget_not_scientific_gate": True,
    }
    cost_path = OUT / "cost_ceiling.json"
    write_json(cost_path, cost)
    checks = {
        "parent_authority_exact": True,
        "p2a_packets_exact": sha256_file(PACKET_DIR / "reviewer_a_packet_unlabeled.jsonl")
        == "289226c699ead15ff0fd154683ce0ea6ce1938f84d03175b3b49c9b5bf976a6a"
        and sha256_file(PACKET_DIR / "reviewer_b_packet_unlabeled.jsonl")
        == "9565a511b0a7937c9b55b0f91d00fa8b8c3a714f5b085947de1d151d9a41f5b4",
        "controls_24_balanced_by_component": len(controls) == 24
        and all(sum(row["component"] == component for row in controls) == 6 for component in ("MP", "MS", "ME", "RS")),
        "reviewer_control_order_independent": [row["review_item_id"] for row in control_a]
        != [row["review_item_id"] for row in control_b],
        "call_plan_exact": len(plan) == 312
        and sum(row["call_stage"] == "CONTROL" for row in plan) == 48
        and sum(row["call_stage"] == "PUBLIC" for row in plan) == 264,
        "call_keys_unique": len({row["call_key"] for row in plan}) == 312,
        "budget_within_frozen_cap": total_upper <= USD_CAP,
        "formal_labels_and_outcomes_not_read": True,
    }
    if not all(checks.values()):
        raise RuntimeError(f"P2B freeze failed: {[key for key, value in checks.items() if not value]}")
    report_path = OUT / "report.json"
    report = {
        "protocol": "pm-v1.5-paper1-p2b-dual-review-freeze-report-v1",
        "status": "P2B_ZERO_API_FREEZE_PASS_EXECUTION_NOT_YET_AUTHORIZED",
        "parent_authority_sha256": parent_authority_sha,
        "checks": checks,
        "controls": {"items_per_reviewer": 24, "per_component": 6},
        "calls": {"control": 48, "public": 264, "total": 312, "maximum_physical_attempts": 624},
        "reviewer_control_gate": {
            "per_component_axis_accuracy_min": 0.875,
            "per_component_derived_accuracy_min": 5 / 6,
            "critical_boundary_controls_all_correct": True,
            "failure": "reviewer-component ineligible; component is fixed OFF if either reviewer is ineligible; no public calls for that component",
            "no_prompt_rewrite_no_extra_controls_no_gate_reduction": True,
        },
        "artifacts": {},
        "api_calls": 0,
        "labels_created": 0,
        "private_public_gold_read": False,
    }
    write_json(report_path, report)
    report["artifacts"] = {
        "control_a": binding(control_a_path, "reviewer_a_controls"),
        "control_b": binding(control_b_path, "reviewer_b_controls"),
        "control_gold": binding(gold_path, "private_control_gold"),
        "call_plan": binding(plan_path, "call_plan"),
        "cost_ceiling": binding(cost_path, "cost_ceiling"),
    }
    write_json(report_path, report)
    phase = {
        "protocol": "pm-v1.5-paper1-p2b-dual-reviewer-suitability-phase-v1",
        "date": "2026-08-10",
        "status": "P2B_EXECUTION_CANDIDATE_REQUIRES_AUTHORITY_PROMOTION_AND_PAID_RELEASE",
        "method_id": authority["active_method"]["method_id"],
        "parent_authority_sha256": parent_authority_sha,
        "active_contract_sha256": authority["active_method"]["contract_sha256"],
        "active_method_amendment_sha256": authority["active_method"]["method_amendment_sha256"],
        "input_bindings": [
            binding(DESIGN, "p2_atomic_design"),
            binding(PACKET_DIR / "reviewer_a_packet_unlabeled.jsonl", "reviewer_a_public_packet"),
            binding(PACKET_DIR / "reviewer_b_packet_unlabeled.jsonl", "reviewer_b_public_packet"),
            binding(PRIVATE_P2A, "private_case_key_analysis_only_after_reviews_frozen"),
            binding(ENDPOINTS, "endpoint_config"),
            binding(control_a_path, "reviewer_a_controls"),
            binding(control_b_path, "reviewer_b_controls"),
            binding(gold_path, "private_control_gold"),
            binding(plan_path, "call_plan"),
            binding(cost_path, "cost_ceiling"),
            binding(report_path, "zero_api_freeze_report"),
        ],
        "implementation_bindings": [
            binding(ROOT / "src/metacom_pm/v1_5_paper1_suitability.py", "projection_and_metrics"),
            binding(ROOT / "src/metacom_pm/v1_5_paper1_suitability_review.py", "review_schema_prompt_controls"),
        ],
        "reviewers": {
            reviewer: {
                "endpoint_key": endpoint_key,
                "model": endpoint_config["candidates"][endpoint_key]["model"],
                "transport": endpoint_config["candidates"][endpoint_key]["transport"],
            }
            for reviewer, endpoint_key, _ in REVIEWERS
        },
        "execution": {
            "controls_first": True,
            "public_component_calls_only_if_both_reviewers_pass_that_component": True,
            "temperature": 0.0,
            "seed_base": 20260810,
            "maximum_output_tokens": MAX_OUTPUT_TOKENS,
            "maximum_physical_attempts_per_logical_call": MAX_ATTEMPTS_PER_CALL,
            "retry": "same byte-identical provider-visible request only; no semantic repair message",
            "absolute_usd_cap": USD_CAP,
            "formal_agreement_before_adjudication": True,
        },
        "forbidden": [
            "response or paired-effect generation",
            "safe-yield label creation",
            "PM fitting or threshold selection",
            "baseline or external outcome scoring",
            "prompt edits, extra controls, appended public cases, or lowered gates after any control response",
        ],
    }
    write_json(PHASE, phase)
    print(json.dumps({"report": rel(report_path), "phase": rel(PHASE), "cost": cost}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
