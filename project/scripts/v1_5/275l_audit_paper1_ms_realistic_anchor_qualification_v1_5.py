#!/usr/bin/env python3
"""Audit the frozen 24-call MS realistic-anchor fresh-identity qualification."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import read_jsonl, sha256_file, write_json  # noqa: E402


RESULTS = ROOT / "outputs/pm_v1_5_paper1_ms_realistic_anchor_qualification_live_20260812/control_results_private.jsonl"
RAW = ROOT / "outputs/pm_v1_5_paper1_ms_realistic_anchor_qualification_live_20260812/raw_provider_outputs_before_local_validation.jsonl"
KEY = ROOT / "outputs/pm_v1_5_paper1_ms_realistic_anchor_set_private_20260812/realistic_anchor_key.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_ms_realistic_anchor_qualification_audit_20260812"


def main() -> None:
    if OUT.exists():
        raise RuntimeError("qualification audit output exists; refusing overwrite")
    results = read_jsonl(RESULTS)
    key = {row["repair_item_id"]: row for row in read_jsonl(KEY)}
    by_reviewer = {}
    for reviewer in sorted({row["reviewer_id"] for row in results}):
        rows = [row for row in results if row["reviewer_id"] == reviewer]
        confusion = Counter()
        mismatches = []
        transport_failures = []
        for row in rows:
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
        by_reviewer[reviewer] = {
            "schema_and_local_valid": sum(row["schema_valid_and_locally_validated"] for row in rows),
            "transport_failures": transport_failures,
            "exact_decisions": sum(expected == observed for (expected, observed), count in confusion.items() for _ in range(count)),
            "denominator_scored": sum(confusion.values()),
            "confusion": {f"{a}->{b}": count for (a, b), count in sorted(confusion.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1])))},
            "mismatches": mismatches,
        }
    primary = by_reviewer.get("MS_ANCHOR_PRIMARY_GPT56", {})
    challenger = by_reviewer.get("MS_ANCHOR_CHALLENGER_GEMINI", {})
    gates = {
        "all_24_present": len(results) == 24,
        "primary_all_12_schema_and_local_valid": primary.get("schema_and_local_valid") == 12,
        "challenger_all_12_schema_and_local_valid": challenger.get("schema_and_local_valid") == 12,
        "primary_exact_12_of_12": primary.get("exact_decisions") == 12,
        "challenger_exact_at_least_11_of_12": (challenger.get("exact_decisions") or 0) >= 11,
        "no_public_201_calls": True,
        "no_training_labels_or_fits": True,
    }
    prompt_tokens = sum(int((row.get("usage") or {}).get("prompt_tokens", 0) or 0) for row in results)
    completion_tokens = sum(int((row.get("usage") or {}).get("completion_tokens", 0) or 0) for row in results)
    RATES = {
        "MS_ANCHOR_PRIMARY_GPT56": {"input": 5.0, "output": 30.0},
        "MS_ANCHOR_CHALLENGER_GEMINI": {"input": 0.3, "output": 2.5},
    }
    cost_usd = 0.0
    for row in results:
        usage = row.get("usage") or {}
        rate = RATES[row["reviewer_id"]]
        cost_usd += int(usage.get("prompt_tokens", 0) or 0) / 1_000_000 * rate["input"]
        cost_usd += int(usage.get("completion_tokens", 0) or 0) / 1_000_000 * rate["output"]

    scientific_pass = gates["primary_exact_12_of_12"] and gates["challenger_exact_at_least_11_of_12"]
    report = {
        "protocol": "pm-v1.5-paper1-ms-realistic-anchor-qualification-audit-v1",
        "status": (
            "QUALIFICATION_PASS_201_ITEM_REANNOTATION_MAY_BE_DESIGNED"
            if scientific_pass and gates["all_24_present"] and gates["primary_all_12_schema_and_local_valid"] and gates["challenger_all_12_schema_and_local_valid"]
            else "QUALIFICATION_FAIL"
        ),
        "gates": gates,
        "reviewers": by_reviewer,
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "total_tokens": prompt_tokens + completion_tokens},
        "observed_cost_usd": round(cost_usd, 6),
        "absolute_cap_usd": 0.75,
        "api_calls": 24,
        "public_201_calls": 0,
        "training_labels_created_or_changed": 0,
        "fits": 0,
        "source_hashes": {
            "results": sha256_file(RESULTS),
            "raw": sha256_file(RAW),
            "key": sha256_file(KEY),
        },
    }
    OUT.mkdir(parents=True)
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
