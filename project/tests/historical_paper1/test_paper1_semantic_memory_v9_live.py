from decimal import Decimal
import importlib.util
from pathlib import Path

import pytest
from pydantic import ValidationError

from metacom_pm.io import read_json, sha256_file
from metacom_pm.paper1.semantic_memory.runtime import FROZEN_QWEN_MODEL
from metacom_pm.paper1.semantic_memory.runtime_v9_live import (
    SemanticMemoryV9DevVerifier,
    V9_DEV_HARD_BUDGET_USD,
    V9DevAuthorization,
    V9DevBudgetLedger,
)


PROJECT = Path(__file__).resolve().parents[2]
RUNNER_PATH = PROJECT / "scripts/paper1/38_run_semantic_memory_v9_dev.py"
RUNTIME_PATH = PROJECT / "src/metacom_pm/paper1/semantic_memory/runtime_v9_live.py"
OFFLINE_GATE_PATH = PROJECT / "src/metacom_pm/paper1/semantic_memory/runtime_v9_dev.py"
CONFIG_PATH = PROJECT / "configs/paper1_semantic_memory_compiler_v9_dev.yaml"
PACKAGE_PATH = PROJECT / "data/paper1_authority/paper1_semantic_memory_v9_dev_package_20260902_v1.jsonl"
REPORT_PATH = PROJECT / "data/paper1_authority/paper1_semantic_memory_v9_dev_package_report_20260902_v1.json"
AUTH_PATH = PROJECT / "data/paper1_authority/paper1_semantic_memory_v9_dev_live_authorization_20260902_v1.json"


def _runner_module():
    spec = importlib.util.spec_from_file_location("paper1_semantic_memory_v9_runner", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v9_live_authorization_binds_exact_frozen_runtime_and_inputs():
    runner = _runner_module()
    binding, price = runner.binding_and_price(CONFIG_PATH)
    authorization = V9DevAuthorization.model_validate(read_json(AUTH_PATH))

    assert authorization.authorized_model == FROZEN_QWEN_MODEL
    assert authorization.hard_budget_usd == Decimal("0.25")
    assert authorization.maximum_provider_calls == 29
    assert not authorization.full_401_compile_authorized
    assert authorization.outcome_calls == 0
    assert authorization.runtime_binding_sha256 == binding.identity_sha256
    assert authorization.runner_sha256 == sha256_file(RUNNER_PATH)
    assert authorization.live_runtime_module_sha256 == sha256_file(RUNTIME_PATH)
    assert authorization.offline_gate_module_sha256 == sha256_file(OFFLINE_GATE_PATH)
    assert authorization.frozen_package_sha256 == sha256_file(PACKAGE_PATH)
    assert authorization.package_report_sha256 == sha256_file(REPORT_PATH)
    assert authorization.price_snapshot_sha256 == price.identity_sha256


def test_v9_live_authorization_rejects_budget_or_401_scope_drift():
    raw = read_json(AUTH_PATH)
    with pytest.raises(ValidationError):
        V9DevAuthorization.model_validate({**raw, "hard_budget_usd": "0.26"})
    with pytest.raises(ValidationError):
        V9DevAuthorization.model_validate(
            {**raw, "full_401_compile_authorized": True}
        )


def test_v9_live_ledger_has_exact_quarter_dollar_cap(tmp_path):
    runner = _runner_module()
    _, price = runner.binding_and_price(CONFIG_PATH)
    ledger = V9DevBudgetLedger(tmp_path / "budget.jsonl", price=price)
    assert ledger.hard_budget_usd == V9_DEV_HARD_BUDGET_USD
    assert ledger.remaining_usd == Decimal("0.25")


def test_v9_live_runtime_is_verifier_only():
    with pytest.raises(RuntimeError, match="cannot compile the 401-session catalog"):
        SemanticMemoryV9DevVerifier.compile_session(object(), None)
