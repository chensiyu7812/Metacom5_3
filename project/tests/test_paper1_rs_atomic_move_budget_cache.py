from __future__ import annotations

from decimal import Decimal

import pytest

from metacom_pm.paper1.rs_atomic_move.budget import PriceSnapshot, RsAtomicMoveBudgetLedger
from metacom_pm.paper1.rs_atomic_move.cache import CompilerCallIdentity, SuccessCache

HEX64 = "b" * 64


def _price() -> PriceSnapshot:
    return PriceSnapshot(
        snapshot_id="test-price-v1",
        provider="Alibaba Cloud Model Studio",
        region="Singapore (International)",
        currency="USD",
        input_usd_per_million_tokens=Decimal("0.23"),
        output_usd_per_million_tokens=Decimal("0.92"),
    )


def test_reserve_and_settle_within_budget(tmp_path):
    ledger = RsAtomicMoveBudgetLedger(
        tmp_path / "ledger.jsonl", price=_price(), hard_budget_usd=Decimal("1.00")
    )
    reservation = ledger.reserve(
        reservation_id="r1", phase="extractor", call_key="k1",
        maximum_prompt_tokens=1000, maximum_completion_tokens=200,
    )
    assert reservation.maximum_cost_usd > 0
    actual = ledger.settle(
        reservation, usage={"prompt_tokens": 500, "completion_tokens": 100}, outcome="SUCCEEDED"
    )
    assert actual < reservation.maximum_cost_usd
    assert ledger.accounted_cost_usd == actual


def test_reserve_fails_closed_when_it_would_exceed_hard_cap(tmp_path):
    ledger = RsAtomicMoveBudgetLedger(
        tmp_path / "ledger.jsonl", price=_price(), hard_budget_usd=Decimal("0.0001")
    )
    with pytest.raises(RuntimeError, match="hard budget would be exceeded"):
        ledger.reserve(
            reservation_id="r1", phase="extractor", call_key="k1",
            maximum_prompt_tokens=100_000, maximum_completion_tokens=10_000,
        )


def test_reopening_ledger_with_different_cap_fails_closed(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger = RsAtomicMoveBudgetLedger(path, price=_price(), hard_budget_usd=Decimal("2.00"))
    r = ledger.reserve(
        reservation_id="r1", phase="extractor", call_key="k1",
        maximum_prompt_tokens=100, maximum_completion_tokens=50,
    )
    ledger.settle(r, usage={"prompt_tokens": 50, "completion_tokens": 20}, outcome="SUCCEEDED")

    with pytest.raises(RuntimeError, match="cannot reopen with"):
        RsAtomicMoveBudgetLedger(path, price=_price(), hard_budget_usd=Decimal("5.00"))


def test_settle_rejects_usage_exceeding_reservation(tmp_path):
    ledger = RsAtomicMoveBudgetLedger(
        tmp_path / "ledger.jsonl", price=_price(), hard_budget_usd=Decimal("1.00")
    )
    reservation = ledger.reserve(
        reservation_id="r1", phase="extractor", call_key="k1",
        maximum_prompt_tokens=100, maximum_completion_tokens=50,
    )
    with pytest.raises(RuntimeError, match="exceeds pre-call budget reservation"):
        ledger.settle(
            reservation,
            usage={"prompt_tokens": 10_000_000, "completion_tokens": 10_000_000},
            outcome="SUCCEEDED",
        )


def test_success_cache_round_trip(tmp_path):
    cache = SuccessCache(tmp_path / "cache")
    identity = CompilerCallIdentity(
        phase="extractor",
        compiler_version="paper1-rs-atomic-move-compiler-v1",
        provider="Alibaba Cloud Model Studio",
        region="Singapore (International)",
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        model="qwen3-235b-a22b-instruct-2507",
        enable_thinking=False,
        response_mode="json_object_plus_local_pydantic",
        request_parameters={"temperature": 0.0, "max_tokens": 2048},
        prompt_sha256=HEX64,
        schema_sha256=HEX64,
        source_card_id="rs_src_" + "0" * 24,
        source_sha256=HEX64,
        request_payload_sha256=HEX64,
    )
    assert cache.load(identity) is None
    path = cache.store_success(identity, {"proposals": []})
    assert path.exists()
    loaded = cache.load(identity)
    assert loaded == {"proposals": []}


def test_success_cache_refuses_to_overwrite_with_different_result(tmp_path):
    cache = SuccessCache(tmp_path / "cache")
    identity = CompilerCallIdentity(
        phase="verifier",
        compiler_version="paper1-rs-atomic-move-compiler-v1",
        provider="Alibaba Cloud Model Studio",
        region="Singapore (International)",
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        model="qwen3-235b-a22b-instruct-2507",
        enable_thinking=False,
        response_mode="json_object_plus_local_pydantic",
        request_parameters={"temperature": 0.0, "max_tokens": 2048},
        prompt_sha256=HEX64,
        schema_sha256=HEX64,
        source_card_id="rs_src_" + "0" * 24,
        source_sha256=HEX64,
        request_payload_sha256=HEX64,
    )
    cache.store_success(identity, {"decisions": ["accept"]})
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        cache.store_success(identity, {"decisions": ["reject"]})
    # Storing the identical result again is idempotent, not an error.
    cache.store_success(identity, {"decisions": ["accept"]})


def test_reopening_ledger_with_same_snapshot_id_but_different_rate_fails_closed(tmp_path):
    # Regression: a same-snapshot_id/provider/region reopen with a silently
    # edited rate (e.g. $999/M instead of $0.23/M) must be rejected, not
    # silently accepted for all future reserve()/settle() calls.
    path = tmp_path / "ledger.jsonl"
    price_real = _price()
    ledger = RsAtomicMoveBudgetLedger(path, price=price_real, hard_budget_usd=Decimal("5.00"))
    r = ledger.reserve(
        reservation_id="r1", phase="extractor", call_key="k1",
        maximum_prompt_tokens=1000, maximum_completion_tokens=200,
    )
    ledger.settle(r, usage={"prompt_tokens": 1000, "completion_tokens": 200}, outcome="SUCCEEDED")

    price_evil = PriceSnapshot(
        snapshot_id=price_real.snapshot_id,  # same id
        provider=price_real.provider,
        region=price_real.region,
        currency="USD",
        input_usd_per_million_tokens=Decimal("999"),
        output_usd_per_million_tokens=Decimal("999"),
    )
    with pytest.raises(RuntimeError, match="different rate"):
        RsAtomicMoveBudgetLedger(path, price=price_evil, hard_budget_usd=Decimal("5.00"))
