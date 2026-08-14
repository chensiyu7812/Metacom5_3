#!/usr/bin/env python3
"""Materialize the zero-API G4B call plan, budgets and readiness report."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.api import Endpoint  # noqa: E402
from metacom_pm.attempt_ledger import physical_call_key  # noqa: E402
from metacom_pm.io import (  # noqa: E402
    canonical_json,
    sha256_file,
    sha256_text,
    write_json,
    write_jsonl,
)
from metacom_pm.v1_5_g4b_nonexclusive_suitability_review import (  # noqa: E402
    G4BSuitabilityReview,
    prompt_messages,
)


DESIGN = ROOT / "data/pm_v1_5_contracts/paper1_v3_g4b_review_design_v1.json"
ENDPOINTS = ROOT / "configs/pm_v1_5_strict_judge_bakeoff_v1.json"
PACKET = ROOT / "outputs/pm_v1_5_paper1_v3_g4a_packet_v2_20260811"
DEFAULT_OUT = ROOT / "outputs/pm_v1_5_paper1_v3_g4b_review_preflight_v2_20260811"
REVIEWERS = {
    "REVIEWER_A": ("anthropic_claude_haiku_4_5", "reviewer_a"),
    "REVIEWER_B": ("openai_gpt_5_mini", "reviewer_b"),
}
MAX_OUTPUT_TOKENS = 500
MAX_ATTEMPTS = 2
SEED_BASE = 20260811


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def endpoint(raw: Mapping[str, Any]) -> Endpoint:
    return Endpoint(
        base_url=str(raw["base_url"]),
        model=str(raw["model"]),
        api_key_env=str(raw["api_key_env"]),
        timeout_seconds=240.0,
        family=str(raw["family"]),
        transport=str(raw["transport"]),
        supports_strict_json_schema=bool(raw["supports_strict_json_schema"]),
        temperature_mode=str(raw.get("temperature_mode") or "explicit"),
        max_output_tokens_parameter=str(
            raw.get("max_output_tokens_parameter") or "max_tokens"
        ),
        anthropic_strict_tool_use=bool(raw.get("anthropic_strict_tool_use", False)),
        openai_reasoning_effort=raw.get("openai_reasoning_effort"),
    )


def _plan(endpoints: Mapping[str, Any]) -> list[dict[str, Any]]:
    planned: list[dict[str, Any]] = []
    for reviewer_id, (endpoint_key, stem) in REVIEWERS.items():
        ep = endpoint(endpoints["candidates"][endpoint_key])
        for call_stage, filename in (
            ("CONTROL", f"{stem}_controls.jsonl"),
            ("PUBLIC", f"{stem}_packet.jsonl"),
        ):
            for item in rows(PACKET / filename):
                messages = prompt_messages(item, reviewer_id)
                prompt_sha = sha256_text(canonical_json(messages))
                request_parameters = {
                    "temperature": 0.0,
                    "max_tokens": MAX_OUTPUT_TOKENS,
                    "seed": SEED_BASE + int(item["review_position"]),
                    "response_schema": G4BSuitabilityReview.__name__,
                    "client_internal_retries": 1,
                }
                record_ids = {
                    "reviewer_id": reviewer_id,
                    "review_item_id": item["review_item_id"],
                    "call_stage": call_stage,
                }
                planned.append(
                    {
                        "protocol": "pm-v1.5-paper1-v3-g4b-logical-call-plan-v1",
                        "call_stage": call_stage,
                        "reviewer_id": reviewer_id,
                        "review_item_id": item["review_item_id"],
                        "review_position": int(item["review_position"]),
                        "component": item["component"],
                        "endpoint_key": endpoint_key,
                        "model": ep.model,
                        "prompt_sha256": prompt_sha,
                        "logical_call_key": physical_call_key(
                            stage="paper1_v3_g4b_nonexclusive_suitability_review_v1",
                            record_ids=record_ids,
                            prompt_sha256=prompt_sha,
                            endpoint=ep,
                            request_parameters=request_parameters,
                        ),
                        "request_parameters": request_parameters,
                        "maximum_physical_attempts": MAX_ATTEMPTS,
                        "input_character_count": len(canonical_json(messages)),
                    }
                )
    return sorted(
        planned,
        key=lambda row: (
            0 if row["call_stage"] == "CONTROL" else 1,
            row["reviewer_id"],
            row["review_position"],
        ),
    )


def _cost_bound(plan: list[dict[str, Any]], endpoints: Mapping[str, Any]) -> dict[str, Any]:
    by_stage: dict[str, float] = {"CONTROL": 0.0, "PUBLIC": 0.0}
    details: dict[str, Any] = {}
    for stage in by_stage:
        stage_rows = [row for row in plan if row["call_stage"] == stage]
        subtotal = 0.0
        for row in stage_rows:
            raw = endpoints["candidates"][row["endpoint_key"]]
            # char/3 is deliberately conservative for these English JSON
            # prompts; multiply by 1.5 and charge both physical attempts.
            input_tokens = math.ceil(row["input_character_count"] / 3 * 1.5)
            per_attempt = (
                input_tokens * float(raw["input_usd_per_million_tokens"])
                + MAX_OUTPUT_TOKENS
                * float(raw["output_usd_per_million_tokens"])
            ) / 1_000_000
            subtotal += per_attempt * MAX_ATTEMPTS
        by_stage[stage] = subtotal
        details[stage] = {
            "logical_calls": len(stage_rows),
            "maximum_physical_attempts": len(stage_rows) * MAX_ATTEMPTS,
            "conservative_computed_usd": subtotal,
        }
    # Administrative caps are rounded upward and intentionally exceed the
    # conservative computed bounds. They are independent by stage.
    return {
        "protocol": "pm-v1.5-paper1-v3-g4b-cost-ceiling-v1",
        "method": "ceil(chars/3*1.5) input + full 500 output tokens, charged for both attempts",
        "CONTROL": {**details["CONTROL"], "absolute_usd_cap": 0.75},
        "PUBLIC": {**details["PUBLIC"], "absolute_usd_cap": 8.0},
        "combined_absolute_usd_cap": 8.75,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    if args.out_dir.exists():
        raise RuntimeError("G4B preflight output exists; refusing overwrite")

    design = read(DESIGN)
    endpoints = read(ENDPOINTS)
    plan = _plan(endpoints)
    counts = Counter((row["call_stage"], row["reviewer_id"]) for row in plan)
    if counts != Counter(
        {
            ("CONTROL", "REVIEWER_A"): 36,
            ("CONTROL", "REVIEWER_B"): 36,
            ("PUBLIC", "REVIEWER_A"): 507,
            ("PUBLIC", "REVIEWER_B"): 507,
        }
    ):
        raise RuntimeError(f"G4B call denominators drifted: {counts}")
    if len({row["logical_call_key"] for row in plan}) != len(plan):
        raise RuntimeError("G4B call keys are not unique")

    args.out_dir.mkdir(parents=True)
    call_plan_path = args.out_dir / "call_plan.jsonl"
    cost_path = args.out_dir / "cost_ceiling.json"
    write_jsonl(call_plan_path, plan)
    write_json(cost_path, _cost_bound(plan, endpoints))

    execution_runner = (
        ROOT / "scripts/v1_5/209l_run_paper1_v3_g4b_reviews_v1_5.py"
    ).read_text(encoding="utf-8")
    checks = {
        "single_decision_schema_has_no_retired_axes": not any(
            name in set(G4BSuitabilityReview.model_fields)
            for name in (
                "current_target_fit",
                "specific_increment_available",
                "component_minimum_possible_now",
                "current_boundary_permits",
            )
        ),
        "one_case_per_logical_call": len(plan) == 1086,
        "control_execution_cannot_name_gold_or_private_paths": all(
            token not in execution_runner
            for token in ("control_gold_key", "private_case_key", "_private_20260811")
        ),
        "reviewer_families_are_independent": len(
            {
                endpoints["candidates"][key]["family"]
                for key, _stem in REVIEWERS.values()
            }
        )
        == 2,
        "strict_schema_supported_by_both": all(
            endpoints["candidates"][key]["supports_strict_json_schema"]
            for key, _stem in REVIEWERS.values()
        ),
        "control_calls_are_exactly_72": sum(
            row["call_stage"] == "CONTROL" for row in plan
        )
        == 72,
        "public_calls_are_exactly_1014_but_not_authorized": sum(
            row["call_stage"] == "PUBLIC" for row in plan
        )
        == 1014,
        "four_axis_outputs_and_gates_are_forbidden": bool(
            design["review_schema"]["per_axis_fields_forbidden"]
            and design["review_schema"]["per_axis_accuracy_or_agreement_forbidden"]
        ),
        "nonexclusive_contract_is_explicit": bool(
            design["nonexclusive_label_and_action_invariants"]["nonexclusive"]
        ),
        "gold_first_access_is_post_response_qualification": bool(
            design["gold_isolation"]["review_execution_reads_gold"] is False
        ),
    }
    failed = [key for key, value in checks.items() if not value]
    report = {
        "protocol": "pm-v1.5-paper1-v3-g4b-review-preflight-report-v1",
        "status": (
            "G4B_REVIEW_PREFLIGHT_PASS_CONTROL_EXECUTION_PHASE_MAY_BE_DESIGNED"
            if not failed
            else "G4B_REVIEW_PREFLIGHT_FAIL"
        ),
        "checks": checks,
        "failed_checks": failed,
        "reviewers": design["reviewers"],
        "logical_calls": len(plan),
        "call_counts": {
            "controls": 72,
            "public_not_authorized": 1014,
        },
        "call_plan": {
            "path": str(call_plan_path.relative_to(ROOT)),
            "sha256": sha256_file(call_plan_path),
            "rows": len(plan),
        },
        "cost_ceiling": {
            "path": str(cost_path.relative_to(ROOT)),
            "sha256": sha256_file(cost_path),
            **read(cost_path),
        },
        "api_calls": 0,
        "reviews_created": 0,
        "labels_created": 0,
        "public_execution_authorized": False,
        "next_gate": "G4B1_EXACT_72_CONTROL_CALL_EXECUTION_PHASE",
    }
    write_json(args.out_dir / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
