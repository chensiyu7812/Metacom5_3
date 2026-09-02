from __future__ import annotations

import importlib.util
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT / "scripts/paper1/37_build_semantic_memory_v9_dev_package.py"


def _module():
    spec = importlib.util.spec_from_file_location("v9_package", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_v9_package_reconstructs_exact_32_items_in_29_public_sessions():
    module = _module()
    authority = PROJECT / "data/paper1_authority"
    rows = module.build_rows(
        runtime=PROJECT / "data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json",
        audit=authority / "paper1_precalibration_memory_candidate_audit_20260820_v1.json",
        dev_plan=authority / "paper1_semantic_memory_old_dev_regression_v7_20260820.json",
    )
    assert len(rows) == 29
    assert sum(len(row["old_dev"]) for row in rows) == 32
    assert all(row["source"]["strictly_past_memory_table"] == [] for row in rows)
    assert all(row["outcome_calls"] == 0 for row in rows)
