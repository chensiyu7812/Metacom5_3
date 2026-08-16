"""Fail-closed guard for formal Paper-1 outcome access."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


LOCKED_STATUS = "LOCKED_PRE_ZERO_OUTCOME_FREEZE"


def load_public_only_config(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Paper-1 config must be a mapping")
    return value


def assert_pre_outcome_locked(config: dict[str, Any]) -> None:
    lock = config.get("outcome_lock")
    if not isinstance(lock, dict) or lock.get("status") != LOCKED_STATUS:
        raise RuntimeError("Paper-1 pre-outcome lock is missing or drifted")
    forbidden = (
        "formal_effect_calls_allowed",
        "formal_training_allowed",
        "formal_benchmark_outcomes_allowed",
    )
    if any(lock.get(field) is not False for field in forbidden):
        raise RuntimeError("formal outcome activity is enabled before the freeze manifest")


def require_formal_outcome_unlock(config: dict[str, Any], *, freeze_manifest: Path | None) -> None:
    assert_pre_outcome_locked(config)
    raise RuntimeError(
        "Formal Paper-1 outcome access is locked until a reviewed zero-outcome freeze "
        f"manifest replaces the pre-outcome config (received {freeze_manifest!s})."
    )
