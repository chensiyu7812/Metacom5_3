"""The RS/DG readiness audit must derive its numbers, never invent them."""
from __future__ import annotations

import importlib.util
import json
from decimal import Decimal
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts/paper1"


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audit = load("rs_dg_readiness", "82_audit_rs_and_dg_calibration_readiness.py")

PLANNING = {"rq1_rs_external_calibration_scenarios": {
    "amount_arms": [0, 1, 2, 3, 4], "turns_per_esc_eval_trajectory": 5,
    "large_52": {"role_cards": 52, "trajectories": 260, "nvidia_generator_calls": 1300,
                 "esc_role_local_inference_turns": 1300, "official_esc_rank_dimension_passes": 1820}}}
COMPATIBILITY = {"runtime_evidence_before_amendment": {"mean_seven_dimension_seconds": 4.8}}
SPLIT = ([{"split": "calibration"}] * 52) + ([{"split": "confirmatory"}] * 121)

DG_COST = {
    "upstream": {"seeker_rounds_per_scenario": 10},
    "public_population": {"scenarios": 34},
    "six_system_call_surface": {"seeker_logical_calls": 2040, "gpt4o_overall_judge_calls": 204,
                                "total_local_mistral24b_turn_judge_calls": 102720},
    "seeker_cost_surface_six_systems": {
        "one_physical_attempt_per_logical_call": {"uncached_worst_case_usd": 29.51055}},
}


def test_rs_calibration_requires_no_paid_call_because_the_whole_loop_is_local():
    rs = audit.audit_rs(PLANNING, COMPATIBILITY, SPLIT)
    assert rs["paid_api_calls_required"] == 0
    assert Decimal(rs["paid_usd_required"]) == 0
    assert rs["feasible_within_remaining_budget"] is True
    assert rs["binding_constraint"] == "GPU wall time, not money"


def test_rs_audit_reads_card_counts_from_the_frozen_split_not_from_the_envelope():
    rs = audit.audit_rs(PLANNING, COMPATIBILITY, SPLIT)
    assert rs["cards"]["calibration"] == 52 and rs["cards"]["confirmatory"] == 121
    thin = ([{"split": "calibration"}] * 3) + ([{"split": "confirmatory"}] * 4)
    assert audit.audit_rs(PLANNING, COMPATIBILITY, thin)["cards"] == {
        "calibration": 3, "confirmatory": 4, "planning_envelope_role_cards": 52}


def test_rs_wall_time_is_reported_as_unmeasured_rather_than_guessed():
    rs = audit.audit_rs(PLANNING, COMPATIBILITY, SPLIT)
    assert rs["generation_wall_time"] == "UNMEASURED_FOR_THIS_LOOP"
    # Only the scorer pass has a measured rate, so only it gets a wall-clock number.
    assert rs["official_scorer_wall_seconds_for_all_trajectories"] == pytest.approx(4.8 * 260)


def test_dg_volume_is_one_paid_trajectory_per_condition_because_retrieval_is_live():
    dg = audit.audit_dg(DG_COST, {}, Decimal("48"), Decimal("43"))
    assert dg["conditions_per_scenario"] == 13, "3 heads x 4 k plus one shared OFF"
    assert dg["calibration_volume"]["paid_seeker_logical_calls"] == 34 * 10 * 13
    assert dg["static_query_substitute_forbidden"] is True


def test_dg_unit_cost_is_derived_from_the_recorded_six_system_surface():
    dg = audit.audit_dg(DG_COST, {}, Decimal("48"), Decimal("43"))
    derived = Decimal(dg["recorded_six_system_reference"]["derived_usd_per_logical_seeker_call"])
    assert derived == pytest.approx(Decimal("29.51055") / 2040)
    total = Decimal(dg["paid_usd_required_seeker_only_worst_case"])
    assert total == pytest.approx(derived * 4420, rel=Decimal("1e-6"))


def test_dg_is_reported_infeasible_with_an_explicit_shortfall_against_real_headroom():
    dg = audit.audit_dg(DG_COST, {}, Decimal("48.49275709"), Decimal("43.49275709"))
    assert dg["feasible_within_remaining_budget"] is False
    shortfall = Decimal(dg["shortfall_usd"])
    assert shortfall > 0
    assert shortfall == pytest.approx(
        Decimal(dg["paid_usd_required_seeker_only_worst_case"]) - Decimal("43.49275709"),
        rel=Decimal("1e-6"))
    assert dg["blocking_decisions"], "an infeasible stage must name the decision it needs"


def test_dg_becomes_feasible_only_when_headroom_actually_covers_it():
    dg = audit.audit_dg(DG_COST, {}, Decimal("100"), Decimal("95"))
    assert dg["feasible_within_remaining_budget"] is True
    assert Decimal(dg["shortfall_usd"]) == 0


def test_the_confirmatory_dg_run_is_kept_separate_from_the_calibration_cost():
    dg = audit.audit_dg(DG_COST, {}, Decimal("48"), Decimal("43"))
    still_owed = Decimal(dg["still_owed_after_calibration"][
        "six_system_confirmatory_seeker_worst_case_usd"])
    assert still_owed == pytest.approx(Decimal("29.51055"))
    assert still_owed not in {Decimal(dg["paid_usd_required_seeker_only_worst_case"])}


def test_the_generated_report_claims_no_execution_of_any_kind():
    report = json.loads((Path(__file__).resolve().parents[1]
                         / "docs/reviews/20260918/rs_dg_readiness_20260918_v1"
                         / "readiness_report.json").read_text())
    assert "NO_EXECUTION_NO_PAID_CALLS_NO_K_SELECTION" in report["status"]
    for claim in ["no generation", "no paid API call", "no k selection", "no k* freeze",
                  "no formal outcome", "no PM training", "no lock opened"]:
        assert claim in report["explicitly_not_done_here"]
    assert report["budget"]["static_stage_authorized"] is False
