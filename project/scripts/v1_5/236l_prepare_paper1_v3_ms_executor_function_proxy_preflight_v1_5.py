#!/usr/bin/env python3
"""Freeze fresh Function controls and an outcome-blind two-proxy call plan."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import canonical_json, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_ms_executor_function_review import MSExecutorFunctionReview, prompt_messages  # noqa: E402


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
CLOSEOUT = ROOT / "data/pm_v1_5_contracts/paper1_v3_ms_executor_measurement_packet_closeout_v1.json"
PUBLIC = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_measurement_packet_20260811/function_packet_blind.jsonl"
ENDPOINTS = ROOT / "configs/pm_v1_5_strict_judge_bakeoff_v1.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_function_proxy_preflight_20260811"
REVIEWERS = {
    "FUNCTION_PROXY_A": "anthropic_claude_haiku_4_5",
    "FUNCTION_PROXY_B": "openai_gpt_5_mini",
}


def stable(*values: object, length: int = 24) -> str:
    return hashlib.sha256("\u241f".join(map(str, values)).encode()).hexdigest()[:length]


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def control_specs() -> list[tuple[str, str, str, str]]:
    return [
        ("The review meeting is tomorrow and I fear going blank again.", "Earlier I went blank when I was asked for an answer without preparation time.", "When this happened before, answering without preparation was the hard part. Would asking for a brief minute to gather your thoughts feel useful this time, or has the situation changed?", "FUNCTIONAL"),
        ("My sister ended our call abruptly again, and I want one careful way to reopen it.", "Last month my sister ended our call as soon as retirement money came up.", "Money was where the earlier call stopped. Would it feel safer to first ask whether she is willing to discuss that topic now, or is this call different?", "FUNCTIONAL"),
        ("The afternoon dizziness returned and I want to describe its timing without assuming a cause.", "Previously the dizziness began shortly after my late shift ended.", "You noticed it after a late shift before. Did it begin around the same point today, or has the timing changed?", "FUNCTIONAL"),
        ("I want the least demanding way to reopen my portfolio today.", "Previously opening just one image file made restarting feel possible.", "Would opening one image file feel like a small enough re-entry today, or would something else fit better now?", "FUNCTIONAL"),
        ("I need help understanding this tuition bill.", "Thank you for listening yesterday.", "We can take the bill one line at a time and identify which charge is unclear.", "NOT_USED_FINAL"),
        ("I am worried about a new lease clause.", "Last spring I enjoyed walking my dog before dinner.", "Which sentence in the lease feels most uncertain or consequential right now?", "NOT_USED_FINAL"),
        ("I need help deciding what to say after the argument.", "I did not like the tea at the cafe last week.", "What outcome would you most want from the next conversation?", "NOT_USED_FINAL"),
        ("I already said I feel isolated every Sunday.", "Earlier I said Sundays often felt isolating.", "It sounds isolating to feel alone on Sundays.", "SURFACE_ECHO_ONLY"),
        ("I already explained that I panicked during today's review.", "During an earlier review I panicked when the questions began.", "Reviews can feel panicky when questions begin.", "SURFACE_ECHO_ONLY"),
        ("I am worried about tomorrow but have not said how I sleep now.", "Months ago I could not sleep before an interview.", "You still cannot sleep at night, so insomnia is clearly your ongoing pattern.", "BOUNDARY_FAILURE"),
        ("I want to think about whether that old conversation still matters.", "I felt ashamed when my manager interrupted me.", "I felt ashamed when my manager interrupted me, so we should confront him now.", "BOUNDARY_FAILURE"),
        ("They dismissed my idea again, but I have not said whether this was my supervisor or study partner.", "Earlier my supervisor dismissed an idea before hearing it.", "When they dismissed you again, it may help to ask what they need clarified.", "UNRESOLVED"),
    ]


def main() -> None:
    if OUT.exists():
        raise RuntimeError("Function proxy preflight exists; refusing overwrite")
    authority = read(AUTHORITY)
    active = authority["active_v3_phase"]
    if active["id"] != "MS_EXECUTOR_QUALIFIED_REVIEW_PENDING":
        raise RuntimeError("Function review is not the active phase")
    if active["active_phase_manifest"] != {"path": str(CLOSEOUT.relative_to(ROOT)), "sha256": sha256_file(CLOSEOUT)}:
        raise RuntimeError("measurement packet closeout drifted")
    endpoints = read(ENDPOINTS)["candidates"]
    public = rows(PUBLIC)
    controls = []
    gold = []
    for index, (current, source, response, label) in enumerate(control_specs(), 1):
        case_id = "msfctrl_" + stable(index, current, source, response)
        controls.append({
            "protocol": "pm-v1.5-paper1-v3-ms-executor-function-fresh-control-v1",
            "blind_item_id": case_id,
            "visible_current_dialogue": "SEEKER: " + current,
            "strictly_past_user_owned_source": source,
            "response": response,
        })
        gold.append({"blind_item_id": case_id, "gold_label": label})

    plan = []
    for reviewer_id, endpoint_key in REVIEWERS.items():
        endpoint = endpoints[endpoint_key]
        for stage, packet in (("CONTROL", controls), ("PUBLIC", public)):
            for item in packet:
                messages = prompt_messages(item, reviewer_id)
                plan.append({
                    "protocol": "pm-v1.5-paper1-v3-ms-executor-function-proxy-call-v1",
                    "logical_call_id": "msfcall_" + stable(reviewer_id, stage, item["blind_item_id"]),
                    "reviewer_id": reviewer_id,
                    "endpoint_key": endpoint_key,
                    "model": endpoint["model"],
                    "stage": stage,
                    "blind_item_id": item["blind_item_id"],
                    "messages": messages,
                    "messages_sha256": sha256_text(canonical_json(messages)),
                    "seed": 20260811 + int(stable(reviewer_id, item["blind_item_id"], length=8), 16) % 100000,
                    "temperature": 0.0,
                    "max_output_tokens": 600,
                    "schema_sha256": sha256_text(canonical_json(MSExecutorFunctionReview.model_json_schema())),
                })
    provider_text = "\n".join(canonical_json(row["messages"]) for row in plan)
    checks = {
        "exact_12_controls_32_public": len(controls) == 12 and len(public) == 32,
        "exact_88_calls": len(plan) == 88 and len({row["logical_call_id"] for row in plan}) == 88,
        "two_independent_model_families": len({endpoints[key]["family"] for key in REVIEWERS.values()}) == 2,
        "control_balance": Counter(row["gold_label"] for row in gold) == Counter({"FUNCTIONAL": 4, "NOT_USED_FINAL": 3, "SURFACE_ECHO_ONLY": 2, "BOUNDARY_FAILURE": 2, "UNRESOLVED": 1}),
        "gold_never_provider_visible": not any(label in provider_text for label in ("gold_label", "msfctrl_" + "never")),
        "public_teacher_assignment_not_visible": "TEACHER_SUITABLE" not in provider_text and "TEACHER_NOT_SUITABLE" not in provider_text,
        "function_only_not_quality_risk": all("Do not judge overall helpfulness" in text for text in (canonical_json(row["messages"]) for row in plan)),
        "schema_frozen": len({row["schema_sha256"] for row in plan}) == 1,
        "zero_api": True,
    }
    failed = [name for name, ok in checks.items() if not ok]
    OUT.mkdir(parents=True)
    controls_path = OUT / "fresh_controls_blind.jsonl"
    gold_path = OUT / "fresh_control_gold_private.jsonl"
    plan_path = OUT / "call_plan_private.jsonl"
    write_jsonl(controls_path, controls)
    write_jsonl(gold_path, gold)
    write_jsonl(plan_path, plan)
    report = {
        "protocol": "pm-v1.5-paper1-v3-ms-executor-function-proxy-preflight-v1",
        "status": "PASS_SEQUENTIAL_CONTROL_QUALIFICATION_AND_PUBLIC_REVIEW_MAY_BE_AUTHORIZED" if not failed else "FAIL_API_FORBIDDEN",
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
            "controls": {"path": str(controls_path.relative_to(ROOT)), "sha256": sha256_file(controls_path)},
            "gold": {"path": str(gold_path.relative_to(ROOT)), "sha256": sha256_file(gold_path)},
            "plan": {"path": str(plan_path.relative_to(ROOT)), "sha256": sha256_file(plan_path)},
        },
        "source_hashes": {"authority": sha256_file(AUTHORITY), "closeout": sha256_file(CLOSEOUT), "public_function_packet": sha256_file(PUBLIC), "instrument": sha256_file(ROOT / "src/metacom_pm/v1_5_ms_executor_function_review.py"), "endpoints": sha256_file(ENDPOINTS)},
        "api_calls": 0,
        "next": "INDEPENDENT_PREFLIGHT_AUDIT_THEN_ONE_TIME_SEQUENTIAL_LIVE_PHASE",
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
