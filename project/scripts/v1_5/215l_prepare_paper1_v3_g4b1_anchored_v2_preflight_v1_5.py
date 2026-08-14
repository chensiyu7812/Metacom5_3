#!/usr/bin/env python3
"""Freeze the exact 72-call G4B1 anchored V2 control plan, zero API."""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.api import Endpoint  # noqa: E402
from metacom_pm.attempt_ledger import physical_call_key  # noqa: E402
from metacom_pm.io import canonical_json, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_g4b_anchored_review_v2 import G4BSuitabilityReview, prompt_messages  # noqa: E402


ENDPOINTS = ROOT / "configs/pm_v1_5_strict_judge_bakeoff_v1.json"
PACKET = ROOT / "outputs/pm_v1_5_paper1_v3_g4b1_anchored_v2_controls_20260811"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_g4b1_anchored_v2_preflight_20260811"
REVIEWERS = {
    "REVIEWER_A": ("anthropic_claude_haiku_4_5", "reviewer_a"),
    "REVIEWER_B": ("openai_gpt_5_mini", "reviewer_b"),
}
MAX_OUTPUT_TOKENS = 500
MAX_ATTEMPTS = 2
STAGE = "paper1_v3_g4b1_anchored_v2_control_review_v1"


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def endpoint(raw: Mapping[str, Any]) -> Endpoint:
    return Endpoint(
        base_url=raw["base_url"], model=raw["model"], api_key_env=raw["api_key_env"],
        timeout_seconds=240.0, family=raw["family"], transport=raw["transport"],
        supports_strict_json_schema=raw["supports_strict_json_schema"],
        temperature_mode=raw.get("temperature_mode", "explicit"),
        max_output_tokens_parameter=raw.get("max_output_tokens_parameter", "max_tokens"),
        anthropic_strict_tool_use=raw.get("anthropic_strict_tool_use", False),
        openai_reasoning_effort=raw.get("openai_reasoning_effort"),
    )


def main() -> None:
    if OUT.exists():
        raise RuntimeError("anchored V2 preflight exists; refusing overwrite")
    endpoints = read(ENDPOINTS)
    plan = []
    cost = 0.0
    for reviewer_id, (endpoint_key, stem) in REVIEWERS.items():
        ep = endpoint(endpoints["candidates"][endpoint_key])
        for item in rows(PACKET / f"{stem}_controls.jsonl"):
            messages = prompt_messages(item, reviewer_id)
            prompt_sha = sha256_text(canonical_json(messages))
            params = {
                "temperature": 0.0,
                "max_tokens": MAX_OUTPUT_TOKENS,
                "seed": 20260811 + int(item["review_position"]),
                "response_schema": G4BSuitabilityReview.__name__,
                "client_internal_retries": 1,
            }
            record_ids = {
                "reviewer_id": reviewer_id,
                "review_item_id": item["review_item_id"],
                "call_stage": "CONTROL",
            }
            chars = len(canonical_json(messages))
            raw = endpoints["candidates"][endpoint_key]
            input_tokens = math.ceil(chars / 3 * 1.5)
            cost += MAX_ATTEMPTS * (
                input_tokens * raw["input_usd_per_million_tokens"]
                + MAX_OUTPUT_TOKENS * raw["output_usd_per_million_tokens"]
            ) / 1_000_000
            plan.append(
                {
                    "protocol": "pm-v1.5-paper1-v3-g4b1-anchored-v2-call-plan-v1",
                    "call_stage": "CONTROL",
                    "reviewer_id": reviewer_id,
                    "review_item_id": item["review_item_id"],
                    "review_position": item["review_position"],
                    "component": item["component"],
                    "endpoint_key": endpoint_key,
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
                    "input_character_count": chars,
                }
            )
    plan.sort(key=lambda row: (row["reviewer_id"], row["review_position"]))
    if len(plan) != 72 or len({row["logical_call_key"] for row in plan}) != 72:
        raise RuntimeError("anchored V2 call plan denominator/key drift")
    if not all("WORKED TRAINING ANCHORS" in prompt_messages(
        next(item for item in rows(PACKET / ("reviewer_a_controls.jsonl" if row["reviewer_id"] == "REVIEWER_A" else "reviewer_b_controls.jsonl")) if item["review_item_id"] == row["review_item_id"]), row["reviewer_id"]
    )[0]["content"] for row in plan):
        raise RuntimeError("provider-visible anchor preflight failed")
    OUT.mkdir(parents=True)
    write_jsonl(OUT / "call_plan.jsonl", plan)
    write_json(OUT / "cost_ceiling.json", {
        "protocol": "pm-v1.5-paper1-v3-g4b1-anchored-v2-cost-v1",
        "conservative_two_attempt_cost_usd": cost,
        "absolute_usd_cap": 1.0,
        "logical_calls": 72,
        "maximum_physical_attempts": 144,
    })
    report = {
        "protocol": "pm-v1.5-paper1-v3-g4b1-anchored-v2-preflight-v1",
        "status": "G4B1_ANCHORED_V2_PREFLIGHT_PASS_EXECUTION_PHASE_MAY_BE_DESIGNED",
        "logical_calls": 72,
        "worked_anchors_provider_visible_all_calls": True,
        "one_case_per_call": True,
        "control_gold_access": False,
        "public_calls": 0,
        "call_plan": {"path": str((OUT / "call_plan.jsonl").relative_to(ROOT)), "sha256": sha256_file(OUT / "call_plan.jsonl")},
        "cost": {"path": str((OUT / "cost_ceiling.json").relative_to(ROOT)), "sha256": sha256_file(OUT / "cost_ceiling.json"), "conservative_usd": cost, "cap_usd": 1.0},
        "api_calls": 0,
        "reviews_or_labels": 0,
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
