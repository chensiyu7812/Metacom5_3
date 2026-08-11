from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY_PATH = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_active_v2_authority_is_content_addressed_and_fail_closed() -> None:
    authority = read(AUTHORITY_PATH)
    active = authority["active_method"]
    contract = read(ROOT / active["contract_path"])
    amendment = read(ROOT / active["method_amendment_path"])
    phase = authority["current_phase"]["active_phase_manifest"]
    paid = read(ROOT / authority["paid_execution_guard"]["central_release_path"])

    assert authority["status"] in {
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
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_MS_EXECUTOR_QUALIFIED_REVIEW_PENDING",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_MS_EXECUTOR_FUNCTION_PROXY_EXECUTION",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_MS_FUNCTION_FEASIBILITY_COMPLETE_BASELINE_DESIGN_NEXT",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_RS_MS_BASELINE_PLAN_COMPLETE_BLIND_OUTCOME_DESIGN_NEXT",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_RS_MS_DUAL_HUMAN_BLIND_BUNDLE_READY",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_RS_MS_PI_ADJUDICATED_FUNCTION_FAIL_R0_DIAGNOSTIC_DESIGN_NEXT",
        "ACTIVE_V2_TERMINAL_ROUTING_FAIL_COMPONENT_GENERAL_V3_R0_FUNCTION_CLOSURE_PACKETS_READY_PI_REVIEW_NEXT",
    }
    assert active["method_id"] == "PAPER1_SOURCE_ANNOTATED_RESOURCE_SUITABILITY_V2"
    assert sha(ROOT / active["contract_path"]) == active["contract_sha256"]
    assert sha(ROOT / active["method_amendment_path"]) == active["method_amendment_sha256"]
    assert sha(ROOT / phase["path"]) == phase["sha256"]
    assert contract["method_id"] == active["method_id"]
    assert amendment["base_method"]["method_id"] == active["method_id"]
    assert authority["current_phase"]["status"] == "FINAL_OOF_CONSUMED_PRIMARY_FAIL_NO_FURTHER_PM_FIT"
    assert paid["paid_execution_authorized"] is (
        authority["active_v3_phase"]["id"] == "MS_EXECUTOR_FUNCTION_PROXY_EXECUTION"
    )


def test_v2_claim_and_action_space_are_narrow_and_explicit() -> None:
    authority = read(AUTHORITY_PATH)
    contract = read(ROOT / authority["active_method"]["contract_path"])
    rule = read(ROOT / authority["active_method"]["method_amendment_path"])

    assert contract["action_space"]["legal_actions"] == 16
    assert contract["action_space"]["MP"] == "fixed OFF"
    assert contract["action_space"]["ME"] == "fixed OFF"
    assert rule["effective_primary_head_rule"]["machine_predicate"] == "RS_pass AND MS_pass"
    assert rule["observed_result"]["paper1_primary_pass"] is False
    assert all(term in contract["claim"]["primary"] for term in ("quality", "risk", "function", "cost"))


def test_active_v3_primary_success_requires_two_memory_heads_without_shrinking_actions() -> None:
    authority = read(AUTHORITY_PATH)
    binding = authority["active_v3_phase"]["primary_success_rule"]
    rule_path = ROOT / binding["path"]
    rule = read(rule_path)

    assert sha(rule_path) == binding["sha256"]
    assert rule["primary_success_predicate"]["machine_predicate"] == "RS_pass AND count_pass(MP,MS,ME) >= 2"
    assert rule["primary_success_predicate"]["required_memory_pass_count"] == 2
    assert rule["primary_success_predicate"]["maximum_memory_heads_fixed_off"] == 1
    assert rule["component_scope"]["all_four_heads_must_be_defined_and_reported"] is True
    assert rule["component_scope"]["all_sixteen_requested_actions_remain_in_the_scientific_design"] is True
    assert rule["component_scope"]["memory_heads_are_independent_nonexclusive_binary_decisions"] is True


def test_v2_runtime_boundary_and_no_loop_rule_are_explicit() -> None:
    authority = read(AUTHORITY_PATH)
    contract = read(ROOT / authority["active_method"]["contract_path"])
    forbidden = set(contract["MS"]["forbidden_runtime_fields"])

    assert {"summary", "observation", "event", "influenced_by", "QA answer", "QA evidence"}.issubset(forbidden)
    assert contract["MS"]["one_learning_row_per_current_session"] is True
    assert any("exactly one V2 grouped OOF" in line for line in contract["no_loop_rules"])


def test_registry_has_one_terminal_current_pointer() -> None:
    authority = read(AUTHORITY_PATH)
    active = authority["active_method"]
    registry = read(ROOT / active["method_registry_path"])
    versions = [row for row in registry["versions"] if row["id"] == active["method_id"]]

    assert registry["canonical_next"] == active["method_id"]
    assert len(versions) == 1
    assert versions[0]["result"] == "TERMINAL_MECHANICAL_PRIMARY_FAIL_BORDERLINE_DIRECTIONAL_ONLY"
    assert versions[0]["formal_training_allowed"] is False


def test_authority_validator_passes_and_writes_no_new_outcome(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    script = ROOT / "scripts/v1_5/172l_validate_paper1_active_method_authority_v1_5.py"
    subprocess.run([sys.executable, str(script), "--output", str(output)], cwd=ROOT, check=True, capture_output=True, text=True)
    report = read(output)

    assert report["status"] == "ACTIVE_AUTHORITY_PASS_V2_TERMINAL_WITH_SEPARATE_SYSTEM_FEASIBILITY"
    assert report["failed_checks"] == []
    assert report["api_calls"] == 0
    assert report["responses_generated"] == 0
    assert report["pm_trained"] is True
    assert report["additional_pm_fit_authorized"] is False
    assert report["external_outcomes_read"] is False
