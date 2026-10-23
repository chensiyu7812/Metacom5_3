#!/usr/bin/env python3
"""Reconcile finished development runs and export content-free public aggregates."""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))
from metacom_pm.io import read_json, write_json, sha256_file, utc_now

EXPECTED = {
    "selene_mini_8b": 160, "compassjudger2_7b": 160, "qwen35_9b": 160,
    "selene_reasoning_first": 160, "summary_generator": 26,
    "summary_evidence_qwen35_9b": 52, "summary_evidence_compassjudger2_7b": 52,
    "summary_evidence_selene_reasoning_first": 52,
}


def main():
    current = PROJECT / "outputs/paper1_pairwise_teacher/local_comparison_20260917_v2"
    public = PROJECT / "docs/reviews/20260917"
    runs = {}
    for key, count in EXPECTED.items():
        directory = current / key
        rows = [read_json(p) for p in (directory / "responses").glob("*.json")]
        if len(rows) != count:
            raise RuntimeError(f"cannot close out incomplete scheduled run: {key}: {len(rows)}/{count}")
        requests = read_json(directory / "requests.json")
        manifest = read_json(directory / "manifest.json")
        by_id = {r["presentation_id"]: r for r in requests}
        assert len(by_id) == len(rows)
        for row in rows:
            assert row["request_sha256"] == by_id[row["presentation_id"]]["request_sha256"]
            assert row["identity_sha256"] == manifest["identity_sha256"]
        progress = read_json(directory / "progress.json")
        output_tokens = [r["output_tokens"] for r in rows]
        runs[key] = {"planned": count, "completed_records": len(rows),
            "natural_ends": sum(r["natural_end"] for r in rows),
            "statuses": dict(Counter(r["status"] for r in rows)),
            "finishes": dict(Counter(r["finish_reason"] for r in rows)),
            "engine_wall_seconds": progress.get("engine_wall_seconds", progress["seconds"]),
            "overlapping_request_seconds_not_GPU_wall": progress["seconds"],
            "output_tokens_min_median_max": [min(output_tokens), statistics.median(output_tokens), max(output_tokens)],
            "model_revision": manifest["revision"], "identity_sha256": manifest["identity_sha256"],
            "response_format": manifest.get("response_format", "JSON" if key != "summary_generator" else "original_Generator_text"),
            "backend": manifest.get("backend", "transformers"), "packages": manifest["packages"]}
    previous = read_json(current / "qwen35_9b_coding_profile_diagnostic/progress.json")
    all_starts = 0
    for path in current.glob("*/attempts.jsonl"):
        all_starts += sum(json.loads(line).get("event") == "start" for line in path.read_text().splitlines())
    evidence = read_json(current / "summary_evidence_diagnostic/statistics.json")
    comparison = read_json(current / "comparison_statistics.json")
    natural = read_json(current / "summary_natural_end_statistics.json")
    historical = read_json(current / "historical_length_sensitivity.json")
    audit = read_json(current / "existing_response_characteristics.json")
    wall = sum(r["engine_wall_seconds"] for r in runs.values()) + previous["engine_wall_seconds"] + 900
    result = {"protocol": "paper1-local-teacher-development-execution-result-v1", "completed_at": utc_now(),
        "development_scope_complete": True, "runs": runs,
        "planned_completed_records_excluding_discontinued_configurations": sum(r["completed_records"] for r in runs.values()),
        "all_recorded_generation_starts_including_discontinued_configurations": all_starts,
        "interrupted_Qwen_setup": {"recorded_starts": 1, "completed_records": 0, "conservative_wall_reserve_seconds": 900},
        "discontinued_Qwen_coding_profile": {"recorded_starts": 50, "completed_records": 46, "interrupted_active_starts": 4,
            "natural_ends": 45, "timeout_records": 1, "engine_wall_seconds": previous["engine_wall_seconds"],
            "not_combined_with_general_task_results": True},
        "conservatively_accounted_generation_wall_seconds": wall,
        "generation_budget_seconds": 14400, "within_generation_budget": wall <= 14400,
        "new_API_cost_usd": 0, "formal_outcomes": 0, "PM_training_runs": 0,
        "reference_interpretation": "joint-human and reused-sample development reference, not independent gold accuracy",
        "tests": {"non_GPU_Paper1_passed": 881, "failed": 0,
            "later_format_recovery_targeted_tests_passed": 22,
            "log_sha256": sha256_file(Path('/opt/tokkio-data0/tokkio_logs/paper1_judges/tests_paper1_final.log'))},
        "private_artifact_hashes": {str(p.relative_to(PROJECT)): sha256_file(p) for p in [
            current / "comparison_statistics.json", current / "summary_evidence_diagnostic/statistics.json",
            current / "summary_natural_end_statistics.json", current / "base80_reference_and_judges.csv",
            current / "summary_evidence_diagnostic/summary13_evidence_and_completion_comparison.csv"]}}
    write_json(current / "execution_summary.json", result)
    write_json(public / "local_teacher_execution_summary.json", result)
    write_json(public / "local_teacher_comparison_statistics.json", comparison)
    write_json(public / "local_teacher_summary_evidence_statistics.json", evidence)
    write_json(public / "summary_natural_end_statistics.json", {k: v for k, v in natural.items() if k != "paired"})
    write_json(public / "local_teacher_existing_response_characteristics.json", {k: v for k, v in audit.items() if k != "case_cards"})
    # The historical parser sensitivity includes aligned individual rows; keep it private.
    write_json(current / "historical_sensitivity_source_digest.json", {"source_sha256": sha256_file(current / "historical_length_sensitivity.json"),
        "top_level_keys": sorted(historical), "raw_historical_results_overwritten": False})
    print(json.dumps({"completed": result["planned_completed_records_excluding_discontinued_configurations"],
        "all_starts": all_starts, "accounted_wall_hours": wall / 3600, "new_API_cost_usd": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
