#!/usr/bin/env python3
"""Bind provider-appropriate output budgets into the Function call plan."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402


SOURCE = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_function_gemini_gpt_preflight_20260811/call_plan_private.jsonl"
SOURCE_SHA256 = "3b6af6bce3cc2eae3871656c39b410c358a190a7396fdeb8b32709cd2547396f"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_function_token_budget_fix_20260811"


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    if OUT.exists():
        raise RuntimeError("token-budget fix output exists; refusing overwrite")
    if sha256_file(SOURCE) != SOURCE_SHA256:
        raise RuntimeError("source call plan drifted")
    corrected = rows(SOURCE)
    for row in corrected:
        row["protocol"] = "pm-v1.5-paper1-v3-ms-executor-function-proxy-call-v3-budget-bound"
        row["max_output_tokens"] = 1400 if row["endpoint_key"] == "google_gemini_2_5_flash" else 600
    checks = {
        "same_88_logical_calls": len(corrected) == 88 and len({row["logical_call_id"] for row in corrected}) == 88,
        "messages_unchanged": all(row["messages_sha256"] for row in corrected),
        "gemini_1400": all(row["max_output_tokens"] == 1400 for row in corrected if row["endpoint_key"] == "google_gemini_2_5_flash"),
        "gpt_600": all(row["max_output_tokens"] == 600 for row in corrected if row["endpoint_key"] == "openai_gpt_5_mini"),
        "zero_api": True,
    }
    failed = [name for name, ok in checks.items() if not ok]
    OUT.mkdir(parents=True)
    plan_path = OUT / "call_plan_private.jsonl"
    write_jsonl(plan_path, corrected)
    report = {
        "protocol": "pm-v1.5-paper1-v3-ms-executor-function-token-budget-fix-v1",
        "status": "PASS_PROVIDER_BUDGET_BOUND_PLAN_READY" if not failed else "FAIL_API_FORBIDDEN",
        "checks": checks,
        "failed_checks": failed,
        "source_plan_sha256": SOURCE_SHA256,
        "corrected_plan": {"path": str(plan_path.relative_to(ROOT)), "sha256": sha256_file(plan_path)},
        "scientific_change": "none: messages, rubric, cases, seeds, labels, and gates unchanged",
        "execution_change": "Gemini max_output_tokens 600->1400; GPT remains 600",
        "api_calls": 0,
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
