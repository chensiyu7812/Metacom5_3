from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
DEFAULT_OUTPUT = ROOT / "outputs/pm_v1_5_paper1_active_authority_validation_20260810/report.json"


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    path.relative_to(ROOT.resolve())
    return path


def validate_active_authority() -> dict[str, Any]:
    authority = read(AUTHORITY)
    active = authority["active_method"]
    contract_path = resolve(active["contract_path"])
    amendment_path = resolve(active["method_amendment_path"])
    registry_path = resolve(active["method_registry_path"])
    plan_path = resolve(active["human_plan_path"])
    phase_path = resolve(authority["current_phase"]["active_phase_manifest"]["path"])
    paid_path = resolve(authority["paid_execution_guard"]["central_release_path"])
    contract = read(contract_path)
    amendment = read(amendment_path)
    registry = read(registry_path)
    paid = read(paid_path)
    phase = read(phase_path)
    versions = [row for row in registry["versions"] if row["id"] == active["method_id"]]
    completed = authority["current_phase"].get("completed_V2_oof")
    feasibility = authority["current_phase"].get("system_feasibility_design_candidate") or {}
    live = feasibility.get("live_execution") or {}
    live_path = resolve(live["path"]) if live.get("path") else None
    development = feasibility.get("development_measurement") or {}
    development_report = development.get("completed_report") or {}
    rescue = feasibility.get("memory_head_rescue_design_candidate") or {}
    rescue_document = read(resolve(rescue["path"])) if rescue.get("path") else {}
    v3_repair = feasibility.get("component_general_v3_repair_contract") or {}
    v3_repair_document = read(resolve(v3_repair["path"])) if v3_repair.get("path") else {}
    known_authority_statuses = {
        "ACTIVE_ZERO_API_V2_TERMINAL_ROUTING_FAIL_SYSTEM_FEASIBILITY_DESIGN_ONLY",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_MS_SYSTEM_FEASIBILITY_GENERATION",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_MS_DEVELOPMENT_MEASUREMENT",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_MS_RESCUE_DESIGN_AUDIT",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_MEMORY_RESCUE_V2_DESIGN_AUDIT",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_REPAIR_CONTRACT_AUDIT",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_G2_DESIGN",
    }
    checks = {
        "authority_protocol": authority["protocol"] == "pm-v1.5-active-method-authority-v1",
        "authority_keeps_terminal_routing_result": authority["status"] in known_authority_statuses,
        "active_method_is_v2": active["method_id"] == "PAPER1_SOURCE_ANNOTATED_RESOURCE_SUITABILITY_V2",
        "contract_hash_matches": contract_path.is_file() and sha(contract_path) == active["contract_sha256"],
        "contract_method_matches": contract["method_id"] == active["method_id"],
        "amendment_hash_matches": amendment_path.is_file() and sha(amendment_path) == active["method_amendment_sha256"],
        "amendment_base_matches": amendment["base_method"]["method_id"] == active["method_id"] and amendment["base_method"]["contract_sha256"] == active["contract_sha256"],
        "primary_requires_rs_and_ms": amendment["effective_primary_head_rule"]["machine_predicate"] == "RS_pass AND MS_pass",
        "observed_primary_is_false": amendment["observed_result"] == {"RS": "PASS", "MS": "FAIL_FIXED_OFF", "paper1_primary_pass": False},
        "sixteen_actions_preserved": contract["action_space"]["legal_actions"] == 16,
        "failed_heads_fixed_off": contract["action_space"]["MP"] == "fixed OFF" and contract["action_space"]["ME"] == "fixed OFF",
        "runtime_event_graph_forbidden": {"summary", "observation", "event", "influenced_by", "QA answer", "QA evidence"}.issubset(set(contract["MS"]["forbidden_runtime_fields"])),
        "quality_risk_function_cost_separate": all(term in contract["claim"]["primary"] for term in ("quality", "risk", "function", "cost")),
        "phase_is_consumed_final_oof": authority["current_phase"]["id"] == "MS_SESSION_ALIGNED_FINAL_OOF_V2" and authority["current_phase"]["status"] == "FINAL_OOF_CONSUMED_PRIMARY_FAIL_NO_FURTHER_PM_FIT",
        "phase_hash_matches": sha(phase_path) == authority["current_phase"]["active_phase_manifest"]["sha256"],
        "phase_method_matches": phase["method_id"] == active["method_id"],
        "phase_forbids_second_oof": "any second V2 OOF" in phase["forbidden"],
        "completed_oof_hash_and_status": bool(completed) and sha(resolve(completed["path"])) == completed["sha256"] and read(resolve(completed["path"]))["status"] == completed["required_status"],
        "registry_has_one_active_record": len(versions) == 1,
        "registry_canonical_matches": registry["canonical_next"] == active["method_id"],
        "registry_records_terminal_failure": len(versions) == 1 and versions[0]["result"] == "TERMINAL_MECHANICAL_PRIMARY_FAIL_BORDERLINE_DIRECTIONAL_ONLY" and versions[0]["formal_training_allowed"] is False,
        "human_plan_records_no_v3": "V2 到此关闭，不再建立 V3" in plan_path.read_text(encoding="utf-8"),
        "paid_release_false": paid.get("paid_execution_authorized") is False,
        "authority_requires_paid_false": authority["paid_execution_guard"]["required_current_value"] is False,
        "live_phase_binding_valid_if_present": not live or (
            live_path is not None
            and live_path.is_file()
            and sha(live_path) == live["sha256"]
            and read(live_path)["status"] == live.get("phase_required_status", live["status"])
        ),
        "live_phase_never_authorizes_pm_refit": not live or all(
            "PM refit" in item or "threshold" in item or "feature" in item or "label" in item
            for item in read(live_path)["forbidden"]
            if any(term in item for term in ("PM refit", "threshold", "feature", "label"))
        ),
        "development_report_bound_if_complete": not development_report or (
            sha(resolve(development_report["path"])) == development_report["sha256"]
            and read(resolve(development_report["path"]))["status"] == development_report["required_status"]
        ),
        "rescue_design_bound_and_nonexecuting_if_present": not rescue or (
            sha(resolve(rescue["path"])) == rescue["sha256"]
            and rescue.get("execution_authority") is False
            and all(value is False for value in rescue_document["authorization"].values())
        ),
        "rescue_v2_scope_correction_is_bound": not rescue or (
            rescue_document.get("protocol") == "pm-v1.5-paper1-memory-head-rescue-decision-v2"
            and "Profile-based Personalization only" in rescue_document["scope_correction"]["MP"]
            and "MP_PREFERENCE" in rescue_document["scope_correction"]["forbidden_legacy_fields"]
        ),
        "rescue_v2_repairs_executor_before_fit": not rescue or (
            rescue_document["component_general_executor_v3"]["status"]
            == "REQUIRED_BEFORE_ANY_NEW_HEAD_LABEL_OR_FIT"
            and rescue_document["next_authorized_sequence_after_independent_design_audit"][0].startswith(
                "Implement and test the shared component-general V3"
            )
        ),
        "rescue_v2_has_parallel_profile_and_session_heads": not rescue or (
            {
                row["head"]: row["decision"] for row in rescue_document["head_program"]
            }.get("MP_PROFILE") == "PARALLEL_ZERO_API_RESCUE_CANDIDATE"
            and {
                row["head"]: row["decision"] for row in rescue_document["head_program"]
            }.get("MS") == "PARALLEL_ZERO_API_RESCUE_CANDIDATE"
        ),
        "rescue_v2_preserves_all_sixteen_requested_actions": not rescue or (
            rescue_document["paper_success_requirement"]["sixteen_requested_actions_unchanged"] is True
        ),
        "v3_repair_contract_bound_and_nonexecuting": not v3_repair or (
            sha(resolve(v3_repair["path"])) == v3_repair["sha256"]
            and v3_repair.get("execution_authority") is False
            and all(value is False for value in v3_repair_document["authorization"].values())
        ),
        "v3_repair_validation_report_bound_if_present": not v3_repair
        or not v3_repair.get("validation_report")
        or (
            sha(resolve(v3_repair["validation_report"]["path"]))
            == v3_repair["validation_report"]["sha256"]
            and read(resolve(v3_repair["validation_report"]["path"]))["status"]
            == v3_repair["validation_report"]["required_status"]
        ),
        "v3_repair_human_plan_and_ledger_hashes_match": not v3_repair or (
            sha(resolve(v3_repair_document["human_plan"]["path"]))
            == v3_repair_document["human_plan"]["sha256"]
            and sha(resolve(v3_repair_document["global_failure_ledger"]["path"]))
            == v3_repair_document["global_failure_ledger"]["sha256"]
            and v3_repair_document["global_failure_ledger"]["required_section"]
            in resolve(v3_repair_document["global_failure_ledger"]["path"]).read_text(encoding="utf-8")
        ),
        "v3_repair_preserves_old_v2_hashes": not v3_repair or all(
            sha(resolve(row["path"])) == row["sha256"]
            for row in v3_repair_document["historical_evidence"]
        ),
        "v3_repair_scope_actions_pairs_and_tracks_frozen": not v3_repair or (
            v3_repair_document["research_success"]["requested_action_count"] == 16
            and set(v3_repair_document["v3_executor"]["pair_rules_required"])
            == {"MP-MS", "MP-ME", "MP-RS", "MS-ME", "MS-RS", "ME-RS"}
            and set(v3_repair_document["external_tracks"])
            == {"ESConv", "EvoEmo", "ES-MemEval"}
            and "MP_PREFERENCE" in v3_repair_document["component_scope"]["forbidden"]
        ),
        "v3_repair_forbids_literal_lexical_and_generic_nonuse_fallback": not v3_repair or (
            v3_repair_document["v3_executor"]["meaning_absorption"]["literal_mention_required"] is False
            and v3_repair_document["v3_executor"]["meaning_absorption"]["lexical_overlap_required"] is False
            and v3_repair_document["v3_executor"]["guard"]["fixed_generic_safe_nonuse_fallback_forbidden"] is True
        ),
        "v3_repair_separates_five_action_layers": not v3_repair or (
            v3_repair_document["action_accounting"]["layers"]
            == [
                "requested",
                "structurally_eligible",
                "jointly_planned",
                "generator_claimed",
                "offline_verified_functional",
            ]
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "protocol": "pm-v1.5-paper1-active-method-authority-readiness-v2",
        "status": "ACTIVE_AUTHORITY_PASS_V2_TERMINAL_WITH_SEPARATE_SYSTEM_FEASIBILITY" if not failed else "ACTIVE_AUTHORITY_FAIL_CLOSED",
        "active_method_id": active["method_id"],
        "current_phase": authority["current_phase"]["id"],
        "checks": checks,
        "failed_checks": failed,
        "hashes": {
            "active_authority_sha256": sha(AUTHORITY),
            "active_contract_sha256": sha(contract_path),
            "active_method_amendment_sha256": sha(amendment_path),
            "active_phase_sha256": sha(phase_path),
            "method_registry_sha256": sha(registry_path),
            "human_plan_sha256": sha(plan_path),
            "paid_release_sha256": sha(paid_path),
        },
        "next": (
            "DESIGN_G2_COMPONENT_GENERAL_V3_ZERO_API_IMPLEMENTATION_PHASE"
            if v3_repair
            else (
                "INDEPENDENTLY_AUDIT_MEMORY_HEAD_RESCUE_DESIGN_NO_EXECUTION"
                if rescue
                else (
                    "EXECUTE_ONLY_THE_CONTENT_ADDRESSED_SYSTEM_FEASIBILITY_PHASE"
                    if live
                    else "DESIGN_SEPARATE_SAME_STACK_SYSTEM_FEASIBILITY_NO_EXECUTION_AUTHORITY"
                )
            )
        ),
        "api_calls": 0,
        "responses_generated": 0,
        "pm_trained": True,
        "additional_pm_fit_authorized": False,
        "external_outcomes_read": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = validate_active_authority()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    if report["failed_checks"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
