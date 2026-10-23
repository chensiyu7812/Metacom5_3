#!/usr/bin/env python3
"""Compare fixed-answer evidence expansion and natural-end Summary development."""
from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))
from metacom_pm.io import read_json, write_json
from metacom_pm.paper1.evaluation.teacher_diagnostics import reversal_consistency
from metacom_pm.paper1.evaluation.teacher_format_recovery import recover_teacher_format, recover_reasoning_result


def usable(response, thinking, reasoning_first=False):
    if response.get("candidate_verdict"):
        return response["candidate_verdict"], response.get("rationale"), []
    if response.get("status") == "PARSE_FAILED" and response.get("natural_end"):
        try:
            parsed = (recover_reasoning_result(response["raw_output"]) if reasoning_first else
                      recover_teacher_format(response["raw_output"], thinking=thinking))
            return parsed["verdict"], parsed["rationale"], parsed["repairs"]
        except ValueError:
            pass
    return None, None, []


def main():
    current = PROJECT / "outputs/paper1_pairwise_teacher/local_comparison_20260917_v2"
    directory = current / "summary_evidence_diagnostic"
    requests = read_json(directory / "requests.json")
    assert len(requests) == 52
    statistics, table = {}, []
    for candidate in ["compassjudger2_7b", "qwen35_9b", "selene_reasoning_first"]:
        thinking = candidate == "qwen35_9b"
        primary = {p.stem: read_json(p) for p in (current / candidate / "responses").glob("*.json")}
        results = {p.stem: read_json(p) for p in (current / ("summary_evidence_" + candidate) / "responses").glob("*.json")}
        aligned = []
        for request in requests:
            r = results.get(request["presentation_id"], {})
            verdict, rationale, repairs = usable(r, thinking, candidate == "selene_reasoning_first")
            old, old_rationale, _ = usable(primary.get(request["seed_key"], {}), thinking, candidate == "selene_reasoning_first")
            aligned.append({k: v for k, v in request.items() if k != "messages"} | {
                "candidate_verdict": verdict, "rationale": rationale, "format_repairs": repairs,
                "status": r.get("status", "PENDING"), "finish_reason": r.get("finish_reason"),
                "baseline_verdict_same_order": old, "baseline_rationale_same_order": old_rationale})
        write_json(directory / (candidate + "_aligned.json"), aligned)
        groups = {}
        for variant in ["same_answers_full_history", "natural_answers_full_history"]:
            rows = [r for r in aligned if r["development_variant"] == variant]
            base = [r for r in rows if not r["reverse_duplicate"]]
            groups[variant] = {"scheduled": 26, "attempted": sum(r["status"] != "PENDING" for r in rows),
                "statuses": dict(Counter(r["status"] for r in rows)),
                "format_normalized_usable": sum(r["candidate_verdict"] is not None for r in rows),
                "base_verdicts": dict(Counter(r["candidate_verdict"] for r in base)),
                "order": reversal_consistency(rows, "candidate_verdict")}
        fixed = {r["base_pair_id"]: r for r in aligned if r["development_variant"] == "same_answers_full_history" and not r["reverse_duplicate"]}
        natural = {r["base_pair_id"]: r for r in aligned if r["development_variant"] == "natural_answers_full_history" and not r["reverse_duplicate"]}
        assert len(fixed) == len(natural) == 13
        for bid, old in sorted(fixed.items()):
            new = natural[bid]
            table.append({"candidate": candidate, "base_pair_id": bid, "A_arm": old["A_arm"],
                "baseline_short_reference": old["baseline_verdict_same_order"],
                "old_answers_full_history": old["candidate_verdict"],
                "natural_answers_full_history": new["candidate_verdict"],
                "baseline_rationale": old["baseline_rationale_same_order"],
                "old_answers_full_history_rationale": old["rationale"],
                "natural_answers_full_history_rationale": new["rationale"]})
        evidence_pairs = [r for r in fixed.values() if r["candidate_verdict"] is not None and r["baseline_verdict_same_order"] is not None]
        completion_pairs = [(fixed[k], natural[k]) for k in fixed if fixed[k]["candidate_verdict"] is not None and natural[k]["candidate_verdict"] is not None]
        unchanged_ids = {k for k in fixed if all(fixed[k][field] == natural[k][field]
            for field in ["response_A_sha256", "response_B_sha256", "reference_sha256"])}
        controls = [(a, b) for a, b in completion_pairs if a["base_pair_id"] in unchanged_ids]
        changed_inputs = [(a, b) for a, b in completion_pairs if a["base_pair_id"] not in unchanged_ids]
        statistics[candidate] = {"variants": groups,
            "source_expansion_base_comparisons": len(evidence_pairs),
            "source_expansion_changed_base_verdicts": sum(r["candidate_verdict"] != r["baseline_verdict_same_order"] for r in evidence_pairs),
            "natural_completion_base_comparisons": len(completion_pairs),
            "natural_completion_changed_base_verdicts": sum(a["candidate_verdict"] != b["candidate_verdict"] for a, b in completion_pairs),
            "unchanged_answer_base_controls": len(unchanged_ids),
            "unchanged_answer_base_controls_comparable": len(controls),
            "unchanged_answer_base_controls_verdict_changes": sum(a["candidate_verdict"] != b["candidate_verdict"] for a, b in controls),
            "changed_answer_base_comparisons": len(changed_inputs),
            "changed_answer_changed_base_verdicts": sum(a["candidate_verdict"] != b["candidate_verdict"] for a, b in changed_inputs)}
    with (directory / "summary13_evidence_and_completion_comparison.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(table[0]))
        writer.writeheader()
        writer.writerows(table)
    write_json(directory / "statistics.json", {"kind": "development_comparison_not_new_human_accuracy",
        "base_pairs": 13, "new_human_ratings": 0, "API_cost_usd": 0, "formal_labels": False,
        "sampling_note": "Qwen uses source-presentation seeds across versions; different inputs and batched inference still preclude treating changes as noiseless causal effects.",
        "candidates": statistics})
    print(statistics)


if __name__ == "__main__":
    main()
