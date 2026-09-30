#!/usr/bin/env python3
"""Reparse saved Gemini finals without the old 600-character rationale ceiling.

Offline development sensitivity only: no provider request, label promotion, or
historical result overwrite. Always use the original terminal attempt.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))
from metacom_pm.io import read_json, write_json, sha256_file
from metacom_pm.paper1.evaluation.local_teacher import parse_local_verdict
from metacom_pm.paper1.evaluation.teacher_diagnostics import reference_comparison


def main():
    source = PROJECT / "outputs/paper1_pairwise_teacher/gemini_qualification_v2"
    original = read_json(source / "aligned_results.json")
    final_attempts = {}
    for path in (source / "attempts").glob("*.json"):
        record = read_json(path)
        pid = record["presentation_id"]
        if pid not in final_attempts or record["attempt"] > final_attempts[pid]["attempt"]:
            final_attempts[pid] = {**record, "path": str(path.relative_to(PROJECT)), "sha256": sha256_file(path)}
    rows, recovered = [], []
    for row in original:
        attempt = final_attempts[row["presentation_id"]]
        response = attempt["response"]
        candidates = response.get("candidates", [])
        assert len(candidates) == 1 and candidates[0]["finishReason"] == "STOP"
        parts = candidates[0]["content"]["parts"]
        assert parts and all(set(p) == {"text"} for p in parts)
        parsed = parse_local_verdict("".join(p["text"] for p in parts))
        if row["Gemini"] is not None:
            assert row["Gemini"] == parsed["verdict"]
        else:
            assert len(parsed["rationale"]) > 600
            recovered.append({"presentation_id": row["presentation_id"], "reverse_duplicate": row["reverse_duplicate"],
                "verdict": parsed["verdict"], "rationale_characters": len(parsed["rationale"]),
                "terminal_attempt_path": attempt["path"], "terminal_attempt_sha256": attempt["sha256"]})
        rows.append({**row, "candidate_verdict": parsed["verdict"]})
    assert len(rows) == 96 and len(recovered) == 4
    result = {"kind": "offline_development_parser_sensitivity", "changed_rule": "remove 600-character rationale ceiling",
        "source_aligned_results_sha256": sha256_file(source / "aligned_results.json"),
        "original_valid": 92, "reparsed_valid": 96, "recovered": recovered,
        "new_calls": 0, "new_API_cost_usd": 0, "historical_primary_overwritten": False, "teacher_promoted": False,
        "views": {view: reference_comparison([{**r, "reference_verdict": r[view]} for r in rows])
                  for view in ["original_A", "human_followup", "assistant_fact_sensitivity", "exploratory_AI_B"]}}
    dest = PROJECT / "outputs/paper1_pairwise_teacher/local_comparison_20260917_v2/historical_length_sensitivity.json"
    write_json(dest, result)
    print({"reparsed": 96, "recovered": 4,
        "original_A_base_matches": result["views"]["original_A"]["base_pairs"]["exact_matches"],
        "original_A_base_observed": result["views"]["original_A"]["base_pairs"]["observed"],
        "order": result["views"]["original_A"]["candidate_reversal"]})


if __name__ == "__main__":
    main()
