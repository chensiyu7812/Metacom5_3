#!/usr/bin/env python3
"""Read-only analysis of local judge development, including missingness and ON labels."""
from __future__ import annotations

import json
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))
from metacom_pm.io import read_json, write_json, sha256_file
from metacom_pm.paper1.evaluation.local_teacher import binary_benefit
from metacom_pm.paper1.evaluation.teacher_format_recovery import recover_teacher_format, recover_reasoning_result
from metacom_pm.paper1.evaluation.teacher_diagnostics import (
    reference_comparison, reversal_consistency, clustered_agreement_interval,
)


def binary_comparison(rows):
    confusion = Counter()
    for r in rows:
        a = binary_benefit(r["reference_verdict"], r["A_arm"])
        b = binary_benefit(r["candidate_verdict"], r["A_arm"])
        if a is not None and b is not None:
            confusion[a, b] += 1
    n = sum(confusion.values())
    predicted_positive = confusion[0, 1] + confusion[1, 1]
    reference_positive = confusion[1, 0] + confusion[1, 1]
    return {"comparable": n, "matches": confusion[0, 0] + confusion[1, 1],
            "reference0_candidate0": confusion[0, 0], "reference0_candidate1": confusion[0, 1],
            "reference1_candidate0": confusion[1, 0], "reference1_candidate1": confusion[1, 1],
            "always_zero_matches_on_same_subset": confusion[0, 0] + confusion[0, 1],
            "positive_precision_against_reference": confusion[1, 1] / predicted_positive if predicted_positive else None,
            "positive_recall_against_reference": confusion[1, 1] / reference_positive if reference_positive else None,
            "reference_uncertain_candidate_decisive": sum(r["reference_verdict"] == "uncertain" and
                r["candidate_verdict"] in {"A_better", "B_better"} for r in rows),
            "uncertain_reference_is_not_automatic_candidate_error": True,
            "combined_with_official_anchors": False, "formal_training_labels": False}


def binary_reversal(rows):
    groups = defaultdict(list)
    for r in rows:
        groups[r["base_pair_id"]].append(binary_benefit(r["candidate_verdict"], r["A_arm"]))
    usable = [v for v in groups.values() if len(v) == 2 and all(x is not None for x in v)]
    consistent = sum(v[0] == v[1] for v in usable)
    return {"comparable_pairs": len(usable), "consistent": consistent,
            "rate": consistent / len(usable) if usable else None,
            "missing_or_uncertain_pairs": len(groups) - len(usable)}


def stable_determinate_bases(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row["base_pair_id"]].append(row)
    selected = []
    flip = {"A_better": "B_better", "B_better": "A_better"}
    for pair in groups.values():
        assert len(pair) == 2
        base = next(r for r in pair if r["is_base"])
        reverse = next(r for r in pair if not r["is_base"])
        verdict = base["candidate_verdict"]
        if verdict in {"A_better", "B_better", "equivalent"} and verdict == flip.get(reverse["candidate_verdict"], reverse["candidate_verdict"]):
            selected.append(base)
    return selected


def main():
    root = PROJECT / "outputs/paper1_pairwise_teacher"
    current = root / "local_comparison_20260917_v2"
    original = read_json(root / "gemini_qualification_v2/aligned_results.json")
    old_by_id = {r["presentation_id"]: r for r in original}
    old_base = {r["base_pair_id"]: r for r in original if not r["reverse_duplicate"]}
    mapping = read_json(root / "local_comparison_proposal_20260917_v1/presentation_mapping.json")
    preflight = {r["base_pair_id"]: r for r in map(json.loads,
        (PROJECT / "data/paper1_authority/paper1_pairwise_teacher_base_pair_preflight_20260904_v1.jsonl").read_text().splitlines())}
    all_stats = {}
    aligned_by_candidate = {}
    candidates = ["selene_mini_8b", "compassjudger2_7b", "qwen35_9b", "selene_reasoning_first"]
    for candidate in candidates:
        directory = current / candidate
        result = {}
        segments = [directory, current / (candidate + "_continuation")]
        for segment in segments:
            for path in (segment / "responses").glob("*.json"):
                response = read_json(path)
                pid = response["presentation_id"]
                if pid in result:
                    raise ValueError("presentation duplicated across execution segments")
                if response["status"] == "PARSE_FAILED" and response.get("natural_end"):
                    try:
                        response["format_recovery"] = (recover_reasoning_result(response["raw_output"])
                            if candidate == "selene_reasoning_first" else
                            recover_teacher_format(response["raw_output"], thinking=candidate == "qwen35_9b"))
                    except ValueError:
                        pass
                result[pid] = response
        aligned = []
        for m in mapping:
            source = old_base[m["base_pair_id"]]
            a_arm = source["A_arm"] if m["is_base"] else ("OFF" if source["A_arm"] == "ON" else "ON")
            response = result.get(m["presentation_id"], {})
            aligned.append({**m, "A_arm": a_arm, "reverse_duplicate": not m["is_base"],
                "head": preflight[m["base_pair_id"]]["head"], "cluster_id": source["cluster_id"],
                "candidate_verdict": response.get("candidate_verdict"),
                "status": response.get("status", "PENDING"), "input_tokens": response.get("input_tokens"),
                "rationale": response.get("rationale"), "finish_reason": response.get("finish_reason"),
                "format_recovery": response.get("format_recovery"),
                "output_tokens": response.get("output_tokens"), "seconds": response.get("seconds")})
        aligned_by_candidate[candidate] = aligned
        write_json(directory / "aligned_results.json", aligned)
        stats = {"scheduled": 160, "attempted": len(result), "base_pairs": 80,
                 "development_variant": "output_format_only_after_baseline_inspection" if candidate == "selene_reasoning_first" else "shared_JSON_prompt_candidate",
                 "execution_segments": [str(s.relative_to(PROJECT)) for s in segments if (s / "manifest.json").exists()],
                 "statuses": dict(Counter(r["status"] for r in aligned)),
                 "order_all_80": reversal_consistency(aligned, "candidate_verdict"),
                 "binary_order_all_80": binary_reversal(aligned),
                 "order_original_16": reversal_consistency([r for r in aligned if r["presentation_id"] in old_by_id], "candidate_verdict"),
                 "views": {}, "task_coverage": {}, "head_coverage": {}}
        for view in ["original_A", "human_followup", "assistant_fact_sensitivity", "exploratory_AI_B"]:
            rows = [{**r, "reference_verdict": old_by_id[r["presentation_id"]][view]}
                    for r in aligned if r["presentation_id"] in old_by_id]
            base = [r for r in rows if not r["reverse_duplicate"]]
            stats["views"][view] = {"four_class": reference_comparison(rows),
                "binary": binary_comparison(base),
                "binary_by_task": {t: binary_comparison([r for r in base if r["task"] == t])
                                   for t in sorted({r["task"] for r in base})},
                "clustered_by_task": {t: clustered_agreement_interval([r for r in base if r["task"] == t])
                                      for t in sorted({r["task"] for r in base})}}
        for field, key in [("task", "task_coverage"), ("head", "head_coverage")]:
            for group in sorted({r[field] for r in aligned}):
                rs = [r for r in aligned if r[field] == group and r["is_base"]]
                stats[key][group] = {"planned_bases": len(rs), "valid": sum(r["status"] == "SUCCEEDED" for r in rs),
                    "determinate": sum(r["candidate_verdict"] in {"A_better", "B_better", "equivalent"} for r in rs),
                    "verdicts": dict(Counter(r["candidate_verdict"] for r in rs)),
                    "order": reversal_consistency([r for r in aligned if r[field] == group], "candidate_verdict")}
        normalized = [{**r, "candidate_verdict": r["candidate_verdict"] or (r.get("format_recovery") or {}).get("verdict")} for r in aligned]
        stats["format_normalized_sensitivity"] = {
            "recovered_presentations": sum(bool(r.get("format_recovery")) for r in aligned),
            "usable_presentations": sum(r["candidate_verdict"] is not None for r in normalized),
            "order": reversal_consistency(normalized, "candidate_verdict"),
            "order_by_task": {task: reversal_consistency([r for r in normalized if r["task"] == task], "candidate_verdict")
                              for task in sorted({r["task"] for r in normalized})},
            "base_verdicts_by_task": {task: dict(Counter(r["candidate_verdict"] for r in normalized if r["is_base"] and r["task"] == task))
                                      for task in sorted({r["task"] for r in normalized})},
            "binary_order": binary_reversal(normalized), "views": {}}
        for view in ["original_A", "human_followup", "assistant_fact_sensitivity"]:
            rs = [{**r, "reference_verdict": old_by_id[r["presentation_id"]][view]}
                  for r in normalized if r["presentation_id"] in old_by_id]
            stats["format_normalized_sensitivity"]["views"][view] = {
                "four_class": reference_comparison(rs),
                "binary": binary_comparison([r for r in rs if r["is_base"]])}
        stable = stable_determinate_bases(normalized)
        stats["order_stable_determinate_subset_diagnostic"] = {
            "covered_bases": len(stable), "scheduled_bases": 80,
            "per_task": dict(Counter(r["task"] for r in stable)),
            "verdicts": dict(Counter(r["candidate_verdict"] for r in stable)),
            "agreement_does_not_establish_correctness": True,
            "formal_labels": False,
            "binary_vs_human_followup": binary_comparison([{**r,
                "reference_verdict": old_by_id[r["presentation_id"]]["human_followup"]} for r in stable])}
        all_stats[candidate] = stats
    common = set.intersection(*[{r["presentation_id"] for r in aligned_by_candidate[key] if r["is_base"] and r["status"] == "SUCCEEDED"}
                               for key in candidates[:3]])
    for candidate, aligned in aligned_by_candidate.items():
        rows = [{**r, "reference_verdict": old_by_id[r["presentation_id"]]["original_A"]}
                for r in aligned if r["presentation_id"] in common]
        all_stats[candidate]["shared_valid_base_comparison"] = reference_comparison(rows)
    write_json(current / "comparison_statistics.json", {"role": "development_evidence_not_independent_gold_accuracy",
        "format_recovery_implementation_sha256": sha256_file(PROJECT / "src/metacom_pm/paper1/evaluation/teacher_format_recovery.py"),
        "shared_valid_bases": len(common), "candidates": all_stats})
    indexed = {key: {r["presentation_id"]: r for r in rows} for key, rows in aligned_by_candidate.items()}
    reverses = {m["base_pair_id"]: m["presentation_id"] for m in mapping if not m["is_base"]}
    table = []
    for original_row in original:
        if original_row["reverse_duplicate"]:
            continue
        pid = original_row["presentation_id"]
        row = {k: original_row[k] for k in ["presentation_id", "base_pair_id", "task", "A_arm",
            "original_A", "human_followup", "assistant_fact_sensitivity", "exploratory_AI_B"]}
        row["Gemini_historical"] = original_row["Gemini"]
        for candidate, candidate_rows in indexed.items():
            answer = candidate_rows[pid]
            reverse = candidate_rows[reverses[row["base_pair_id"]]]["candidate_verdict"]
            row[candidate + "_verdict"] = answer["candidate_verdict"]
            row[candidate + "_reversed_normalized"] = {"A_better": "B_better", "B_better": "A_better"}.get(reverse, reverse)
            row[candidate + "_ON_benefit"] = binary_benefit(answer["candidate_verdict"], answer["A_arm"])
            row[candidate + "_rationale"] = answer["rationale"]
            row[candidate + "_format_recovered_verdict"] = (answer.get("format_recovery") or {}).get("verdict")
            row[candidate + "_format_repairs"] = ";".join((answer.get("format_recovery") or {}).get("repairs", []))
        table.append(row)
    assert len(table) == 80
    with (current / "base80_reference_and_judges.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(table[0]))
        writer.writeheader()
        writer.writerows(table)
    print(json.dumps({k: {"attempted": v["attempted"], "statuses": v["statuses"], "order": v["order_all_80"],
         "binary_original_A": v["views"]["original_A"]["binary"]} for k, v in all_stats.items()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
