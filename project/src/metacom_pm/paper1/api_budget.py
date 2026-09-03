"""Append-only cumulative paid-API budget guard for active Paper-1 work.

This ledger is provider-agnostic. Individual runtimes still calculate their
own token-based worst case, then reserve that USD amount here before making a
paid call. An interrupted reservation remains conservatively accounted at its
maximum until explicitly settled.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from metacom_pm.io import append_jsonl, iter_jsonl, utc_now


API_BUDGET_PROTOCOL = "pm-paper1-cumulative-paid-api-budget-ledger-v1"
PAPER1_API_HARD_CAP_USD = Decimal("50.00")
PAPER1_OPTIONAL_STOP_USD = Decimal("43.00")
PAPER1_RETRY_RESERVE_USD = Decimal("5.00")
PAPER1_KNOWN_V9_COST_USD = Decimal("0.03079930")


@dataclass(frozen=True)
class ApiBudgetReservation:
    reservation_id: str
    maximum_cost_usd: Decimal


class CumulativePaper1ApiBudgetLedger:
    """Enforce the researcher-authorized cumulative USD 50 hard stop."""

    def __init__(
        self,
        path: str | Path,
        *,
        opening_cost_usd: Decimal = PAPER1_KNOWN_V9_COST_USD,
    ) -> None:
        self.path = Path(path)
        self.opening_cost_usd = Decimal(opening_cost_usd)
        if self.opening_cost_usd < 0:
            raise ValueError("opening Paper-1 API cost cannot be negative")
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        for line_no, row in enumerate(iter_jsonl(self.path), 1):
            if row.get("protocol") != API_BUDGET_PROTOCOL:
                raise RuntimeError(f"API budget protocol mismatch at line {line_no}")
            if Decimal(str(row.get("hard_cap_usd"))) != PAPER1_API_HARD_CAP_USD:
                raise RuntimeError(f"API hard-cap mismatch at line {line_no}")
            if Decimal(str(row.get("opening_cost_usd"))) != self.opening_cost_usd:
                raise RuntimeError(f"API opening-cost mismatch at line {line_no}")
            reservation_id = str(row.get("reservation_id") or "")
            event = str(row.get("event") or "")
            events = self._events.setdefault(reservation_id, [])
            if not events and event != "RESERVED":
                raise RuntimeError(f"API settlement precedes reservation at line {line_no}")
            if events and (len(events) != 1 or event != "SETTLED"):
                raise RuntimeError(f"duplicate API budget event at line {line_no}")
            events.append(row)
        if self.accounted_cost_usd > PAPER1_API_HARD_CAP_USD:
            raise RuntimeError("historical Paper-1 paid API cost exceeds USD 50")

    @property
    def accounted_new_cost_usd(self) -> Decimal:
        total = Decimal("0")
        for events in self._events.values():
            terminal = events[-1]
            field = (
                "actual_cost_usd"
                if terminal.get("event") == "SETTLED"
                else "maximum_cost_usd"
            )
            total += Decimal(str(terminal[field]))
        return total

    @property
    def accounted_cost_usd(self) -> Decimal:
        return self.opening_cost_usd + self.accounted_new_cost_usd

    @property
    def remaining_usd(self) -> Decimal:
        return PAPER1_API_HARD_CAP_USD - self.accounted_cost_usd

    def _successful_hashes(self) -> set[str]:
        return {
            str(events[-1]["call_hash"])
            for events in self._events.values()
            if events[-1].get("event") == "SETTLED"
            and events[-1].get("outcome") == "SUCCEEDED"
        }

    def _attempts(self, logical_call_id: str) -> int:
        return sum(
            1
            for events in self._events.values()
            if events[0].get("logical_call_id") == logical_call_id
        )

    def reserve(
        self,
        *,
        reservation_id: str,
        logical_call_id: str,
        call_hash: str,
        stage: str,
        provider: str,
        model: str,
        maximum_cost_usd: Decimal,
        call_class: Literal["PRIMARY", "OPTIONAL", "PRIMARY_RETRY"],
    ) -> ApiBudgetReservation:
        maximum = Decimal(maximum_cost_usd)
        if not reservation_id or not logical_call_id or not call_hash:
            raise ValueError("reservation, logical-call and call-hash identities are required")
        if reservation_id in self._events:
            raise RuntimeError("API budget reservation ID already exists")
        if maximum <= 0:
            raise ValueError("maximum API call cost must be positive")
        if call_hash in self._successful_hashes():
            raise RuntimeError("successful prompt/call hash cannot be paid twice")

        prior_attempts = self._attempts(logical_call_id)
        if prior_attempts >= 2:
            raise RuntimeError("Paper-1 paid API calls allow at most one retry")
        if call_class == "PRIMARY_RETRY" and prior_attempts != 1:
            raise RuntimeError("PRIMARY_RETRY requires exactly one prior attempt")
        if call_class != "PRIMARY_RETRY" and prior_attempts:
            raise RuntimeError("a repeated logical call must be classified PRIMARY_RETRY")

        projected = self.accounted_cost_usd + maximum
        if projected > PAPER1_API_HARD_CAP_USD:
            raise RuntimeError("Paper-1 cumulative USD 50 API hard cap would be exceeded")
        if call_class == "OPTIONAL" and projected > PAPER1_OPTIONAL_STOP_USD:
            raise RuntimeError("optional API work must stop before cumulative USD 43")
        if (
            call_class != "PRIMARY_RETRY"
            and projected > PAPER1_API_HARD_CAP_USD - PAPER1_RETRY_RESERVE_USD
        ):
            raise RuntimeError("USD 5 primary retry reserve must remain uncommitted")

        row = {
            "protocol": API_BUDGET_PROTOCOL,
            "event": "RESERVED",
            "timestamp": utc_now(),
            "reservation_id": reservation_id,
            "logical_call_id": logical_call_id,
            "call_hash": call_hash,
            "stage": stage,
            "provider": provider,
            "model": model,
            "call_class": call_class,
            "opening_cost_usd": str(self.opening_cost_usd),
            "hard_cap_usd": str(PAPER1_API_HARD_CAP_USD),
            "maximum_cost_usd": str(maximum),
        }
        append_jsonl(self.path, row)
        self._events[reservation_id] = [row]
        return ApiBudgetReservation(reservation_id, maximum)

    def settle(
        self,
        reservation: ApiBudgetReservation,
        *,
        actual_cost_usd: Decimal | None,
        outcome: Literal["SUCCEEDED", "FAILED", "UNKNOWN"],
    ) -> Decimal:
        events = self._events.get(reservation.reservation_id)
        if events is None or len(events) != 1:
            raise RuntimeError("API reservation is absent or already settled")
        if actual_cost_usd is None:
            actual = reservation.maximum_cost_usd
            accounting = "unknown_cost_charged_at_reserved_maximum"
        else:
            actual = Decimal(actual_cost_usd)
            if actual < 0 or actual > reservation.maximum_cost_usd:
                raise RuntimeError("actual API cost is outside the reserved range")
            accounting = "provider_reported_or_price_snapshot_cost"
        opening = events[0]
        row = {
            "protocol": API_BUDGET_PROTOCOL,
            "event": "SETTLED",
            "timestamp": utc_now(),
            "reservation_id": reservation.reservation_id,
            "logical_call_id": opening["logical_call_id"],
            "call_hash": opening["call_hash"],
            "stage": opening["stage"],
            "provider": opening["provider"],
            "model": opening["model"],
            "call_class": opening["call_class"],
            "opening_cost_usd": str(self.opening_cost_usd),
            "hard_cap_usd": str(PAPER1_API_HARD_CAP_USD),
            "outcome": outcome,
            "actual_cost_usd": str(actual),
            "accounting": accounting,
        }
        append_jsonl(self.path, row)
        events.append(row)
        return actual


__all__ = [
    "API_BUDGET_PROTOCOL",
    "ApiBudgetReservation",
    "CumulativePaper1ApiBudgetLedger",
    "PAPER1_API_HARD_CAP_USD",
    "PAPER1_KNOWN_V9_COST_USD",
    "PAPER1_OPTIONAL_STOP_USD",
    "PAPER1_RETRY_RESERVE_USD",
]
