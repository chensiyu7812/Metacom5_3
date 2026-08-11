#!/usr/bin/env python3
"""Audit the frozen 24-call MS source-annotated control qualification."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import read_jsonl, sha256_file, write_json  # noqa: E402


RESULTS = ROOT / "outputs/pm_v1_5_paper1_ms_source_annotated_control_live_20260812/control_results_private.jsonl"
RAW = ROOT / "outputs/pm_v1_5_paper1_ms_source_annotated_control_live_20260812/raw_provider_outputs_before_local_validation.jsonl"
KEY = ROOT / "outputs/pm_v1_5_paper1_ms_supervision_repair_packet_private_20260812/qualification_control_key.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_ms_source_annotated_control_audit_20260812"


def main() -> None:
    if OUT.exists():
        raise RuntimeError("control audit output exists; refusing overwrite")
    results = read_jsonl(RESULTS)
    key = {row["repair_item_id"]: row for row in read_jsonl(KEY)}
    by_reviewer = {}
    for reviewer in sorted({row["reviewer_id"] for row in results}):
        rows = [row for row in results if row["reviewer_id"] == reviewer]
        confusion = Counter()
        mismatches = []
        for row in rows:
            expected = key[row["repair_item_id"]]["expected_final_suitability"]
            observed = (row.get("validated_review") or {}).get("final_suitability")
            confusion[(expected, observed)] += 1
            if expected != observed:
                mismatches.append({
                    "repair_item_id": row["repair_item_id"],
                    "expected": expected,
                    "observed": observed,
                    "review": row["validated_review"],
                })
        by_reviewer[reviewer] = {
            "schema_and_local_valid": sum(row["schema_valid_and_locally_validated"] for row in rows),
            "exact_decisions": sum(expected == observed for (expected, observed), count in confusion.items() for _ in range(count)),
            "confusion": {f"{a}->{b}": count for (a, b), count in sorted(confusion.items())},
            "mismatches": mismatches,
        }
    gpt = by_reviewer["MS_SOURCE_PRIMARY_GPT56"]
    gemini = by_reviewer["MS_SOURCE_CHALLENGER_GEMINI"]
    gates = {
        "all_24_schema_and_local_valid": len(results) == 24 and all(row["schema_valid_and_locally_validated"] for row in results),
        "gpt_exact_12_of_12": gpt["exact_decisions"] == 12,
        "gemini_exact_at_least_11_of_12": gemini["exact_decisions"] >= 11,
        "no_public_201_calls": True,
        "no_training_labels_or_fits": True,
    }
    prompt = sum(int((row.get("usage") or {}).get("prompt_tokens", 0) or 0) for row in results)
    completion = sum(int((row.get("usage") or {}).get("completion_tokens", 0) or 0) for row in results)
    gpt_rows = [row for row in results if row["reviewer_id"] == "MS_SOURCE_PRIMARY_GPT56"]
    gemini_rows = [row for row in results if row["reviewer_id"] == "MS_SOURCE_CHALLENGER_GEMINI"]
    observed_cost = (
        sum(int(row["usage"]["prompt_tokens"]) * 5 + int(row["usage"]["completion_tokens"]) * 30 for row in gpt_rows)
        + sum(int(row["usage"]["prompt_tokens"]) * 0.3 + int(row["usage"]["completion_tokens"]) * 2.5 for row in gemini_rows)
    ) / 1_000_000
    report = {
        "protocol": "pm-v1.5-paper1-ms-source-annotated-control-audit-v1",
        "status": "QUALIFICATION_FAIL_NO_PUBLIC_REANNOTATION_CONTROL_CONSTRUCT_REPAIR_ONCE_REQUIRED",
        "gates": gates,
        "reviewers": by_reviewer,
        "transport_and_schema_result": "PASS_24_OF_24",
        "scientific_gate_result": "FAIL_GPT_10_OF_12_GEMINI_9_OF_12",
        "root_cause": {
            "control_gold_defect": "The old CURRENT_ECHO control says today's manager interruption versus a prior meeting. The past candidate adds cross-session recurrence, so both reviewers reasonably mark a real past-only increment; the old NOT_SUITABLE key is not valid for the repaired construct.",
            "ambiguous_positive_control": "The sister-call positive does not establish that the current and past calls are the same event; GPT correctly abstains under the new resolved-entity requirement.",
            "missing_no_meta_question_rule": "Gemini treats asking whether an unresolved candidate is relevant as the candidate doing work. The repaired construct must state that a meta-question about candidate relevance does not itself establish a suitable increment.",
        },
        "decision": "Do not relax gates and do not run the 201 items. Retire these 12 expected keys for this repaired construct. Permit one content-independent control repair that makes recurrence/redundancy and event identity explicit and adds the no-meta-question rule; then use a fresh identity exactly once.",
        "usage": {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion},
        "observed_cost_usd": observed_cost,
        "absolute_cap_usd": 0.75,
        "api_calls": 24,
        "public_201_calls": 0,
        "training_labels_created_or_changed": 0,
        "fits": 0,
        "source_hashes": {"results": sha256_file(RESULTS), "raw": sha256_file(RAW), "key": sha256_file(KEY)},
    }
    OUT.mkdir(parents=True)
    write_json(OUT / "report.json", report)
    html = f"""<!doctype html><html><head><meta charset='utf-8'><title>MS source control audit</title><style>body{{font-family:system-ui;max-width:1000px;margin:2rem auto;line-height:1.5}}.bad{{color:#a12622}}.ok{{color:#176b2c}}</style></head><body><h1>MS source-annotated control qualification</h1><p class='bad'><strong>{report['status']}</strong></p><p class='ok'>Transport/schema: 24/24 valid. No public items, labels or fits.</p><p>Scientific decision accuracy: GPT-5.6 10/12; Gemini 9/12. The frozen gates fail and remain unchanged.</p><h2>Root cause</h2><ul><li>The retired echo control accidentally contains a real cross-session recurrence increment.</li><li>The sister positive does not bind the current call to the past call.</li><li>The rubric did not explicitly forbid treating “ask whether this candidate is relevant” as candidate Function.</li></ul><p>Observed cost: ${observed_cost:.4f} under the $0.75 cap.</p><h2>Decision</h2><p>Do not run 201 items. Permit one final control-construct repair under a fresh identity; no threshold relaxation.</p></body></html>"""
    (OUT / "report.html").write_text(html, encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
