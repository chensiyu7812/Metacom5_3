#!/usr/bin/env python3
"""Independently audit the frozen MS V3 executor qualification prompts."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PREFLIGHT = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_qualification_preflight_v3_20260811"
CASES = PREFLIGHT / "qualification_cases_private.jsonl"
CALLS = PREFLIGHT / "physical_call_plan_private.jsonl"
REPORT = PREFLIGHT / "report.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_qualification_preflight_audit_20260811"


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    if OUT.exists():
        raise RuntimeError("independent preflight audit exists; refusing overwrite")
    report = read(REPORT)
    cases = rows(CASES)
    calls = rows(CALLS)
    by_case: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for call in calls:
        by_case[call["qualification_case_id"]].append(call)
    case_by_id = {row["qualification_case_id"]: row for row in cases}
    actions = {"M0+R0", "MS+R0", "M0+RS", "MS+RS"}

    provider_system = {row["physical_call_id"]: row["messages"][0]["content"] for row in calls}
    provider_all = {row["physical_call_id"]: json.dumps(row["messages"], ensure_ascii=False) for row in calls}
    exact_source_system_count = {
        row["physical_call_id"]: provider_system[row["physical_call_id"]].count(
            case_by_id[row["qualification_case_id"]]["exact_source"]
        )
        for row in calls
    }
    private_markers = (
        "TEACHER_SUITABLE",
        "TEACHER_NOT_SUITABLE",
        "LOW_INFORMATION",
        "CURRENT_ECHO",
        "ORDINARY_ATOMIC",
        "qualification_class_private",
        "teacher_decision",
    )
    forbidden_legacy = (
        "Use this exact prior-user statement",
        "requires_literal_mention",
        "It sounds like that's been weighing on you.",
    )
    checks = {
        "upstream_preflight_pass": report["status"] == "MS_V3_EXECUTOR_QUALIFICATION_PREFLIGHT_PASS_LIVE_PHASE_MAY_BE_DESIGNED",
        "upstream_hashes_bind_exact_files": report["artifacts"]["cases"]["sha256"] == sha(CASES) and report["artifacts"]["calls"]["sha256"] == sha(CALLS),
        "exact_16_states_64_calls_64_ids": len(cases) == 16 and len(calls) == 64 and len({row["physical_call_id"] for row in calls}) == 64,
        "exact_four_actions_per_state": all({row["requested_action_id"] for row in state_calls} == actions for state_calls in by_case.values()) and len(by_case) == 16,
        "balanced_classes_and_groups": Counter(row["qualification_class"] for row in cases) == Counter({"TEACHER_SUITABLE": 8, "TEACHER_NOT_SUITABLE": 8}) and len({row["split_group_key"] for row in cases}) == 8,
        "visible_context_ends_in_seeker": all(row["current_context"].splitlines()[-1].startswith("SEEKER:") for row in cases),
        "teacher_fields_not_provider_visible": all(not any(marker in text for marker in private_markers) for text in provider_all.values()),
        "legacy_literal_and_fallback_instructions_absent": all(not any(marker in text for marker in forbidden_legacy) for text in provider_all.values()),
        "meaning_absorption_and_safe_nonuse_explicit": all("Literal mention and lexical overlap are not required" in text and "leave it unused and still produce a safe current-context-grounded reply" in text for text in provider_all.values()),
        "exact_source_once_when_ms_on_zero_when_ms_off": all(exact_source_system_count[row["physical_call_id"]] == (1 if row["requested_action_id"] in {"MS+R0", "MS+RS"} else 0) for row in calls),
        "requested_eligible_planned_bits_unchanged": all(row["plan_accounting"]["requested_action_id"] == row["plan_accounting"]["structurally_eligible_action_id"] == row["plan_accounting"]["jointly_planned_action_id"] for row in calls),
        "ms_rs_never_exclusive_or_suppressed": all("relation=COMPLEMENTARY" in provider_system[row["physical_call_id"]] for row in calls if row["requested_action_id"] == "MS+RS"),
        "paired_seed_and_rotated_order": all(len({row["seed"] for row in state_calls}) == 1 and {row["within_state_call_order"] for row in state_calls} == {1, 2, 3, 4} for state_calls in by_case.values()),
        "reviewer_decision_not_used_as_runtime_input": all("teacher_decision" not in row["plan_accounting"] and "qualification_class" not in row["plan_accounting"] for row in calls),
        "zero_api_zero_refit": report["api_calls"] == 0 and report["pm_fits"] == 0,
    }
    failed = [name for name, value in checks.items() if not value]
    audit = {
        "protocol": "pm-v1.5-paper1-v3-ms-executor-qualification-preflight-independent-audit-v1",
        "status": "PASS_EXACT_64_CALL_LIVE_PHASE_MAY_BE_HASH_BOUND" if not failed else "FAIL_LIVE_EXECUTION_FORBIDDEN",
        "checks": checks,
        "failed_checks": failed,
        "scope_boundary": {
            "this_is": "bounded executor qualification over four MS-relevant actions",
            "this_is_not": "a PM refit, a quality-effect conclusion, or a reduction of the global 16-action space",
            "global_action_space_preserved": 16,
            "MP_ME_work_authorized": False,
        },
        "input_bindings": {
            "preflight_report": {"path": str(REPORT.relative_to(ROOT)), "sha256": sha(REPORT)},
            "cases": {"path": str(CASES.relative_to(ROOT)), "sha256": sha(CASES)},
            "calls": {"path": str(CALLS.relative_to(ROOT)), "sha256": sha(CALLS)},
        },
        "api_calls": 0,
        "next": "CREATE_ONE_TIME_LIVE_PHASE_BOUND_TO_THESE_HASHES" if not failed else "REPAIR_PREFLIGHT_WITHOUT_API",
    }
    write(OUT / "report.json", audit)
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
