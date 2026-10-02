"""The 2026-09-18 follow-up cap: about USD 10 planned, USD 20 never exceeded.

The cap covers every remaining paid stage together, so these tests check that
the boundary cannot drift, that batch liabilities count from submission, and
that the executor stops on the follow-up cap even when the older programme cap
would still allow the call.
"""
from __future__ import annotations

import importlib.util
import json
from decimal import Decimal
from pathlib import Path

import pytest

from metacom_pm.paper1.api_budget import CumulativePaper1ApiBudgetLedger
from metacom_pm.paper1.followup_budget import (
    FOLLOWUP_HARD_CAP_USD, FOLLOWUP_TARGET_USD, FollowupBudget, FollowupBudgetExceeded,
)

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts/paper1"


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scoring = load("static_official_scoring_runner", "80_execute_official_static_scoring.py")


def ledger_with(tmp_path: Path, opening: str = "1.50724291") -> CumulativePaper1ApiBudgetLedger:
    return CumulativePaper1ApiBudgetLedger(tmp_path / "ledger.jsonl", opening_cost_usd=Decimal(opening))


def spend(ledger, amount: str, *, ident: str, stage: str = "s") -> None:
    reservation = ledger.reserve(reservation_id=f"{ident}:1", logical_call_id=ident,
                                 call_hash=ident, stage=stage, provider="p", model="m",
                                 maximum_cost_usd=Decimal(amount), call_class="PRIMARY")
    ledger.settle(reservation, actual_cost_usd=Decimal(amount), outcome="SUCCEEDED")


def test_the_caps_are_the_researcher_stated_target_and_ceiling():
    assert FOLLOWUP_TARGET_USD == Decimal("10")
    assert FOLLOWUP_HARD_CAP_USD == Decimal("20")


def test_the_boundary_starts_at_the_existing_accounted_total_and_history_is_kept(tmp_path):
    ledger = ledger_with(tmp_path)
    budget = FollowupBudget(ledger, tmp_path / "boundary.json")
    assert budget.baseline_accounted_usd == Decimal("1.50724291")
    status = budget.status()
    assert status.settled_new_spend_usd == 0
    assert status.remaining_to_hard_cap_usd == Decimal("20")
    assert status.remaining_to_target_usd == Decimal("10")


def test_only_new_spend_counts_against_the_followup_cap(tmp_path):
    ledger = ledger_with(tmp_path)
    budget = FollowupBudget(ledger, tmp_path / "boundary.json")
    spend(ledger, "3.00", ident="new1")
    status = budget.status()
    assert status.settled_new_spend_usd == Decimal("3.00")
    assert status.remaining_to_hard_cap_usd == Decimal("17.00")
    assert status.as_dict()["target_exceeded"] is False


def test_resuming_never_resets_the_starting_point(tmp_path):
    ledger = ledger_with(tmp_path)
    snapshot = tmp_path / "boundary.json"
    FollowupBudget(ledger, snapshot)
    spend(ledger, "7.00", ident="new1")

    # A later process re-opens the same boundary rather than taking today's total.
    reopened = FollowupBudget(ledger_with(tmp_path), snapshot)
    assert reopened.baseline_accounted_usd == Decimal("1.50724291")
    assert reopened.status().settled_new_spend_usd == Decimal("7.00")


def test_an_edited_boundary_file_is_refused(tmp_path):
    ledger = ledger_with(tmp_path)
    snapshot = tmp_path / "boundary.json"
    FollowupBudget(ledger, snapshot)
    tampered = json.loads(snapshot.read_text())
    tampered["baseline_accounted_usd"] = "40.0"
    snapshot.write_text(json.dumps(tampered))
    with pytest.raises(RuntimeError, match="edited after it was written"):
        FollowupBudget(ledger, snapshot)


def test_a_submitted_batch_counts_as_committed_before_it_returns(tmp_path):
    ledger = ledger_with(tmp_path)
    budget = FollowupBudget(ledger, tmp_path / "boundary.json")
    liabilities = [{"batch_id": "b1", "state": "IN_PROGRESS", "worst_case_usd": "8.00"}]
    status = budget.status(liabilities)
    assert status.outstanding_liability_usd == Decimal("8.00")
    assert status.committed_new_spend_usd == Decimal("8.00")
    assert status.remaining_to_hard_cap_usd == Decimal("12.00")
    # A serial balance check that ignored the in-flight batch would wrongly allow this.
    with pytest.raises(FollowupBudgetExceeded):
        budget.check(Decimal("13.00"), liabilities=liabilities, what="second batch")


def test_a_settled_or_cancelled_batch_stops_being_a_liability(tmp_path):
    ledger = ledger_with(tmp_path)
    budget = FollowupBudget(ledger, tmp_path / "boundary.json")
    done = [{"batch_id": "b1", "state": "SETTLED", "worst_case_usd": "8.00"},
            {"batch_id": "b2", "state": "CANCELLED", "worst_case_usd": "5.00"}]
    assert budget.status(done).outstanding_liability_usd == 0


def test_reaching_the_ten_dollar_target_is_reported_but_does_not_block(tmp_path):
    ledger = ledger_with(tmp_path)
    budget = FollowupBudget(ledger, tmp_path / "boundary.json")
    spend(ledger, "11.00", ident="new1")
    status = budget.status()
    assert status.as_dict()["target_exceeded"] is True
    assert status.as_dict()["target_is_a_plan_not_a_gate"] is True
    # Still inside the hard cap, so work may continue on the allowed remainder.
    budget.check(Decimal("5.00"), what="next request")
    assert status.remaining_to_hard_cap_usd == Decimal("9.00")


def test_the_hard_cap_blocks_even_though_the_old_programme_cap_would_allow_it(tmp_path):
    ledger = ledger_with(tmp_path)
    budget = FollowupBudget(ledger, tmp_path / "boundary.json")
    spend(ledger, "19.50", ident="new1")
    # The old USD 50 programme cap still has roughly USD 29 of room here.
    assert ledger.remaining_usd > Decimal("28")
    assert budget.would_exceed(Decimal("1.00")) is True
    with pytest.raises(FollowupBudgetExceeded, match="over the USD 20"):
        budget.check(Decimal("1.00"), what="request")


def test_the_executor_stops_on_the_followup_cap_before_sending(tmp_path):
    ledger = ledger_with(tmp_path, opening="0")
    budget = FollowupBudget(ledger, tmp_path / "boundary.json")
    spend(ledger, "19.95", ident="earlier")
    sent = []

    def send(body):
        sent.append(body)
        return (200, {"choices": [{"message": {"content": "Score: 2"}, "finish_reason": "stop"}],
                      "usage": {"prompt_tokens": 400, "completion_tokens": 8}}, "")

    payload = {"logical_call_id": "amount_score_r1", "request_id": "r1", "target_id": "t1",
               "task": "qa", "body": {"messages": []}, "call_hash": "h1",
               "prediction_sha256": "p1", "estimated_input_tokens_with_framing_reserve": 400}
    stopped, records, skipped = scoring.execute_payloads(
        [payload], scorer_config={"model": "gpt-4o-2024-11-20", "provider_max_output_tokens": 16384,
                                  "project_retry_max": 1},
        ledger=ledger, stage_cap=Decimal("15"), scores_dir=tmp_path / "scores",
        send=send, followup=budget)
    assert sent == [], "nothing was sent once the follow-up cap was reached"
    assert records == []
    assert stopped["reason"] == "followup_budget_cap_reached"
    assert Decimal(stopped["remaining_to_hard_cap_usd"]) < Decimal("0.17")
