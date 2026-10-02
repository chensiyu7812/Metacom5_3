"""The follow-up budget plan must quote honestly and select nothing."""
from __future__ import annotations

import importlib.util
import json
from decimal import Decimal
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts/paper1"
PLAN = (Path(__file__).resolve().parents[1]
        / "docs/reviews/20260918/followup_budget_plan_20260918_v1/followup_budget_plan.json")


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


planner = load("followup_budget_plan", "84_plan_followup_research_budget.py")


def test_batch_delivery_is_exactly_half_of_synchronous_for_the_same_call():
    for task in ["qa", "summary"]:
        assert planner.static_call_usd(task, planner.BATCH) * 2 == planner.static_call_usd(
            task, planner.SYNC)


def test_a_summary_judgement_really_is_the_expensive_one():
    qa = planner.static_call_usd("qa", planner.BATCH)
    summary = planner.static_call_usd("summary", planner.BATCH)
    assert summary > qa * 5, "the plan's headline driver must hold"


def test_reserve_is_always_at_least_the_observed_estimate():
    for task in ["qa", "summary"]:
        assert planner.static_reserve_usd(task, planner.BATCH) > planner.static_call_usd(
            task, planner.BATCH)


def test_dg_rates_keep_the_reserve_and_the_single_pilot_separate():
    dg_cost = planner.read_json(planner.DG_COST_SURFACE)
    rates = planner.dg_seeker_rates(dg_cost)
    assert rates["reserve_per_call_usd"] > rates["observed_per_call_usd"]
    assert "not a population mean" in rates["observed_source"]


def test_the_pilot_rate_comes_from_the_recorded_trajectory_not_a_guess():
    assert planner.dg_cost_pilot_usd() == Decimal("0.0859925")


def test_rq1_is_free_and_dg_full_grid_is_refused():
    rows = planner.stage_rows(planner.dg_seeker_rates(planner.read_json(planner.DG_COST_SURFACE)))
    rq1 = next(r for r in rows if r["stage"].startswith("C."))
    assert rq1["paid_calls"] == 0 and rq1["usd"] == "0"
    grid = next(r for r in rows if r["stage"].startswith("F."))
    assert grid["paid_calls"] == 34 * 10 * 13
    assert "incompatible" in grid["verdict"]


def test_every_plan_states_what_it_gives_up_and_cannot_claim():
    plans = planner.plans(planner.dg_seeker_rates(planner.read_json(planner.DG_COST_SURFACE)))
    assert len(plans) >= 4
    for plan in plans:
        assert plan["keeps"] and plan["gives_up"] and plan["cannot_claim"]
        assert Decimal(plan["total_at_observed_rates_usd"]) > 0


def test_at_least_one_plan_lands_near_the_ten_dollar_target_with_margin():
    plans = planner.plans(planner.dg_seeker_rates(planner.read_json(planner.DG_COST_SURFACE)))
    target_plan = next(p for p in plans if p["plan"].startswith("P0"))
    total = Decimal(target_plan["total_at_observed_rates_usd"])
    # "about USD 10" is a plan, not a gate; what matters is that it is the
    # cheapest option and still leaves a real retry margin under the hard cap.
    assert total == min(Decimal(p["total_at_observed_rates_usd"]) for p in plans)
    assert total < Decimal("12"), "P0 must actually be near the stated target"
    assert Decimal(target_plan["retry_margin_to_cap_usd"]) > Decimal("8")


def test_no_plan_exceeds_the_hard_cap_at_its_own_worst_case():
    plans = planner.plans(planner.dg_seeker_rates(planner.read_json(planner.DG_COST_SURFACE)))
    for plan in plans:
        assert Decimal(plan["total_at_dg_reserve_usd"]) <= Decimal("20"), plan["plan"]


def test_the_written_report_selects_nothing_and_names_its_unmeasured_inputs():
    report = json.loads(PLAN.read_text())
    assert report["status"] == "QUOTATION_ONLY_NOTHING_SELECTED_NOTHING_SENT"
    assert "No plan here is chosen" in report["not_selected"]
    unmeasured = " ".join(report["assumptions"]["unmeasured"])
    assert "judge reply lengths" in unmeasured, "the remaining unknown must stay disclosed"
    measured = " ".join(report["assumptions"]["measured"])
    assert "INCLUDING the real prediction" in measured
    assert report["assumptions"]["assumed_not_capped"]["judge_output_tokens"]["summary"] == 1024
    forbidden = report["cost_drivers"]["levers_that_must_not_be_used"]
    assert "shortening Generator answers" in forbidden
    assert "substituting a local judge for the official scorer" in forbidden
