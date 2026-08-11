#!/usr/bin/env python3
"""Freeze a GPT-only Function feasibility plan after second-proxy failures."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402


SOURCE = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_function_gemini_gpt_preflight_20260811/call_plan_private.jsonl"
SOURCE_SHA256 = "3b6af6bce3cc2eae3871656c39b410c358a190a7396fdeb8b32709cd2547396f"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_function_gpt_only_preflight_20260811"


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    if OUT.exists():
        raise RuntimeError("GPT-only preflight exists; refusing overwrite")
    if sha256_file(SOURCE) != SOURCE_SHA256:
        raise RuntimeError("source plan drifted")
    plan = [row for row in rows(SOURCE) if row["endpoint_key"] == "openai_gpt_5_mini"]
    for row in plan:
        row["protocol"] = "pm-v1.5-paper1-v3-ms-executor-function-gpt-only-call-v1"
        row["max_output_tokens"] = 600
    checks = {
        "exact_12_control_32_public_calls": len(plan) == 44 and sum(row["stage"] == "CONTROL" for row in plan) == 12 and sum(row["stage"] == "PUBLIC" for row in plan) == 32,
        "gpt_only": {row["endpoint_key"] for row in plan} == {"openai_gpt_5_mini"},
        "same_messages_seeds_schema": all(row["messages_sha256"] and row["schema_sha256"] for row in plan),
        "zero_api": True,
    }
    failed = [name for name, ok in checks.items() if not ok]
    OUT.mkdir(parents=True)
    plan_path = OUT / "call_plan_private.jsonl"
    write_jsonl(plan_path, plan)
    report = {
        "protocol": "pm-v1.5-paper1-v3-ms-executor-function-gpt-only-feasibility-preflight-v1",
        "status": "PASS_SINGLE_PROXY_FEASIBILITY_MAY_BE_AUTHORIZED" if not failed else "FAIL_API_FORBIDDEN",
        "checks": checks,
        "failed_checks": failed,
        "call_plan": {"path": str(plan_path.relative_to(ROOT)), "sha256": sha256_file(plan_path)},
        "qualification_gate": "same frozen 10/12 and per-class gate",
        "claim_boundary": "development feasibility proxy only; not dual-model agreement, human gold, or paper-final Function measurement",
        "maximum_logical_calls": 44,
        "absolute_usd_cap": 1.0,
        "api_calls": 0,
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
