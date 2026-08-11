#!/usr/bin/env python3
"""Create a zero-API completion assessment for the public Q/F pilot."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import write_json  # noqa: E402


QF = ROOT / "outputs/pm_v1_5_v5_3_public_qf_development_pilot_20260809"
CANARY = ROOT / "outputs/pm_v1_5_v5_3_public_learnability_canary_20260809"
FREEZE = ROOT / "outputs/pm_v1_5_v5_3_public_formal_effect_freeze_20260809"


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    rows = _jsonl(QF / "qf_results.jsonl")
    freeze = json.loads((FREEZE / "formal_effect_freeze.json").read_text())
    analysis = json.loads((FREEZE / "learnability_report.json").read_text())
    original_report = json.loads((QF / "report.json").read_text())
    risk_v2 = json.loads((CANARY / "risk_v2/report.json").read_text())

    unique_groups = {row["effect_group_id"] for row in rows}
    component_counts = Counter(row["component"] for row in rows)
    q_missing = sum(row.get("quality_effect") is None for row in rows)
    f_missing = sum(row.get("functional") is None for row in rows)
    generator_status = Counter(
        generated[arm]["status"]
        for row in rows
        for generated in row["generated"]
        for arm in ("OFF", "ON")
    )

    prompt_tokens = 0
    output_tokens = 0
    judge_calls = 0
    for row in rows:
        for call in row.get("call_records", []):
            if str(call.get("role", "")).startswith("judge_"):
                usage = call.get("usage") or {}
                prompt_tokens += int(usage.get("prompt_tokens", 0))
                output_tokens += int(usage.get("completion_tokens", 0))
                judge_calls += 1
        repair = row.get("functional_repair")
        if repair:
            usage = repair.get("usage") or {}
            prompt_tokens += int(usage.get("prompt_tokens", 0))
            output_tokens += int(usage.get("completion_tokens", 0))
            judge_calls += 1
    estimated_usd = prompt_tokens * 0.10 / 1_000_000 + output_tokens * 0.40 / 1_000_000

    checks = {
        "96_unique_groups": len(rows) == len(unique_groups) == 96,
        "24_groups_per_head": component_counts == Counter({key: 24 for key in ("MP", "MS", "ME", "RS")}),
        "quality_complete": q_missing == 0,
        "function_complete_after_targeted_repair": f_missing == 0,
        "576_generator_arms": sum(generator_status.values()) == 576,
        "all_four_development_signals_pass": analysis["status"] == "ALL_FOUR_DEVELOPMENT_SIGNALS_PASS_FORMAL_EXPANSION_GATE",
        "formal_design_frozen": freeze["formal_total_groups"] == 576,
        "automatic_risk_excluded": "excluded from labels" in freeze["risk"],
    }
    report = {
        "protocol": "pm-v1.5-v5.3-public-development-pilot-completion-assessment-v1",
        "status": "PASS_FORMAL_EXPANSION_AUTHORIZED" if all(checks.values()) else "BLOCKED",
        "checks": checks,
        "groups": len(rows),
        "component_counts": dict(component_counts),
        "generator_status_counts": dict(generator_status),
        "quality_missing": q_missing,
        "function_missing": f_missing,
        "historical_structured_output_failures": original_report["structured_output_failures"],
        "judge_usage_including_function_repair": {
            "calls": judge_calls,
            "prompt_tokens": prompt_tokens,
            "output_tokens": output_tokens,
            "estimated_usd_at_frozen_gemini_flash_lite_paid_rates": estimated_usd,
        },
        "risk_instrument_decision": {
            "status": "AUTOMATIC_RISK_JUDGE_UNQUALIFIED_EXCLUDED",
            "reason": "canary v2 still over-flagged visible-dialogue paraphrases and benign questions",
            "v2_event_counts": risk_v2["event_counts"],
            "replacement": "machine-critical full audit plus stratified blind human audit",
            "does_not_change_quality_target": True,
        },
        "formal_freeze_identity": freeze["freeze_identity"],
        "api_calls_for_this_assessment": 0,
    }
    write_json(QF / "completion_assessment.json", report)
    print({"status": report["status"], "checks": checks, "estimated_usd": round(estimated_usd, 6)})


if __name__ == "__main__":
    main()
