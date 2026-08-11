#!/usr/bin/env python3
"""Carry eight pre-gold Gemini controls after transient retry exhaustion."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASE_PATH = ROOT / "scripts/v1_5/237l_run_paper1_v3_ms_executor_function_proxy_reviews_v1_5.py"
spec = importlib.util.spec_from_file_location("function_proxy_v1_runner_transport_continuation", BASE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load V1 Function proxy runner")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402


SOURCE = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_function_gemini_gpt_reviews_20260811/reviews.jsonl"
SOURCE_SHA256 = "1c7ca8016d431b8752609beb5a42a845b6e9b42d14867a71c866a14bd5b9b6ba"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_function_gemini_gpt_reviews_continuation_20260811"


def bootstrap() -> None:
    if sha256_file(SOURCE) != SOURCE_SHA256:
        raise RuntimeError("accepted pre-gold reviews drifted")
    carried = runner.rows(SOURCE)
    if len(carried) != 8 or any(row["stage"] != "CONTROL" for row in carried):
        raise RuntimeError("exactly eight pre-gold controls must be carried")
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "reviews.jsonl"
    if target.exists():
        if runner.rows(target) != carried:
            raise RuntimeError("carried review set drifted")
    else:
        write_jsonl(target, carried)
    write_json(
        OUT / "carry_forward_receipt.json",
        {
            "protocol": "pm-v1.5-paper1-v3-ms-function-gemini-gpt-transport-carry-v1",
            "source_path": str(SOURCE.relative_to(ROOT)),
            "source_sha256": SOURCE_SHA256,
            "control_reviews_carried": 8,
            "control_gold_opened_before_carry": False,
            "maximum_new_control_calls": 16,
            "maximum_new_public_calls": 64,
            "maximum_new_logical_calls": 80,
        },
    )


if __name__ == "__main__":
    bootstrap()
    runner.PHASE = ROOT / "data/pm_v1_5_contracts/paper1_v3_ms_executor_function_gemini_gpt_execution_phase_v2.json"
    runner.CONFIG = ROOT / "configs/paper1_v3_ms_executor_function_gemini_gpt_execution_v2.json"
    runner.PREFLIGHT = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_function_gemini_gpt_preflight_20260811"
    runner.PLAN = runner.PREFLIGHT / "call_plan_private.jsonl"
    runner.OUT = OUT
    runner.STAGE = "paper1_v3_ms_executor_function_gemini_gpt_review_continuation_v1"
    runner.main()
