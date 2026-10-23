from decimal import Decimal

import pytest

from metacom_pm.paper1.semantic_memory.budget import (
    PriceSnapshot,
    SemanticCompilerBudgetLedger,
)
from metacom_pm.paper1.semantic_memory.cache import CompilerCallIdentity, SuccessCache


def _identity(**changes) -> CompilerCallIdentity:
    values = {
        "phase": "extractor",
        "compiler_version": "v1",
        "provider": "Alibaba",
        "region": "region-a",
        "base_url": "https://example.invalid/v1",
        "model": "qwen3-235b-a22b-instruct-2507",
        "enable_thinking": False,
        "response_mode": "json_object_plus_local_pydantic",
        "request_parameters": {"temperature": 0.0, "max_tokens": 100},
        "prompt_sha256": "1" * 64,
        "schema_sha256": "2" * 64,
        "source_sha256": "3" * 64,
        "prior_memory_table_sha256": "4" * 64,
        "request_payload_sha256": "5" * 64,
    }
    values.update(changes)
    return CompilerCallIdentity(**values)


@pytest.mark.parametrize(
    "change",
    [
        {"compiler_version": "v2"},
        {"model": "changed"},
        {"prompt_sha256": "a" * 64},
        {"schema_sha256": "b" * 64},
        {"source_sha256": "c" * 64},
        {"prior_memory_table_sha256": "d" * 64},
        {"request_parameters": {"temperature": 0.1, "max_tokens": 100}},
    ],
)
def test_every_required_identity_change_invalidates_cache_key(change) -> None:
    assert _identity(**change).cache_key != _identity().cache_key


def test_success_cache_is_immutable_and_resumable(tmp_path) -> None:
    cache = SuccessCache(tmp_path / "cache")
    identity = _identity()
    cache.store_success(identity, {"parsed": {"ok": True}})
    assert cache.load(identity) == {"parsed": {"ok": True}}
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        cache.store_success(identity, {"parsed": {"ok": False}})


def test_budget_reserves_before_call_and_hard_stops_at_five_usd(tmp_path) -> None:
    price = PriceSnapshot(
        snapshot_id="official-price-snapshot-test",
        provider="Alibaba",
        region="region-a",
        currency="USD",
        input_usd_per_million_tokens=Decimal("1"),
        output_usd_per_million_tokens=Decimal("1"),
    )
    ledger = SemanticCompilerBudgetLedger(tmp_path / "budget.jsonl", price=price)
    reservation = ledger.reserve(
        reservation_id="r1",
        phase="extractor",
        call_key="c1",
        maximum_prompt_tokens=1_000_000,
        maximum_completion_tokens=500_000,
    )
    assert ledger.remaining_usd == Decimal("3.5")
    with pytest.raises(RuntimeError, match="hard budget would be exceeded"):
        ledger.reserve(
            reservation_id="r2",
            phase="verifier",
            call_key="c2",
            maximum_prompt_tokens=3_500_001,
            maximum_completion_tokens=0,
        )
    ledger.settle(
        reservation,
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        outcome="SUCCEEDED",
    )
    assert ledger.remaining_usd == Decimal("4.999985")


def test_budget_ledger_cannot_reopen_same_snapshot_id_with_changed_prices(tmp_path) -> None:
    path = tmp_path / "budget.jsonl"
    frozen = PriceSnapshot(
        snapshot_id="same-human-label",
        provider="Alibaba",
        region="region-a",
        currency="USD",
        input_usd_per_million_tokens=Decimal("0.23"),
        output_usd_per_million_tokens=Decimal("0.92"),
    )
    ledger = SemanticCompilerBudgetLedger(path, price=frozen)
    reservation = ledger.reserve(
        reservation_id="r1",
        phase="extractor",
        call_key="c1",
        maximum_prompt_tokens=100,
        maximum_completion_tokens=100,
    )
    ledger.settle(
        reservation,
        usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        outcome="SUCCEEDED",
    )
    changed = PriceSnapshot(
        snapshot_id=frozen.snapshot_id,
        provider=frozen.provider,
        region=frozen.region,
        currency="USD",
        input_usd_per_million_tokens=Decimal("0.01"),
        output_usd_per_million_tokens=frozen.output_usd_per_million_tokens,
    )
    with pytest.raises(RuntimeError, match="exact price identity mismatch"):
        SemanticCompilerBudgetLedger(path, price=changed)
