from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "data/pm_v1_5_contracts/paper1_external_treatment_stress_test_design_v1.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_external_treatment_stress_test_preflight_20260813"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_function_is_secondary_to_randomized_qrc_in_exploratory_diagnostic() -> None:
    design = read(DESIGN)
    hierarchy = " ".join(design["measurement_validity_correction"]["evidence_hierarchy"])
    assert "Primary: randomized same-state Quality, Risk, and Cost" in hierarchy
    assert "Secondary mechanism evidence" in hierarchy
    interpretation = design["measurement_validity_correction"]["first_version_interpretation"]
    assert "Do not automatically declare the head ineffective" in interpretation["quality_positive_risk_safe_function_none"]


def test_preflight_is_owner_unique_five_arm_and_never_generated() -> None:
    report = read(OUT / "report.json")
    cases = read_jsonl(OUT / "cases_private.jsonl")
    calls = read_jsonl(OUT / "call_plan_private.jsonl")
    assert report["status"] == "PASS_EXACT_18_OWNER_90_CALL_EXPLORATORY_PROPOSAL_HUMAN_APPROVAL_REQUIRED"
    assert len(cases) == len({row["runtime_owner_key"] for row in cases}) == 18
    assert len(calls) == 90
    assert {row["arm"] for row in calls} == {"always_off", "full", "minus_RS", "minus_MP", "minus_MS"}
    assert all(row["selection"]["previously_generated"] is False for row in cases)
    assert report["selection"]["response_or_judge_outcomes_read_for_selection"] is False


def test_every_arm_is_structurally_realized_and_identity_is_bound() -> None:
    report = read(OUT / "report.json")
    calls = read_jsonl(OUT / "call_plan_private.jsonl")
    assert report["checks"]["all_requested_equal_structurally_eligible_and_jointly_planned"] is True
    assert all(
        row["requested_action_id"]
        == row["plan_accounting"]["structurally_eligible_action_id"]
        == row["plan_accounting"]["jointly_planned_action_id"]
        for row in calls
    )
    assert sha(OUT / "cases_private.jsonl") == report["artifacts"]["cases"]["sha256"]
    assert sha(OUT / "call_plan_private.jsonl") == report["artifacts"]["call_plan"]["sha256"]
    assert len(report["run_identity"]) == 64


def test_native_rs_checkpoint_runtime_reproduces_selected_probabilities() -> None:
    validation = read(OUT / "selector_runtime_validation.json")
    assert validation["status"] == "PASS_NATIVE_RS_RUNTIME_REPRODUCES_FROZEN_SELECTION"
    assert validation["checks"]["native_sklearn_version"] == "1.7.2"
    assert validation["checks"]["selected_states_checked"] == 18
    assert validation["checks"]["maximum_absolute_rs_probability_delta_vs_preflight"] == 0.0
    assert validation["bindings"]["cases_private_sha256"] == sha(OUT / "cases_private.jsonl")


def test_diagnostic_does_not_impersonate_formal_learned_pm() -> None:
    design = read(DESIGN)
    report = read(OUT / "report.json")
    assert "not pristine" in design["scope"]["externality_label"]
    assert "not a qualified learned four-head policy" in design["routing_and_candidate_policy"]["joint_system_label"]
    assert "not formal learned-PM confirmation" in report["scope_label"]
    assert report["authorization"] == {"api_calls": 0, "generator_calls": 0, "judge_calls": 0, "fits": 0}
