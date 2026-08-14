#!/usr/bin/env python3
"""Create a no-overwrite accountability derivative for all 576 formal groups.

The derivative preserves deployment-ITT outcomes while fail-closing semantic
training eligibility.  It makes no API calls and never edits the spent formal
manifest, responses, judgments, or OOF predictions.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, stable_hex, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_v5_3_measurement_repair import (  # noqa: E402
    CandidateTruth,
    ResponsibilityOwner,
    derive_execution_truth,
)


PROTOCOL = "pm-v1.5-v5.3-formal-accountability-derivative-v1"
COMPONENTS = ("MP", "MS", "ME", "RS")
FORMAL_MANIFEST = (
    ROOT
    / "outputs/pm_v1_5_v5_3_public_formal_effect_manifest_20260809/"
    "effect_group_manifest_private.jsonl"
)
FORMAL_RESULTS = ROOT / "outputs/pm_v1_5_v5_3_public_formal_qf_20260809/shards"
OUT = ROOT / "outputs/pm_v1_5_v5_3_formal_accountability_derivative_20260810"


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _candidate_machine_status(row: dict[str, Any]) -> tuple[str, list[str]]:
    candidate = row.get("candidate") or {}
    reasons: list[str] = []
    if not candidate.get("resource_id"):
        reasons.append("missing_resource_id")
    if row.get("component") in {"MP", "MS", "ME"} and not candidate.get("owner_id"):
        reasons.append("missing_owner_id")
    if row.get("component") in {"MP", "MS", "ME"} and candidate.get("strictly_prior") is not True:
        reasons.append("not_strictly_prior")
    if candidate.get("component") != row.get("component"):
        reasons.append("component_mismatch")
    return ("INVALID_MACHINE_LINEAGE" if reasons else "VALID_MACHINE_LINEAGE", reasons)


def _cluster_id(row: dict[str, Any]) -> str:
    return str(row.get("user_id") or row.get("dialogue_id"))


def main() -> None:
    manifests = _jsonl(FORMAL_MANIFEST)
    results: list[dict[str, Any]] = []
    result_paths: list[Path] = []
    for fold in range(1, 7):
        path = FORMAL_RESULTS / f"fold_{fold}_results.jsonl"
        result_paths.append(path)
        results.extend(_jsonl(path))

    manifest_by_group = {str(row["effect_group_id"]): row for row in manifests}
    result_by_group = {str(row["effect_group_id"]): row for row in results}
    if len(manifests) != 576 or len(manifest_by_group) != 576:
        raise RuntimeError("exactly 576 unique formal manifest groups required")
    if len(results) != 576 or len(result_by_group) != 576:
        raise RuntimeError("exactly 576 unique formal result groups required")
    if set(manifest_by_group) != set(result_by_group):
        raise RuntimeError("manifest/result effect-group identities differ")

    replicate_rows: list[dict[str, Any]] = []
    group_rows: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    by_component: dict[str, Counter[str]] = {name: Counter() for name in COMPONENTS}

    for effect_group_id in sorted(manifest_by_group):
        manifest = manifest_by_group[effect_group_id]
        result = result_by_group[effect_group_id]
        component = str(manifest["component"])
        if component != result["component"] or component not in COMPONENTS:
            raise RuntimeError(f"component mismatch for {effect_group_id}")
        machine_status, machine_reasons = _candidate_machine_status(manifest)
        function_by_replicate = {
            str(row["replicate_id"]): row
            for row in result["functional"]["replicates"]
        }
        group_has_fallback = False
        group_original_false_used = 0

        for generated in result["generated"]:
            replicate_id = str(generated["replicate_id"])
            on = generated["ON"]
            off = generated["OFF"]
            raw_first_pass_saved = bool(on.get("raw_first_pass_reply"))
            final_truth, raw_truth, guard_truth = derive_execution_truth(
                on_status=str(on["status"]),
                raw_first_pass_saved=raw_first_pass_saved,
            )
            fallback = str(on["status"]) == "fell_back_to_m0"
            original_function = function_by_replicate[replicate_id]
            if fallback:
                group_has_fallback = True
                counts["on_fallback_replicates"] += 1
                by_component[component]["on_fallback_replicates"] += 1
                if original_function["use_status"] == "USED":
                    group_original_false_used += 1
                    counts["fallback_originally_labeled_used"] += 1
            if str(off["status"]) == "fell_back_to_m0":
                counts["off_fallback_replicates"] += 1

            replicate_rows.append(
                {
                    "protocol": PROTOCOL,
                    "audit_row_id": "acctfix_" + stable_hex(
                        PROTOCOL, effect_group_id, replicate_id, n=24
                    ),
                    "effect_group_id": effect_group_id,
                    "state_id": manifest["state_id"],
                    "source_state_id": manifest["source_state_id"],
                    "component": component,
                    "independent_cluster_id": _cluster_id(manifest),
                    "user_id": manifest.get("user_id"),
                    "dialogue_id": manifest.get("dialogue_id"),
                    "source_dataset": manifest["source_dataset"],
                    "outer_fold": manifest["outer_fold"],
                    "replicate_id": replicate_id,
                    "seed": generated["seed"],
                    "candidate_id": manifest["candidate"].get("resource_id"),
                    "candidate_machine_status": machine_status,
                    "candidate_truth": CandidateTruth.UNRESOLVED.value,
                    "on_requested_action": on["requested_action_id"],
                    "on_realized_action": on["realized_action_id"],
                    "on_final_status": on["status"],
                    "off_final_status": off["status"],
                    "final_execution_truth": final_truth.value,
                    "raw_execution_truth": raw_truth.value,
                    "guard_truth": guard_truth.value,
                    "raw_first_pass_saved": raw_first_pass_saved,
                    "original_function_judgment": original_function,
                    "original_function_usable_for_training": False,
                    "risk_truth": "UNRESOLVED_CANARY_UNQUALIFIED",
                    "semantic_value_label_eligible": False,
                    "deployment_itt_outcome_retained": True,
                    "mechanism_primary_owner": (
                        ResponsibilityOwner.STEP2_GUARD_SUBSYSTEM_UNRESOLVED.value
                        if fallback
                        else ResponsibilityOwner.MEASUREMENT.value
                    ),
                    "mechanism_owner_reason": (
                        "requested ON became deterministic M0; rejected raw reply was not saved"
                        if fallback and not raw_first_pass_saved
                        else "candidate/function/risk semantic truth awaits calibrated review"
                    ),
                }
            )

        if group_has_fallback:
            counts["groups_with_on_fallback"] += 1
            by_component[component]["groups_with_on_fallback"] += 1
        if machine_status == "VALID_MACHINE_LINEAGE":
            counts["candidate_machine_lineage_valid_groups"] += 1
        by_component[component]["groups"] += 1
        group_rows.append(
            {
                "protocol": PROTOCOL,
                "effect_group_id": effect_group_id,
                "state_id": manifest["state_id"],
                "component": component,
                "candidate_type": manifest["candidate_type"],
                "independent_cluster_id": _cluster_id(manifest),
                "user_id": manifest.get("user_id"),
                "dialogue_id": manifest.get("dialogue_id"),
                "source_dataset": manifest["source_dataset"],
                "outer_fold": manifest["outer_fold"],
                "candidate_machine_status": machine_status,
                "candidate_machine_reasons": machine_reasons,
                "candidate_truth": CandidateTruth.UNRESOLVED.value,
                "any_on_fallback": group_has_fallback,
                "fallback_originally_labeled_used": group_original_false_used,
                "risk_instrument_status": result.get("risk_instrument_status"),
                "risk_truth": "UNRESOLVED_CANARY_UNQUALIFIED",
                "original_q_uplift_deployment_itt": result["quality_effect"]["aggregate"][
                    "mean_positive_support_contribution"
                ],
                "original_q_remains_semantic_pm_gold": False,
                "semantic_value_label": "UNRESOLVED",
                "deployment_itt_outcome_retained": True,
                "review_required": True,
            }
        )

    if len(replicate_rows) != 1728:
        raise RuntimeError("exactly 1,728 formal replicates required")

    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "group_accountability.jsonl", group_rows)
    write_jsonl(OUT / "replicate_accountability.jsonl", replicate_rows)
    source_hashes = {str(FORMAL_MANIFEST.relative_to(ROOT)): sha256_file(FORMAL_MANIFEST)}
    source_hashes.update(
        {str(path.relative_to(ROOT)): sha256_file(path) for path in result_paths}
    )
    report = {
        "protocol": PROTOCOL,
        "status": "DERIVATIVE_COMPLETE_SEMANTIC_TRAINING_BLOCKED_PENDING_CALIBRATION",
        "source_artifacts_unchanged": True,
        "groups": len(group_rows),
        "replicates": len(replicate_rows),
        "component_counts": {
            component: dict(by_component[component]) for component in COMPONENTS
        },
        "counts": dict(counts),
        "hard_findings": {
            "all_risk_labels_unresolved": all(
                row["risk_instrument_status"] == "CANARY_UNQUALIFIED"
                for row in group_rows
            ),
            "semantic_value_labels_eligible": sum(
                bool(row["semantic_value_label_eligible"]) for row in replicate_rows
            ),
            "fallback_final_use_repaired_to_not_used": sum(
                row["final_execution_truth"] == "NOT_USED_FINAL"
                for row in replicate_rows
            ),
            "fallback_raw_execution_and_guard_unresolved": sum(
                row["raw_execution_truth"] == "UNRESOLVED_RAW_MISSING"
                for row in replicate_rows
            ),
            "original_q_retained_only_as_deployment_itt": True,
        },
        "gate": {
            "all_formal_groups_accounted_for": len(group_rows) == 576,
            "all_replicates_accounted_for": len(replicate_rows) == 1728,
            "new_training_allowed": False,
            "reason": "candidate applicability, functional realization, and risk are not jointly calibrated",
        },
        "source_hashes": source_hashes,
        "api_calls": 0,
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
