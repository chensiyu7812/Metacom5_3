from decimal import Decimal

import pytest

from metacom_pm.paper1.api_budget import (
    CumulativePaper1ApiBudgetLedger,
    PAPER1_KNOWN_V9_COST_USD,
)


def _reserve(ledger, suffix, maximum, call_class="PRIMARY", logical=None):
    return ledger.reserve(
        reservation_id=f"reservation-{suffix}",
        logical_call_id=logical or f"logical-{suffix}",
        call_hash=f"hash-{suffix}",
        stage="test",
        provider="provider",
        model="model",
        maximum_cost_usd=Decimal(maximum),
        call_class=call_class,
    )


def test_opening_v9_cost_and_unsettled_reservation_are_conservatively_counted(tmp_path):
    ledger = CumulativePaper1ApiBudgetLedger(tmp_path / "api.jsonl")
    reservation = _reserve(ledger, "one", "1.00")
    assert ledger.accounted_cost_usd == PAPER1_KNOWN_V9_COST_USD + Decimal("1.00")
    ledger.settle(reservation, actual_cost_usd=Decimal("0.25"), outcome="SUCCEEDED")
    assert ledger.accounted_cost_usd == PAPER1_KNOWN_V9_COST_USD + Decimal("0.25")


def test_normal_calls_preserve_five_dollar_retry_reserve(tmp_path):
    ledger = CumulativePaper1ApiBudgetLedger(tmp_path / "api.jsonl")
    with pytest.raises(RuntimeError, match="retry reserve"):
        _reserve(ledger, "too-large", "45.00")


def test_optional_calls_cannot_cross_43_dollars(tmp_path):
    ledger = CumulativePaper1ApiBudgetLedger(tmp_path / "api.jsonl")
    with pytest.raises(RuntimeError, match="optional API work"):
        _reserve(ledger, "optional", "43.00", call_class="OPTIONAL")


def test_only_one_retry_and_retry_can_use_protected_reserve(tmp_path):
    ledger = CumulativePaper1ApiBudgetLedger(tmp_path / "api.jsonl")
    first = _reserve(ledger, "first", "44.00", logical="same")
    ledger.settle(first, actual_cost_usd=Decimal("44.00"), outcome="FAILED")
    retry = _reserve(
        ledger,
        "retry",
        "5.00",
        call_class="PRIMARY_RETRY",
        logical="same",
    )
    ledger.settle(retry, actual_cost_usd=Decimal("5.00"), outcome="SUCCEEDED")
    with pytest.raises(RuntimeError, match="at most one retry"):
        _reserve(
            ledger,
            "third",
            "0.01",
            call_class="PRIMARY_RETRY",
            logical="same",
        )


def test_successful_call_hash_cannot_be_rebilled_and_ledger_reopens(tmp_path):
    path = tmp_path / "api.jsonl"
    ledger = CumulativePaper1ApiBudgetLedger(path)
    reservation = _reserve(ledger, "one", "1.00")
    ledger.settle(reservation, actual_cost_usd=Decimal("0.50"), outcome="SUCCEEDED")
    reopened = CumulativePaper1ApiBudgetLedger(path)
    with pytest.raises(RuntimeError, match="cannot be paid twice"):
        reopened.reserve(
            reservation_id="different-reservation",
            logical_call_id="different-logical",
            call_hash="hash-one",
            stage="test",
            provider="provider",
            model="model",
            maximum_cost_usd=Decimal("0.10"),
            call_class="PRIMARY",
        )
