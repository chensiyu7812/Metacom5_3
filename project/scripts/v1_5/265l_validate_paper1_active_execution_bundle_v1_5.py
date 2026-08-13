#!/usr/bin/env python3
"""Fail-closed validation of the small Paper 1 active execution bundle."""

from __future__ import annotations

import ast
from itertools import product
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.v1_5b_policy_runtime import compile_component_bits  # noqa: E402


BUNDLE = ROOT / "data/pm_v1_5_contracts/paper1_active_execution_bundle_v1.json"
AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_active_execution_bundle_20260812/validation.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def main() -> None:
    bundle = read(BUNDLE)
    authority = read(AUTHORITY)
    file_checks = {
        row["path"]: (ROOT / row["path"]).is_file() and sha(ROOT / row["path"]) == row["sha256"]
        for row in bundle["files"]
    }
    deny = {Path(row["path"]).stem for row in bundle["legacy_import_denylist"]}
    active_python = [ROOT / row["path"] for row in bundle["files"] if row["path"].endswith(".py")]
    imported = set().union(*(imported_modules(path) for path in active_python))
    all_actions = {
        compile_component_bits(dict(zip(("MP", "MS", "ME", "RS"), bits)))
        for bits in product((False, True), repeat=4)
    }
    current = authority["current_execution_phase"]
    alias = authority["active_v3_phase"]
    active_revision = bundle["experiment_version"]["active_revision"]
    registry = read(ROOT / bundle["experiment_version"]["registry"])
    revision_binding = next(
        row for row in registry["revisions"] if row["version"] == active_revision
    )
    revision = read(ROOT / revision_binding["path"])
    expected_bundle = {"path": str(BUNDLE.relative_to(ROOT)), "sha256": sha(BUNDLE)}
    checks = {
        "bundle_protocol": bundle["protocol"] == "pm-v1.5-paper1-active-execution-bundle-v1",
        "all_file_hashes_match": all(file_checks.values()),
        "authority_points_to_bundle": current["active_phase_manifest"] == expected_bundle,
        "one_current_pointer_and_alias": alias.get("compatibility_alias_of") == "current_execution_phase" and alias["active_phase_manifest"] == expected_bundle,
        "authority_and_bundle_phase_match": current["id"] == bundle["current_phase"]["id"] and current["status"] == bundle["current_phase"]["status"],
        "active_experiment_revision_is_content_addressed": revision_binding["sha256"] == sha(ROOT / revision_binding["path"]),
        "function_v2_has_no_latent_binary_count_gate": revision["function_observability_v2"]["development_decision_rule"]["standalone_binary_function_count_gate"] is False,
        "old_56_call_panel_withdrawn": revision["historical_evidence_disposition"]["existing_four_arm_panel"]["current_disposition"] == "DO_NOT_EXECUTE_AS_MS_SCIENTIFIC_QUALIFICATION",
        "experiment_revision_does_not_change_method_version": registry["method_boundary"]["new_method_version_created"] is False,
        "success_is_rs_plus_two_memory": bundle["method"]["effective_primary_success_predicate"] == "RS_pass AND count_pass(MP,MS,ME) >= 2",
        "sixteen_actions_compile": len(all_actions) == 16,
        "independent_heads_joint_execution": bundle["method"]["independent_heads_joint_execution"] is True,
        "no_api_label_fit_or_external_authority": bundle["current_phase"]["authorization"] == {"api_calls": 0, "training_labels": 0, "diagnostic_fits": 0, "generator_calls": 0, "external_execution": False},
        "generic_nli_rejected": bundle["semantic_runtime"]["generic_nli"] == "REJECTED",
        "challenger_is_feature_only": "never gold or hard gate" in bundle["semantic_runtime"]["challenger_role"],
        "semantic_calibration_not_overclaimed": bundle["semantic_runtime"]["uncertain_as_off"] == "INTERFACE_IMPLEMENTED_OUTER_TRAIN_CALIBRATION_AND_RUNNER_WIRING_PENDING",
        "legacy_v2_imports_absent": not any(any(name.endswith(stem) for stem in deny) for name in imported),
        "legacy_files_hash_bound": all(sha(ROOT / row["path"]) == row["sha256"] and row["active_import_forbidden"] is True for row in bundle["legacy_import_denylist"]),
        "old_current_phase_is_historical": authority["current_phase"].get("historical_only") is True and authority["current_phase"].get("must_not_route_execution") is True,
    }
    result = {
        "protocol": "pm-v1.5-paper1-active-execution-bundle-validation-v1",
        "status": "PASS_ACTIVE_BUNDLE_ZERO_API_DESIGN_ONLY" if all(checks.values()) else "FAIL_ACTIVE_BUNDLE",
        "checks": checks,
        "failed_checks": [key for key, value in checks.items() if not value],
        "file_checks": file_checks,
        "action_count": len(all_actions),
        "active_method": bundle["method"]["base_method_id"],
        "effective_primary_success": bundle["method"]["effective_primary_success_predicate"],
        "current_phase": bundle["current_phase"]["id"],
        "semantic_runtime": bundle["semantic_runtime"]["uncertain_as_off"],
        "api_calls": 0,
        "training_labels": 0,
        "fits": 0,
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["failed_checks"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
