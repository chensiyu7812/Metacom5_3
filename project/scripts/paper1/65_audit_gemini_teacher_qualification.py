#!/usr/bin/env python3
"""Audit saved qualification responses and costs offline; create no labels/calls."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import canonical_json, read_json, sha256_file, sha256_text, utc_now, write_json
from metacom_pm.paper1.api_budget import CumulativePaper1ApiBudgetLedger
from metacom_pm.paper1.evaluation.gemini_teacher import MODEL, STAGE, cost, parsed_response, reported_cost
from metacom_pm.paper1.evaluation.teacher_diagnostics import index_presentations, reference_comparison, reversal_consistency
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config


def main():
    assert_pre_outcome_locked(load_public_only_config(PROJECT / "configs/paper1_public_only.yaml"))
    out = PROJECT / "outputs/paper1_pairwise_teacher/gemini_qualification_v2"
    spec = importlib.util.spec_from_file_location("qualification_runner", PROJECT / "scripts/paper1/64_run_gemini_teacher_qualification.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    plan, requests, references = runner.plan_for(PROJECT, out)
    approval = read_json(PROJECT / "data/paper1_authority/paper1_gemini_qualification_authorization_20260917_v2.json")
    runner.require_authorization(approval, plan)
    assert plan == read_json(out / "execution_plan.usage_repair_v2.json")
    results = read_json(out / "results.json")
    reqs, refs, returned = map(index_presentations, (requests, references, results))
    assert returned.keys() <= reqs.keys()
    ledger_path = PROJECT / "outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl"
    ledger = CumulativePaper1ApiBudgetLedger(ledger_path)
    events, before = defaultdict(list), []
    started = False
    for line in ledger_path.read_text().splitlines(keepends=True):
        event = json.loads(line)
        if event["stage"] == STAGE:
            started = True
            events[event["reservation_id"]].append(event)
        elif not started:
            before.append(line)
        else:
            raise AssertionError("Unexpected concurrent budget writer during qualification")
    intake = read_json(PROJECT / "outputs/paper1_pairwise_teacher/review_closeout_20260917_v1/intake_result.json")
    assert sha256_text("".join(before)) == intake["API_budget"]["ledger_sha256"]
    original = index_presentations(read_json(Path(intake["sources"]["human_A"]["path"]))["items"])
    base_groups = defaultdict(list)
    for ref in references:
        base_groups[ref["base_pair_id"]].append(original[ref["presentation_id"]])
    exact_reversals = 0
    for pair in base_groups.values():
        if len(pair) == 2:
            a, b = pair
            assert all(a[k] == b[k] for k in ("task", "task_input", "reference_material"))
            assert a["response_A"] == b["response_B"] and a["response_B"] == b["response_A"]
            exact_reversals += 1
    assert exact_reversals == 16
    attempts, grouped, cache_hashes = [], defaultdict(list), {}
    raw_cost = Decimal("0")
    discount_cost = Decimal("0")
    total_in = total_out = total_thought = total_cached = 0
    for path in sorted((out / "attempts").glob("*.json")):
        record = read_json(path)
        pid, n = record["presentation_id"], record["attempt"]
        assert pid in reqs and n in (1, 2)
        request = reqs[pid]
        assert request["body_sha256"] == record["body_sha256"]
        assert record["call_hash"] == sha256_text(canonical_json({"model": MODEL, "body_sha256": request["body_sha256"]}))
        assert record["response_sha256"] == sha256_text(canonical_json(record["response"]))
        if record.get("raw_http_body"):
            try:
                assert json.loads(record["raw_http_body"]) == record["response"]
            except json.JSONDecodeError:
                assert record["response"] == {}
        rid = f"{STAGE}:{pid}:{n}"
        assert path.name == f"{sha256_text(rid)}.json"
        history = events[rid]
        assert len(history) == 2 and history[-1]["event"] == "SETTLED"
        assert all(e["call_hash"] == record["call_hash"] for e in history)
        payload = record["response"]
        usage = payload.get("usageMetadata", {})
        parsed, parse_error = None, None
        try:
            parsed = parsed_response(payload)
        except ValueError as exc:
            parse_error = str(exc)
        candidate = (payload.get("candidates") or [{}])[0]
        text = "".join(p.get("text", "") for p in candidate.get("content", {}).get("parts", []))
        raw_verdict, rationale_chars = None, None
        try:
            raw = json.loads(text)
            if isinstance(raw, dict):
                raw_verdict = raw.get("verdict")
                rationale_chars = len(raw["rationale"]) if isinstance(raw.get("rationale"), str) else None
        except ValueError:
            pass
        estimated = reported_cost(payload)
        inp, visible, thought, cached = (usage.get(k, 0) for k in
            ("promptTokenCount", "candidatesTokenCount", "thoughtsTokenCount", "cachedContentTokenCount"))
        assert all(type(x) is int and x >= 0 for x in (inp, visible, thought, cached))
        assert cached <= inp and visible + thought <= request["maximum_output_tokens"]
        if usage.get("totalTokenCount") is not None:
            assert usage["totalTokenCount"] == inp + visible + thought
        total_in += inp
        total_out += visible
        total_thought += thought
        total_cached += cached
        if estimated is not None:
            raw_cost += estimated
            discount_cost += cost(inp - cached, visible + thought) + Decimal(cached) * Decimal("0.01") / 1000000
        detail = {"presentation_id": pid, "attempt": n, "http_status": record["http_status"],
                  "response_model_version": payload.get("modelVersion"), "finish_reason": candidate.get("finishReason"),
                  "parsed": parsed, "parse_error": parse_error, "rationale_characters": rationale_chars,
                  "raw_json_verdict_diagnostic_only": raw_verdict,
                  "thinking_tokens": thought, "prompt_tokens": inp, "visible_tokens": visible,
                  "cached_input_tokens": cached, "standard_rate_usage_cost_usd": str(estimated) if estimated is not None else None,
                  "ledger_accounting": history[-1].get("accounting"), "ledger_outcome": history[-1]["outcome"],
                  "ledger_accounted_usd": history[-1]["actual_cost_usd"]}
        attempts.append(detail)
        grouped[pid].append(detail)
        cache_hashes[str(path.relative_to(PROJECT))] = sha256_file(path)
    assert len(events) == len(attempts)
    rows = []
    for ref in references:
        pid = ref["presentation_id"]
        result = returned.get(pid, {})
        traces = sorted(grouped.get(pid, []), key=lambda x: x["attempt"])
        if traces:
            assert [a["attempt"] for a in traces] == list(range(1, len(traces) + 1))
            assert result["attempts"] == len(traces)
            assert not (len(traces) == 2 and traces[0]["parsed"] is not None)
            last = traces[-1]
            if result["status"] == "SUCCEEDED":
                assert last["parsed"] == {"verdict": result["parsed_verdict"], "rationale": result["rationale"]}
                assert last["ledger_outcome"] == "SUCCEEDED" or result["saved_settlement_reconciled_without_rebilling"]
            else:
                assert result["parsed_verdict"] is None and last["parsed"] is None
        row = {"presentation_id": pid, "item_number_A": ref["item_number_A"], "task": ref["task"],
               "base_pair_id": ref["base_pair_id"], "A_arm": ref["A_arm"], "reverse_duplicate": ref["reverse_duplicate"],
               "cluster_id": ref["cluster_id"], "original_A": ref["reference_verdict"],
               "human_followup": ref.get("followup", {}).get("verdict", ref["reference_verdict"]),
               "assistant_fact_sensitivity": ref.get("closeout", {}).get("assistant_sensitivity_verdict", ref["reference_verdict"]),
               "exploratory_AI_B": ref["candidate_verdict"],
               "Gemini": result.get("parsed_verdict"), "Gemini_status": result.get("status", "UNATTEMPTED"),
               "Gemini_rationale": result.get("rationale"), "original_A_rationale": ref["reference_rationale"],
               "exploratory_AI_B_rationale": ref["candidate_rationale"], "attempts": result.get("attempts", 0),
               "parse_errors": [a["parse_error"] for a in traces if a["parse_error"]],
               "raw_json_verdict_diagnostic_only": traces[-1]["raw_json_verdict_diagnostic_only"] if traces else None,
               "rationale_characters": traces[-1]["rationale_characters"] if traces else None}
        rows.append(row)
    ai_comparison = reference_comparison([{**r, "reference_verdict": r["exploratory_AI_B"], "candidate_verdict": r["Gemini"]} for r in rows])
    by_task = {}
    for task in sorted({r["task"] for r in rows}):
        part = [r for r in rows if r["task"] == task]
        by_task[task] = {"presentations": len(part), "status_counts": dict(Counter(r["Gemini_status"] for r in part)),
                         "base_status_counts": dict(Counter(r["Gemini_status"] for r in part if not r["reverse_duplicate"])),
                         "reversal": reversal_consistency([{**r, "candidate_verdict": r["Gemini"]} for r in part], "candidate_verdict")}
    audit = {
        "protocol": "paper1-gemini-qualification-execution-audit-v1", "created_at": utc_now(),
        "status": "COMPLETE" if len(results) == len(requests) else "PARTIAL",
        "scheduled": len(requests), "completed": len(results), "physical_calls": len(attempts),
        "retries": sum(a["attempt"] == 2 for a in attempts), "status_counts": dict(Counter(r["Gemini_status"] for r in rows)),
        "http_status_counts": dict(Counter(str(a["http_status"]) for a in attempts)),
        "finish_reason_counts": dict(Counter(str(a["finish_reason"]) for a in attempts)),
        "response_model_version_counts": dict(Counter(str(a["response_model_version"]) for a in attempts)),
        "parse_error_counts_physical_attempts": dict(Counter(a["parse_error"] for a in attempts if a["parse_error"])),
        "by_task": by_task, "AI_B_comparison_exploratory": ai_comparison,
        "token_usage": {"input": total_in, "visible_output": total_out, "thinking_output": total_thought, "cached_input": total_cached,
                        "thinking_histogram_per_physical_call": dict(Counter(str(a["thinking_tokens"]) for a in attempts))},
        "budget": {"stage_cap_usd": "0.10", "stage_accounted_usd": str(ledger.accounted_stage_cost_usd(STAGE)),
                   "standard_rate_usage_derived_usd": str(raw_cost), "usage_with_reported_cache_discount_usd": str(discount_cost),
                   "pricing_note": "Ledger conservatively uses full standard input price and preserves the first reserved-maximum settlement. Cache-adjusted figure is calculated at published rates, not a billing-invoice confirmation.",
                   "cumulative_accounted_usd": str(ledger.accounted_cost_usd), "remaining_cumulative_usd": str(ledger.remaining_usd),
                   "stage_remaining_accounted_usd": str(Decimal("0.10") - ledger.accounted_stage_cost_usd(STAGE)),
                   "unsettled_reservations": 0},
        "integrity": {"authorized_plan_sha256": approval["execution_plan_sha256"], "request_manifest_sha256": plan["requests_sha256"],
                      "preexisting_ledger_prefix_unchanged": True, "source_submissions_unchanged": True,
                      "exact_byte_swapped_reversal_pairs": exact_reversals,
                      "ledger_sha256": sha256_file(ledger_path), "results_sha256": sha256_file(out / "results.json"),
                      "reference_comparisons_sha256": sha256_file(out / "reference_comparisons.json"),
                      "attempt_cache_sha256": cache_hashes},
        "first_response_recovered_without_call": sum(bool(r.get("saved_settlement_reconciled_without_rebilling")) for r in results),
        "new_generator_calls": 0, "formal_outcomes": 0, "PM_training": 0, "outcome_locks": "ALL_CLOSED",
        "diagnostic_raw_verdicts_used_in_primary_comparisons": False,
    }
    assert ledger.accounted_stage_cost_usd(STAGE) <= Decimal("0.10")
    write_json(out / "execution_audit.json", audit)
    write_json(out / "aligned_results.json", rows)
    write_json(out / "attempt_diagnostics.json", attempts)
    with (out / "aligned_results.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({k: audit[k] for k in ("status", "physical_calls", "retries", "status_counts", "budget")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
