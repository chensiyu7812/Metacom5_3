"""Fail-closed guard for formal Paper-1 outcome access."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


LOCKED_STATUS = "LOCKED_PRE_ZERO_OUTCOME_FREEZE"
SCOPED_CLOSED_STATUS = "CLOSED"


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
    assert_calibration_outcome_locked(config)
    assert_confirmatory_outcome_locked(config)


def _assert_scoped_lock_closed(
    config: dict[str, Any], *, key: str, forbidden_fields: tuple[str, ...]
) -> None:
    lock = config.get(key)
    if not isinstance(lock, dict) or lock.get("status") != SCOPED_CLOSED_STATUS:
        raise RuntimeError(f"Paper-1 {key} is missing or not CLOSED")
    if any(lock.get(field) is not False for field in forbidden_fields):
        raise RuntimeError(f"Paper-1 {key} enables forbidden activity while CLOSED")


def assert_calibration_outcome_locked(config: dict[str, Any]) -> None:
    assert_rq1_rs_calibration_outcome_locked(config)
    assert_rq2_memory_calibration_outcome_locked(config)


def assert_rq1_rs_calibration_outcome_locked(config: dict[str, Any]) -> None:
    _assert_scoped_lock_closed(
        config,
        key="RQ1_RS_CALIBRATION_OUTCOME_LOCK",
        forbidden_fields=(
            "resource_amount_calibration_allowed",
            "repeated_effect_qualification_allowed",
            "pm_effect_construction_allowed",
            "pm_training_allowed",
            "operating_point_calibration_allowed",
        ),
    )


def assert_rq2_memory_calibration_outcome_locked(config: dict[str, Any]) -> None:
    _assert_scoped_lock_closed(
        config,
        key="RQ2_MEMORY_CALIBRATION_OUTCOME_LOCK",
        forbidden_fields=(
            "resource_amount_calibration_allowed",
            "repeated_effect_qualification_allowed",
            "pm_effect_construction_allowed",
            "pm_training_allowed",
            "operating_point_calibration_allowed",
        ),
    )


def assert_confirmatory_outcome_locked(config: dict[str, Any]) -> None:
    assert_rq1_confirmatory_outcome_locked(config)
    assert_rq2_confirmatory_outcome_locked(config)


def assert_rq1_confirmatory_outcome_locked(config: dict[str, Any]) -> None:
    _assert_scoped_lock_closed(
        config,
        key="RQ1_CONFIRMATORY_OUTCOME_LOCK",
        forbidden_fields=(
            "formal_effect_dataset_allowed",
            "pm_training_allowed",
            "formal_benchmark_outcomes_allowed",
        ),
    )


def assert_rq2_confirmatory_outcome_locked(config: dict[str, Any]) -> None:
    _assert_scoped_lock_closed(
        config,
        key="RQ2_CONFIRMATORY_OUTCOME_LOCK",
        forbidden_fields=(
            "formal_effect_dataset_allowed",
            "pm_training_allowed",
            "formal_benchmark_outcomes_allowed",
        ),
    )


def require_formal_outcome_unlock(config: dict[str, Any], *, freeze_manifest: Path | None) -> None:
    assert_pre_outcome_locked(config)
    raise RuntimeError(
        "Formal Paper-1 outcome access is locked until a reviewed zero-outcome freeze "
        f"manifest replaces the pre-outcome config (received {freeze_manifest!s})."
    )
