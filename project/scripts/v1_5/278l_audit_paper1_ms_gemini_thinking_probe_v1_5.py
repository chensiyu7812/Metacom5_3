#!/usr/bin/env python3
"""Audit the Gemini-thinking probe, combined with the reused GPT-5.6 primary result."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import read_json, read_jsonl, sha256_file, write_json  # noqa: E402


RESULTS = ROOT / "outputs/pm_v1_5_paper1_ms_gemini_thinking_probe_live_20260812/control_results_private.jsonl"
RAW = ROOT / "outputs/pm_v1_5_paper1_ms_gemini_thinking_probe_live_20260812/raw_provider_outputs_before_local_validation.jsonl"
KEY = ROOT / "outputs/pm_v1_5_paper1_ms_realistic_anchor_set_private_20260812/realistic_anchor_key.jsonl"
PRIOR_AUDIT = ROOT / "outputs/pm_v1_5_paper1_ms_realistic_anchor_qualification_audit_20260812/report.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_ms_gemini_thinking_probe_audit_20260812"


def main() -> None:
    if OUT.exists():
        raise RuntimeError("probe audit output exists; refusing overwrite")
    results = read_jsonl(RESULTS)
    key = {row["repair_item_id"]: row for row in read_jsonl(KEY)}
    prior_audit = read_json(PRIOR_AUDIT)

    confusion = Counter()
    mismatches = []
    transport_failures = []
    for row in results:
        gold = key.get(row["repair_item_id"])
        expected = gold["expected_final_suitability"] if gold else None
        observed = (row.get("validated_review") or {}).get("final_suitability")
        if not row["schema_valid_and_locally_validated"]:
            transport_failures.append({
                "logical_call_id": row["logical_call_id"],
                "repair_item_id": row["repair_item_id"],
                "error": row["error"],
            })
            continue
        confusion[(expected, observed)] += 1
        if expected != observed:
            mismatches.append({
                "repair_item_id": row["repair_item_id"],
                "repair_family": gold.get("repair_family"),
                "expected": expected,
                "observed": observed,
                "review": row["validated_review"],
            })

    exact_decisions = sum(expected == observed for (expected, observed), count in confusion.items() for _ in range(count))
    schema_and_local_valid = sum(row["schema_valid_and_locally_validated"] for row in results)

    prompt_tokens = sum(int((row.get("usage") or {}).get("prompt_tokens", 0) or 0) for row in results)
    completion_tokens = sum(int((row.get("usage") or {}).get("completion_tokens", 0) or 0) for row in results)
    thinking_tokens = sum(int((row.get("usage") or {}).get("thoughts_token_count", 0) or (row.get("usage") or {}).get("gemini_thought_tokens", 0) or 0) for row in results)
    cost_usd = (prompt_tokens / 1_000_000) * 0.3 + (completion_tokens / 1_000_000) * 2.5

    gemini_gate_pass = schema_and_local_valid == 12 and exact_decisions >= 11
    primary_gate_pass = prior_audit["gates"]["primary_exact_12_of_12"] and prior_audit["gates"]["primary_all_12_schema_and_local_valid"]
    overall_pass = gemini_gate_pass and primary_gate_pass

    old_gemini_exact = prior_audit["reviewers"]["MS_ANCHOR_CHALLENGER_GEMINI"]["exact_decisions"]

    report = {
        "protocol": "pm-v1.5-paper1-ms-gemini-thinking-probe-audit-v1",
        "status": "QUALIFICATION_PASS_201_ITEM_REANNOTATION_MAY_BE_DESIGNED" if overall_pass else "QUALIFICATION_FAIL",
        "gates": {
            "gemini_thinking_all_12_schema_and_local_valid": schema_and_local_valid == 12,
            "gemini_thinking_exact_at_least_11_of_12": exact_decisions >= 11,
            "primary_gpt56_reused_from_prior_round_all_pass": primary_gate_pass,
            "overall_qualification_pass": overall_pass,
        },
        "comparison": {
            "gemini_no_thinking_prior_round_exact": f"{old_gemini_exact}/12",
            "gemini_thinking_this_round_exact": f"{exact_decisions}/12",
            "delta": exact_decisions - old_gemini_exact,
        },
        "gemini_thinking": {
            "schema_and_local_valid": schema_and_local_valid,
            "transport_failures": transport_failures,
            "exact_decisions": exact_decisions,
            "confusion": {f"{a}->{b}": count for (a, b), count in sorted(confusion.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1])))},
            "mismatches": mismatches,
        },
        "primary_gpt56_reused": {
            "source": str(PRIOR_AUDIT.relative_to(ROOT)),
            "exact_decisions": prior_audit["reviewers"]["MS_ANCHOR_PRIMARY_GPT56"]["exact_decisions"],
            "denominator": 12,
        },
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "reported_thinking_tokens_field_if_present": thinking_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
        "observed_cost_usd": round(cost_usd, 6),
        "absolute_cap_usd": 0.75,
        "api_calls": 12,
        "public_201_calls": 0,
        "training_labels_created_or_changed": 0,
        "fits": 0,
        "source_hashes": {
            "results": sha256_file(RESULTS),
            "raw": sha256_file(RAW),
            "key": sha256_file(KEY),
            "prior_audit": sha256_file(PRIOR_AUDIT),
        },
    }
    OUT.mkdir(parents=True)
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
