"""The 2026-09-18 follow-up budget: one cap across all remaining paid work.

The researcher set a single constraint for *everything* still to be paid for --
first attempts, retries, the DG simulated user, judges, training labels and the
formal evaluation alike: aim for about USD 10, never exceed USD 20. This is
stricter than the older USD 50 programme cap, so it binds first; the older cap
and its USD 5 primary-retry reserve stay in force underneath.

Because the cap applies to *new* spend, it needs a boundary. The boundary is
recorded once as a snapshot of the shared ledger and is never re-derived from a
later ledger state: otherwise a resumed run would silently reset its own
starting point and could spend the allowance twice.

Batch work is a liability the moment it is submitted, not when it returns. A
submitted batch therefore reserves its full worst case here immediately, and
that outstanding liability counts against the cap until the batch settles.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from metacom_pm.io import canonical_json, sha256_file, sha256_text, utc_now

FOLLOWUP_BUDGET_PROTOCOL = "pm-paper1-followup-total-budget-v1"
FOLLOWUP_TARGET_USD = Decimal("10.00")
FOLLOWUP_HARD_CAP_USD = Decimal("20.00")


class FollowupBudgetExceeded(RuntimeError):
    """Raised instead of sending a request that would break the follow-up cap."""


@dataclass(frozen=True)
class FollowupBudgetStatus:
    baseline_accounted_usd: Decimal
    ledger_accounted_usd: Decimal
    outstanding_liability_usd: Decimal

    @property
    def settled_new_spend_usd(self) -> Decimal:
        return self.ledger_accounted_usd - self.baseline_accounted_usd

    @property
    def committed_new_spend_usd(self) -> Decimal:
        return self.settled_new_spend_usd + self.outstanding_liability_usd

    @property
    def remaining_to_hard_cap_usd(self) -> Decimal:
        return FOLLOWUP_HARD_CAP_USD - self.committed_new_spend_usd

    @property
    def remaining_to_target_usd(self) -> Decimal:
        return FOLLOWUP_TARGET_USD - self.committed_new_spend_usd

    def as_dict(self) -> dict[str, Any]:
        return {
            "protocol": FOLLOWUP_BUDGET_PROTOCOL,
            "baseline_accounted_usd": str(self.baseline_accounted_usd),
            "ledger_accounted_usd": str(self.ledger_accounted_usd),
            "settled_new_spend_usd": str(self.settled_new_spend_usd),
            "outstanding_batch_liability_usd": str(self.outstanding_liability_usd),
            "committed_new_spend_usd": str(self.committed_new_spend_usd),
            "target_usd": str(FOLLOWUP_TARGET_USD),
            "hard_cap_usd": str(FOLLOWUP_HARD_CAP_USD),
            "remaining_to_target_usd": str(self.remaining_to_target_usd),
            "remaining_to_hard_cap_usd": str(self.remaining_to_hard_cap_usd),
            "target_exceeded": self.committed_new_spend_usd > FOLLOWUP_TARGET_USD,
            "target_is_a_plan_not_a_gate": True,
        }


class FollowupBudget:
    """Enforce the follow-up cap on top of an existing cumulative ledger."""

    def __init__(self, ledger, snapshot_path: str | Path) -> None:
        self.ledger = ledger
        self.snapshot_path = Path(snapshot_path)
        self.snapshot = self._load_or_create_snapshot()
        self.baseline_accounted_usd = Decimal(str(self.snapshot["baseline_accounted_usd"]))

    def _load_or_create_snapshot(self) -> dict[str, Any]:
        if self.snapshot_path.exists():
            snapshot = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
            if snapshot.get("protocol") != FOLLOWUP_BUDGET_PROTOCOL:
                raise RuntimeError("follow-up budget snapshot protocol mismatch")
            if snapshot.get("identity_sha256") != self._identity_hash(snapshot):
                raise RuntimeError("follow-up budget snapshot was edited after it was written")
            # The boundary is immutable. Re-deriving it from today's ledger is
            # exactly the mistake that would reset the allowance on resume.
            if Decimal(str(snapshot["baseline_accounted_usd"])) > self.ledger.accounted_cost_usd:
                raise RuntimeError("ledger total fell below the recorded follow-up baseline")
            return snapshot
        snapshot = {
            "protocol": FOLLOWUP_BUDGET_PROTOCOL,
            "created_at": utc_now(),
            "researcher_direction": "最多20美元，最好是10美元左右",
            "scope": ("all remaining new paid API work: first attempts, retries, simulated user, "
                      "judges, training labels and formal evaluation"),
            "baseline_accounted_usd": str(self.ledger.accounted_cost_usd),
            "baseline_ledger_sha256": sha256_file(self.ledger.path) if Path(self.ledger.path).exists() else None,
            # The event set is pinned by digest and count rather than by listing
            # every historical reservation id, which would bloat the boundary.
            "baseline_reservation_count": len(self.ledger._events),
            "baseline_reservation_ids_sha256": sha256_text(canonical_json(sorted(self.ledger._events))),
            "target_usd": str(FOLLOWUP_TARGET_USD),
            "hard_cap_usd": str(FOLLOWUP_HARD_CAP_USD),
            "older_programme_cap_still_applies": True,
        }
        snapshot["identity_sha256"] = self._identity_hash(snapshot)
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.snapshot_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.snapshot_path)
        return snapshot

    @staticmethod
    def _identity_hash(snapshot: dict[str, Any]) -> str:
        return sha256_text(canonical_json({k: v for k, v in snapshot.items() if k != "identity_sha256"}))

    def outstanding_liability_usd(self, liabilities: list[dict] | None = None) -> Decimal:
        """Worst case of submitted work that has not settled yet.

        Unsettled ledger reservations are already inside `accounted_cost_usd`, so
        only externally tracked obligations -- an in-flight batch -- are added.
        """
        total = Decimal("0")
        for row in liabilities or []:
            if row.get("state") in {"SETTLED", "CANCELLED"}:
                continue
            total += Decimal(str(row["worst_case_usd"]))
        return total

    def status(self, liabilities: list[dict] | None = None) -> FollowupBudgetStatus:
        return FollowupBudgetStatus(
            baseline_accounted_usd=self.baseline_accounted_usd,
            ledger_accounted_usd=self.ledger.accounted_cost_usd,
            outstanding_liability_usd=self.outstanding_liability_usd(liabilities),
        )

    def check(self, next_worst_case_usd: Decimal, *, liabilities: list[dict] | None = None,
              what: str = "request") -> FollowupBudgetStatus:
        """Raise before committing anything that would break the follow-up cap."""
        status = self.status(liabilities)
        projected = status.committed_new_spend_usd + Decimal(next_worst_case_usd)
        if projected > FOLLOWUP_HARD_CAP_USD:
            raise FollowupBudgetExceeded(
                f"{what} would take follow-up spend to USD {projected}, over the USD "
                f"{FOLLOWUP_HARD_CAP_USD} cap (committed USD {status.committed_new_spend_usd})")
        return status

    def would_exceed(self, next_worst_case_usd: Decimal,
                     *, liabilities: list[dict] | None = None) -> bool:
        status = self.status(liabilities)
        return status.committed_new_spend_usd + Decimal(next_worst_case_usd) > FOLLOWUP_HARD_CAP_USD


__all__ = [
    "FOLLOWUP_BUDGET_PROTOCOL", "FOLLOWUP_HARD_CAP_USD", "FOLLOWUP_TARGET_USD",
    "FollowupBudget", "FollowupBudgetExceeded", "FollowupBudgetStatus",
]
