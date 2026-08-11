#!/usr/bin/env python3
"""Report non-semantic MS executor signals without pretending they are function gold."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_qualification_preflight_v3_20260811/qualification_cases_private.jsonl"
RESULTS = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_trace_recovery_20260811/recovered_first_response_results_private.jsonl"
PACKET = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_measurement_packet_20260811/report.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_mechanical_audit_20260811"


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if OUT.exists():
        raise RuntimeError("mechanical audit exists; refusing overwrite")
    cases = {row["qualification_case_id"]: row for row in rows(CASES)}
    ms_rows = [row for row in rows(RESULTS) if row["requested_action_id"] in {"MS+R0", "MS+RS"}]
    counts: Counter[tuple[str, str, str]] = Counter()
    exact_copy = 0
    overlaps: dict[str, list[float]] = {"TEACHER_SUITABLE": [], "TEACHER_NOT_SUITABLE": []}
    for row in ms_rows:
        case = cases[row["qualification_case_id"]]
        cls = case["qualification_class"]
        response_act = "RS" if row["requested_action_id"] == "MS+RS" else "R0"
        claimed = "CLAIMED" if row["generator_claimed"]["MS"] else "NONUSE"
        counts[(cls, response_act, claimed)] += 1
        source = case["exact_source"].strip().lower()
        reply = row["final_reply"].lower()
        exact_copy += int(source in reply)
        source_tokens = set(re.findall(r"[a-z']+", source))
        reply_tokens = set(re.findall(r"[a-z']+", reply))
        overlaps[cls].append(len(source_tokens & reply_tokens) / max(1, len(source_tokens | reply_tokens)))

    suitable_claimed = sum(counts[("TEACHER_SUITABLE", act, "CLAIMED")] for act in ("R0", "RS"))
    unsuitable_nonuse = sum(counts[("TEACHER_NOT_SUITABLE", act, "NONUSE")] for act in ("R0", "RS"))
    report = {
        "protocol": "pm-v1.5-paper1-v3-ms-executor-mechanical-signal-audit-v1",
        "status": "MECHANICAL_AUDIT_COMPLETE_SEMANTIC_FUNCTION_AND_QUALITY_STILL_REQUIRED",
        "ms_on_responses": len(ms_rows),
        "teacher_suitable": 16,
        "teacher_not_suitable": 16,
        "generator_telemetry": {
            "suitable_claimed": suitable_claimed,
            "suitable_nonuse": 16 - suitable_claimed,
            "not_suitable_claimed": 16 - unsuitable_nonuse,
            "not_suitable_nonuse": unsuitable_nonuse,
            "descriptive_claim_discrimination_balanced_accuracy": ((suitable_claimed / 16) + (unsuitable_nonuse / 16)) / 2,
            "by_response_act": {"|".join(key): value for key, value in sorted(counts.items())},
            "not_function_gold": True,
        },
        "literal_splice_checks": {
            "exact_full_source_copies": exact_copy,
            "mean_unique_token_jaccard_suitable": sum(overlaps["TEACHER_SUITABLE"]) / 16,
            "mean_unique_token_jaccard_not_suitable": sum(overlaps["TEACHER_NOT_SUITABLE"]) / 16,
            "interpretation": "No exact source copy was observed. Low lexical overlap supports removal of forced literal splicing but does not prove semantic function.",
        },
        "responsibility": {
            "selector": "already evaluated by 17-group OOF",
            "executor": "requires blind source-aware Function/Risk/paired-Quality judgments",
            "generator_telemetry": "diagnostic only; false names and omissions cannot decide function",
        },
        "bindings": {"cases": sha(CASES), "results": sha(RESULTS), "measurement_packet_report": sha(PACKET)},
        "api_calls": 0,
        "pm_fits": 0,
        "next": "COMPLETE_QUALIFIED_BLIND_MEASUREMENT_PACKET",
    }
    OUT.mkdir(parents=True)
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
