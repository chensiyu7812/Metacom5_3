from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from metacom_pm.paper1.rs_atomic_move.authorization import (
    FULL_CATALOG_SIZE,
    FULL_SCOPE,
    REPAIR_MAXIMUM_CARDS,
    REPAIR_SCOPE,
    SMOKE_MAXIMUM_CARDS,
    SMOKE_SCOPE,
    LiveCompilerAuthorization,
)

HEX64 = "d" * 64


def _common(**overrides) -> dict:
    fields = dict(
        rs_atomic_move_calls_authorized=True,
        model="qwen3-235b-a22b-instruct-2507",
        esconv_sha256=HEX64,
        run_identity_sha256=HEX64,
        price_snapshot_id="test-price",
        price_snapshot_sha256=HEX64,
        hard_budget_usd=Decimal("1.00"),
        outcome_calls=0,
        outcome_lock="LOCKED_PRE_ZERO_OUTCOME_FREEZE",
    )
    fields.update(overrides)
    return fields


def test_valid_smoke_authorization():
    auth = LiveCompilerAuthorization(scope=SMOKE_SCOPE, maximum_cards=10, **_common())
    assert auth.scope == SMOKE_SCOPE


def test_smoke_authorization_cannot_exceed_smoke_maximum():
    with pytest.raises(ValidationError, match=f"cannot exceed {SMOKE_MAXIMUM_CARDS}"):
        LiveCompilerAuthorization(scope=SMOKE_SCOPE, maximum_cards=SMOKE_MAXIMUM_CARDS + 1, **_common())


def test_full_scope_must_bind_the_entire_catalog():
    with pytest.raises(ValidationError, match=f"all {FULL_CATALOG_SIZE}"):
        LiveCompilerAuthorization(scope=FULL_SCOPE, maximum_cards=100, **_common())
    auth = LiveCompilerAuthorization(scope=FULL_SCOPE, maximum_cards=FULL_CATALOG_SIZE, **_common())
    assert auth.maximum_cards == FULL_CATALOG_SIZE


def test_valid_repair_authorization():
    auth = LiveCompilerAuthorization(scope=REPAIR_SCOPE, maximum_cards=14, **_common())
    assert auth.scope == REPAIR_SCOPE


def test_repair_authorization_cannot_exceed_repair_maximum():
    with pytest.raises(ValidationError, match=f"cannot exceed {REPAIR_MAXIMUM_CARDS}"):
        LiveCompilerAuthorization(
            scope=REPAIR_SCOPE, maximum_cards=REPAIR_MAXIMUM_CARDS + 1, **_common()
        )


def test_unauthorized_flag_fails_closed():
    with pytest.raises(ValidationError, match="not authorized"):
        LiveCompilerAuthorization(
            scope=SMOKE_SCOPE, maximum_cards=10,
            **_common(rs_atomic_move_calls_authorized=False),
        )


def test_outcome_lock_must_stay_closed():
    with pytest.raises(ValidationError, match="outcome lock must remain closed"):
        LiveCompilerAuthorization(
            scope=SMOKE_SCOPE, maximum_cards=10,
            **_common(outcome_lock="UNLOCKED"),
        )


def test_nonzero_outcome_calls_fails_closed():
    with pytest.raises(ValidationError, match="outcome calls must remain zero"):
        LiveCompilerAuthorization(
            scope=SMOKE_SCOPE, maximum_cards=10,
            **_common(outcome_calls=1),
        )


def test_wrong_model_fails_closed():
    with pytest.raises(ValidationError, match="model mismatch"):
        LiveCompilerAuthorization(
            scope=SMOKE_SCOPE, maximum_cards=10,
            **_common(model="gpt-4o"),
        )
