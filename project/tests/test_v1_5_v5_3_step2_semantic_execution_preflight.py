from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/v1_5/88l_freeze_v5_3_step2_semantic_execution_preflight_v1_5.py"


def _module():
    spec = importlib.util.spec_from_file_location("step2_semantic_execution_preflight", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_preflight_is_zero_api_and_binds_the_frozen_plan() -> None:
    contract = _module().build_preflight()
    assert contract["qualification_plan_identity"] == "v53step2semplan_4a644f74b60d633d9b1b15c1"
    assert contract["generation"]["logical_calls"] == 64
    assert contract["generation"]["maximum_physical_calls"] == 128
    assert contract["generation"]["free_rewrite_or_semantic_retry_allowed"] is False
    assert contract["generation"]["recovery_after_guard_failure"] == "deterministic_fallback"
    assert contract["cost"]["requested_authorization_ceiling_usd"] == 0.20
    assert contract["api_calls"] == 0
    assert contract["status"] == "AWAITING_EXPLICIT_IDENTITY_AND_COST_AUTHORIZATION"
    assert str(contract["run_identity"]).startswith("v53step2semexec_")
