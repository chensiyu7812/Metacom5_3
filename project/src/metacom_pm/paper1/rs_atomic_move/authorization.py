"""Fail-closed live-call authorization contract for the RS atomic-move
compiler.

Mirrors ``semantic_memory/authorization.py``'s pattern (smoke vs full scope,
model/identity/budget/outcome-lock binding) but is its own independent
authorization surface: the 2026-08-17 semantic-memory-compiler amendment's
budget/authorization only covers MP/MS/ME. RS atomic-move calls require this
separate artifact and are tracked against their own budget ledger,
independent of the memory compiler's USD 5.00 cap.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from metacom_pm.io import read_json
from metacom_pm.paper1.contracts import StrictContract

from .runtime import FROZEN_QWEN_MODEL

LIVE_AUTHORIZATION_PROTOCOL = "paper1-rs-atomic-move-live-authorization-v1"

SMOKE_SCOPE = "PUBLIC_ESCONV_RS_ATOMIC_MOVE_SMOKE_ONLY"
FULL_SCOPE = "PUBLIC_ESCONV_RS_ATOMIC_MOVE_FULL_CATALOG_RESUME"
# A repair run is neither a smoke (exploring/testing the pipeline) nor a
# full-catalog pass -- it is a small, targeted re-attempt of specific
# call_failure_phase cards from an already-completed full run (see
# scripts/paper1/17_repair_rs_atomic_move_failed_cards.py). It was first run
# under SMOKE_SCOPE (2026-08-19, 20 cards, $0.15 cap) because this scope did
# not yet exist; that historical authorization file is left as-is rather than
# rewritten, but every repair run from here on must use this scope instead.
REPAIR_SCOPE = "PUBLIC_ESCONV_RS_ATOMIC_MOVE_REPAIR_ONLY"

# The real, already-materialized ESConv-train-only source catalog size (see
# rs/strategy_bank.build_strategy_source_catalog, confirmed against the real
# artifact in tests/test_paper1_rs_atomic_move_integration.py). A full-scope
# authorization must bind exactly this count, the same way the memory
# compiler's full-resume scope binds exactly 401.
FULL_CATALOG_SIZE = 12169
# 20 covered the initial single-dialogue pipeline smoke. Raised to 100 on
# 2026-08-18 to cover a stratified cross-dialogue/cross-family diverse
# compiler-QA smoke (still >100x smaller than FULL_CATALOG_SIZE, and each
# smoke run still needs its own hard_budget_usd cap independent of this
# card-count ceiling).
SMOKE_MAXIMUM_CARDS = 100
# A repair batch only ever covers the call_failure_phase rows of one prior
# run; it should never approach full-catalog scale (if it did, the source
# run was not actually usable and needs a fresh full-scope run instead, not
# a repair).
REPAIR_MAXIMUM_CARDS = 100


class LiveCompilerAuthorization(StrictContract):
    protocol: str = LIVE_AUTHORIZATION_PROTOCOL
    rs_atomic_move_calls_authorized: bool
    scope: Literal[
        "PUBLIC_ESCONV_RS_ATOMIC_MOVE_SMOKE_ONLY",
        "PUBLIC_ESCONV_RS_ATOMIC_MOVE_FULL_CATALOG_RESUME",
        "PUBLIC_ESCONV_RS_ATOMIC_MOVE_REPAIR_ONLY",
    ]
    maximum_cards: int = Field(gt=0, le=FULL_CATALOG_SIZE)
    model: str
    esconv_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_identity_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    price_snapshot_id: str = Field(min_length=1)
    price_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    hard_budget_usd: Decimal
    outcome_calls: int
    outcome_lock: str

    @model_validator(mode="after")
    def validate_live_gate(self) -> "LiveCompilerAuthorization":
        if not self.rs_atomic_move_calls_authorized:
            raise ValueError("RS atomic-move calls are not authorized")
        if self.scope == SMOKE_SCOPE and self.maximum_cards > SMOKE_MAXIMUM_CARDS:
            raise ValueError(f"smoke authorization cannot exceed {SMOKE_MAXIMUM_CARDS} cards")
        if self.scope == FULL_SCOPE and self.maximum_cards != FULL_CATALOG_SIZE:
            raise ValueError(f"full-catalog authorization must bind all {FULL_CATALOG_SIZE} cards")
        if self.scope == REPAIR_SCOPE and self.maximum_cards > REPAIR_MAXIMUM_CARDS:
            raise ValueError(f"repair authorization cannot exceed {REPAIR_MAXIMUM_CARDS} cards")
        if self.model != FROZEN_QWEN_MODEL:
            raise ValueError("live authorization model mismatch")
        if self.hard_budget_usd <= 0:
            raise ValueError("live authorization hard_budget_usd must be positive")
        if self.outcome_calls != 0:
            raise ValueError("outcome calls must remain zero")
        if self.outcome_lock != "LOCKED_PRE_ZERO_OUTCOME_FREEZE":
            raise ValueError("outcome lock must remain closed")
        return self


def load_live_authorization(path: str | Path) -> LiveCompilerAuthorization:
    return LiveCompilerAuthorization.model_validate(read_json(path))
