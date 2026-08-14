#!/usr/bin/env python3
"""Diagnose why the V5.4 bounded-observability V1 result is not PM evidence."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402

PROTOCOL = "pm-v1.5-v5.4-observability-target-drift-diagnosis-v1"
RUNTIME = ROOT / "outputs/pm_v1_5_v5_4_v4_state_local_actual_rank1_20260810/runtime_state_candidate_surface_no_ids_no_assignment.jsonl"
AUTHORING = ROOT / "outputs/pm_v1_5_v5_4_state_local_authoring_v4_20260810/authoring_v4_packet_private_outcome_blind.jsonl"
ASSIGNMENTS = ROOT / "outputs/pm_v1_5_v5_4_state_local_authoring_v4_20260810/construction_assignment_private_do_not_join.jsonl"
OBS_REPORT = ROOT / "outputs/pm_v1_5_v5_4_bounded_semantic_observability_20260810/report.json"
OBS_PREDICTIONS = ROOT / "outputs/pm_v1_5_v5_4_bounded_semantic_observability_20260810/oof_predictions_private_evaluator_assignment_only.jsonl"
OUT = ROOT / "outputs/pm_v1_5_v5_4_observability_target_drift_diagnosis_20260810"
COMPONENTS = ("MP", "MS", "ME", "RS")


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def metric(items: list[dict]) -> dict:
    tp = sum(row["gold"] == "INCREMENTAL" and row["prediction"] == "INCREMENTAL" for row in items)
    tn = sum(row["gold"] == "LOW_OPPORTUNITY" and row["prediction"] == "LOW_OPPORTUNITY" for row in items)
    fp = sum(row["gold"] == "LOW_OPPORTUNITY" and row["prediction"] == "INCREMENTAL" for row in items)
    fn = sum(row["gold"] == "INCREMENTAL" and row["prediction"] == "LOW_OPPORTUNITY" for row in items)
    sensitivity = tp / (tp + fn) if tp + fn else None
    specificity = tn / (tn + fp) if tn + fp else None
    return {
        "n": len(items), "positive": tp + fn, "negative": tn + fp,
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "balanced_accuracy": (sensitivity + specificity) / 2 if sensitivity is not None and specificity is not None else None,
    }


def main() -> None:
    runtime = rows(RUNTIME)
    authoring = {row["pair_id"]: row for row in rows(AUTHORING)}
    assignments = {row["pair_id"]: row for row in rows(ASSIGNMENTS)}
    predictions = {row["state_id"]: row for row in rows(OBS_PREDICTIONS)}
    obs_report = json.loads(OBS_REPORT.read_text())
    if len(runtime) != 96 or len(authoring) != 48 or len(assignments) != 48 or len(predictions) != 96:
        raise RuntimeError("diagnostic identities are incomplete")

    details = []
    component_counts: dict[str, Counter] = defaultdict(Counter)
    full_pair_retention: dict[str, int] = Counter()
    by_pair: dict[str, list[bool]] = defaultdict(list)
    retained_predictions = []
    for row in runtime:
        source = authoring[row["pair_id"]]
        retained = row["actual_rank1_candidate_text"].strip() == source["frozen_candidate_text"].strip()
        by_pair[row["pair_id"]].append(retained)
        component_counts[row["component"]]["anchor_retained" if retained else "anchor_changed"] += 1
        assignment = assignments[row["pair_id"]]
        variant = row["variant_id"].rsplit("_", 1)[-1].upper()
        gold = assignment[f"variant_{variant}_assignment"]
        pred = predictions[row["state_id"]]["semantic_prediction"]
        if retained:
            retained_predictions.append({"component": row["component"], "gold": gold, "prediction": pred})
        details.append({
            "protocol": PROTOCOL,
            "state_id": row["state_id"],
            "pair_id": row["pair_id"],
            "component": row["component"],
            "construction_assignment_evaluator_only": gold,
            "source_anchor_retained_by_actual_rank1": retained,
            "source_anchor_text": source["frozen_candidate_text"],
            "actual_rank1_candidate_text": row["actual_rank1_candidate_text"],
            "observability_v1_prediction": pred,
            "response_effect_or_oracle_read": False,
        })
    for pair_id, values in by_pair.items():
        if len(values) == 2 and all(values):
            full_pair_retention[authoring[pair_id]["component"]] += 1

    report = {
        "protocol": PROTOCOL,
        "status": "OBSERVABILITY_V1_NOT_A_PM_LEARNABILITY_RESULT_TARGET_DRIFT_AND_INPUT_SCOPE_REPAIR_REQUIRED",
        "preserved_v1_result": {
            "status": obs_report["status"],
            "overall_balanced_accuracy": obs_report["semantic_overall"]["balanced_accuracy"],
            "meaning": "descriptive performance against the pre-authoring construction assignment only",
            "retroactive_pass": False,
        },
        "actual_rank1_anchor_retention_by_component": {component: dict(component_counts[component]) for component in COMPONENTS},
        "both_variants_retain_source_anchor_pairs": {component: full_pair_retention[component] for component in COMPONENTS},
        "all_components_state_total": 96,
        "anchor_changed_state_total": sum(counts["anchor_changed"] for counts in component_counts.values()),
        "anchor_retained_subset_posthoc_diagnostic": {
            "overall": metric(retained_predictions),
            "by_component": {component: metric([row for row in retained_predictions if row["component"] == component]) for component in COMPONENTS},
            "not_a_requalification": True,
        },
        "invalid_inference_chain": [
            "construction assignment was authored relative to a verified source anchor",
            "state-local materialization correctly allowed production actual Rank-1 to change",
            "the observability script nevertheless treated the old assignment as truth for the new candidate",
            "the script embedded only current_user_text although deployable visible_dialogue is available and is required for redundancy, boundary, and prior-move context",
        ],
        "scientific_correction": {
            "causal_effect_unit_unchanged": "one completed state with its own actual Rank-1 frozen across matched requested-action arms",
            "construction_assignment_role": "authoring/design diagnostic only; never PM gold and never presumed valid after candidate identity changes",
            "pre_effect_requirement": "machine-complete deployable full-dialogue/current-turn/candidate feature materialization with no forbidden fields",
            "first_value_evidence": "a bounded randomized same-state ON/OFF deployment-ITT effect feasibility panel",
            "learnability_evidence": "family/user-grouped OOF prediction of randomized continuous effects, followed by fresh confirmation",
            "no_bge_tuning_on_v1": True,
        },
        "authorization": {
            "observability_v1_promotes_effect_calls": False,
            "new_effect_calls": False,
            "next": "freeze a separately named small outcome-blind deployment-ITT feasibility manifest and budget after feature-surface integrity and Step2 identity checks",
        },
        "response_effect_or_oracle_read": False,
        "api_calls": 0,
        "source_hashes": {name: sha256_file(path) for name, path in {
            "runtime": RUNTIME, "authoring": AUTHORING, "assignments": ASSIGNMENTS,
            "observability_report": OBS_REPORT, "observability_predictions": OBS_PREDICTIONS,
        }.items()},
    }
    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "state_level_anchor_drift_private.jsonl", details)
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
