#!/usr/bin/env python3
"""Freeze a clean Gemini/GPT Function-review plan after Claude transport failure."""

from __future__ import annotations

from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import canonical_json, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_ms_executor_function_review import MSExecutorFunctionReview, prompt_messages  # noqa: E402


BASE_PATH = ROOT / "scripts/v1_5/236l_prepare_paper1_v3_ms_executor_function_proxy_preflight_v1_5.py"
spec = importlib.util.spec_from_file_location("function_preflight_v1", BASE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load frozen Function preflight helpers")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

ENDPOINTS = ROOT / "configs/pm_v1_5_strict_judge_bakeoff_v1.json"
PUBLIC = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_measurement_packet_20260811/function_packet_blind.jsonl"
CONTROLS = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_function_proxy_preflight_20260811/fresh_controls_blind.jsonl"
GOLD = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_function_proxy_preflight_20260811/fresh_control_gold_private.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_function_gemini_gpt_preflight_20260811"
REVIEWERS = {
    "FUNCTION_PROXY_GEMINI": "google_gemini_2_5_flash",
    "FUNCTION_PROXY_GPT": "openai_gpt_5_mini",
}


def main() -> None:
    if OUT.exists():
        raise RuntimeError("Gemini/GPT preflight exists; refusing overwrite")
    endpoints = base.read(ENDPOINTS)["candidates"]
    controls = base.rows(CONTROLS)
    gold = base.rows(GOLD)
    public = base.rows(PUBLIC)
    plan = []
    for reviewer_id, endpoint_key in REVIEWERS.items():
        endpoint = endpoints[endpoint_key]
        for stage, packet in (("CONTROL", controls), ("PUBLIC", public)):
            for item in packet:
                messages = prompt_messages(item, reviewer_id)
                plan.append(
                    {
                        "protocol": "pm-v1.5-paper1-v3-ms-executor-function-proxy-call-v2",
                        "logical_call_id": "msfcall2_" + base.stable(reviewer_id, stage, item["blind_item_id"]),
                        "reviewer_id": reviewer_id,
                        "endpoint_key": endpoint_key,
                        "model": endpoint["model"],
                        "stage": stage,
                        "blind_item_id": item["blind_item_id"],
                        "messages": messages,
                        "messages_sha256": sha256_text(canonical_json(messages)),
                        "seed": 20260811 + int(base.stable(reviewer_id, item["blind_item_id"], length=8), 16) % 100000,
                        "temperature": 0.0,
                        "max_output_tokens": 600,
                        "schema_sha256": sha256_text(canonical_json(MSExecutorFunctionReview.model_json_schema())),
                    }
                )
    provider_text = "\n".join(canonical_json(row["messages"]) for row in plan)
    checks = {
        "original_controls_and_gold_unchanged": sha256_file(CONTROLS) == "110de96abee26837e476619e457e843cfbfaa0b3e7c3c148e7064e470ec74933" and sha256_file(GOLD) == "7aa7af0a3f24ef83bced90ec7e2323fc7e33b296880b1a57dda3526e4d09f5f2",
        "exact_12_controls_32_public": len(controls) == 12 and len(public) == 32,
        "exact_88_calls": len(plan) == 88 and len({row["logical_call_id"] for row in plan}) == 88,
        "two_independent_non_anthropic_families": len({endpoints[key]["family"] for key in REVIEWERS.values()}) == 2 and all("anthropic" not in key for key in REVIEWERS.values()),
        "control_balance": Counter(row["gold_label"] for row in gold) == Counter({"FUNCTIONAL": 4, "NOT_USED_FINAL": 3, "SURFACE_ECHO_ONLY": 2, "BOUNDARY_FAILURE": 2, "UNRESOLVED": 1}),
        "gold_never_provider_visible": "gold_label" not in provider_text,
        "public_teacher_assignment_not_visible": "TEACHER_SUITABLE" not in provider_text and "TEACHER_NOT_SUITABLE" not in provider_text,
        "function_only": all("Do not judge overall helpfulness" in canonical_json(row["messages"]) for row in plan),
        "zero_api": True,
    }
    failed = [name for name, ok in checks.items() if not ok]
    OUT.mkdir(parents=True)
    plan_path = OUT / "call_plan_private.jsonl"
    write_jsonl(plan_path, plan)
    report = {
        "protocol": "pm-v1.5-paper1-v3-ms-executor-function-gemini-gpt-preflight-v1",
        "status": "PASS_CLEAN_NON_ANTHROPIC_SEQUENTIAL_REVIEW_MAY_BE_AUTHORIZED" if not failed else "FAIL_API_FORBIDDEN",
        "checks": checks,
        "failed_checks": failed,
        "reviewers": REVIEWERS,
        "qualification_gate_per_reviewer": {
            "exact_label_min": "10/12",
            "functional_min": "3/4",
            "not_used_min": "2/3",
            "surface_echo_min": "1/2",
            "boundary_failure": "2/2",
            "unresolved": "1/1",
            "public_calls_if_gate_fails": 0,
        },
        "execution": {"control_calls": 24, "public_calls_if_both_qualify": 64, "maximum_logical_calls": 88, "max_attempts_per_call": 2, "absolute_usd_cap": 2.0},
        "artifacts": {
            "controls": {"path": str(CONTROLS.relative_to(ROOT)), "sha256": sha256_file(CONTROLS)},
            "gold": {"path": str(GOLD.relative_to(ROOT)), "sha256": sha256_file(GOLD)},
            "plan": {"path": str(plan_path.relative_to(ROOT)), "sha256": sha256_file(plan_path)},
        },
        "abandoned_transport": "Anthropic strict tool-use only; no Claude judgment is used in qualification or public review",
        "api_calls": 0,
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
