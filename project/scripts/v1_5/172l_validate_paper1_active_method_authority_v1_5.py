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
    g2 = feasibility.get("component_general_v3_g2_implementation") or {}
    g2_document = read(resolve(g2["path"])) if g2.get("path") else {}
    g3 = feasibility.get("component_general_v3_g3_candidate_surface_audit") or {}
    g3_document = read(resolve(g3["path"])) if g3.get("path") else {}
    g4 = feasibility.get("component_general_v3_g4_nonexclusive_suitability_design") or {}
    g4_document = read(resolve(g4["path"])) if g4.get("path") else {}
    g4a = feasibility.get("component_general_v3_g4a_packet_materialization") or {}
    g4a_document = read(resolve(g4a["path"])) if g4a.get("path") else {}
    g4a_v2 = feasibility.get("component_general_v3_g4a_packet_materialization_v2") or {}
    g4a_v2_document = read(resolve(g4a_v2["path"])) if g4a_v2.get("path") else {}
    g4b = feasibility.get("component_general_v3_g4b_review") or {}
    g4b_document = read(resolve(g4b["path"])) if g4b.get("path") else {}
    active_v3 = authority.get("active_v3_phase") or {}
    active_v3_manifest = active_v3.get("active_phase_manifest") or {}
    active_v3_document = (
        read(resolve(active_v3_manifest["path"]))
        if active_v3_manifest.get("path")
        else {}
    )
    primary_success_binding = active_v3.get("primary_success_rule") or {}
    primary_success_document = (
        read(resolve(primary_success_binding["path"]))
        if primary_success_binding.get("path")
        else {}
    )
    known_authority_statuses = {
        "ACTIVE_ZERO_API_V2_TERMINAL_ROUTING_FAIL_SYSTEM_FEASIBILITY_DESIGN_ONLY",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_MS_SYSTEM_FEASIBILITY_GENERATION",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_MS_DEVELOPMENT_MEASUREMENT",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_MS_RESCUE_DESIGN_AUDIT",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_MEMORY_RESCUE_V2_DESIGN_AUDIT",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_REPAIR_CONTRACT_AUDIT",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_G2_DESIGN",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_G2_IMPLEMENTATION",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_G3_SURFACE_AUDIT_DESIGN",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_G3_SURFACE_AUDIT_EXECUTION",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_G4_SUITABILITY_PACKET_DESIGN",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_G4A_PACKET_PHASE_DESIGN",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_G4A_PACKET_MATERIALIZATION",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_G4A_V2_PACKET_MATERIALIZATION",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_G4B_REVIEW_PHASE_DESIGN",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_G4B1_CONTROL_EXECUTION",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_G4B1_CONTROL_QUALIFICATION",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_G4B1_ANCHORED_V2_CONTROL_EXECUTION",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_G4B1_ANCHORED_V2_QUALIFICATION",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_G4B2_MP_PUBLIC_REVIEW_EXECUTION",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_G4B2_MP_PUBLIC_529_CONTINUATION",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_G4B3_MP_PRE_ADJUDICATION",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_G4B3_MP_MEASUREMENT_FAILURE_AUDIT",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_MP_CONSENSUS_DIAGNOSTIC_LOGO_OOF",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_MP_DIAGNOSTIC_CLOSEOUT_MS_ATOMIC_LABEL_AUDIT_DESIGN",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_MS_SINGLE_TEACHER_EXECUTION",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_MS_SINGLE_TEACHER_LABEL_FREEZE",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_MS_ATOMIC_TEACHER_LOGO_OOF",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_MS_ATOMIC_TEACHER_FULL_FIT",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_MS_EXECUTOR_QUALIFICATION_DESIGN",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_MS_EXECUTOR_QUALIFICATION_EXECUTION",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_MS_EXECUTOR_MEASUREMENT_DESIGN",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_MS_EXECUTOR_QUALIFIED_REVIEW_PENDING",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_MS_EXECUTOR_FUNCTION_PROXY_EXECUTION",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_MS_FUNCTION_FEASIBILITY_COMPLETE_BASELINE_DESIGN_NEXT",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_RS_MS_BASELINE_PLAN_COMPLETE_BLIND_OUTCOME_DESIGN_NEXT",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_RS_MS_DUAL_HUMAN_BLIND_BUNDLE_READY",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_RS_MS_PI_ADJUDICATED_FUNCTION_FAIL_R0_DIAGNOSTIC_DESIGN_NEXT",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_R0_FUNCTION_CLOSURE_PACKETS_READY_PI_REVIEW_NEXT",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_R0_FUNCTION_FORCED_OPEN_CARD_PACKETS_CORRECTED_PI_REVIEW_NEXT",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_MS_ORACLE_PLAN_UPPER_BOUND_EXECUTION",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_MS_ORACLE_PLAN_RESPONSIBILITY_AUDIT",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_MS_SUPERVISION_UNIT_REPAIR_DESIGN",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_MS_REPAIR_PACKET_READY",
    }
    current_execution = authority.get("current_execution_phase") or {}
    checks = {
        "authority_protocol": authority["protocol"] == "pm-v1.5-active-method-authority-v1",
        "authority_keeps_terminal_routing_result": authority["status"] in known_authority_statuses,
        "one_current_execution_pointer_with_explicit_alias": (
            bool(current_execution)
            and active_v3.get("compatibility_alias_of") == "current_execution_phase"
            and active_v3.get("id") == current_execution.get("id")
            and active_v3.get("status") == current_execution.get("status")
            and active_v3.get("active_phase_manifest")
            == current_execution.get("active_phase_manifest")
            and authority["current_phase"].get("historical_only") is True
            and authority["current_phase"].get("must_not_route_execution") is True
        ),
        "v3_primary_success_rule_is_content_addressed": bool(primary_success_binding)
        and sha(resolve(primary_success_binding["path"])) == primary_success_binding["sha256"],
        "v3_primary_requires_rs_plus_two_memory_heads": (
            primary_success_document.get("primary_success_predicate", {}).get("machine_predicate")
            == "RS_pass AND count_pass(MP,MS,ME) >= 2"
            and primary_success_document.get("primary_success_predicate", {}).get("required_memory_pass_count") == 2
            and primary_success_document.get("primary_success_predicate", {}).get("maximum_memory_heads_fixed_off") == 1
        ),
        "v3_primary_preserves_four_heads_and_sixteen_actions": (
            primary_success_document.get("component_scope", {}).get("all_four_heads_must_be_defined_and_reported") is True
            and primary_success_document.get("component_scope", {}).get("all_sixteen_requested_actions_remain_in_the_scientific_design") is True
            and primary_success_document.get("component_scope", {}).get("memory_heads_are_independent_nonexclusive_binary_decisions") is True
        ),
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
        "paid_release_matches_active_phase": (
            paid.get("paid_execution_authorized") is True
            and authority["paid_execution_guard"]["required_current_value"] is True
            if active_v3.get("id") in {
                "MS_SINGLE_TEACHER_PUBLIC_EXECUTION",
                "MS_EXECUTOR_QUALIFICATION_EXECUTION",
                "MS_EXECUTOR_FUNCTION_PROXY_EXECUTION",
                "MS_ORACLE_PLAN_UPPER_BOUND_EXECUTION",
            }
            else paid.get("paid_execution_authorized") is False
            and authority["paid_execution_guard"]["required_current_value"] is False
        ),
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
            (
                sha(resolve(v3_repair_document["human_plan"]["path"]))
                == v3_repair_document["human_plan"]["sha256"]
                and sha(resolve(v3_repair_document["global_failure_ledger"]["path"]))
                == v3_repair_document["global_failure_ledger"]["sha256"]
                and v3_repair_document["global_failure_ledger"]["required_section"]
                in resolve(v3_repair_document["global_failure_ledger"]["path"]).read_text(encoding="utf-8")
            )
            or (
                bool(g4b.get("append_only_documentation_addendum"))
                and sha(resolve(g4b["append_only_documentation_addendum"]["repair_plan"]["path"]))
                == g4b["append_only_documentation_addendum"]["repair_plan"]["sha256"]
                and g4b["append_only_documentation_addendum"]["repair_plan"]["required_text"]
                in resolve(g4b["append_only_documentation_addendum"]["repair_plan"]["path"]).read_text(encoding="utf-8")
                and sha(resolve(g4b["append_only_documentation_addendum"]["failure_ledger"]["path"]))
                == g4b["append_only_documentation_addendum"]["failure_ledger"]["sha256"]
                and g4b["append_only_documentation_addendum"]["failure_ledger"]["required_text"]
                in resolve(g4b["append_only_documentation_addendum"]["failure_ledger"]["path"]).read_text(encoding="utf-8")
            )
            or (
                active_v3.get("id") == "MS_SUPERVISION_REPAIR_PACKET_READY"
                and any(
                    item.get("role") == "global_failure_ledger"
                    and sha(resolve(item["path"])) == item["sha256"]
                    and "## 26. 2026-08-12 MS监督单位修复" in resolve(item["path"]).read_text(encoding="utf-8")
                    for item in active_v3_document.get("artifacts", [])
                )
            )
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
        "v3_repair_preserves_full_sixteen_without_one_memory_cap": not v3_repair or (
            v3_repair_document["v3_executor"]["response_budget"]["global_one_memory_cap"]
            is False
            and v3_repair_document["v3_executor"]["response_budget"][
                "explicit_memory_contributions_max"
            ]
            == 2
            and v3_repair_document["v3_executor"]["pre_outcome_joint_policy"][
                "preserve_all_requested_bits_when_structurally_eligible_and_no_hard_safety_veto"
            ]
            is True
            and v3_repair_document["v3_executor"]["pre_outcome_joint_policy"][
                "unknown_redundant_or_conflicting_relation_automatically_suppresses_a_bit"
            ]
            is False
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
        "v3_repair_suitability_is_per_component_and_nonexclusive": not v3_repair or (
            v3_repair_document["suitability_gold"][
                "components_may_all_be_suitable_in_the_same_state"
            ]
            is True
            and v3_repair_document["suitability_gold"][
                "one_of_k_softmax_or_winner_take_all_forbidden"
            ]
            is True
            and "state by component"
            in v3_repair_document["suitability_gold"]["decision_grain"]
        ),
        "g2_phase_bound_and_zero_api_only": not g2 or (
            sha(resolve(g2["path"])) == g2["sha256"]
            and g2_document["status"]
            == "G2_ZERO_API_IMPLEMENTATION_AND_TESTS_AUTHORIZED_ONCE"
            and g2_document["git_baseline"] == g2["git_baseline"]
            and g2_document["promoted_from_authority_sha256"]
            == "f36f5d2a73e809b155d4d9f325f815d1d1a11614ffa98097eafe5a2c6b9fa530"
            and all(g2_document["forbidden"].values())
            and g2_document["allowed"]["new_v3_code"] is True
            and g2_document["allowed"]["zero_api_validator"] is True
            and (
                g2["execution_authority"] is True
                or (
                    g2["execution_authority"] is False
                    and g2["status"]
                    == "G2_COMPONENT_GENERAL_V3_IMPLEMENTATION_COMPLETE_G3_SURFACE_AUDIT_MAY_BE_DESIGNED"
                    and sha(resolve(g2["validation_report"]["path"]))
                    == g2["validation_report"]["sha256"]
                    and read(resolve(g2["validation_report"]["path"]))["status"]
                    == g2["validation_report"]["required_status"]
                )
            )
        ),
        "g2_phase_preserves_all_sixteen_without_one_memory_cap": not g2 or (
            any(
                "compile all 16 requested actions" in item
                for item in g2_document["required_capabilities"]
            )
            and any(
                "without imposing a global one-memory cap" in item
                for item in g2_document["required_capabilities"]
            )
            and any(
                "full MP+MS+ME+RS" in item
                for item in g2_document["required_non_regression_tests"]
            )
        ),
        "g3_surface_audit_bound_zero_api_and_unlabeled": not g3 or (
            sha(resolve(g3["path"])) == g3["sha256"]
            and g3_document["status"]
            == "G3_ZERO_API_PUBLIC_CANDIDATE_SURFACE_AUDIT_AUTHORIZED_ONCE"
            and g3_document["promoted_from_authority_sha256"]
            == "d70c9db50e2fefe30e597ae0846f3066dc86e78bae8d1799d362e027a7ce4b93"
            and g3_document["authorization"]["suitability_label_creation"] is False
            and g3_document["authorization"]["generator_calls"] is False
            and g3_document["authorization"]["reviewer_calls"] is False
            and g3_document["authorization"]["pm_fit"] is False
            and g3_document["authorization"]["paid_execution"] is False
            and (
                g3["execution_authority"] is True
                or (
                    g3["execution_authority"] is False
                    and g3["status"]
                    == "G3_CANDIDATE_SURFACE_COMPLETE_MP_MS_G4_PACKET_DESIGN_READY_ME_PROVISIONAL"
                    and sha(resolve(g3["validation_report"]["path"]))
                    == g3["validation_report"]["sha256"]
                    and read(resolve(g3["validation_report"]["path"]))["status"]
                    == g3["validation_report"]["required_status"]
                    and sha(resolve(g3["diagnostic_rows"]["path"]))
                    == g3["diagnostic_rows"]["sha256"]
                    and g3["diagnostic_rows"]["labels_created"] == 0
                    and sha(resolve(g3["html_report"]["path"]))
                    == g3["html_report"]["sha256"]
                )
            )
        ),
        "g3_surface_audit_preserves_nonexclusive_components": not g3 or (
            g3_document["nonexclusive_requirement"][
                "multiple_components_may_be_suitable_in_one_state"
            ]
            is True
            and g3_document["nonexclusive_requirement"][
                "one_of_k_softmax_winner_take_all_forbidden"
            ]
            is True
            and g3_document["nonexclusive_requirement"][
                "co_present_components_must_remain_separate_rows"
            ]
            is True
        ),
        "g4_design_bound_validated_and_nonexecuting": not g4 or (
            sha(resolve(g4["path"])) == g4["sha256"]
            and g4["status"]
            == "G4_NONEXCLUSIVE_SUITABILITY_DESIGN_COMPLETE_G4A_PACKET_PHASE_MAY_BE_DESIGNED"
            and g4["execution_authority"] is False
            and sha(resolve(g4["validation_report"]["path"]))
            == g4["validation_report"]["sha256"]
            and read(resolve(g4["validation_report"]["path"]))["status"]
            == g4["validation_report"]["required_status"]
            and all(value is False for value in g4_document["authorization"].values())
        ),
        "g4_design_is_per_component_not_one_memory": not g4 or (
            g4_document["scientific_unit"]["nonexclusive"] is True
            and g4_document["scientific_unit"][
                "same_state_may_enter_multiple_component_packets"
            ]
            is True
            and g4_document["scientific_unit"][
                "same_state_may_receive_suitable_for_all_present_components"
            ]
            is True
            and g4_document["scientific_unit"][
                "one_of_k_softmax_winner_take_all_forbidden"
            ]
            is True
            and g4_document["packet_capacity"]["total_planned_cases"] == 507
            and g4["planned_cases"]
            == {"MP": 204, "MS": 204, "ME": 99, "total": 507}
        ),
        "g4_checklist_is_not_four_labels": not g4 or (
            g4_document["review_instrument"]["one_primary_decision_only"] is True
            and g4_document["review_instrument"][
                "per_axis_yes_no_unknown_outputs_forbidden"
            ]
            is True
            and g4_document["review_instrument"][
                "per_axis_accuracy_kappa_or_gate_forbidden"
            ]
            is True
        ),
        "g4a_phase_bound_and_zero_api_materialization_only": not g4a or (
            sha(resolve(g4a["path"])) == g4a["sha256"]
            and g4a_document["status"]
            == "G4A_ZERO_API_NONEXCLUSIVE_PACKET_AND_FRESH_CONTROLS_AUTHORIZED_ONCE"
            and g4a_document["promoted_from_authority_sha256"]
            == "b3f95a24693f8c039ccd26387b32b7e1b09f3b4e9f34f9749ee412e3f5bb30ec"
            and sha(resolve(g4a["validation_report"]["path"]))
            == g4a["validation_report"]["sha256"]
            and read(resolve(g4a["validation_report"]["path"]))["status"]
            == g4a["validation_report"]["required_status"]
            and g4a_document["authorization"]["packet_materialization"] is True
            and g4a_document["authorization"]["fresh_control_materialization"]
            is True
            and g4a_document["authorization"]["reviewer_calls"] is False
            and g4a_document["authorization"]["suitability_label_creation"]
            is False
            and g4a_document["authorization"]["pm_fit"] is False
            and g4a_document["authorization"]["paid_execution"] is False
            and (
                g4a["execution_authority"] is True
                or (
                    g4a["execution_authority"] is False
                    and g4a["status"]
                    == "G4A_V1_PUBLIC_PACKET_MACHINE_PASS_CONTROLS_SEMANTIC_FAIL_SUPERSEDED_BEFORE_REVIEW"
                    and sha(resolve(g4a["completed_report"]["path"]))
                    == g4a["completed_report"]["sha256"]
                    and read(resolve(g4a["completed_report"]["path"]))["status"]
                    == g4a["completed_report"]["required_status"]
                    and sha(resolve(g4a["semantic_audit"]["path"]))
                    == g4a["semantic_audit"]["sha256"]
                    and read(resolve(g4a["semantic_audit"]["path"]))["status"]
                    == g4a["semantic_audit"]["required_status"]
                )
            )
        ),
        "g4a_v2_control_repair_bound_and_zero_api_only": not g4a_v2 or (
            sha(resolve(g4a_v2["path"])) == g4a_v2["sha256"]
            and g4a_v2_document["status"]
            == "G4A_V2_ZERO_API_CONTROL_REPAIR_AND_PACKET_REMATERIALIZATION_AUTHORIZED_ONCE"
            and g4a_v2_document["promoted_from_authority_sha256"]
            == "89afda8fc0e6dad0cbae0cf9878d4a66d572cb61185ab914418297c25fe633a7"
            and sha(resolve(g4a_v2["validation_report"]["path"]))
            == g4a_v2["validation_report"]["sha256"]
            and read(resolve(g4a_v2["validation_report"]["path"]))["status"]
            == g4a_v2["validation_report"]["required_status"]
            and g4a_v2_document["control_delta"]["changed_surfaces"] == 6
            and g4a_v2_document["control_delta"]["unchanged_surfaces"] == 30
            and g4a_v2_document["authorization"]["reviewer_calls"] is False
            and g4a_v2_document["authorization"]["suitability_label_creation"]
            is False
            and g4a_v2_document["authorization"]["pm_fit"] is False
            and g4a_v2_document["authorization"]["paid_execution"] is False
            and (
                g4a_v2["execution_authority"] is True
                or (
                    g4a_v2["execution_authority"] is False
                    and g4a_v2["status"]
                    == "G4A_V2_PACKET_AND_CONTROL_INDEPENDENT_AUDIT_COMPLETE_G4B_REVIEW_PHASE_MAY_BE_DESIGNED"
                    and sha(resolve(g4a_v2["completed_report"]["path"]))
                    == g4a_v2["completed_report"]["sha256"]
                    and read(resolve(g4a_v2["completed_report"]["path"]))["status"]
                    == g4a_v2["completed_report"]["required_status"]
                    and sha(resolve(g4a_v2["independent_audit"]["path"]))
                    == g4a_v2["independent_audit"]["sha256"]
                    and read(resolve(g4a_v2["independent_audit"]["path"]))["status"]
                    == g4a_v2["independent_audit"]["required_status"]
                )
            )
        ),
        "g4b_design_preflight_and_control_phase_bound": not g4b or (
            sha(resolve(g4b["path"])) == g4b["sha256"]
            and g4b_document["status"]
            == "G4B_ZERO_API_REVIEW_DESIGN_FROZEN_V1_PREFLIGHT_FAIL_PRESERVED_V2_PREFLIGHT_PASS_EXECUTION_NOT_AUTHORIZED"
            and sha(resolve(g4b["validation_report"]["path"]))
            == g4b["validation_report"]["sha256"]
            and read(resolve(g4b["validation_report"]["path"]))["status"]
            == g4b["validation_report"]["required_status"]
            and sha(resolve(g4b["preflight_report"]["path"]))
            == g4b["preflight_report"]["sha256"]
            and read(resolve(g4b["preflight_report"]["path"]))["status"]
            == g4b["preflight_report"]["required_status"]
            and sha(resolve(g4b["active_control_phase"]["path"]))
            == g4b["active_control_phase"]["sha256"]
            and (
                (
                    active_v3.get("id") == "G4B1_CONTROL_REVIEW_EXECUTION"
                    and active_v3_manifest.get("path")
                    == g4b["active_control_phase"]["path"]
                    and active_v3_manifest.get("sha256")
                    == g4b["active_control_phase"]["sha256"]
                    and active_v3_document.get("status")
                    == g4b["active_control_phase"]["required_status"]
                    and active_v3_document["authorization"]["control_reviewer_calls"]
                    is True
                    and active_v3_document["authorization"]["control_gold_access"]
                    is False
                    and active_v3_document["authorization"]["public_reviewer_calls"]
                    is False
                    and active_v3_document["authorization"]["suitability_label_creation"]
                    is False
                    and active_v3_document["authorization"]["pm_fit"] is False
                )
                or (
                    active_v3.get("id") == "G4B1_CONTROL_REVIEW_EXECUTION"
                    and bool(g4b.get("anchored_v2"))
                    and sha(resolve(g4b["v1_qualification_result"]["path"]))
                    == g4b["v1_qualification_result"]["sha256"]
                    and read(resolve(g4b["v1_qualification_result"]["path"]))["status"]
                    == g4b["v1_qualification_result"]["required_status"]
                    and sha(resolve(g4b["v1_failure_audit"]["path"]))
                    == g4b["v1_failure_audit"]["sha256"]
                    and read(resolve(g4b["v1_failure_audit"]["path"]))["status"]
                    == g4b["v1_failure_audit"]["required_status"]
                    and sha(resolve(g4b["anchored_v2"]["design"]["path"]))
                    == g4b["anchored_v2"]["design"]["sha256"]
                    and sha(resolve(g4b["anchored_v2"]["fresh_controls"]["path"]))
                    == g4b["anchored_v2"]["fresh_controls"]["sha256"]
                    and read(resolve(g4b["anchored_v2"]["fresh_controls"]["path"]))["status"]
                    == g4b["anchored_v2"]["fresh_controls"]["required_status"]
                    and sha(resolve(g4b["anchored_v2"]["preflight"]["path"]))
                    == g4b["anchored_v2"]["preflight"]["sha256"]
                    and read(resolve(g4b["anchored_v2"]["preflight"]["path"]))["status"]
                    == g4b["anchored_v2"]["preflight"]["required_status"]
                    and active_v3_manifest.get("path")
                    == g4b["anchored_v2"]["active_phase"]["path"]
                    and active_v3_manifest.get("sha256")
                    == g4b["anchored_v2"]["active_phase"]["sha256"]
                    and active_v3_document.get("status")
                    == g4b["anchored_v2"]["active_phase"]["required_status"]
                    and active_v3_document["authorization"]["control_reviewer_calls"]
                    is True
                    and active_v3_document["authorization"]["control_gold_access"]
                    is False
                    and active_v3_document["authorization"]["public_reviewer_calls"]
                    is False
                    and active_v3_document["authorization"]["training_label_creation"]
                    is False
                    and active_v3_document["authorization"]["pm_fit"] is False
                )
                or (
                    active_v3.get("id") == "G4B1_CONTROL_QUALIFICATION"
                    and sha(resolve(g4b["completed_control_reviews"]["path"]))
                    == g4b["completed_control_reviews"]["sha256"]
                    and read(resolve(g4b["completed_control_reviews"]["path"]))["status"]
                    == g4b["completed_control_reviews"]["required_status"]
                    and active_v3_manifest.get("path")
                    == g4b["active_qualification_phase"]["path"]
                    and active_v3_manifest.get("sha256")
                    == g4b["active_qualification_phase"]["sha256"]
                    and active_v3_document.get("status")
                    == g4b["active_qualification_phase"]["required_status"]
                    and active_v3_document["authorization"]["control_gold_access"]
                    is True
                    and active_v3_document["authorization"]["public_reviewer_calls"]
                    is False
                    and active_v3_document["authorization"]["training_label_creation"]
                    is False
                    and active_v3_document["authorization"]["pm_fit"] is False
                )
                or (
                    active_v3.get("id") == "G4B1_ANCHORED_V2_CONTROL_QUALIFICATION"
                    and bool(g4b.get("anchored_v2"))
                    and sha(resolve(g4b["anchored_v2"]["primary_decision_freeze"]["path"]))
                    == g4b["anchored_v2"]["primary_decision_freeze"]["sha256"]
                    and read(resolve(g4b["anchored_v2"]["primary_decision_freeze"]["path"]))["status"]
                    == g4b["anchored_v2"]["primary_decision_freeze"]["required_status"]
                    and active_v3_manifest.get("path")
                    == g4b["anchored_v2"]["active_qualification_phase"]["path"]
                    and active_v3_manifest.get("sha256")
                    == g4b["anchored_v2"]["active_qualification_phase"]["sha256"]
                    and active_v3_document.get("status")
                    == g4b["anchored_v2"]["active_qualification_phase"]["required_status"]
                    and active_v3_document["authorization"]["control_gold_access"]
                    is True
                    and active_v3_document["authorization"]["zero_api_qualification"]
                    is True
                    and active_v3_document["authorization"]["public_reviewer_calls"]
                    is False
                    and active_v3_document["authorization"]["training_label_creation"]
                    is False
                    and active_v3_document["authorization"]["pm_fit"] is False
                    and active_v3_document["authorization"]["generator_calls"] is False
                    and active_v3_document["no_third_instrument_loop"] is True
                )
                or (
                    active_v3.get("id") == "G4B2_PUBLIC_DUAL_REVIEW_EXECUTION"
                    and bool(g4b.get("anchored_v2"))
                    and sha(resolve(g4b["anchored_v2"]["qualification_result"]["path"]))
                    == g4b["anchored_v2"]["qualification_result"]["sha256"]
                    and read(resolve(g4b["anchored_v2"]["qualification_result"]["path"]))["status"]
                    == g4b["anchored_v2"]["qualification_result"]["required_status"]
                    and g4b["anchored_v2"]["qualification_result"]["eligible_components"]
                    == ["MP"]
                    and g4b["anchored_v2"]["qualification_result"]["fixed_off_components"]
                    == ["MS", "ME"]
                    and sha(resolve(g4b["anchored_v2"]["public_preflight"]["path"]))
                    == g4b["anchored_v2"]["public_preflight"]["sha256"]
                    and read(resolve(g4b["anchored_v2"]["public_preflight"]["path"]))["status"]
                    == g4b["anchored_v2"]["public_preflight"]["required_status"]
                    and active_v3_manifest.get("path")
                    == g4b["anchored_v2"]["active_public_phase"]["path"]
                    and active_v3_manifest.get("sha256")
                    == g4b["anchored_v2"]["active_public_phase"]["sha256"]
                    and active_v3_document.get("status")
                    == g4b["anchored_v2"]["active_public_phase"]["required_status"]
                    and active_v3_document["execution"]["eligible_components"]
                    == ["MP"]
                    and active_v3_document["execution"]["logical_calls"] == 408
                    and active_v3_document["authorization"]["public_reviewer_calls"]
                    is True
                    and active_v3_document["authorization"]["private_case_mapping_access"]
                    is False
                    and active_v3_document["authorization"]["training_label_creation"]
                    is False
                    and active_v3_document["authorization"]["pm_fit"] is False
                    and active_v3_document["authorization"]["generator_calls"] is False
                    and active_v3_document["nonexclusive_invariant"]["does_not_impose_one_memory_cap"]
                    is True
                    and active_v3_document["nonexclusive_invariant"]["all_16_requested_actions_remain_downstream"]
                    is True
                )
                or (
                    active_v3.get("id") == "G4B2_MP_PUBLIC_529_NO_COMPLETION_CONTINUATION"
                    and active_v3_document.get("status")
                    == "G4B2_SINGLE_HTTP_529_NO_COMPLETION_CONTINUATION_AUTHORIZED_ONCE"
                    and active_v3_document["execution"]["logical_calls"] == 1
                    and active_v3_document["execution"]["source_status_code"] == 529
                    and active_v3_document["execution"]["source_provider_text"] is None
                    and active_v3_document["execution"]["other_407_calls_must_not_run"] is True
                    and active_v3_document["authorization"]["private_case_mapping_access"] is False
                    and active_v3_document["authorization"]["training_label_creation"] is False
                    and active_v3_document["authorization"]["pm_fit"] is False
                )
                or (
                    active_v3.get("id") == "G4B3_MP_PRE_ADJUDICATION"
                    and active_v3_document.get("status")
                    == "G4B3_ZERO_API_MP_PRIVATE_MAPPING_AND_EXACT_CONSENSUS_LABEL_CREATION_AUTHORIZED_ONCE"
                    and active_v3_document["authorization"]["private_case_mapping_access"] is True
                    and active_v3_document["authorization"]["exact_consensus_label_creation"] is True
                    and active_v3_document["authorization"]["adjudication"] is False
                    and active_v3_document["authorization"]["api_calls"] == 0
                    and active_v3_document["authorization"]["pm_fit"] is False
                    and active_v3_document["label_rule"]["one_of_k_or_one_memory_cap"] is False
                    and active_v3_document["label_rule"]["all_16_actions_remain_downstream"] is True
                )
                or (
                    active_v3.get("id") == "G4B3_MP_MEASUREMENT_FAILURE_AUDIT"
                    and active_v3_document.get("status")
                    == "G4B3_MP_REAL_SURFACE_MEASUREMENT_FAIL_FORMAL_FIT_BLOCKED_METHOD_AUDIT_ONLY"
                    and active_v3_document["authorization"]["read_only_method_audit"] is True
                    and active_v3_document["authorization"]["reviewer_calls"] is False
                    and active_v3_document["authorization"]["label_promotion"] is False
                    and active_v3_document["authorization"]["pm_fit"] is False
                    and active_v3_document["authorization"]["generator_calls"] is False
                )
                or (
                    active_v3.get("id") == "MP_CONSENSUS_DIAGNOSTIC_LOGO_OOF"
                    and active_v3_document.get("status")
                    == "MP_CONSENSUS_DIAGNOSTIC_LOGO_OOF_AUTHORIZED_ONCE_FORMAL_PROMOTION_CHECKPOINT_GENERATOR_FORBIDDEN"
                    and active_v3_document["promoted_from_authority_sha256"]
                    == "dda77972a54730a8f85ade3e58247b42e1c64a31174831db5893e179c76c296f"
                    and active_v3_document["frozen_design"]["rows"] == 136
                    and active_v3_document["frozen_design"]["owner_connected_groups"] == 17
                    and active_v3_document["frozen_design"]["split"]
                    == "17-fold LeaveOneGroupOut"
                    and active_v3_document["frozen_design"]["threshold"] == 0.5
                    and active_v3_document["authorization"]["diagnostic_fit_exactly_once"]
                    is True
                    and active_v3_document["authorization"]["formal_label_promotion"]
                    is False
                    and active_v3_document["authorization"]["threshold_selection"]
                    is False
                    and active_v3_document["authorization"]["feature_change_after_result"]
                    is False
                    and active_v3_document["authorization"]["full_fit_checkpoint"]
                    is False
                    and active_v3_document["authorization"]["generator_calls"]
                    is False
                    and active_v3_document["authorization"]["reviewer_calls"]
                    is False
                    and active_v3_document["authorization"]["baseline_outcome_calls"]
                    is False
                    and active_v3_document["authorization"]["external_outcome_calls"]
                    is False
                    and active_v3_document["nonexclusive_invariant"]["does_not_impose_one_memory_cap"]
                    is True
                    and active_v3_document["nonexclusive_invariant"]["all_16_requested_actions_remain_downstream"]
                    is True
                    and all(
                        sha(resolve(item["path"])) == item["sha256"]
                        for item in [
                            *active_v3_document["input_bindings"],
                            *active_v3_document["implementation_bindings"],
                        ]
                    )
                    and sha(resolve(active_v3_document["readiness_audit"]["path"]))
                    == active_v3_document["readiness_audit"]["sha256"]
                    and read(resolve(active_v3_document["readiness_audit"]["path"]))["status"]
                    == active_v3_document["readiness_audit"]["required_status"]
                )
                or (
                    active_v3.get("id")
                    == "MP_DIAGNOSTIC_CLOSEOUT_MS_ATOMIC_LABEL_AUDIT_DESIGN"
                    and active_v3_document.get("status")
                    == "MP_DIAGNOSTIC_FIELD_PRIOR_DOMINATED_FORMAL_ROUTE_REMAINS_FAIL_MS_SOURCE_AWARE_ATOMIC_LABEL_AUDIT_NEXT"
                    and active_v3_document["stable_head_status"]["RS"] == "OOF_PASS"
                    and "DIAGNOSTIC_FIELD_PRIOR_SIGNAL_ONLY"
                    in active_v3_document["stable_head_status"]["MP"]
                    and "V3_LABEL_UNPROVEN"
                    in active_v3_document["stable_head_status"]["MS"]
                    and active_v3_document["training_and_execution_invariant"]["heads_train_and_qualify_separately"]
                    is True
                    and active_v3_document["training_and_execution_invariant"]["qualified_heads_execute_jointly"]
                    is True
                    and active_v3_document["training_and_execution_invariant"]["requested_action_count"]
                    == 16
                    and active_v3_document["training_and_execution_invariant"]["global_one_memory_cap"]
                    is False
                    and active_v3_document["authorization"]["mp_refit"] is False
                    and active_v3_document["authorization"]["full_fit_checkpoint"] is False
                    and active_v3_document["authorization"]["generator_calls"] is False
                    and active_v3_document["authorization"]["influenced_by_as_response_pm_gold"]
                    is False
                    and active_v3_document["authorization"]["es_memeval_qa_evidence_as_response_pm_gold"]
                    is False
                    and all(
                        sha(resolve(item["path"])) == item["sha256"]
                        and (
                            "required_status" not in item
                            or read(resolve(item["path"]))["status"]
                            == item["required_status"]
                        )
                        for item in [
                            active_v3_document["executed_phase"],
                            active_v3_document["oof_report"],
                            active_v3_document["predictions"],
                            active_v3_document["independent_interpretation_audit"],
                            active_v3_document["documentation"]["repair_plan"],
                            active_v3_document["documentation"]["failure_ledger"],
                        ]
                    )
                )
                or (
                    active_v3.get("id") == "MS_SINGLE_TEACHER_PUBLIC_EXECUTION"
                    and active_v3_document.get("status")
                    == "MS_EXACT_204_SINGLE_QUALIFIED_TEACHER_CALLS_AUTHORIZED_ONCE_LABEL_FIT_GENERATOR_FORBIDDEN"
                    and active_v3_document["execution"]["logical_calls"] == 204
                    and active_v3_document["execution"]["connected_groups"] == 17
                    and active_v3_document["execution"]["absolute_usd_cap"] == 2.5
                    and active_v3_document["label_contract"]["teacher_supervision_not_human_gold"]
                    is True
                    and active_v3_document["label_contract"]["reviewer_b_failure_remains_recorded"]
                    is True
                    and active_v3_document["label_contract"]["influenced_by_as_label"]
                    is False
                    and active_v3_document["label_contract"]["es_memeval_qa_evidence_as_label"]
                    is False
                    and active_v3_document["authorization"]["teacher_api_calls"]
                    is True
                    and active_v3_document["authorization"]["training_label_projection"]
                    is False
                    and active_v3_document["authorization"]["pm_fit"] is False
                    and active_v3_document["authorization"]["generator_calls"] is False
                    and active_v3_document["authorization"]["baseline_calls"] is False
                    and active_v3_document["authorization"]["external_calls"] is False
                    and active_v3_document["nonexclusive_invariant"]["heads_train_and_qualify_separately"]
                    is True
                    and active_v3_document["nonexclusive_invariant"]["qualified_heads_execute_jointly"]
                    is True
                    and active_v3_document["nonexclusive_invariant"]["does_not_impose_one_memory_cap"]
                    is True
                    and active_v3_document["nonexclusive_invariant"]["all_16_requested_actions_remain_downstream"]
                    is True
                    and all(
                        sha(resolve(item["path"])) == item["sha256"]
                        for item in [
                            *active_v3_document["input_bindings"],
                            *active_v3_document["implementation_bindings"],
                        ]
                    )
                )
                or (
                    active_v3.get("id") == "MS_SINGLE_TEACHER_LABEL_FREEZE"
                    and active_v3_document.get("status")
                    == "MS_EXACT_204_ZERO_API_LABEL_FREEZE_AUTHORIZED_ONCE_OOF_GENERATOR_FORBIDDEN"
                    and active_v3_document["alias_recovery_preconditions"]["exact_missing_reviews"]
                    == 5
                    and active_v3_document["alias_recovery_preconditions"]["all_decisions"]
                    == "NOT_SUITABLE"
                    and active_v3_document["alias_recovery_preconditions"]["semantic_rejudgment"]
                    is False
                    and active_v3_document["alias_recovery_preconditions"]["paid_retry"]
                    is False
                    and active_v3_document["label_projection"]
                    == {
                        "SUITABLE": 1,
                        "NOT_SUITABLE": 0,
                        "SEMANTIC_ABSTAIN": None,
                        "abstention_runtime_default": "OFF",
                        "teacher_is_human_gold": False,
                    }
                    and active_v3_document["authorization"]["api_calls"] == 0
                    and active_v3_document["authorization"]["label_freeze_runs"] == 1
                    and active_v3_document["authorization"]["pm_fits"] == 0
                    and active_v3_document["authorization"]["generator_calls"] == 0
                    and active_v3_document["authorization"]["mp_or_me_work"] == 0
                    and all(
                        sha(resolve(item["path"])) == item["sha256"]
                        for item in active_v3_document["input_bindings"]
                    )
                    and sha(resolve(active_v3_document["implementation_binding"]["path"]))
                    == active_v3_document["implementation_binding"]["sha256"]
                )
                or (
                    active_v3.get("id") == "MS_ATOMIC_TEACHER_LOGO_OOF"
                    and active_v3_document.get("status")
                    == "MS_ATOMIC_SINGLE_TEACHER_EXACT_ONE_IDENTITY_FREE_LOGO_OOF_AUTHORIZED"
                    and active_v3_document["frozen_denominator"]
                    == {
                        "resolved_rows": 201,
                        "abstentions_excluded": 3,
                        "connected_groups": 17,
                        "positive": 73,
                        "negative": 128,
                    }
                    and active_v3_document["frozen_primary_model"]["C"] == 0.1
                    and active_v3_document["frozen_primary_model"]["threshold"] == 0.5
                    and active_v3_document["frozen_primary_model"]["split"]
                    == "LeaveOneConnectedGroupOut"
                    and active_v3_document["authorization"]["oof_runs"] == 1
                    and active_v3_document["authorization"]["full_fit_checkpoints"] == 0
                    and active_v3_document["authorization"]["api_calls"] == 0
                    and active_v3_document["authorization"]["generator_calls"] == 0
                    and active_v3_document["authorization"]["mp_or_me_work"] == 0
                    and all(
                        sha(resolve(item["path"])) == item["sha256"]
                        and (
                            "required_status" not in item
                            or read(resolve(item["path"]))["status"] == item["required_status"]
                        )
                        for item in [
                            *active_v3_document["input_bindings"],
                            *active_v3_document["implementation_bindings"],
                        ]
                    )
                )
                or (
                    active_v3.get("id") == "MS_ATOMIC_TEACHER_FULL_FIT"
                    and active_v3_document.get("status")
                    == "MS_ATOMIC_TEACHER_FROZEN_FULL_FIT_AUTHORIZED_ONCE_EXECUTOR_STILL_REQUIRED"
                    and active_v3_document["frozen_fit"]["resolved_rows"] == 201
                    and active_v3_document["frozen_fit"]["connected_groups"] == 17
                    and active_v3_document["frozen_fit"]["positive"] == 73
                    and active_v3_document["frozen_fit"]["negative"] == 128
                    and active_v3_document["frozen_fit"]["C"] == 0.1
                    and active_v3_document["frozen_fit"]["threshold"] == 0.5
                    and active_v3_document["authorization"]["full_fit_runs"] == 1
                    and active_v3_document["authorization"]["api_calls"] == 0
                    and active_v3_document["authorization"]["generator_calls"] == 0
                    and active_v3_document["authorization"]["executor_qualification_runs"] == 0
                    and active_v3_document["authorization"]["mp_or_me_work"] == 0
                    and all(
                        sha(resolve(item["path"])) == item["sha256"]
                        and (
                            "required_status" not in item
                            or read(resolve(item["path"]))["status"] == item["required_status"]
                        )
                        for item in [
                            *active_v3_document["input_bindings"],
                            *active_v3_document["implementation_bindings"],
                        ]
                    )
                )
                or (
                    active_v3.get("id") == "MS_EXECUTOR_QUALIFICATION_DESIGN"
                    and active_v3_document.get("status")
                    == "MS_ATOMIC_SELECTOR_TRAINED_OOF_SIGNAL_PRESENT_EXECUTOR_QUALIFICATION_NEXT"
                    and active_v3_document["training_supervision"]["resolved_binary"] == 201
                    and active_v3_document["training_supervision"]["connected_groups"] == 17
                    and active_v3_document["training_supervision"]["influenced_by_or_qa_used_as_label"]
                    is False
                    and active_v3_document["cross_fitted_evidence"]["roc_auc"]
                    == 0.8289811643835616
                    and active_v3_document["cross_fitted_evidence"]["balanced_accuracy_at_0_5"]
                    == 0.7449165239726028
                    and active_v3_document["checkpoint"]["rerun_or_refit_allowed"] is False
                    and active_v3_document["next_authority"]
                    == {"phase": "MS_EXECUTOR_QUALIFICATION_DESIGN", "api_calls": 0, "pm_fits": 0, "mp_or_me_work": 0}
                    and all(
                        sha(resolve(item["path"])) == item["sha256"]
                        and (
                            "required_status" not in item
                            or read(resolve(item["path"]))["status"] == item["required_status"]
                        )
                        for item in [
                            active_v3_document["cross_fitted_evidence"],
                            active_v3_document["checkpoint"]["report"],
                            active_v3_document["checkpoint"]["model"],
                            active_v3_document["checkpoint"]["feature_schema"],
                        ]
                    )
                )
                or (
                    active_v3.get("id") == "MS_EXECUTOR_QUALIFICATION_EXECUTION"
                    and active_v3_document.get("status")
                    == "EXACT_64_MS_EXECUTOR_QUALIFICATION_CALLS_AUTHORIZED_ONCE_NO_REFIT_NO_MP_ME"
                    and active_v3_document["execution"]["states"] == 16
                    and active_v3_document["execution"]["connected_groups"] == 8
                    and active_v3_document["execution"]["logical_primary_calls"] == 64
                    and active_v3_document["execution"]["absolute_usd_cap"] == 0.05
                    and active_v3_document["authorization"]["generator_calls"] is True
                    and active_v3_document["authorization"]["pm_refit"] is False
                    and active_v3_document["authorization"]["training_label_change"] is False
                    and active_v3_document["authorization"]["MP_work"] is False
                    and active_v3_document["authorization"]["ME_work"] is False
                    and active_v3_document["invariants"]["global_requested_action_count"] == 16
                    and active_v3_document["invariants"]["one_memory_cap"] is False
                    and active_v3_document["invariants"]["MS_RS_relation"] == "COMPLEMENTARY"
                    and all(
                        sha(resolve(item["path"])) == item["sha256"]
                        for item in [
                            *active_v3_document["input_bindings"],
                            *active_v3_document["implementation_bindings"],
                        ]
                    )
                )
                or (
                    active_v3.get("id")
                    == "MS_EXECUTOR_QUALIFICATION_MEASUREMENT_DESIGN"
                    and active_v3_document.get("status")
                    == "MS_EXECUTOR_GENERATION_COMPLETE_TRACE_RESPONSIBILITY_REPAIRED_SOURCE_AWARE_MEASUREMENT_NEXT"
                    and active_v3_document["live_result"]["logical_primary_calls"] == 64
                    and active_v3_document["zero_api_recovery"]["rows"] == 64
                    and active_v3_document["zero_api_recovery"]["trace_sanitized"] == 11
                    and active_v3_document["zero_api_recovery"]["content_contamination_requiring_retry"] == 0
                    and active_v3_document["paid_release"]["paid_execution_authorized"] is False
                    and active_v3_document["paid_release"]["stage_approvals_empty"] is True
                    and active_v3_document["authorization"]["api_calls"] == 0
                    and active_v3_document["authorization"]["pm_refit"] is False
                    and active_v3_document["authorization"]["MP_work"] is False
                    and active_v3_document["authorization"]["ME_work"] is False
                    and all(
                        sha(resolve(item["path"])) == item["sha256"]
                        for item in [
                            active_v3_document["executed_phase"],
                            active_v3_document["live_result"],
                            *active_v3_document["raw_artifacts"],
                            active_v3_document["responsibility_correction"]["patched_response_program"],
                            active_v3_document["zero_api_recovery"]["report"],
                            active_v3_document["zero_api_recovery"]["recovered_first_replies"],
                            active_v3_document["paid_release"],
                        ]
                    )
                )
                or (
                    active_v3.get("id") == "MS_EXECUTOR_QUALIFIED_REVIEW_PENDING"
                    and active_v3_document.get("status")
                    == "MS_EXECUTOR_BLIND_MEASUREMENT_PACKET_READY_QUALIFIED_REVIEW_REQUIRED"
                    and active_v3_document["measurement_packet"]["function_items"] == 32
                    and active_v3_document["measurement_packet"]["quality_pairs"] == 32
                    and active_v3_document["measurement_packet"]["risk_items"] == 64
                    and active_v3_document["mechanical_audit"]["exact_source_copies"] == 0
                    and active_v3_document["mechanical_audit"]["generator_claim_is_function_gold"] is False
                    and active_v3_document["claim_boundary"]["MS_selector_trained"] is True
                    and active_v3_document["claim_boundary"]["MS_executor_function_pass"]
                    == "PENDING_QUALIFIED_BLIND_REVIEW"
                    and active_v3_document["authorization"]["api_judge_calls"] is False
                    and active_v3_document["authorization"]["pm_refit"] is False
                    and active_v3_document["authorization"]["MP_work"] is False
                    and active_v3_document["authorization"]["ME_work"] is False
                    and all(
                        sha(resolve(item["path"])) == item["sha256"]
                        for item in [
                            active_v3_document["measurement_packet"],
                            active_v3_document["mechanical_audit"],
                        ]
                    )
                )
                or (
                    active_v3.get("id") == "R0_FUNCTION_FORCED_OPEN_CARD_PACKETS_CORRECTED_PI_REVIEW_NEXT"
                    and active_v3_document.get("status")
                    == "ZERO_API_CORRECTED_PACKETS_READY_PI_REVIEW_NEXT"
                    and active_v3_document["primary_success_rule"]["machine_predicate"]
                    == "RS_pass AND count_pass(MP,MS,ME) >= 2"
                    and active_v3_document["diagnostic"]["MS_R0_Function"]["cases"] == 7
                    and active_v3_document["diagnostic"]["MS_R0_Function"]["connected_groups"] == 7
                    and active_v3_document["diagnostic"]["MS_R0_Function"]["unchanged_from_v1"] is True
                    and active_v3_document["diagnostic"]["forced_open_card_closure"]["cases"] == 2
                    and active_v3_document["diagnostic"]["forced_open_card_closure"]["actual_rank1_selection_mode"]
                    == "lexical_fallback"
                    and active_v3_document["diagnostic"]["forced_open_card_closure"]["all_observable_opportunity_flags_false"] is True
                    and active_v3_document["diagnostic"]["forced_open_card_closure"]["all_transparent_rule_off"] is True
                    and active_v3_document["diagnostic"]["forced_open_card_closure"]["compatible_full_fit_RS_checkpoint_exists"] is False
                    and active_v3_document["authorization"]["PI_source_aware_Function_review"] is True
                    and active_v3_document["authorization"]["PI_forced_open_card_closure_quality_review"] is True
                    and active_v3_document["authorization"]["API_calls"] == 0
                    and active_v3_document["authorization"]["response_generation"] is False
                    and active_v3_document["authorization"]["PM_refit"] is False
                    and active_v3_document["authorization"]["threshold_change"] is False
                    and active_v3_document["authorization"]["training_label_creation"] is False
                    and sha(resolve(active_v3_document["measurement_contract"]["path"]))
                    == active_v3_document["measurement_contract"]["sha256"]
                    and all(
                        sha(resolve(item["path"])) == item["sha256"]
                        for item in active_v3_document["artifacts"]
                    )
                )
                or (
                    active_v3.get("id") == "R0_FUNCTION_CLOSURE_PACKETS_READY_PI_REVIEW_NEXT"
                    and active_v3_document.get("status")
                    == "ZERO_API_EXISTING_ARM_DIAGNOSTIC_PACKETS_READY_PI_REVIEW_NEXT"
                    and active_v3_document["primary_success_rule"]["machine_predicate"]
                    == "RS_pass AND count_pass(MP,MS,ME) >= 2"
                    and active_v3_document["diagnostic"]["MS_R0_Function"]["cases"] == 7
                    and active_v3_document["diagnostic"]["MS_R0_Function"]["connected_groups"] == 7
                    and active_v3_document["diagnostic"]["MS_R0_Function"]["matched_PI_usable_sources"] == 7
                    and active_v3_document["diagnostic"]["MS_R0_Function"]["generator_claimed_MS"] == 3
                    and active_v3_document["diagnostic"]["MS_R0_Function"]["formal_source_aware_Function"]
                    == "PENDING_PI_REVIEW"
                    and active_v3_document["diagnostic"]["closure_routing"]["cases"] == 2
                    and active_v3_document["diagnostic"]["closure_routing"]["kept_separate_from_MS_Function"] is True
                    and active_v3_document["authorization"]["PI_source_aware_Function_review"] is True
                    and active_v3_document["authorization"]["PI_closure_quality_review"] is True
                    and active_v3_document["authorization"]["API_calls"] == 0
                    and active_v3_document["authorization"]["response_generation"] is False
                    and active_v3_document["authorization"]["PM_refit"] is False
                    and active_v3_document["authorization"]["threshold_change"] is False
                    and active_v3_document["authorization"]["training_label_creation"] is False
                    and all(
                        sha(resolve(item["path"])) == item["sha256"]
                        for item in active_v3_document["artifacts"]
                    )
                )
                or (
                    active_v3.get("id") == "RS_MS_PI_ADJUDICATED_FUNCTION_FAIL_R0_DIAGNOSTIC_DESIGN_NEXT"
                    and active_v3_document.get("status")
                    == "PI_ADJUDICATED_RS_MS_FUNCTION_FAIL_R0_DIAGNOSTIC_DESIGN_NEXT"
                    and active_v3_document["observed"]["states"] == 16
                    and active_v3_document["observed"]["learned_ms_on_states"] == 7
                    and active_v3_document["observed"]["quality_pi_final_learned_on"]
                    == "5 MS-win / 2 RS-only-win"
                    and active_v3_document["observed"]["verified_function_pi_final_learned_on"] == "0/7"
                    and active_v3_document["observed"]["verified_function_pi_final_all"] == "0/16"
                    and active_v3_document["observed"]["source_availability_pi_final_all"] == "8/16"
                    and active_v3_document["observed"]["conditional_execution_success_pi_final"] == "0/8"
                    and active_v3_document["observed"]["closure_states_learned_ms_off"] == 2
                    and active_v3_document["authorization"]["repeat_disagreement_adjudication"] is False
                    and active_v3_document["authorization"]["modify_raw_A_B"] is False
                    and active_v3_document["authorization"]["declare_independent_human_IAA"] is False
                    and active_v3_document["authorization"]["declare_MS_pass"] is False
                    and active_v3_document["authorization"]["r0_existing_arm_zero_api_diagnostic_design"] is True
                    and active_v3_document["authorization"]["r0_diagnostic_execution"] is False
                    and active_v3_document["authorization"]["api_calls"] == 0
                    and active_v3_document["authorization"]["response_generation"] is False
                    and active_v3_document["authorization"]["pm_refit"] is False
                    and sha(resolve(active_v3_document["problem_ledger"]["path"]))
                    == active_v3_document["problem_ledger"]["sha256"]
                    and all(
                        entry in resolve(active_v3_document["problem_ledger"]["path"]).read_text(encoding="utf-8")
                        for entry in active_v3_document["problem_ledger"]["required_entries"]
                    )
                    and all(sha(resolve(item["path"])) == item["sha256"] for item in active_v3_document["artifacts"])
                )
                or (
                    active_v3.get("id") == "RS_MS_DUAL_HUMAN_BLIND_BUNDLE_READY"
                    and active_v3_document.get("status")
                    == "DUAL_HUMAN_BLIND_BUNDLE_READY_LABELS_NOT_STARTED"
                    and active_v3_document["scope"]["quality_pairs_per_reviewer"] == 16
                    and active_v3_document["scope"]["risk_absolute_items_per_reviewer"] == 32
                    and active_v3_document["scope"]["function_source_aware_items_per_reviewer"] == 16
                    and active_v3_document["scope"]["total_items_per_reviewer"] == 64
                    and active_v3_document["scope"]["independent_full_overlap"] is True
                    and active_v3_document["pre_review_repairs"]["quality_past_source_hidden"] is True
                    and active_v3_document["pre_review_repairs"]["quality_ms_on_position_v2"]
                    == {"A": 8, "B": 8}
                    and active_v3_document["pre_review_repairs"]["response_text_changes"] == 0
                    and active_v3_document["pre_review_repairs"]["labels_seen_before_repair"] == 0
                    and active_v3_document["measurement_rules"]["raw_A_B_disagreements_preserved"] is True
                    and active_v3_document["measurement_rules"]["majority_vote_forbidden"] is True
                    and active_v3_document["authorization"]["human_offline_annotation"] is True
                    and active_v3_document["authorization"]["llm_reviewer_calls"] is False
                    and active_v3_document["authorization"]["api_calls"] == 0
                    and active_v3_document["authorization"]["response_generation"] is False
                    and active_v3_document["authorization"]["pm_refit"] is False
                    and active_v3_document["authorization"]["private_key_access_before_both_human_files_freeze"] is False
                    and active_v3_document["authorization"]["aggregation_before_both_human_files_freeze"] is False
                    and sha(resolve(active_v3_document["problem_ledger"]["path"]))
                    == active_v3_document["problem_ledger"]["sha256"]
                    and all(
                        entry
                        in resolve(active_v3_document["problem_ledger"]["path"]).read_text(encoding="utf-8")
                        for entry in active_v3_document["problem_ledger"]["required_entries"]
                    )
                    and all(
                        sha(resolve(item["path"])) == item["sha256"]
                        for item in active_v3_document["artifacts"]
                    )
                )
                or (
                    active_v3.get("id") == "RS_MS_SAME_STACK_BASELINE_PLAN_COMPLETE"
                    and active_v3_document.get("status")
                    == "ZERO_API_BASELINE_ACTIONS_AND_MINIMAL_BLIND_RS_SLICE_MATERIALIZED"
                    and active_v3_document.get("decision")
                    == "ONE_BLIND_16_PAIR_RS_SLICE_OUTCOME_MEASUREMENT_MAY_BE_DESIGNED_NO_GENERATION_OR_REFIT"
                    and active_v3_document["scope"]["primary_policy"]
                    == "RS fixed ON plus learned MS"
                    and active_v3_document["scope"]["primary_comparator"] == "RS-only"
                    and active_v3_document["scope"]["global_action_space_unchanged"] == 16
                    and active_v3_document["observed"]["states"] == 16
                    and active_v3_document["observed"]["connected_groups"] == 8
                    and active_v3_document["observed"]["existing_responses"] == 64
                    and active_v3_document["observed"]["learned_ms_on"] == 7
                    and active_v3_document["observed"]["learned_ms_off"] == 9
                    and active_v3_document["authorization"]["api_calls"] == 0
                    and active_v3_document["authorization"]["response_generation"] is False
                    and active_v3_document["authorization"]["pm_refit"] is False
                    and active_v3_document["authorization"]["threshold_change"] is False
                    and active_v3_document["authorization"]["quality_or_risk_label_creation"] is False
                    and active_v3_document["authorization"]["blind_measurement_phase_design"] is True
                    and active_v3_document["authorization"]["blind_measurement_execution"] is False
                    and active_v3_document["authorization"]["MP_work"] is False
                    and active_v3_document["authorization"]["ME_work"] is False
                    and all(
                        sha(resolve(item["path"])) == item["sha256"]
                        for item in active_v3_document["artifacts"]
                    )
                )
                or (
                    active_v3.get("id") == "MS_EXECUTOR_FUNCTION_PARTIAL_FEASIBILITY_COMPLETE"
                    and active_v3_document.get("status")
                    == "POSITIVE_MEANING_ABSORPTION_SUPPORTED_NEGATIVE_SELF_SUPPRESSION_WEAK_PARTIAL_PROXY_ONLY"
                    and active_v3_document.get("decision")
                    == "PROCEED_TO_BOUNDED_RS_MS_SAME_STACK_BASELINE_DESIGN_NOT_PAPER_FINAL_FUNCTION_CLAIM"
                    and active_v3_document["observed"]["accepted_public_reviews"] == 24
                    and active_v3_document["observed"]["planned_public_reviews"] == 32
                    and active_v3_document["observed"]["suitable_functional"] == "12/12"
                    and active_v3_document["observed"]["not_suitable_safe_nonuse"] == "6/12"
                    and active_v3_document["observed"]["paper_final_function_pass"] is False
                    and active_v3_document["measurement_boundary"]["single_proxy"] is True
                    and active_v3_document["measurement_boundary"]["human_gold"] is False
                    and active_v3_document["paid_release"]["paid_execution_authorized"] is False
                    and active_v3_document["paid_release"]["stage_approvals_empty"] is True
                    and active_v3_document["authorization"]["api_calls"] == 0
                    and active_v3_document["authorization"]["baseline_design_zero_api"] is True
                    and active_v3_document["authorization"]["baseline_execution"] is False
                    and active_v3_document["authorization"]["MP_work"] is False
                    and active_v3_document["authorization"]["ME_work"] is False
                    and all(
                        sha(resolve(item["path"])) == item["sha256"]
                        for item in active_v3_document["artifacts"]
                    )
                )
                or (
                    active_v3.get("id") == "MS_EXECUTOR_FUNCTION_PROXY_EXECUTION"
                    and active_v3_document.get("status")
                    in {
                        "SEQUENTIAL_TWO_PROXY_FUNCTION_CONTROL_QUALIFICATION_THEN_PUBLIC_REVIEW_AUTHORIZED_ONCE",
                        "ONE_PRE_GOLD_CONTROL_CARRIED_THEN_SEQUENTIAL_TWO_PROXY_REVIEW_AUTHORIZED_ONCE",
                        "CLEAN_GEMINI_GPT_SEQUENTIAL_FUNCTION_CONTROL_THEN_PUBLIC_REVIEW_AUTHORIZED_ONCE",
                        "EIGHT_PRE_GOLD_CONTROLS_CARRIED_AFTER_TRANSIENT_THEN_REMAINING_REVIEW_AUTHORIZED_ONCE",
                        "EIGHT_PRE_GOLD_CONTROLS_CARRIED_PROVIDER_BUDGET_BOUND_REVIEW_AUTHORIZED_ONCE",
                        "SINGLE_QUALIFIED_PROXY_FUNCTION_FEASIBILITY_AUTHORIZED_ONCE",
                        "GPT_FUNCTION_ID_ONLY_REPAIR_THEN_TEN_PUBLIC_CALLS_AUTHORIZED_ONCE",
                    }
                    and (
                        active_v3_document["execution"].get("control_calls") in {12, 24}
                        or (
                            active_v3_document["execution"].get("control_reviews_carried") == 12
                            and active_v3_document["execution"].get("public_reviews_carried") == 21
                            and active_v3_document["execution"].get("public_reviews_recovered_zero_api") == 1
                            and active_v3_document["execution"].get("maximum_new_logical_calls") == 10
                            and active_v3_document["execution"].get("label_or_evidence_changed_by_repair") is False
                        )
                        or (
                            active_v3_document["execution"].get("control_reviews_total") == 24
                            and active_v3_document["execution"].get("control_reviews_carried") in {1, 8}
                            and active_v3_document["execution"].get("maximum_new_control_calls")
                            == 24 - active_v3_document["execution"].get("control_reviews_carried")
                            and active_v3_document["execution"].get("maximum_new_logical_calls")
                            == 88 - active_v3_document["execution"].get("control_reviews_carried")
                            and active_v3_document["execution"].get("carry_is_pre_gold") is True
                            and (
                                active_v3_document["execution"].get("carry_changes_label_or_decision_evidence") is False
                                or active_v3_document["execution"].get("carry_changes_labels") is False
                            )
                        )
                    )
                    and (
                        active_v3_document["execution"].get("public_calls_only_if_both_qualify") == 64
                        or active_v3_document["execution"].get("public_calls_only_if_proxy_qualifies") == 32
                        or active_v3_document["execution"].get("maximum_new_public_calls") == 10
                    )
                    and active_v3_document["execution"].get("maximum_logical_calls", 88) in {44, 88}
                    and active_v3_document["execution"]["absolute_usd_cap"] in {0.5, 1.0, 2.0}
                    and active_v3_document["authorization"]["function_proxy_api_calls"] is True
                    and active_v3_document["authorization"]["human_gold_claim"] is False
                    and active_v3_document["authorization"]["quality_or_risk_judging"] is False
                    and active_v3_document["authorization"]["pm_refit"] is False
                    and active_v3_document["authorization"]["MP_work"] is False
                    and active_v3_document["authorization"]["ME_work"] is False
                    and all(
                        sha(resolve(item["path"])) == item["sha256"]
                        for item in [
                            *active_v3_document["input_bindings"],
                            *active_v3_document["implementation_bindings"],
                        ]
                    )
                )
                or (
                    active_v3.get("id") == "MS_ORACLE_PLAN_UPPER_BOUND_EXECUTION"
                    and active_v3_document.get("status")
                    == "EXACT_8_ORACLE_PLAN_MS_R0_CALLS_AUTHORIZED_ONCE"
                    and active_v3_document["method_version"]
                    == "PAPER1_SOURCE_ANNOTATED_RESOURCE_SUITABILITY_V2"
                    and active_v3_document["experiment_revision"]
                    == "SEMANTIC_ADAPTER_ABLATION_V1"
                    and active_v3_document["execution"]["states"] == 8
                    and active_v3_document["execution"]["use_if_natural_controls"] == 6
                    and active_v3_document["execution"]["safe_nonuse_controls"] == 2
                    and active_v3_document["execution"]["logical_primary_calls"] == 8
                    and active_v3_document["execution"]["absolute_usd_cap"] == 0.01
                    and active_v3_document["authorization"]["generator_calls"] is True
                    and active_v3_document["authorization"]["pm_refit"] is False
                    and active_v3_document["authorization"]["threshold_change"] is False
                    and active_v3_document["authorization"]["training_label_change"] is False
                    and active_v3_document["authorization"]["MP_or_ME_work"] is False
                    and active_v3_document["authorization"]["baseline_or_external_calls"] is False
                    and active_v3_document["invariants"]["full_sixteen_action_space_unchanged"] is True
                    and active_v3_document["invariants"]["oracle_is_never_pm_input_or_gold"] is True
                    and all(
                        sha(resolve(item["path"])) == item["sha256"]
                        for item in [
                            *active_v3_document["input_bindings"],
                            *active_v3_document["implementation_bindings"],
                        ]
                    )
                )
                or (
                    active_v3.get("id") == "MS_ORACLE_PLAN_RESPONSIBILITY_AUDIT"
                    and active_v3_document.get("status")
                    == "ORACLE_PLAN_GENERATION_COMPLETE_PAID_RELEASE_CLOSED_ZERO_API_RESPONSIBILITY_AUDIT_NEXT"
                    and active_v3_document["observed"]["logical_calls"] == 8
                    and active_v3_document["observed"]["semantic_calls"] == 8
                    and active_v3_document["observed"]["transport_retries"] == 0
                    and active_v3_document["observed"]["total_tokens"] == 8896
                    and active_v3_document["authorization"]["api_calls"] == 0
                    and active_v3_document["authorization"]["zero_api_responsibility_audit"] is True
                    and active_v3_document["authorization"]["blind_review_execution"] is False
                    and active_v3_document["authorization"]["pm_refit"] is False
                    and active_v3_document["authorization"]["training_label_change"] is False
                    and active_v3_document["authorization"]["MP_or_ME_work"] is False
                    and all(
                        sha(resolve(item["path"])) == item["sha256"]
                        for item in active_v3_document["artifacts"]
                    )
                    and sha(resolve(active_v3_document["executed_phase"]["path"]))
                    == active_v3_document["executed_phase"]["sha256"]
                )
                or (
                    active_v3.get("id") == "MS_SUPERVISION_UNIT_REPAIR_DESIGN"
                    and active_v3_document.get("status")
                    == "ORACLE_AUDIT_COMPLETE_MS_SUPERVISION_UNIT_REPAIR_DESIGN_NEXT_NO_REFIT"
                    and active_v3_document["method_version"]
                    == "PAPER1_SOURCE_ANNOTATED_RESOURCE_SUITABILITY_V2"
                    and active_v3_document["diagnostic_result"]["intended_use_controls"] == 6
                    and active_v3_document["diagnostic_result"]["source_attributable_functional"] == 2
                    and active_v3_document["diagnostic_result"]["not_used"] == 3
                    and active_v3_document["diagnostic_result"]["execution_failure"] == 1
                    and active_v3_document["diagnostic_result"]["safe_nonuse_correct"] == 2
                    and active_v3_document["diagnostic_result"]["generic_nli_accepted"] is False
                    and active_v3_document["repaired_MS_supervision_unit"]["teacher_suitable_is_not_automatically_positive"] is True
                    and active_v3_document["bounded_next_phase"]["no_open_review_repair_loop"] is True
                    and active_v3_document["authorization"]["zero_api_packet_design"] is True
                    and active_v3_document["authorization"]["review_calls"] is False
                    and active_v3_document["authorization"]["training_label_change"] is False
                    and active_v3_document["authorization"]["pm_refit"] is False
                    and active_v3_document["authorization"]["generator_calls"] is False
                    and all(
                        sha(resolve(item["path"])) == item["sha256"]
                        for item in active_v3_document["evidence"]
                    )
                )
                or (
                    active_v3.get("id") == "MS_SUPERVISION_REPAIR_PACKET_READY"
                    and active_v3_document.get("status")
                    == "MS_REPAIR_PACKET_MATERIALIZED_ZERO_API_FIXED_CONTROL_QUALIFICATION_DESIGN_NEXT"
                    and active_v3_document["method_version"]
                    == "PAPER1_SOURCE_ANNOTATED_RESOURCE_SUITABILITY_V2"
                    and active_v3_document["experiment_revision"]
                    == "SEMANTIC_ADAPTER_ABLATION_V1"
                    and active_v3_document["observed"]["resolved_review_units"] == 201
                    and active_v3_document["observed"]["repaired_target_complete_before_reannotation"] == 0
                    and active_v3_document["observed"]["qualification_controls"] == 12
                    and active_v3_document["observed"]["control_distribution"]
                    == {"SUITABLE": 5, "NOT_SUITABLE": 5, "SEMANTIC_ABSTAIN": 2}
                    and active_v3_document["authorization"]["control_qualification_design"] is True
                    and active_v3_document["authorization"]["control_review_execution"] is False
                    and active_v3_document["authorization"]["public_201_reannotation"] is False
                    and active_v3_document["authorization"]["training_label_change"] is False
                    and active_v3_document["authorization"]["pm_fit_or_threshold_change"] is False
                    and active_v3_document["authorization"]["generator_calls"] is False
                    and active_v3_document["invariants"]["one_per_component_label_not_one_memory_cap"] is True
                    and active_v3_document["invariants"]["sixteen_requested_actions_unchanged"] is True
                    and sha(resolve(active_v3_document["executed_phase"]["path"]))
                    == active_v3_document["executed_phase"]["sha256"]
                    and all(
                        sha(resolve(item["path"])) == item["sha256"]
                        for item in active_v3_document["artifacts"]
                    )
                )
            )
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "protocol": "pm-v1.5-paper1-active-method-authority-readiness-v2",
        "status": "ACTIVE_AUTHORITY_PASS_V2_TERMINAL_WITH_SEPARATE_SYSTEM_FEASIBILITY" if not failed else "ACTIVE_AUTHORITY_FAIL_CLOSED",
        "active_method_id": active["method_id"],
        "current_phase": current_execution.get("id"),
        "historical_v2_phase": authority["current_phase"]["id"],
        "active_v3_phase": active_v3.get("id"),
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
            "v3_primary_success_rule_sha256": sha(resolve(primary_success_binding["path"])),
        },
        "next": (
            "DESIGN_FIXED_12_CONTROL_SOURCE_AWARE_QUALIFICATION_NO_PUBLIC_REANNOTATION"
            if active_v3.get("id") == "MS_SUPERVISION_REPAIR_PACKET_READY"
            else
            "DESIGN_ZERO_API_MS_SUPERVISION_REPAIR_PACKET_FROM_FROZEN_201_ROWS"
            if active_v3.get("id") == "MS_SUPERVISION_UNIT_REPAIR_DESIGN"
            else
            "RUN_ZERO_API_SOURCE_AWARE_RESPONSIBILITY_AUDIT_AND_BUILD_BLIND_PACKET"
            if active_v3.get("id") == "MS_ORACLE_PLAN_RESPONSIBILITY_AUDIT"
            else
            "EXECUTE_EXACT_8_MS_ORACLE_PLAN_UPPER_BOUND_CALLS"
            if active_v3.get("id") == "MS_ORACLE_PLAN_UPPER_BOUND_EXECUTION"
            else
            "PI_REVIEW_SEVEN_R0_FUNCTION_AND_TWO_FORCED_OPEN_CARD_CLOSURE_ITEMS"
            if active_v3.get("id") == "R0_FUNCTION_FORCED_OPEN_CARD_PACKETS_CORRECTED_PI_REVIEW_NEXT"
            else
            "PI_REVIEW_SEVEN_R0_FUNCTION_AND_TWO_CLOSURE_ROUTING_EXISTING_ARM_ITEMS"
            if active_v3.get("id") == "R0_FUNCTION_CLOSURE_PACKETS_READY_PI_REVIEW_NEXT"
            else
            "DESIGN_ZERO_API_EXISTING_R0_SLICE_DIAGNOSTIC_TO_SEPARATE_RS_CROWD_OUT_FROM_GENERAL_MS_NONUSE"
            if active_v3.get("id") == "RS_MS_PI_ADJUDICATED_FUNCTION_FAIL_R0_DIAGNOSTIC_DESIGN_NEXT"
            else
            "FREEZE_HUMAN_A_AND_HUMAN_B_JSON_EXPORTS_THEN_ZERO_API_AGGREGATION"
            if active_v3.get("id") == "RS_MS_DUAL_HUMAN_BLIND_BUNDLE_READY"
            else
            "DESIGN_ONE_BLIND_RS_SLICE_OUTCOME_MEASUREMENT_PHASE"
            if active_v3.get("id") == "RS_MS_SAME_STACK_BASELINE_PLAN_COMPLETE"
            else
            "MATERIALIZE_ZERO_API_RS_MS_SAME_STACK_BASELINE_PLAN_FROM_EXISTING_ARMS"
            if active_v3.get("id") == "MS_EXECUTOR_FUNCTION_PARTIAL_FEASIBILITY_COMPLETE"
            else
            "RUN_SEQUENTIAL_FUNCTION_PROXY_CONTROLS_THEN_PUBLIC_REVIEWS"
            if active_v3.get("id") == "MS_EXECUTOR_FUNCTION_PROXY_EXECUTION"
            else "COMPLETE_TWO_IDENTIFIED_HUMAN_BLIND_REVIEWS_OR_QUALIFY_A_PROXY_SEPARATELY"
            if active_v3.get("id") == "MS_EXECUTOR_QUALIFIED_REVIEW_PENDING"
            else "MATERIALIZE_BLIND_SOURCE_AWARE_MS_EXECUTOR_MEASUREMENT_PACKET_ZERO_API"
            if active_v3.get("id")
            == "MS_EXECUTOR_QUALIFICATION_MEASUREMENT_DESIGN"
            else "EXECUTE_EXACT_64_MS_MEANING_ABSORPTION_CALLS"
            if active_v3.get("id") == "MS_EXECUTOR_QUALIFICATION_EXECUTION"
            else "DESIGN_BOUNDED_MS_MEANING_ABSORPTION_QUALIFICATION_ZERO_API"
            if active_v3.get("id") == "MS_EXECUTOR_QUALIFICATION_DESIGN"
            else "FIT_EXACT_ONE_MS_ATOMIC_SUITABILITY_CHECKPOINT"
            if active_v3.get("id") == "MS_ATOMIC_TEACHER_FULL_FIT"
            else "RUN_EXACT_ONE_FROZEN_MS_ATOMIC_TEACHER_LOGO_OOF"
            if active_v3.get("id") == "MS_ATOMIC_TEACHER_LOGO_OOF"
            else "EXECUTE_ONE_ZERO_API_MS_LABEL_FREEZE"
            if active_v3.get("id") == "MS_SINGLE_TEACHER_LABEL_FREEZE"
            else "EXECUTE_EXACT_204_MS_SINGLE_TEACHER_CALLS"
            if active_v3.get("id") == "MS_SINGLE_TEACHER_PUBLIC_EXECUTION"
            else "DESIGN_MS_SOURCE_AWARE_EXACT_TURN_LABEL_ROUTE_READINESS_AUDIT_ZERO_API"
            if active_v3.get("id")
            == "MP_DIAGNOSTIC_CLOSEOUT_MS_ATOMIC_LABEL_AUDIT_DESIGN"
            else "RUN_EXACT_ONE_FROZEN_MP_CONSENSUS_DIAGNOSTIC_LOGO_OOF"
            if active_v3.get("id") == "MP_CONSENSUS_DIAGNOSTIC_LOGO_OOF"
            else "RUN_ZERO_API_METHOD_LEVEL_SOURCE_AWARE_MP_MEASUREMENT_FAILURE_AUDIT"
            if active_v3.get("id") == "G4B3_MP_MEASUREMENT_FAILURE_AUDIT"
            else "RUN_ZERO_API_G4B3_MP_PRE_ADJUDICATION_EXACT_CONSENSUS"
            if active_v3.get("id") == "G4B3_MP_PRE_ADJUDICATION"
            else "EXECUTE_EXACT_ONE_G4B2_MP_HTTP_529_NO_COMPLETION_CONTINUATION"
            if active_v3.get("id") == "G4B2_MP_PUBLIC_529_NO_COMPLETION_CONTINUATION"
            else "EXECUTE_EXACT_408_G4B2_MP_PUBLIC_DUAL_REVIEWS_NO_PRIVATE_MAPPING"
            if active_v3.get("id") == "G4B2_PUBLIC_DUAL_REVIEW_EXECUTION"
            else "RUN_ZERO_API_G4B1_ANCHORED_V2_POST_FREEZE_CONTROL_QUALIFICATION"
            if active_v3.get("id") == "G4B1_ANCHORED_V2_CONTROL_QUALIFICATION"
            else "RUN_ZERO_API_G4B1_POST_FREEZE_CONTROL_QUALIFICATION"
            if active_v3.get("id") == "G4B1_CONTROL_QUALIFICATION"
            else "EXECUTE_EXACT_72_G4B1_CONTROL_REVIEW_CALLS_NO_GOLD"
            if active_v3.get("id") == "G4B1_CONTROL_REVIEW_EXECUTION"
            else "DESIGN_G4B_REVIEWER_QUALIFICATION_AND_DUAL_REVIEW_PHASE_ZERO_API"
            if g4a_v2 and g4a_v2.get("execution_authority") is False
            else "EXECUTE_G4A_V2_ZERO_API_CONTROL_REPAIR_REMATERIALIZATION"
            if g4a_v2 and g4a_v2.get("execution_authority") is True
            else "EXECUTE_G4A_ZERO_API_PACKET_AND_FRESH_CONTROL_MATERIALIZATION"
            if g4a and g4a.get("execution_authority") is True
            else "DESIGN_G4A_ZERO_API_PACKET_AND_FRESH_CONTROL_MATERIALIZATION_PHASE"
            if g4 and g4.get("execution_authority") is False
            else "DESIGN_G4_NONEXCLUSIVE_ANCHORED_SUITABILITY_PACKET_ZERO_API"
            if g3 and g3.get("execution_authority") is False
            else "EXECUTE_G3_PUBLIC_MP_MS_ME_CANDIDATE_SURFACE_AUDIT_ZERO_API"
            if g3
            else "DESIGN_G3_PUBLIC_MP_MS_ME_CANDIDATE_SURFACE_AUDIT"
            if g2 and g2.get("execution_authority") is False
            else "EXECUTE_G2_COMPONENT_GENERAL_V3_ZERO_API_IMPLEMENTATION_AND_TESTS"
            if g2
            else "DESIGN_G2_COMPONENT_GENERAL_V3_ZERO_API_IMPLEMENTATION_PHASE"
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
