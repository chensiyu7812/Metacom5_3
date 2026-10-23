#!/usr/bin/env python3
"""Prepare a bounded Summary evidence/completion diagnostic on the same 13 pairs.

No generation or new human reference. Two versions separate evidence expansion
from natural-completion changes. Never rewrite the original comparison inputs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))
from metacom_pm.io import read_json, write_json, sha256_file, sha256_text, canonical_json
from metacom_pm.paper1.contracts import TaskType
from metacom_pm.paper1.data.memory_source import load_sanitized_runtime_users, enumerate_targets
from metacom_pm.paper1.evaluation.human_reference import render_session
from metacom_pm.paper1.evaluation.pairwise_teacher import build_pairwise_teacher_prompt


def main():
    root = PROJECT / "outputs/paper1_pairwise_teacher"
    current = root / "local_comparison_20260917_v2"
    source = PROJECT / "data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json"
    users = load_sanitized_runtime_users(source)
    by_owner = {u.owner_id: u for u in users}
    targets = {t.target_id: t for t in enumerate_targets(users)}
    preflight_path = PROJECT / "data/paper1_authority/paper1_pairwise_teacher_base_pair_preflight_20260904_v1.jsonl"
    bases = {r["base_pair_id"]: r for r in map(json.loads, preflight_path.read_text().splitlines()) if r["task"] == "Summary"}
    binding = read_json(PROJECT / "data/paper1_authority/paper1_pairwise_teacher_human_sheet_manifest_20260908_v2.json")["sheets"]["RATER_A"]
    sheet_path = PROJECT / binding["path"]
    assert sha256_file(sheet_path) == binding["sha256"]
    original_items = {r["presentation_id"]: r for r in read_json(sheet_path)["items"]}
    reverse_ids = {r["base_pair_id"]: r["presentation_id"] for r in read_json(root / "local_comparison_proposal_20260917_v1/presentation_mapping.json") if not r["is_base"]}
    orientations = {r["base_pair_id"]: r for r in read_json(root / "gemini_qualification_v2/aligned_results.json")
                    if not r["reverse_duplicate"] and r["task"] == "Summary"}
    natural = {}
    for path in (current / "summary_generator/responses").glob("*.json"):
        r = read_json(path)
        assert r["natural_end"] and r["status"] == "COMPLETED"
        for bid in r["base_pair_ids"]:
            natural.setdefault(bid, {})[r["arm"]] = r["raw_output"]
    assert len(bases) == len(orientations) == len(natural) == 13
    requests, audits = [], []
    for bid, base in sorted(bases.items()):
        target = targets[base["target_id"]]
        user = by_owner[target.owner_id]
        assert target.task_type is TaskType.SUMMARY
        sessions = sorted(user.sessions, key=lambda s: s.chronological_rank)
        past = [s for s in sessions if s.chronological_rank < target.cutoff_rank]
        assert len(past) == target.cutoff_rank and len({s.session_id for s in past}) == len(past)
        assert all(a.date <= b.date for a, b in zip(past, past[1:]))
        history = "\n\n".join(render_session(s.timestamp, [{"role": t.role, "content": t.content} for t in s.turns]) for s in past)
        orientation = orientations[bid]
        original = original_items[orientation["presentation_id"]]
        assert original["reference_material"] == base["reference_material"]
        reference = (
            "OFFICIAL REFERENCE SUMMARY (short coverage reference, not an exhaustive list of true facts):\n"
            + original["reference_material"]
            + "\n\nEVIDENCE USE: Verify factual claims against the complete prior source history below. "
              "Absence from the short reference summary alone does not establish fabrication. "
              "Distinguish seeker statements from supporter hypotheses, and past from current states. "
              "Do not reward extra true facts when they are irrelevant to the requested summary."
            + "\n\nCOMPLETE PRIOR SOURCE HISTORY (chronological; before this task):\n" + history)
        audits.append({"base_pair_id": bid, "target_id": target.target_id, "owner_id": user.owner_id,
            "cutoff_rank": target.cutoff_rank, "source_session_ids": [s.session_id for s in past],
            "source_session_ranks": [s.chronological_rank for s in past],
            "old_reference_characters": len(original["reference_material"]), "new_reference_characters": len(reference),
            "new_reference_sha256": sha256_text(reference), "source_history_sha256": sha256_text(history)})
        for variant in ["same_answers_full_history", "natural_answers_full_history"]:
            a_arm = orientation["A_arm"]
            b_arm = "OFF" if a_arm == "ON" else "ON"
            a, b = ((original["response_A"], original["response_B"]) if variant == "same_answers_full_history"
                    else (natural[bid][a_arm], natural[bid][b_arm]))
            for reverse in [False, True]:
                response_a, response_b = (b, a) if reverse else (a, b)
                prompt = build_pairwise_teacher_prompt(task="Summary", task_input=original["task_input"],
                    response_a=response_a, response_b=response_b, reference_material=reference)
                pid = "summary_dev_" + sha256_text(f"{variant}|{bid}|{reverse}")[:24]
                requests.append({"presentation_id": pid, "task": "Summary", "messages": [{"role": "user", "content": prompt}],
                    "base_pair_id": bid, "source_base_presentation_id": orientation["presentation_id"],
                    "seed_key": reverse_ids[bid] if reverse else orientation["presentation_id"],
                    "development_variant": variant, "reverse_duplicate": reverse, "A_arm": b_arm if reverse else a_arm,
                    "reference_sha256": sha256_text(reference), "response_A_sha256": sha256_text(response_a),
                    "response_B_sha256": sha256_text(response_b)})
    requests.sort(key=lambda r: sha256_text("summary-evidence-development-seed0|" + r["presentation_id"]))
    assert len(requests) == len({r["presentation_id"] for r in requests}) == 52
    out = current / "summary_evidence_diagnostic"
    write_json(out / "requests.json", requests)
    write_json(out / "source_audit.json", audits)
    write_json(out / "preparation.json", {"kind": "same_13_pairs_versioned_development", "requests_per_candidate": 52,
        "source_sha256": sha256_file(source), "preflight_sha256": sha256_file(preflight_path),
        "original_sheet_sha256": binding["sha256"], "request_sha256": sha256_text(canonical_json(requests)),
        "human_relabeling_requested": False, "original_outputs_overwritten": False, "new_model_calls_in_preparation": 0,
        "interpretation": "First contrast holds old responses fixed while adding source history. Second holds complete source history fixed while substituting natural-end responses. Existing human votes describe the old evidence/outputs; not independent validation of these variants.",
        "new_API_cost_usd": 0, "formal_training_labels": False})
    print({"pairs": 13, "variants": 2, "requests_per_candidate": 52,
           "max_reference_characters": max(r["new_reference_characters"] for r in audits)})


if __name__ == "__main__":
    main()
