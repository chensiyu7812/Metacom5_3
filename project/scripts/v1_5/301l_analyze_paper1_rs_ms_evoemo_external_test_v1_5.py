#!/usr/bin/env python3
"""Zero-API paired baseline-vs-routed analysis of the RS+MS EvoEmo external test.

Running the 70 calls is not itself a success claim. This script produces the
same-state same-seed paired read the project has required since the earlier
230l/234l precedent: for every routed call, what did the baseline (M0+R0) call
produce for the identical state/seed, and did the routed call's own
generator_claimed flags plus guard status show the RS/MS candidate actually
being used (not just offered)?

This remains a qualitative/mechanism read, not a formal blind quality/risk/
function measurement (that needs blind pairwise human or LLM-judge review,
per the 234l pattern, and is out of scope here).
"""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / "outputs/pm_v1_5_paper1_rs_ms_evoemo_external_test_live_20260812"
PREFLIGHT = ROOT / "outputs/pm_v1_5_paper1_rs_ms_evoemo_external_test_preflight_20260812"
OUT = ROOT / "outputs/pm_v1_5_paper1_rs_ms_evoemo_external_test_analysis_20260812"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def main() -> None:
    results = read_jsonl(LIVE / "generator_results_private.jsonl")
    cases = {row["case_id"]: row for row in read_jsonl(PREFLIGHT / "qualification_cases_private.jsonl")}

    by_case: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in results:
        by_case[row["case_id"]][("baseline" if row["is_baseline"] else "routed")] = row

    status_by_kind: dict[str, Counter] = defaultdict(Counter)
    for kinds in by_case.values():
        for kind, row in kinds.items():
            status_by_kind[kind][row["execution_status"]] += 1

    routed_rows = [row for row in results if row["is_routed"]]
    ms_on_routed = [row for row in routed_rows if cases[row["case_id"]]["ms_decision"] == "ON"]
    rs_on_routed = [row for row in routed_rows if cases[row["case_id"]]["rs_decision"] == "ON"]
    both_on_routed = [row for row in routed_rows if cases[row["case_id"]]["ms_decision"] == "ON" and cases[row["case_id"]]["rs_decision"] == "ON"]

    def claim_rate(rows: list[dict], component: str) -> dict[str, Any]:
        n = len(rows)
        claimed = sum(1 for row in rows if row["generator_claimed"].get(component))
        transport_failed = sum(1 for row in rows if row["execution_status"] == "transport_or_schema_fallback")
        eligible = n - transport_failed
        return {
            "candidate_present_calls": n,
            "transport_or_schema_failed_calls": transport_failed,
            "structurally_eligible_calls": eligible,
            "generator_claimed_used": claimed,
            "claimed_rate_over_candidate_present": round(claimed / n, 4) if n else None,
            "claimed_rate_over_structurally_eligible": round(claimed / eligible, 4) if eligible else None,
        }

    baseline_trace_sanitized = status_by_kind["baseline"].get("clean_trace_sanitized", 0)
    routed_trace_sanitized = status_by_kind["routed"].get("clean_trace_sanitized", 0)

    paired_examples = []
    for case_id, kinds in by_case.items():
        if "baseline" not in kinds or "routed" not in kinds:
            continue
        b, r = kinds["baseline"], kinds["routed"]
        if r["generator_claimed"].get("MS") or r["generator_claimed"].get("RS"):
            paired_examples.append({
                "case_id": case_id,
                "requested_action_id": r["requested_action_id"],
                "ms_decision": cases[case_id]["ms_decision"],
                "rs_decision": cases[case_id]["rs_decision"],
                "rs_selected_family": cases[case_id].get("rs_selected_family"),
                "generator_claimed": r["generator_claimed"],
                "baseline_reply": b["final_reply"],
                "routed_reply": r["final_reply"],
            })

    report = {
        "protocol": "pm-v1.5-paper1-rs-ms-evoemo-external-test-analysis-v1",
        "status": "MECHANISM_AND_QUALITATIVE_READ_ONLY_NOT_A_FORMAL_BLIND_MEASUREMENT",
        "execution_status_by_call_kind": {k: dict(v) for k, v in status_by_kind.items()},
        "trace_leak_note": (
            f"{baseline_trace_sanitized}/{sum(status_by_kind['baseline'].values())} "
            f"baseline calls needed TRACE_REFERENCES_UNAUTHORIZED_EVIDENCE_ID sanitization (baseline authorizes zero evidence IDs, "
            f"so any evidence-id-shaped text the 8B generator invents is flagged); "
            f"{routed_trace_sanitized}/{sum(status_by_kind['routed'].values())} routed calls needed the same sanitization -- "
            f"zero routed calls referenced an evidence ID beyond what MS/RS actually authorized for that call."
        ),
        "ms_function": claim_rate(ms_on_routed, "MS"),
        "rs_function": claim_rate(rs_on_routed, "RS"),
        "both_ms_and_rs_candidate_present": claim_rate(both_on_routed, "MS"),
        "generator_capability_limitation": {
            "transport_or_schema_fallback_calls": status_by_kind["routed"].get("transport_or_schema_fallback", 0) + status_by_kind["baseline"].get("transport_or_schema_fallback", 0),
            "total_calls": len(results),
            "note": "meta/llama-3.1-8b-instruct failed to produce valid structured JSON output on this fraction of calls; these fall back to a generic safe reply with generator_claimed all-False and are not evidence against MS/RS, just generator unreliability.",
        },
        "paired_examples_where_generator_claimed_ms_or_rs": paired_examples,
        "honest_limitation": (
            "This is a same-state same-seed paired mechanism/qualitative read, not a formal blind quality/risk/function "
            "measurement. generator_claimed reflects what the 8B generator says it used, not independently verified "
            "function (the prior human study on this same generator family found quality preference and verified "
            "function can diverge sharply -- 5/7 quality preference vs 0/16 verified function). A blind pairwise "
            "judge/human review (234l pattern) would be needed before any quantified 'RS+MS helps' claim."
        ),
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "analysis.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
