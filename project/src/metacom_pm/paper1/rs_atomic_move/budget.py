"""Crash-conservative pre-call reservation and cost ledger for the RS
atomic-move compiler.

Independent budget ledger from ``semantic_memory/budget.py`` -- separate
protocol string, separate ledger file, and (deliberately) NO hard-coded
dollar constant. The memory compiler bakes in ``HARD_BUDGET_USD`` because
that number is already researcher-approved and authority-documented. The RS
atomic-move hard cap has not been approved yet (discussed range: ~$3-6,
pending confirmation), so this module requires the cap to be passed in
explicitly rather than guessing a number now and having to silently change
it later. ``SemanticCompilerBudgetLedger.__init__`` in the memory-compiler
module raises if the passed cap does not equal its hard-coded constant; this
module's equivalent check instead pins the cap to whatever the ledger's
*own* history already recorded, so a ledger cannot be silently re-opened
with a different cap than it was created with -- the same fail-closed
principle, without a premature hard-coded number.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from metacom_pm.io import append_jsonl, canonical_json, iter_jsonl, sha256_text, utc_now

BUDGET_LEDGER_PROTOCOL = "paper1-rs-atomic-move-budget-ledger-v1"


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
            raise ValueError("RS atomic-move budget must use USD pricing")
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
                    "input_usd_per_million_tokens": str(self.input_usd_per_million_tokens),
                    "output_usd_per_million_tokens": str(self.output_usd_per_million_tokens),
                }
            )
        )


@dataclass(frozen=True)
class BudgetReservation:
    reservation_id: str
    maximum_cost_usd: Decimal


class RsAtomicMoveBudgetLedger:
    """Append-only ledger; interrupted reservations remain conservatively
    spent. ``hard_budget_usd`` must be supplied by the caller (from a
    researcher-reviewed authorization artifact, not a module constant); a
    fresh ledger file records it on first use, and every later open of the
    same ledger file must pass the identical value or construction fails."""

    def __init__(
        self,
        path: str | Path,
        *,
        price: PriceSnapshot,
        hard_budget_usd: Decimal,
    ) -> None:
        self.path = Path(path)
        self.price = price
        self.hard_budget_usd = Decimal(hard_budget_usd)
        if self.hard_budget_usd <= 0:
            raise ValueError("RS atomic-move hard budget must be positive")
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
            # A snapshot_id/provider/region match is not enough -- the same
            # snapshot_id could be reused with edited rates. Bind the full
            # rate identity (including the actual input/output USD-per-
            # million-token numbers) so reopening a ledger under a silently
            # changed price is rejected, not merely a changed label.
            recorded_price_identity = row.get("price_identity_sha256")
            if recorded_price_identity is not None and recorded_price_identity != self.price.identity_sha256:
                raise RuntimeError(
                    f"price snapshot '{self.price.snapshot_id}' has a different rate than "
                    f"when this ledger was created at line {line_no}"
                )
            recorded_cap = row.get("hard_budget_usd")
            if recorded_cap is not None and Decimal(str(recorded_cap)) != self.hard_budget_usd:
                raise RuntimeError(
                    f"ledger was created with hard_budget_usd={recorded_cap}, "
                    f"cannot reopen with {self.hard_budget_usd}"
                )
            reservation_id = str(row.get("reservation_id") or "")
            event = str(row.get("event") or "")
            events = self._events.setdefault(reservation_id, [])
            if not events and event != "RESERVED":
                raise RuntimeError(f"budget settlement precedes reservation at line {line_no}")
            if events and (len(events) != 1 or event != "SETTLED"):
                raise RuntimeError(f"duplicate budget event at line {line_no}")
            events.append(row)
        if self.accounted_cost_usd > self.hard_budget_usd:
            raise RuntimeError("historical RS atomic-move cost exceeds hard budget")

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
                "RS atomic-move hard budget would be exceeded: "
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
            "price_identity_sha256": self.price.identity_sha256,
            "provider": self.price.provider,
            "region": self.price.region,
            "currency": self.price.currency,
            "hard_budget_usd": str(self.hard_budget_usd),
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
            actual = self.price.cost(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens)
            if actual > reservation.maximum_cost_usd:
                raise RuntimeError("provider usage exceeds pre-call budget reservation")
            accounting = "provider_reported_usage"
        row = {
            "protocol": BUDGET_LEDGER_PROTOCOL,
            "event": "SETTLED",
            "timestamp": utc_now(),
            "reservation_id": reservation.reservation_id,
            "price_snapshot_id": self.price.snapshot_id,
            "price_identity_sha256": self.price.identity_sha256,
            "provider": self.price.provider,
            "region": self.price.region,
            "hard_budget_usd": str(self.hard_budget_usd),
            "outcome": outcome,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "actual_cost_usd": str(actual),
            "accounting": accounting,
        }
        append_jsonl(self.path, row)
        self._events[reservation.reservation_id].append(row)
        return actual
