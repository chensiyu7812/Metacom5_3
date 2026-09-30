"""Offline end-to-end exercise of the paid official-scoring money path.

Transport is injected, so reservation, settlement, parsing, resume, retry and
cap-stop behaviour are all verified without a provider and without spending
anything. These are the paths that only get one chance to be right once the
stage is authorized.
"""
from __future__ import annotations

import importlib.util
import json
from decimal import Decimal
from pathlib import Path

import pytest

from metacom_pm.paper1.api_budget import (
    CumulativePaper1ApiBudgetLedger, PAPER1_API_HARD_CAP_USD, PAPER1_RETRY_RESERVE_USD,
)

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts/paper1"


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scoring = load("static_official_scoring_runner", "80_execute_official_static_scoring.py")

SCORER_CONFIG = {"model": "gpt-4o-2024-11-20", "provider_max_output_tokens": 16384,
                 "context_tokens": 128000, "project_retry_max": 1}


def payload(index: int, *, task: str = "qa", input_tokens: int = 400) -> dict:
    return {"logical_call_id": f"amount_score_r{index}", "request_id": f"r{index}",
            "target_id": f"t{index}", "task": task,
            "body": {"model": SCORER_CONFIG["model"],
                     "messages": [{"role": "system", "content": "You are a strict evaluator."},
                                  {"role": "user", "content": f"case {index}"}]},
            "call_hash": f"hash{index}", "prediction_sha256": f"pred{index}",
            "estimated_input_tokens_with_framing_reserve": input_tokens,
            "maximum_output_tokens_for_reservation_only": SCORER_CONFIG["provider_max_output_tokens"],
            "reservation_usd": 0.0}


def ok(reply: str, *, prompt_tokens: int = 400, completion_tokens: int = 8):
    return (200, {"choices": [{"message": {"content": reply}, "finish_reason": "stop"}],
                  "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                            "total_tokens": prompt_tokens + completion_tokens}}, "")


def fresh_ledger(tmp_path: Path) -> CumulativePaper1ApiBudgetLedger:
    return CumulativePaper1ApiBudgetLedger(tmp_path / "ledger.jsonl", opening_cost_usd=Decimal("0"))


def one_reservation(input_tokens: int = 400) -> Decimal:
    return scoring.worst_case_usd(payload(0, input_tokens=input_tokens), SCORER_CONFIG)


def run(tmp_path, payloads, send, *, stage_cap="15", ledger=None, scorer_config=None,
        followup=None, liabilities=None):
    ledger = ledger or fresh_ledger(tmp_path)
    stopped, records, skipped = scoring.execute_payloads(
        payloads, scorer_config=scorer_config or SCORER_CONFIG, ledger=ledger,
        stage_cap=Decimal(stage_cap), scores_dir=tmp_path / "scores", send=send,
        followup=followup, liabilities=liabilities)
    return ledger, stopped, records, skipped


def test_a_successful_call_settles_at_observed_usage_not_at_the_reserved_maximum(tmp_path):
    ledger, stopped, records, skipped = run(tmp_path, [payload(1)], lambda body: ok("Score: 2"))
    assert stopped is None and len(records) == 1
    record = records[0]
    assert record["status"] == "SCORED"
    assert record["official"]["quality"] == 1.0
    reserved = Decimal(record["reserved_maximum_usd"])
    settled = Decimal(record["actual_cost_usd"])
    assert settled < reserved
    assert ledger.accounted_stage_cost_usd(scoring.STAGE) == settled
    assert (tmp_path / "scores/r1.json").exists()


def test_every_attempt_reserves_the_full_native_output_allowance_before_sending(tmp_path):
    seen = []

    def send(body):
        # The reservation is already written when transport is entered.
        seen.append(Decimal(str(
            json.loads((tmp_path / "ledger.jsonl").read_text().splitlines()[0])["maximum_cost_usd"])))
        return ok("Score: 1")

    run(tmp_path, [payload(1)], send)
    expected = (Decimal(400) * Decimal("2.5") + Decimal(16384) * Decimal("10")) / Decimal(1_000_000)
    assert seen == [expected]


def test_a_provider_error_is_retried_once_then_stops_the_run(tmp_path):
    calls = []

    def send(body):
        calls.append(body)
        return (500, {"error": "server"}, '{"error": "server"}')

    ledger, stopped, records, skipped = run(tmp_path, [payload(1), payload(2)], send)
    assert len(calls) == 2, "exactly one retry"
    assert records[0]["status"] == "PROVIDER_ERROR" and records[0]["attempt"] == 2
    assert stopped["reason"] == "call_failed_after_allowed_retry"
    assert not (tmp_path / "scores/r2.json").exists(), "the run stops instead of burning the next call"


def test_a_failed_attempt_is_conservatively_accounted_at_its_reserved_maximum(tmp_path):
    def send(body):
        raise TimeoutError("connection dropped")

    ledger, stopped, records, skipped = run(tmp_path, [payload(1)], send)
    assert records[0]["status"] == "TRANSPORT_FAILED"
    reserved = Decimal(records[0]["cost_accounted_at_reserved_maximum"])
    # Two attempts, both of unknown cost, both held at the maximum.
    assert ledger.accounted_stage_cost_usd(scoring.STAGE) == 2 * reserved


def test_a_retry_succeeds_after_one_transient_failure(tmp_path):
    attempts = []

    def send(body):
        attempts.append(1)
        if len(attempts) == 1:
            return (503, None, "upstream unavailable")
        return ok("Score: 2")

    ledger, stopped, records, skipped = run(tmp_path, [payload(1)], send)
    assert stopped is None
    assert records[0]["status"] == "SCORED" and records[0]["attempt"] == 2
    assert records[0]["official"]["quality"] == 1.0


def test_an_unreadable_official_reply_is_recorded_without_a_score(tmp_path):
    ledger, stopped, records, skipped = run(tmp_path, [payload(1)], lambda body: ok("I cannot grade this."))
    record = records[0]
    assert record["status"] == "OFFICIAL_PARSE_FAILED"
    assert record["official"] is None and "parse_error" in record
    # The call really happened, so it is still paid for and still not a zero.
    assert Decimal(record["actual_cost_usd"]) > 0
    assert stopped is None, "a parse failure is missingness, not a transport failure"


def test_summary_replies_produce_event_f1_as_the_primary(tmp_path):
    reply = json.dumps({"score": 4, "num_events_reference": 4, "num_events_generated": 5,
                        "num_events_recalled": 3})
    ledger, stopped, records, skipped = run(tmp_path, [payload(1, task="summary")],
                                   lambda body: ok(reply, completion_tokens=900))
    official = records[0]["official"]
    assert official["primary_metric"] == "official_event_f1"
    assert official["quality"] == pytest.approx(2 * 0.75 * 0.6 / (0.75 + 0.6))


def test_execution_stops_before_the_reservation_that_would_breach_the_stage_cap(tmp_path):
    payloads = [payload(i) for i in range(1, 5)]
    # A cap of exactly one worst-case reservation admits the first call. The
    # first settles far below its reservation, but the *second* reservation is
    # still checked at full worst case, which is what stops the run.
    cap = one_reservation()
    ledger, stopped, records, skipped = run(tmp_path, payloads, lambda body: ok("Score: 2"),
                                            stage_cap=str(cap))
    assert len(records) == 1 and records[0]["status"] == "SCORED"
    assert stopped["reason"] == "stage_cap_reached" and stopped["request_id"] == "r2"
    assert Decimal(stopped["would_be_stage_usd"]) > cap
    assert ledger.accounted_stage_cost_usd(scoring.STAGE) < cap, "settled well under the reservation"
    assert not (tmp_path / "scores/r2.json").exists()


def test_execution_stops_before_breaching_the_primary_retry_reserve(tmp_path):
    ledger = fresh_ledger(tmp_path)
    # Commit the cumulative budget up to just under the USD 45 primary ceiling,
    # so the next full reservation would eat into the USD 5 retry reserve.
    reservation = ledger.reserve(
        reservation_id="other:1", logical_call_id="other", call_hash="otherhash",
        stage="other_stage", provider="p", model="m",
        maximum_cost_usd=PAPER1_API_HARD_CAP_USD - PAPER1_RETRY_RESERVE_USD - Decimal("0.01"),
        call_class="PRIMARY")
    ledger.settle(reservation, actual_cost_usd=None, outcome="UNKNOWN")
    _, stopped, records, skipped = run(tmp_path, [payload(1)], lambda body: ok("Score: 2"), ledger=ledger)
    assert records == [], "stopped cleanly instead of letting the reservation raise mid-run"
    assert stopped["reason"] == "cumulative_cap_reached"
    assert Decimal(stopped["primary_ceiling_usd"]) == PAPER1_API_HARD_CAP_USD - PAPER1_RETRY_RESERVE_USD
    # Nothing new was committed by the refused call.
    assert ledger.accounted_stage_cost_usd(scoring.STAGE) == Decimal("0")


def test_a_lost_result_file_never_causes_a_second_charge_for_the_same_call(tmp_path):
    sent = []

    def send(body):
        sent.append(body)
        return ok("Score: 2")

    ledger, stopped, records, skipped = run(tmp_path, [payload(1)], send)
    assert records[0]["status"] == "SCORED" and len(sent) == 1
    committed = ledger.accounted_stage_cost_usd(scoring.STAGE)

    # Simulate losing the persisted result, which is what would put this payload
    # back into the pending set on resume.
    (tmp_path / "scores/r1.json").unlink()
    _, stopped, records, skipped = run(tmp_path, [payload(1)], send, ledger=ledger)

    assert len(sent) == 1, "the already-paid call is not sent again"
    assert records == [] and stopped is None
    assert skipped == [{"request_id": "r1", "call_hash": "hash1",
                        "reason": "already_settled_successfully_in_ledger"}]
    assert ledger.accounted_stage_cost_usd(scoring.STAGE) == committed


def test_resume_skips_already_scored_payloads_and_only_pays_for_the_remainder(tmp_path):
    sent = []

    def send(body):
        sent.append(body["messages"][1]["content"])
        return ok("Score: 2")

    ledger = fresh_ledger(tmp_path)
    run(tmp_path, [payload(1)], send, ledger=ledger)
    after_first = ledger.accounted_stage_cost_usd(scoring.STAGE)

    # main() computes the pending set from files on disk; reproduce that filter.
    all_payloads = [payload(1), payload(2)]
    pending = [p for p in all_payloads if not (tmp_path / "scores" / f"{p['request_id']}.json").exists()]
    assert [p["request_id"] for p in pending] == ["r2"]
    run(tmp_path, pending, send, ledger=ledger)

    assert sent == ["case 1", "case 2"], "no request is ever sent twice"
    assert ledger.accounted_stage_cost_usd(scoring.STAGE) == 2 * after_first


def test_no_retry_is_attempted_when_the_project_allows_none(tmp_path):
    calls = []

    def send(body):
        calls.append(body)
        return (500, {"error": "server"}, "server")

    config = {**SCORER_CONFIG, "project_retry_max": 0}
    _, stopped, records, skipped = run(tmp_path, [payload(1)], send, scorer_config=config)
    assert len(calls) == 1
    assert records[0]["attempt"] == 1 and stopped["reason"] == "call_failed_after_allowed_retry"


def test_persisted_record_carries_the_full_identity_needed_for_recovery(tmp_path):
    run(tmp_path, [payload(7)], lambda body: ok("Score: 1"))
    record = json.loads((tmp_path / "scores/r7.json").read_text())
    for field in ["protocol", "request_id", "target_id", "task", "call_hash", "logical_call_id",
                  "prediction_sha256", "model", "completed_at", "usage", "raw_reply",
                  "actual_cost_usd", "reserved_maximum_usd"]:
        assert field in record, field
    assert record["official"]["quality"] == 0.5


# --- boundaries reproduced by the 2026-09-18 review ---


def test_a_retry_stops_cleanly_when_the_stage_cap_cannot_cover_it(tmp_path):
    """Review case 1: a 503 first attempt must not let the retry reservation raise."""
    calls = []

    def send(body):
        calls.append(body)
        return (503, None, "unavailable")

    cap = one_reservation()  # room for exactly one reservation, so the retry cannot fit
    ledger, stopped, records, skipped = run(tmp_path, [payload(1)], send, stage_cap=str(cap))
    assert len(calls) == 1, "the retry was never sent because it could not be reserved"
    assert stopped["reason"] == "stage_cap_reached_before_retry"
    assert stopped["attempt"] == 2
    # The first attempt still produced a persisted, disclosed record.
    assert records[0]["status"] == "PROVIDER_ERROR"
    assert (tmp_path / "scores/r1.json").exists()


def test_an_interrupted_reservation_is_reconciled_and_never_blindly_resent(tmp_path):
    """Review case 2: resume after dying between reserve and settle."""
    ledger = fresh_ledger(tmp_path)
    ledger.reserve(reservation_id=f"{scoring.STAGE}:r1:1", logical_call_id=f"{scoring.STAGE}:r1",
                   call_hash="hash1", stage=scoring.STAGE, provider=scoring.PROVIDER,
                   model=SCORER_CONFIG["model"], maximum_cost_usd=one_reservation(),
                   call_class="PRIMARY")
    sent = []
    _, stopped, records, skipped = run(tmp_path, [payload(1)],
                                       lambda body: sent.append(body) or ok("Score: 2"),
                                       ledger=ledger)
    assert sent == [], "an unknown-outcome call is reconciled, not re-sent"
    assert stopped["reason"] == "unsettled_reservation_requires_reconciliation"
    assert stopped["reservation_ids"] == [f"{scoring.STAGE}:r1:1"]


def test_resume_continues_the_attempt_count_instead_of_restarting_at_one(tmp_path):
    ledger = fresh_ledger(tmp_path)
    reservation = ledger.reserve(
        reservation_id=f"{scoring.STAGE}:r1:1", logical_call_id=f"{scoring.STAGE}:r1",
        call_hash="hash1", stage=scoring.STAGE, provider=scoring.PROVIDER,
        model=SCORER_CONFIG["model"], maximum_cost_usd=one_reservation(), call_class="PRIMARY")
    ledger.settle(reservation, actual_cost_usd=None, outcome="FAILED")
    _, stopped, records, skipped = run(tmp_path, [payload(1)], lambda body: ok("Score: 2"),
                                       ledger=ledger)
    assert records[0]["attempt"] == 2, "resumed as the retry, not as a fresh first attempt"
    assert records[0]["status"] == "SCORED"


def test_a_bill_larger_than_the_reservation_is_recorded_in_full_and_stops_the_run(tmp_path):
    """Review case 3: min(actual, maximum) understated a real charge."""
    reserved = one_reservation()
    # Report usage well above the reservation, as a bad estimate would produce.
    huge = {"prompt_tokens": 400, "completion_tokens": 20000}
    ledger, stopped, records, skipped = run(
        tmp_path, [payload(1), payload(2)],
        lambda body: (200, {"choices": [{"message": {"content": "Score: 2"}, "finish_reason": "stop"}],
                            "usage": huge}, ""))
    true_cost = scoring.observed_usd(huge)
    assert true_cost > reserved
    record = records[0]
    assert Decimal(record["actual_cost_usd"]) == true_cost, "the true bill is kept, not truncated"
    assert record["estimator_underestimated_cost"] is True
    assert ledger.accounted_stage_cost_usd(scoring.STAGE) == true_cost
    assert stopped["reason"] == "observed_cost_exceeded_reservation"
    assert not (tmp_path / "scores/r2.json").exists(), "stops so the estimator can be re-checked"


def test_the_raw_provider_response_is_persisted_before_the_cost_is_settled(tmp_path):
    seen_at_settle_time = {}

    def send(body):
        return ok("Score: 2")

    original_settle = type(fresh_ledger(tmp_path)).settle
    ledger = fresh_ledger(tmp_path)

    def spy(self, reservation, **kwargs):
        raw = tmp_path / "scores/raw"
        seen_at_settle_time["files"] = sorted(p.name for p in raw.glob("*.json")) if raw.exists() else []
        return original_settle(self, reservation, **kwargs)

    type(ledger).settle = spy
    try:
        run(tmp_path, [payload(1)], send, ledger=ledger)
    finally:
        type(ledger).settle = original_settle
    assert seen_at_settle_time["files"] == ["r1.attempt1.json"], (
        "the answer was already on disk before bookkeeping ran")


# --- identical-payload reuse (found when real generations produced equal answers) ---


def test_identical_official_payloads_are_scored_once_and_the_rest_are_aliased():
    rows = [payload(1), payload(2), payload(3)]
    rows[1]["call_hash"] = rows[0]["call_hash"]  # k=2 produced the same answer as k=1
    unique, aliases = scoring.deduplicate(rows)
    assert [u["request_id"] for u in unique] == ["r1", "r3"]
    assert aliases == {rows[0]["call_hash"]: ["r2"]}


def test_deduplicate_keeps_the_first_row_and_never_drops_a_distinct_call():
    rows = [payload(i) for i in range(1, 6)]
    unique, aliases = scoring.deduplicate(rows)
    assert len(unique) == 5 and aliases == {}


def test_a_duplicate_payload_is_never_sent_or_paid_for_twice(tmp_path):
    sent = []

    def send(body):
        sent.append(body)
        return ok("Score: 2")

    rows = [payload(1), payload(2)]
    rows[1]["call_hash"] = rows[0]["call_hash"]
    unique, aliases = scoring.deduplicate(rows)
    ledger, stopped, records, skipped = run(tmp_path, unique, send)
    assert len(sent) == 1, "the identical prompt is bought once"
    assert len(records) == 1
    # The alias is served from the same purchased score, not a second call.
    assert aliases[rows[0]["call_hash"]] == ["r2"]
