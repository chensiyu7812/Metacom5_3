#!/usr/bin/env python3
"""Materialize the only human- and runner-facing Paper 1 execution bundle."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
OUT = ROOT / "data/pm_v1_5_contracts/paper1_active_execution_bundle_v1.json"
REPORT_DIR = ROOT / "outputs/pm_v1_5_paper1_active_execution_bundle_20260812"


CURRENT_FILES = [
    ("effective_primary_success_rule", "data/pm_v1_5_contracts/paper1_component_general_v3_primary_success_rule_v1.json"),
    ("component_general_repair_contract", "data/pm_v1_5_contracts/paper1_component_general_v3_repair_contract_v1.json"),
    ("historical_base_method_not_effective_success_rule", "data/pm_v1_5_contracts/paper1_source_annotated_resource_suitability_method_v2.json"),
    ("parent_current_phase_closeout", "data/pm_v1_5_contracts/paper1_ms_source_annotated_control_closeout_v1.json"),
    ("final_ms_control_construct_repair_design", "data/pm_v1_5_contracts/paper1_ms_final_control_construct_repair_design_v1.json"),
    ("semantic_challenger_contract", "data/pm_v1_5_contracts/paper1_semantic_adapter_ablation_v1.json"),
    ("current_human_plan_with_20260812_addendum", "docs/PM_V1_5_PAPER1_COMPONENT_GENERAL_V3_REPAIR_PLAN_20260811_ZH.md"),
    ("global_failure_ledger", "docs/PM_V1_TO_V1_5_GLOBAL_FAILURE_LEDGER_ZH.md"),
    ("v3_factorial_planner", "src/metacom_pm/v1_5_component_general_v3.py"),
    ("v3_meaning_absorption_executor", "src/metacom_pm/v1_5_response_program_v3.py"),
    ("semantic_off_reason_accounting", "src/metacom_pm/v1_5_v5_3_semantic_off_accounting.py"),
    ("per_head_uncertain_as_off_compiler", "src/metacom_pm/v1_5_head_semantic_abstention.py"),
    ("source_aware_ms_review_instrument", "src/metacom_pm/v1_5_ms_source_annotated_suitability_review.py"),
    ("four_bit_action_runtime", "src/metacom_pm/v1_5b_policy_runtime.py"),
    ("typed_response_program", "src/metacom_pm/v1_5_v5_3_typed_response_program.py"),
    ("source_review_endpoint_config", "configs/paper1_ms_source_annotated_review_endpoints_v1.json"),
    ("ms_repair_packet_report", "outputs/pm_v1_5_paper1_ms_supervision_repair_packet_20260812/report.json"),
    ("failed_source_control_audit", "outputs/pm_v1_5_paper1_ms_source_annotated_control_audit_20260812/report.json"),
    ("generic_nli_rejection_report", "outputs/pm_v1_5_paper1_semantic_adapter_zero_api_20260811/report.json"),
]

LEGACY_DENYLIST = [
    "src/metacom_pm/v1_5_memory_response_plan_v2.py",
    "src/metacom_pm/v1_5_memory_realization_v2.py",
    "scripts/v1_5/198l_run_paper1_ms_same_stack_generation_v1_5.py",
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    authority = read(AUTHORITY)
    current = authority["current_execution_phase"]
    parent = current["active_phase_manifest"]
    if parent["path"] != "data/pm_v1_5_contracts/paper1_ms_source_annotated_control_closeout_v1.json":
        raise RuntimeError("unexpected parent current phase; refuse to guess the active version")
    if sha(ROOT / parent["path"]) != parent["sha256"]:
        raise RuntimeError("parent phase hash drift")
    files = []
    for role, relative in CURRENT_FILES:
        path = ROOT / relative
        if not path.is_file():
            raise RuntimeError(f"missing active bundle file: {relative}")
        files.append({"role": role, "path": relative, "sha256": sha(path)})
    denylist = []
    for relative in LEGACY_DENYLIST:
        path = ROOT / relative
        denylist.append({"path": relative, "sha256": sha(path), "active_import_forbidden": True})
    git_baseline = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT.parent, text=True
    ).strip()
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=ROOT.parent, text=True
    ).strip()
    bundle = {
        "protocol": "pm-v1.5-paper1-active-execution-bundle-v1",
        "date": "2026-08-12",
        "status": "ACTIVE_ZERO_API_FINAL_MS_CONTROL_REPAIR_DESIGN_NO_REVIEW_OR_FIT",
        "purpose": "One small fail-closed entry point. Historical files remain auditable but cannot become active by filename, chronology, or conversational memory.",
        "git": {
            "branch": branch,
            "parent_baseline_commit": git_baseline,
            "new_method_version_forbidden": True,
            "allowed_experiment_revision": "SEMANTIC_ADAPTER_ABLATION_V1",
        },
        "method": {
            "base_method_id": "PAPER1_SOURCE_ANNOTATED_RESOURCE_SUITABILITY_V2",
            "effective_primary_success_predicate": "RS_pass AND count_pass(MP,MS,ME) >= 2",
            "base_v2_rs_plus_ms_predicate_is_historical_only": True,
            "requested_action_count": 16,
            "independent_heads_joint_execution": True,
        },
        "current_phase": {
            "id": current["id"],
            "status": current["status"],
            "parent_phase": parent,
            "next_scientific_action": "Materialize and independently audit the already-designed fresh MS controls; review calls remain separately unauthorized.",
            "authorization": {
                "api_calls": 0,
                "training_labels": 0,
                "diagnostic_fits": 0,
                "generator_calls": 0,
                "external_execution": False,
            },
        },
        "semantic_runtime": {
            "claim": "component-specific bounded resource suitability, not unrestricted human-language understanding",
            "retrieval_encoder_role": "BGE-M3 similarity/retrieval only",
            "generic_nli": "REJECTED",
            "next_zero_api_challenger": "Qwen/Qwen3-Reranker-0.6B",
            "challenger_role": "relation feature only; never gold or hard gate",
            "uncertain_as_off": "INTERFACE_IMPLEMENTED_OUTER_TRAIN_CALIBRATION_AND_RUNNER_WIRING_PENDING",
            "uncertain_scope": "only the uncertain component bit is OFF; other bits remain independent",
        },
        "measurement": {
            "bulk_1_to_5_human_rating": "RETIRED",
            "training_label": "dual qualified model-family exact resolved consensus; disagreements and abstentions remain unlabeled/off",
            "human_role": "small frozen anchor set and final stratified sanity audit only",
            "quality": "blind same-state same-seed pairwise A/B/TIE/ABSTAIN",
            "risk": "absolute literal event-family audit plus attributable direction",
            "function": "source-aware binary evidence on selected learned-ON and matched OFF slices",
            "cost": "deterministic retrieval/injection/token/call/retry/latency/USD accounting",
        },
        "files": files,
        "legacy_import_denylist": denylist,
        "artifacts": [row for row in files if row["role"] in {"global_failure_ledger", "current_human_plan_with_20260812_addendum"}],
        "human_start_here": "docs/PM_V1_5_PAPER1_COMPONENT_GENERAL_V3_REPAIR_PLAN_20260811_ZH.md#12-2026-08-12-完成路线与语义边界附录当前有效",
        "runner_start_rule": "Validate this bundle and active_method_authority_v1.json; do not infer currency from any other file.",
    }
    if OUT.exists():
        raise RuntimeError("active bundle exists; refuse overwrite")
    write_json(OUT, bundle)
    REPORT_DIR.mkdir(parents=True, exist_ok=False)
    report = {
        "protocol": "pm-v1.5-paper1-active-execution-bundle-report-v1",
        "status": "ACTIVE_BUNDLE_MATERIALIZED_AUTHORITY_POINTER_UPDATE_REQUIRED",
        "bundle": {"path": str(OUT.relative_to(ROOT)), "sha256": sha(OUT)},
        "active_files": len(files),
        "legacy_denylist_files": len(denylist),
        "api_calls": 0,
        "training_labels": 0,
        "fits": 0,
    }
    write_json(REPORT_DIR / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
