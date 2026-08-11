from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/v1_5/111l_audit_v5_3_external_complementary_source_readiness_v1_5.py"


def _module():
    spec = importlib.util.spec_from_file_location("external_source_readiness", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_forbidden_key_scan_is_recursive_and_key_based() -> None:
    module = _module()
    value = {
        "visible": "the word answer in ordinary text is not a key leak",
        "nested": [{"answer": "gold"}, {"current_session_summary": "future-ish"}],
    }
    assert module._contains_key(value, {"answer", "current_session_summary"}) == {
        "answer", "current_session_summary",
    }
