"""Batch delivery for official scoring: same method, half price, 24h turnaround.

The risk Batch introduces is accounting, not science: a submitted batch is a
real obligation before any result exists, so a serial "what is left in the
balance" check would happily submit a second one.
"""
from __future__ import annotations

import importlib.util
import json
from decimal import Decimal
from pathlib import Path

import pytest

from metacom_pm.paper1.api_budget import CumulativePaper1ApiBudgetLedger
from metacom_pm.paper1.followup_budget import FollowupBudget, FollowupBudgetExceeded

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts/paper1"


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


batch = load("official_scoring_batch", "83_submit_official_static_scoring_batch.py")
sync = load("static_official_scoring_runner", "80_execute_official_static_scoring.py")

SCORER_CONFIG = {"model": "gpt-4o-2024-11-20", "provider_max_output_tokens": 16384,
                 "project_retry_max": 1}


def payload(index: int, *, task: str = "qa", input_tokens: int = 400) -> dict:
    return {"logical_call_id": f"amount_score_r{index}", "request_id": f"r{index}",
            "target_id": f"t{index}", "task": task,
            "body": {"model": SCORER_CONFIG["model"],
                     "messages": [{"role": "system", "content": "You are a strict evaluator."},
                                  {"role": "user", "content": f"case {index}"}]},
            "call_hash": f"hash{index}", "prediction_sha256": f"pred{index}",
            "estimated_input_tokens_with_framing_reserve": input_tokens}


def test_batch_pricing_is_exactly_half_the_synchronous_rate():
    assert batch.BATCH_INPUT_USD_PER_MILLION * 2 == sync.INPUT_USD_PER_MILLION
    assert batch.BATCH_OUTPUT_USD_PER_MILLION * 2 == sync.OUTPUT_USD_PER_MILLION
    payloads = [payload(i) for i in range(1, 6)]
    batched = batch.batch_worst_case_usd(payloads, SCORER_CONFIG)
    serial = sum((sync.worst_case_usd(p, SCORER_CONFIG) for p in payloads), Decimal(0))
    assert batched * 2 == serial


def test_batch_lines_preserve_the_official_body_and_a_recoverable_key():
    payloads = [payload(1), payload(2, task="summary")]
    lines = batch.build_batch_lines(payloads)
    assert [line["custom_id"] for line in lines] == ["r1", "r2"]
    assert all(line["url"] == "/v1/chat/completions" and line["method"] == "POST" for line in lines)
    # The prompt bytes are the ones 78 bound, not a rewritten variant.
    assert lines[0]["body"] == payloads[0]["body"]


def test_a_submitted_batch_is_a_liability_that_blocks_a_second_submission(tmp_path):
    ledger = CumulativePaper1ApiBudgetLedger(tmp_path / "ledger.jsonl", opening_cost_usd=Decimal("0"))
    budget = FollowupBudget(ledger, tmp_path / "boundary.json")
    rows = batch.record_liability(tmp_path, {"batch_id": "batch_1", "state": "IN_PROGRESS",
                                             "worst_case_usd": "12.00"})
    assert batch.liabilities_from(tmp_path) == rows
    # Nothing has settled, so the ledger alone still looks empty.
    assert ledger.accounted_cost_usd == 0
    # The follow-up budget nonetheless counts the obligation.
    assert budget.status(rows).committed_new_spend_usd == Decimal("12.00")
    with pytest.raises(FollowupBudgetExceeded):
        budget.check(Decimal("9.00"), liabilities=rows, what="second batch")


def test_settling_a_batch_releases_its_liability(tmp_path):
    rows = batch.record_liability(tmp_path, {"batch_id": "batch_1", "state": "IN_PROGRESS",
                                             "worst_case_usd": "12.00"})
    rows = batch.record_liability(tmp_path, {"batch_id": "batch_1", "state": "SETTLED",
                                             "actual_cost_usd": "3.10"})
    assert len(rows) == 1, "the same batch is updated in place, never duplicated"
    assert rows[0]["state"] == "SETTLED" and rows[0]["worst_case_usd"] == "12.00"
    ledger = CumulativePaper1ApiBudgetLedger(tmp_path / "ledger.jsonl", opening_cost_usd=Decimal("0"))
    budget = FollowupBudget(ledger, tmp_path / "boundary.json")
    assert budget.status(rows).outstanding_liability_usd == 0


def batch_line(request_id: str, content: str, *, prompt=400, completion=8, status=200):
    return json.dumps({"custom_id": request_id, "response": {
        "status_code": status,
        "body": {"choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                 "usage": {"prompt_tokens": prompt, "completion_tokens": completion}}}})


def test_batch_output_is_parsed_with_the_same_official_rules(tmp_path):
    payloads = {"r1": payload(1), "r2": payload(2, task="summary")}
    summary_reply = json.dumps({"score": 4, "num_events_reference": 4,
                                "num_events_generated": 5, "num_events_recalled": 3})
    records, usage = batch.parse_batch_output(
        [batch_line("r1", "Score: 2"), batch_line("r2", summary_reply, completion=900)], payloads)
    assert {r["request_id"]: r["status"] for r in records} == {"r1": "SCORED", "r2": "SCORED"}
    assert records[0]["official"]["quality"] == 1.0
    assert records[1]["official"]["primary_metric"] == "official_event_f1"
    assert usage == {"prompt_tokens": 800, "completion_tokens": 908}


def test_a_batch_reply_the_official_parser_cannot_read_is_missingness_not_zero(tmp_path):
    records, _ = batch.parse_batch_output([batch_line("r1", "I cannot grade this.")],
                                          {"r1": payload(1)})
    assert records[0]["status"] == "OFFICIAL_PARSE_FAILED"
    assert records[0]["official"] is None
    assert Decimal(records[0].get("actual_cost_usd", "0")) >= 0


def test_a_failed_batch_row_is_recorded_without_inventing_a_score():
    line = json.dumps({"custom_id": "r1", "error": {"message": "rate limited"},
                       "response": {"status_code": 429, "body": {}}})
    records, usage = batch.parse_batch_output([line], {"r1": payload(1)})
    assert records[0]["status"] == "PROVIDER_ERROR"
    assert "official" not in records[0]
    assert usage == {}


def test_an_unknown_custom_id_in_batch_output_is_refused():
    with pytest.raises(RuntimeError, match="unknown custom_id"):
        batch.parse_batch_output([batch_line("r99", "Score: 1")], {"r1": payload(1)})


def test_batch_cost_is_computed_from_returned_usage_not_from_a_halved_estimate():
    usage = {"prompt_tokens": 1_000_000, "completion_tokens": 100_000}
    observed = batch.observed_batch_usd(usage)
    assert observed == Decimal("1.25") + Decimal("0.5")
    assert observed * 2 == sync.observed_usd(usage)
