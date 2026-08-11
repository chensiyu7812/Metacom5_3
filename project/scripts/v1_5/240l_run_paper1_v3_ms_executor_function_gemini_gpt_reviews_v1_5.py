#!/usr/bin/env python3
"""Run the frozen Gemini/GPT Function plan through the raw-first V1 engine."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASE_PATH = ROOT / "scripts/v1_5/237l_run_paper1_v3_ms_executor_function_proxy_reviews_v1_5.py"
spec = importlib.util.spec_from_file_location("function_proxy_v1_runner_clean", BASE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load V1 Function proxy runner")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

runner.PHASE = ROOT / "data/pm_v1_5_contracts/paper1_v3_ms_executor_function_gemini_gpt_execution_phase_v1.json"
runner.CONFIG = ROOT / "configs/paper1_v3_ms_executor_function_gemini_gpt_execution_v1.json"
runner.PREFLIGHT = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_function_gemini_gpt_preflight_20260811"
runner.PLAN = runner.PREFLIGHT / "call_plan_private.jsonl"
runner.OUT = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_function_gemini_gpt_reviews_20260811"
runner.STAGE = "paper1_v3_ms_executor_function_gemini_gpt_review_v1"


if __name__ == "__main__":
    runner.main()
