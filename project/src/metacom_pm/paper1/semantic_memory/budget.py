"""Crash-conservative USD 5 pre-call reservation and cost ledger."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from metacom_pm.io import append_jsonl, canonical_json, iter_jsonl, sha256_text, utc_now

BUDGET_LEDGER_PROTOCOL = "paper1-semantic-memory-budget-ledger-v1"
# Researcher-approved 2026-08-18: raised from USD 2.00 after the v6 20-session
# live smoke showed real per-session cost (~$0.007-0.011) makes USD 2.00
# insufficient to complete the full 401-session compile with margin for
# owner-to-owner variance and retries.
HARD_BUDGET_USD = Decimal("5.00")


@dataclass(frozen=True)
class PriceSnapshot:
    snapshot_id: str
    provider: str
    region: str
    currency: str
    input_usd_per_million_tokens: Decimal
    output_usd_per_million_tokens: Decimal

    def __post_init__(self) -> None:
        if self.currency != "USD":
            raise ValueError("semantic compiler budget must use USD pricing")
        if self.input_usd_per_million_tokens < 0 or self.output_usd_per_million_tokens < 0:
            raise ValueError("token prices must be non-negative")

    def cost(self, *, prompt_tokens: int, completion_tokens: int) -> Decimal:
        million = Decimal(1_000_000)
        return (
            Decimal(prompt_tokens) * self.input_usd_per_million_tokens
            + Decimal(completion_tokens) * self.output_usd_per_million_tokens
        ) / million

    @property
    def identity_sha256(self) -> str:
        return sha256_text(
            canonical_json(
                {
                    "snapshot_id": self.snapshot_id,
                    "provider": self.provider,
                    "region": self.region,
                    "currency": self.currency,
                    "input_usd_per_million_tokens": str(
                        self.input_usd_per_million_tokens
                    ),
                    "output_usd_per_million_tokens": str(
                        self.output_usd_per_million_tokens
                    ),
                }
            )
        )


@dataclass(frozen=True)
class BudgetReservation:
    reservation_id: str
    maximum_cost_usd: Decimal


class SemanticCompilerBudgetLedger:
    """Append-only ledger; interrupted reservations remain conservatively spent."""

    def __init__(
        self,
        path: str | Path,
        *,
        price: PriceSnapshot,
        hard_budget_usd: Decimal = HARD_BUDGET_USD,
    ) -> None:
        self.path = Path(path)
        self.price = price
        self.hard_budget_usd = Decimal(hard_budget_usd)
        if self.hard_budget_usd != HARD_BUDGET_USD:
            raise ValueError("Paper-1 semantic compiler hard budget must remain USD 5.00")
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        for line_no, row in enumerate(iter_jsonl(self.path), 1):
            if row.get("protocol") != BUDGET_LEDGER_PROTOCOL:
                raise RuntimeError(f"budget ledger protocol mismatch at line {line_no}")
            if row.get("price_snapshot_id") != self.price.snapshot_id:
                raise RuntimeError(f"price snapshot mismatch at line {line_no}")
            if row.get("provider") != self.price.provider or row.get("region") != self.price.region:
                raise RuntimeError(f"provider/region mismatch at line {line_no}")
            reservation_id = str(row.get("reservation_id") or "")
            event = str(row.get("event") or "")
            events = self._events.setdefault(reservation_id, [])
            if not events and event != "RESERVED":
                raise RuntimeError(f"budget settlement precedes reservation at line {line_no}")
            if events and (len(events) != 1 or event != "SETTLED"):
                raise RuntimeError(f"duplicate budget event at line {line_no}")
            events.append(row)
        if self.accounted_cost_usd > self.hard_budget_usd:
            raise RuntimeError("historical semantic compiler cost exceeds hard budget")

    @property
    def accounted_cost_usd(self) -> Decimal:
        total = Decimal("0")
        for events in self._events.values():
            terminal = events[-1]
            field = "actual_cost_usd" if terminal.get("event") == "SETTLED" else "maximum_cost_usd"
            total += Decimal(str(terminal[field]))
        return total

    @property
    def remaining_usd(self) -> Decimal:
        return self.hard_budget_usd - self.accounted_cost_usd

    def reserve(
        self,
        *,
        reservation_id: str,
        phase: str,
        call_key: str,
        maximum_prompt_tokens: int,
        maximum_completion_tokens: int,
    ) -> BudgetReservation:
        if reservation_id in self._events:
            raise RuntimeError("budget reservation ID already exists")
        maximum = self.price.cost(
            prompt_tokens=maximum_prompt_tokens,
            completion_tokens=maximum_completion_tokens,
        )
        if maximum > self.remaining_usd:
            raise RuntimeError(
                "semantic compiler USD 5.00 hard budget would be exceeded: "
                f"remaining={self.remaining_usd}, next_maximum={maximum}"
            )
        row = {
            "protocol": BUDGET_LEDGER_PROTOCOL,
            "event": "RESERVED",
            "timestamp": utc_now(),
            "reservation_id": reservation_id,
            "phase": phase,
            "call_key": call_key,
            "price_snapshot_id": self.price.snapshot_id,
            "provider": self.price.provider,
            "region": self.price.region,
            "currency": self.price.currency,
            "input_usd_per_million_tokens": str(self.price.input_usd_per_million_tokens),
            "output_usd_per_million_tokens": str(self.price.output_usd_per_million_tokens),
            "maximum_prompt_tokens": int(maximum_prompt_tokens),
            "maximum_completion_tokens": int(maximum_completion_tokens),
            "maximum_cost_usd": str(maximum),
        }
        append_jsonl(self.path, row)
        self._events[reservation_id] = [row]
        return BudgetReservation(reservation_id=reservation_id, maximum_cost_usd=maximum)

    def settle(
        self,
        reservation: BudgetReservation,
        *,
        usage: Mapping[str, Any] | None,
        outcome: str,
    ) -> Decimal:
        events = self._events.get(reservation.reservation_id)
        if events is None or len(events) != 1:
            raise RuntimeError("budget reservation is absent or already settled")
        if usage is None:
            actual = reservation.maximum_cost_usd
            prompt_tokens = completion_tokens = total_tokens = None
            accounting = "unknown_usage_charged_at_reserved_maximum"
        else:
            prompt_tokens = int(usage.get("prompt_tokens") or 0)
            completion_tokens = int(usage.get("completion_tokens") or 0)
            total_tokens = int(usage.get("total_tokens") or prompt_tokens + completion_tokens)
            if prompt_tokens <= 0 or completion_tokens < 0:
                raise RuntimeError("provider-reported usage is missing or invalid")
            actual = self.price.cost(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
            if actual > reservation.maximum_cost_usd:
                raise RuntimeError("provider usage exceeds pre-call budget reservation")
            accounting = "provider_reported_usage"
        row = {
            "protocol": BUDGET_LEDGER_PROTOCOL,
            "event": "SETTLED",
            "timestamp": utc_now(),
            "reservation_id": reservation.reservation_id,
            "price_snapshot_id": self.price.snapshot_id,
            "provider": self.price.provider,
            "region": self.price.region,
            "outcome": outcome,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "actual_cost_usd": str(actual),
            "accounting": accounting,
        }
        append_jsonl(self.path, row)
        events.append(row)
        return actual
