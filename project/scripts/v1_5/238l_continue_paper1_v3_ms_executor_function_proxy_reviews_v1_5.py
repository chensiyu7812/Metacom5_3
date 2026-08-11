#!/usr/bin/env python3
"""Carry one pre-gold paid response into a fresh Function-review identity."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_ms_executor_function_review_v2 import (  # noqa: E402
    MSExecutorFunctionReview,
    validate_review_provider_safe,
)


BASE_PATH = ROOT / "scripts/v1_5/237l_run_paper1_v3_ms_executor_function_proxy_reviews_v1_5.py"
spec = importlib.util.spec_from_file_location("function_proxy_v1_runner", BASE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load V1 Function proxy runner")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

PHASE = ROOT / "data/pm_v1_5_contracts/paper1_v3_ms_executor_function_proxy_execution_phase_v2.json"
CONFIG = ROOT / "configs/paper1_v3_ms_executor_function_proxy_execution_v2.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_function_proxy_reviews_continuation_20260811"
SOURCE_RAW = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_function_proxy_reviews_20260811/raw_attempts_before_gold.jsonl"
SOURCE_RAW_SHA256 = "4824015b418dab06c2be49676b1bcf5b26f6ddc40553360d640058f6017620b6"
STAGE = "paper1_v3_ms_executor_function_proxy_review_continuation_v1"


def bootstrap_carry() -> None:
    if sha256_file(SOURCE_RAW) != SOURCE_RAW_SHA256:
        raise RuntimeError("consumed pre-gold raw response drifted")
    source_rows = runner.rows(SOURCE_RAW)
    if len(source_rows) != 1:
        raise RuntimeError("continuation requires exactly one carried raw response")
    raw = source_rows[0]
    if raw["stage"] != "CONTROL" or raw["parsed_before_gold"] is None:
        raise RuntimeError("carried response is not an eligible parsed control")
    controls = {row["blind_item_id"]: row for row in runner.rows(runner.CONTROLS)}
    plan = {row["logical_call_id"]: row for row in runner.rows(runner.PLAN)}
    call = plan[raw["logical_call_id"]]
    parsed = MSExecutorFunctionReview.model_validate(raw["parsed_before_gold"])
    reviewed = validate_review_provider_safe(parsed, controls[raw["blind_item_id"]])
    reviewed.update(
        {
            "protocol": "pm-v1.5-paper1-v3-ms-executor-function-proxy-review-v1",
            "reviewer_id": raw["reviewer_id"],
            "endpoint_key": call["endpoint_key"],
            "model": call["model"],
            "stage": raw["stage"],
            "request_hash": raw["request_hash"],
            "carry_forward": True,
        }
    )
    OUT.mkdir(parents=True, exist_ok=True)
    completed = OUT / "reviews.jsonl"
    if completed.exists():
        existing = runner.rows(completed)
        matches = [row for row in existing if row.get("blind_item_id") == raw["blind_item_id"] and row.get("reviewer_id") == raw["reviewer_id"]]
        if len(matches) != 1 or matches[0] != reviewed:
            raise RuntimeError("continuation carry receipt drifted")
    else:
        write_jsonl(completed, [reviewed])
    write_json(
        OUT / "carry_forward_receipt.json",
        {
            "protocol": "pm-v1.5-paper1-v3-ms-function-proxy-carry-v1",
            "source_raw_path": str(SOURCE_RAW.relative_to(ROOT)),
            "source_raw_sha256": SOURCE_RAW_SHA256,
            "logical_call_id": raw["logical_call_id"],
            "blind_item_id": raw["blind_item_id"],
            "reviewer_id": raw["reviewer_id"],
            "control_gold_opened_before_carry": False,
            "normalization": "cleared label-irrelevant boundary_event_quote only",
            "paid_calls_carried": 1,
            "paid_calls_remaining_maximum": 87,
        },
    )


if __name__ == "__main__":
    bootstrap_carry()
    runner.PHASE = PHASE
    runner.CONFIG = CONFIG
    runner.OUT = OUT
    runner.STAGE = STAGE
    runner.validate_review = validate_review_provider_safe
    runner.main()
