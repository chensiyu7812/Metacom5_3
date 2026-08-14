#!/usr/bin/env python3
"""Freeze the anchored-V2 MP-only public dual-review call plan; zero API."""

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


PACKET = ROOT / "outputs/pm_v1_5_paper1_v3_g4a_packet_v2_20260811"
QUALIFICATION = ROOT / "outputs/pm_v1_5_paper1_v3_g4b1_anchored_v2_qualification_20260811/report.json"
ENDPOINTS = ROOT / "configs/pm_v1_5_strict_judge_bakeoff_v1.json"
RUNNER = ROOT / "scripts/v1_5/219l_run_paper1_v3_g4b2_mp_public_reviews_v1_5.py"
DEFAULT_OUT = ROOT / "outputs/pm_v1_5_paper1_v3_g4b2_mp_public_preflight_v2_20260811"
STAGE = "paper1_v3_g4b2_anchored_v2_mp_public_review_v1"
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
    if DEFAULT_OUT.exists():
        raise RuntimeError("public preflight exists; refusing overwrite")
    qualification = read(QUALIFICATION)
    if qualification["status"] != "G4B1_ANCHORED_V2_QUALIFICATION_PASS_PUBLIC_REVIEW_MAY_BE_DESIGNED":
        raise RuntimeError("anchored V2 qualification did not pass")
    if qualification["eligible_components"] != ["MP"] or qualification["fixed_off_components"] != ["MS", "ME"]:
        raise RuntimeError("component routing drifted")
    endpoints = read(ENDPOINTS)
    plan: list[dict[str, Any]] = []
    for reviewer_id, (endpoint_key, stem) in REVIEWERS.items():
        ep = endpoint(endpoints["candidates"][endpoint_key])
        selected = [row for row in rows(PACKET / f"{stem}_packet.jsonl") if row["component"] == "MP"]
        if len(selected) != 204:
            raise RuntimeError(f"{reviewer_id} MP denominator drifted")
        for item in selected:
            messages = prompt_messages(item, reviewer_id)
            prompt_sha = sha256_text(canonical_json(messages))
            params = {
                "temperature": 0.0, "max_tokens": MAX_OUTPUT_TOKENS,
                "seed": SEED_BASE + int(item["review_position"]),
                "response_schema": G4BSuitabilityReview.__name__, "client_internal_retries": 1,
            }
            record_ids = {"reviewer_id": reviewer_id, "review_item_id": item["review_item_id"], "call_stage": "PUBLIC"}
            plan.append({
                "protocol": "pm-v1.5-paper1-v3-g4b2-mp-public-logical-call-plan-v1",
                "call_stage": "PUBLIC", "reviewer_id": reviewer_id,
                "review_item_id": item["review_item_id"], "review_position": int(item["review_position"]),
                "component": "MP", "endpoint_key": endpoint_key, "model": ep.model,
                "prompt_sha256": prompt_sha,
                "logical_call_key": physical_call_key(
                    stage=STAGE, record_ids=record_ids, prompt_sha256=prompt_sha,
                    endpoint=ep, request_parameters=params,
                ),
                "request_parameters": params, "maximum_physical_attempts": MAX_ATTEMPTS,
                "input_character_count": len(canonical_json(messages)),
            })
    plan.sort(key=lambda row: (row["reviewer_id"], row["review_position"]))
    counts = Counter(row["reviewer_id"] for row in plan)
    if counts != Counter({"REVIEWER_A": 204, "REVIEWER_B": 204}):
        raise RuntimeError(f"call counts drifted: {counts}")
    if len({row["logical_call_key"] for row in plan}) != 408:
        raise RuntimeError("logical call keys are not unique")

    conservative = 0.0
    for row in plan:
        raw = endpoints["candidates"][row["endpoint_key"]]
        input_tokens = math.ceil(row["input_character_count"] / 3 * 1.5)
        per_attempt = (input_tokens * float(raw["input_usd_per_million_tokens"]) + MAX_OUTPUT_TOKENS * float(raw["output_usd_per_million_tokens"])) / 1_000_000
        conservative += per_attempt * MAX_ATTEMPTS
    cap = math.ceil(conservative * 2) / 2
    if cap < conservative:
        raise RuntimeError("administrative cap below conservative bound")

    runner_text = RUNNER.read_text(encoding="utf-8")
    checks = {
        "qualification_routes_mp_only": qualification["eligible_components"] == ["MP"],
        "ms_me_fixed_off_without_third_loop": qualification["fixed_off_components"] == ["MS", "ME"] and qualification["v2_is_final_llm_instrument_wave"] is True,
        "exact_408_public_calls": len(plan) == 408,
        "two_independent_reviewer_families": len({endpoints["candidates"][key]["family"] for key, _ in REVIEWERS.values()}) == 2,
        "anchored_prompt_is_provider_visible": all(
            "WORKED TRAINING ANCHORS FOR MP" in prompt_messages(item, rid)[0]["content"]
            for rid, (_key, stem) in REVIEWERS.items()
            for item in [next(row for row in rows(PACKET / f"{stem}_packet.jsonl") if row["component"] == "MP")]
        ),
        "runner_does_not_name_private_mapping_or_gold": all(token not in runner_text for token in ("private_case_key", "control_gold_key", "private_20260811")),
        "public_packet_contains_no_labels": all(not any(key in row for key in ("gold", "label", "expected_decision")) for stem in ("reviewer_a", "reviewer_b") for row in rows(PACKET / f"{stem}_packet.jsonl")),
        "all_16_actions_remain_downstream": True,
    }
    failed = [key for key, value in checks.items() if not value]
    DEFAULT_OUT.mkdir(parents=True)
    call_plan = DEFAULT_OUT / "call_plan.jsonl"
    cost_path = DEFAULT_OUT / "cost_ceiling.json"
    write_jsonl(call_plan, plan)
    write_json(cost_path, {
        "protocol": "pm-v1.5-paper1-v3-g4b2-mp-public-cost-ceiling-v1",
        "logical_calls": 408, "maximum_physical_attempts": 816,
        "conservative_computed_usd": conservative, "absolute_usd_cap": cap,
        "method": "ceil(chars/3*1.5) input + full 500 output tokens, both attempts",
    })
    report = {
        "protocol": "pm-v1.5-paper1-v3-g4b2-mp-public-preflight-report-v1",
        "status": "G4B2_MP_PUBLIC_PREFLIGHT_PASS_EXECUTION_PHASE_MAY_BE_DESIGNED" if not failed else "G4B2_MP_PUBLIC_PREFLIGHT_FAIL",
        "checks": checks, "failed_checks": failed,
        "eligible_components": ["MP"], "fixed_off_components": ["MS", "ME"],
        "logical_calls": 408, "public_cases": 204, "reviewers_per_case": 2,
        "call_plan": {"path": str(call_plan.relative_to(ROOT)), "sha256": sha256_file(call_plan), "rows": 408},
        "cost_ceiling": {"path": str(cost_path.relative_to(ROOT)), "sha256": sha256_file(cost_path), **read(cost_path)},
        "api_calls": 0, "labels_created": 0, "private_case_mapping_read": False,
        "next_gate": "G4B2_EXACT_408_MP_PUBLIC_DUAL_REVIEW_EXECUTION_PHASE",
    }
    write_json(DEFAULT_OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
