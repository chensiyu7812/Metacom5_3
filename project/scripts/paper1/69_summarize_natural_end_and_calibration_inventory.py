#!/usr/bin/env python3
"""Summarize the natural-end diagnostic and inventory prospective top-k work."""
from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))
from metacom_pm.io import read_json, write_json, sha256_file


def lines(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def main():
    root = PROJECT / "outputs/paper1_pairwise_teacher"
    current = root / "local_comparison_20260917_v2"
    old = {r["request_id"]: r for p in (root / "local_generator_success_cache_v1").glob("*.json")
           if (r := read_json(p)).get("task") == "Summary"}
    new = [read_json(p) for p in (current / "summary_generator/responses").glob("*.json")]
    assert len(old) == len(new) == 26
    paired = []
    for row in new:
        previous = old[row["presentation_id"]]
        assert row["old_request_sha256"] == previous["request_sha256"]
        paired.append({"request_id": row["presentation_id"], "base_pair_ids": row["base_pair_ids"],
            "arm": row["arm"], "old_finish": previous["finish_reason"], "new_finish": row["finish_reason"],
            "new_output_tokens": row["output_tokens"], "old_text_is_prefix": row["raw_output"].startswith(previous["raw_text"]),
            "identical_text": row["raw_output"] == previous["raw_text"]})
    summary = {"kind": "development_diagnostic", "requests": 26, "paired": paired, "by_arm": {},
        "new_API_cost_usd": 0, "old_outputs_and_ratings_overwritten": False,
        "timing_note": "Early requests overlapped an interrupted Qwen setup attempt on A6000; timing is not a formal latency measurement.",
        "quality_note": "Completion is not correctness. Several OFF continuations still fabricate events or use the system worked-example identity."}
    for arm in ["ON", "OFF"]:
        selected = [r for r in paired if r["arm"] == arm]
        tokens = [r["new_output_tokens"] for r in selected]
        summary["by_arm"][arm] = {"requests": len(selected), "old_length_stops": sum(r["old_finish"] == "length" for r in selected),
            "new_natural_stops": sum(r["new_finish"] == "stop" for r in selected),
            "min_output_tokens": min(tokens), "median_output_tokens": statistics.median(tokens), "max_output_tokens": max(tokens),
            "all_old_texts_preserved_as_prefix": all(r["old_text_is_prefix"] for r in selected),
            "unchanged_former_natural_stops": sum(r["old_finish"] == "stop" and r["identical_text"] for r in selected)}
    write_json(current / "summary_natural_end_statistics.json", summary)

    ranking_path = PROJECT / "data/paper1_public_memory/es_memeval_public_active_multi_view_bge_top8_v1.jsonl"
    fold_path = PROJECT / "data/paper1_public_memory/es_memeval_public_outer_fold_assignments_k5_seed0_v1.jsonl"
    esc_path = PROJECT / "data/paper1_authority/paper1_esc_split_large52_frozen_v1.jsonl"
    rankings, folds, esc = lines(ranking_path), lines(fold_path), lines(esc_path)
    fold_map = {r["target_id"]: r for r in folds}
    assert len(fold_map) == len(folds) == 1586
    assert len({(r["target_id"], r["head"]) for r in rankings}) == len(rankings) == 4656
    components = {}
    for r in folds:
        components.setdefault(r["group_component_id"], set()).add(r["outer_fold"])
    assert all(len(values) == 1 for values in components.values())
    inventory = []
    for r in rankings:
        f = fold_map[r["target_id"]]
        assert r["task_type"] == f["task_type"]
        for k in [1, 2, 3, 4]:
            selected = r["ranked_candidates"][:k]
            assert len(selected) == min(k, r["eligible_candidate_count"])
            inventory.append({"target_id": r["target_id"], "task": r["task_type"], "head": r["head"],
                "requested_k": k, "realized_k": len(selected), "outer_fold": f["outer_fold"],
                "group_component_id": f["group_component_id"],
                "candidate_ids": [c["candidate_id"] for c in selected],
                "candidate_content_sha256": [c["candidate_content_sha256"] for c in selected],
                "raw_candidate_tokens_excluding_envelope": sum(c["candidate_tokens"] for c in selected)})
    dest = PROJECT / "outputs/paper1_calibration/preparation_20260917_v1"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "static_topk_inventory.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in inventory))
    count_by_task = Counter(r["task_type"] for r in folds)
    coverage = {}
    for task in ["qa", "summary"]:
        coverage[task] = {}
        for head in ["MP", "ME", "MS"]:
            selected = [r for r in inventory if r["task"] == task and r["head"] == head]
            coverage[task][head] = {str(k): {"targets": sum(r["requested_k"] == k for r in selected),
                "full_k": sum(r["requested_k"] == k and r["realized_k"] == k for r in selected)} for k in [1, 2, 3, 4]}
    static_targets = {r["target_id"] for r in rankings}
    stats = {"role": "prospective_inventory_not_authorized_execution_or_selected_sample", "formal_outcomes": 0,
        "sources": {str(p.relative_to(PROJECT)): sha256_file(p) for p in [ranking_path, fold_path, esc_path]},
        "ESC": {"splits": dict(Counter(r["split"] for r in esc)), "initial_k": [0, 1, 2, 3, 4],
                "full_52_card_grid_trajectories": 52 * 5},
        "memory": {"targets_by_task": dict(count_by_task), "group_components": len(components),
            "static_head_k_rows": len(inventory), "shared_off_rows": len(static_targets),
            "full_static_nominal_generation_rows": len(inventory) + len(static_targets),
            "unique_target_head_prefix_rows_plus_shared_off": len({(r["target_id"], r["head"], tuple(r["candidate_ids"])) for r in inventory}) + len(static_targets),
            "full_k_coverage": coverage,
            "per_heldout_fold_calibration_eligible_targets": {str(f): dict(Counter(r["task_type"] for r in folds if r["outer_fold"] != f)) for f in range(5)},
            "DG": "34 trajectories require live per-round seeker queries; static proxy rankings are not executable treatments."},
        "selection_rule": "Official task primary mean; one-SE admissible set; smallest mean Generator input tokens, then k, then canonical order.",
        "extension_rule": "Only if k=4 has best mean and k=3 lies outside its one-SE set, expand once to 6/8.",
        "next_execution_requirements": ["Select a budget-feasible calibration subset within existing partitions",
            "Render exact messages and resource envelopes using a common natural-end Generator version",
            "Count official scorer and simulator tokens and price the concrete schedule",
            "Refresh total-context and end-to-end latency measurements"],
        "final_k_selected": False, "paid_calls": 0}
    write_json(dest / "inventory_summary.json", stats)
    print(json.dumps({"summary": summary["by_arm"], "topk": {"static_rows": len(inventory) + len(static_targets),
        "static_targets": len(static_targets), "ESC_grid_trajectories": 260}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
