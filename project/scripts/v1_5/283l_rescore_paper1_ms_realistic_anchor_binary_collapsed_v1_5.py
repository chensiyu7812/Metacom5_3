#!/usr/bin/env python3
"""Zero-API diagnostic: re-score all 4 already-collected realistic-anchor reviewer
runs (GPT-5.6, Gemini no-thinking, Gemini thinking, Claude Haiku 4.5) under a
binary-collapsed scoring convention (SEMANTIC_ABSTAIN merged into NOT_SUITABLE,
i.e. USE vs DO_NOT_USE) instead of strict 3-way exact match.

This mirrors an existing precedent already used in this project: D2's own primary
human-review analysis (docs/PM_V1_5_D2_PRIMARY_REVIEW_ANALYSIS_20260731_ZH.md)
found strict 3-class Cohen's kappa of .4854 (below its own .75 gate) between two
independent *human clinician* reviewers, but kappa jumped to .6175 (accepted-for-
production range per general LLM-judge-agreement literature) once treatment/
control/tie was collapsed to a binary on/off split. Combined with external
evidence (a follow-up emotional-support strategy-annotation study reporting
Fleiss' kappa ~.458 on a comparable categorical task, and general literature
citing human-human pairwise agreement of only 69-75%), this diagnostic checks
whether the same collapse meaningfully changes the picture for the MS anchor set.

Uses the already-corrected key (282l fixed the confirmed STALE_RESOLVED_OR_
CONFLICTING gold bug). No new API calls, no new labels, no new fits, no gate
change is applied -- this only reports what the numbers would look like under
an alternative, already-precedented scoring convention.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import read_json, read_jsonl, sha256_file, write_json  # noqa: E402


KEY = ROOT / "outputs/pm_v1_5_paper1_ms_realistic_anchor_set_private_20260812/realistic_anchor_key.jsonl"
ROUND3_RESULTS = ROOT / "outputs/pm_v1_5_paper1_ms_realistic_anchor_qualification_live_20260812/control_results_private.jsonl"
ROUND4_RESULTS = ROOT / "outputs/pm_v1_5_paper1_ms_gemini_thinking_probe_live_20260812/control_results_private.jsonl"
ROUND5_RESULTS = ROOT / "outputs/pm_v1_5_paper1_ms_claude_haiku_challenger_probe_live_20260812/control_results_private.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_ms_realistic_anchor_binary_collapsed_rescore_20260812"


def _collapse(label: str | None) -> str | None:
    if label is None:
        return None
    return "USE" if label == "SUITABLE" else "DO_NOT_USE"


def _score(results_path: Path, key: dict[str, Any]) -> dict[str, Any]:
    rows = read_jsonl(results_path)
    by_reviewer: dict[str, dict[str, Any]] = {}
    for row in rows:
        reviewer = row["reviewer_id"]
        stats = by_reviewer.setdefault(
            reviewer,
            {"n": 0, "exact_3way": 0, "exact_binary": 0, "confusion_binary": Counter(), "binary_mismatches": []},
        )
        gold = key.get(row["repair_item_id"])
        if gold is None or not row["schema_valid_and_locally_validated"]:
            continue
        observed = (row.get("validated_review") or {}).get("final_suitability")
        expected = gold["expected_final_suitability"]
        stats["n"] += 1
        if observed == expected:
            stats["exact_3way"] += 1
        obs_b = _collapse(observed)
        exp_b = _collapse(expected)
        stats["confusion_binary"][(exp_b, obs_b)] += 1
        if obs_b == exp_b:
            stats["exact_binary"] += 1
        else:
            stats["binary_mismatches"].append({
                "repair_item_id": row["repair_item_id"],
                "repair_family": gold.get("repair_family"),
                "expected_3way": expected,
                "observed_3way": observed,
            })
    for stats in by_reviewer.values():
        stats["confusion_binary"] = {f"{a}->{b}": c for (a, b), c in sorted(stats["confusion_binary"].items(), key=lambda kv: str(kv[0]))}
    return by_reviewer


def main() -> None:
    if OUT.exists():
        raise RuntimeError("binary-collapsed rescore output exists; refusing overwrite")
    key = {row["repair_item_id"]: row for row in read_jsonl(KEY)}
    gold_counts_3way = Counter(row["expected_final_suitability"] for row in key.values())
    gold_counts_binary = Counter(_collapse(row["expected_final_suitability"]) for row in key.values())

    results = {
        "round3": _score(ROUND3_RESULTS, key),
        "round4": _score(ROUND4_RESULTS, key),
        "round5": _score(ROUND5_RESULTS, key),
    }

    summary = []
    for round_name, reviewers in results.items():
        for reviewer, stats in reviewers.items():
            summary.append({
                "round": round_name,
                "reviewer": reviewer,
                "n": stats["n"],
                "exact_3way": stats["exact_3way"],
                "exact_binary": stats["exact_binary"],
                "3way_fraction": round(stats["exact_3way"] / stats["n"], 4) if stats["n"] else None,
                "binary_fraction": round(stats["exact_binary"] / stats["n"], 4) if stats["n"] else None,
            })

    report = {
        "protocol": "pm-v1.5-paper1-ms-realistic-anchor-binary-collapsed-rescore-v1",
        "status": "ZERO_API_DIAGNOSTIC_COMPLETE_NO_GATE_CHANGE_APPLIED",
        "precedent": "docs/PM_V1_5_D2_PRIMARY_REVIEW_ANALYSIS_20260731_ZH.md collapsed treatment/control/tie to binary on/off (kappa .4854 -> .6175)",
        "gold_distribution_3way": dict(gold_counts_3way),
        "gold_distribution_binary": dict(gold_counts_binary),
        "summary": summary,
        "detail_by_round": results,
        "api_calls": 0,
        "training_labels_created_or_changed": 0,
        "fits": 0,
        "gate_changed": False,
        "source_hashes": {
            "key": sha256_file(KEY),
            "round3_results": sha256_file(ROUND3_RESULTS),
            "round4_results": sha256_file(ROUND4_RESULTS),
            "round5_results": sha256_file(ROUND5_RESULTS),
        },
    }
    OUT.mkdir(parents=True)
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
