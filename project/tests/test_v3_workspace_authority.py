from __future__ import annotations

import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = PROJECT_ROOT / "scripts" / "v3" / "00_validate_v3_workspace.py"


def _validator_module():
    spec = importlib.util.spec_from_file_location("v3_workspace_validator", VALIDATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v3_workspace_authority_and_private_evidence_are_consistent() -> None:
    result = _validator_module().validate(require_private_evidence=True)
    assert result["valid"], result["failures"]
    assert result["private_evidence"]["present"] is True


def test_v3_execution_phases_do_not_authorize_api_calls() -> None:
    module = _validator_module()
    authority = module._load_json(
        module.AUTHORITY_DIR / "v3_research_authority_v1.json"
    )
    assert all(phase["api_authority"] is False for phase in authority["execution_phases"])
