"""Fail-closed live-call authorization contract.

Phase A does not create an authorization artifact. A future smoke runner must
receive a researcher-reviewed artifact explicitly enabling only the semantic
compiler calls while affirming that the outcome lock remains closed.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from metacom_pm.io import read_json
from metacom_pm.paper1.contracts import StrictContract

from .budget import HARD_BUDGET_USD
from .runtime import FROZEN_QWEN_MODEL

LIVE_AUTHORIZATION_PROTOCOL = "paper1-semantic-memory-live-authorization-v2"

SMOKE_SCOPE = "PUBLIC_EVOEMO_SEMANTIC_COMPILER_SMOKE_ONLY"
FULL_SCOPE = "PUBLIC_EVOEMO_SEMANTIC_COMPILER_FULL_401_RESUME"


class LiveCompilerAuthorization(StrictContract):
    protocol: str = LIVE_AUTHORIZATION_PROTOCOL
    semantic_compiler_calls_authorized: bool
    scope: Literal[
        "PUBLIC_EVOEMO_SEMANTIC_COMPILER_SMOKE_ONLY",
        "PUBLIC_EVOEMO_SEMANTIC_COMPILER_FULL_401_RESUME",
    ]
    maximum_sessions: int = Field(gt=0, le=401)
    model: str
    sanitized_runtime_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime_binding_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    price_snapshot_id: str = Field(min_length=1)
    price_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    hard_budget_usd: Decimal
    outcome_calls: int
    outcome_lock: str

    @model_validator(mode="after")
    def validate_live_gate(self) -> "LiveCompilerAuthorization":
        if not self.semantic_compiler_calls_authorized:
            raise ValueError("semantic compiler calls are not authorized")
        if self.scope == SMOKE_SCOPE and self.maximum_sessions > 20:
            raise ValueError("smoke authorization cannot exceed 20 sessions")
        if self.scope == FULL_SCOPE and self.maximum_sessions != 401:
            raise ValueError("full-resume authorization must bind all 401 sessions")
        if self.model != FROZEN_QWEN_MODEL:
            raise ValueError("live authorization model mismatch")
        if self.hard_budget_usd != HARD_BUDGET_USD:
            raise ValueError("live authorization must preserve the USD 5.00 hard budget")
        if self.outcome_calls != 0:
            raise ValueError("outcome calls must remain zero")
        if self.outcome_lock != "LOCKED_PRE_ZERO_OUTCOME_FREEZE":
            raise ValueError("outcome lock must remain closed")
        return self


def load_live_authorization(path: str | Path) -> LiveCompilerAuthorization:
    return LiveCompilerAuthorization.model_validate(read_json(path))
