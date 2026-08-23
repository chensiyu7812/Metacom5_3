import importlib.util
import json
from pathlib import Path

import pytest


PROJECT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT / "scripts/paper1/34_attest_esc_rank_cloud_assets.py"
READINESS = PROJECT / "data/paper1_authority/paper1_esc_rank_cloud_execution_readiness_20260823_v1.json"


def _module():
    spec = importlib.util.spec_from_file_location("esc_rank_attestor", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _template(score_sha: str):
    return {
        "protocol": "pending",
        "status": "IMPLEMENTATION_PENDING",
        "official_identity": {
            "esc_eval_commit": "esc-commit",
            "score_py_sha256": score_sha,
            "esc_rank_revision": "rank-revision",
            "internlm2_revision": "base-revision",
        },
        "dependency_pins": {"torch": "2.3.1", "transformers": "4.41.2"},
        "required_runtime_inventory": {
            "esc_rank_tree_sha256": "IMPLEMENTATION_PENDING_AFTER_PINNED_DOWNLOAD",
            "internlm2_tree_sha256": "IMPLEMENTATION_PENDING_AFTER_PINNED_DOWNLOAD",
        },
    }


def _fake_assets(tmp_path: Path, module):
    esc = tmp_path / "esc"
    rank = tmp_path / "rank-revision"
    base = tmp_path / "base-revision"
    esc.mkdir()
    rank.mkdir()
    base.mkdir()
    (esc / "score.py").write_text("official scorer", encoding="utf-8")
    (base / "config.json").write_text("{}", encoding="utf-8")
    for adapter in module.REQUIRED_ADAPTERS:
        path = rank / adapter
        path.mkdir()
        (path / "adapter_config.json").write_text("{}", encoding="utf-8")
    return esc, rank, base


def test_asset_attestor_resolves_exact_hashes_without_runtime_calls(tmp_path):
    module = _module()
    esc, rank, base = _fake_assets(tmp_path, module)
    template = _template(module.sha_file(esc / "score.py"))
    resolved = module.resolve_manifest(
        template,
        esc_eval=esc,
        rank_path=rank,
        base_path=base,
        actual_dependencies={"torch": "2.3.1", "transformers": "4.41.2"},
        observed_esc_eval_commit="esc-commit",
    )
    assert resolved["status"] == "ASSETS_ATTESTED_READY_FOR_24GIB_RUNTIME"
    assert len(resolved["required_runtime_inventory"]["esc_rank_tree_sha256"]) == 64
    assert len(resolved["required_runtime_inventory"]["internlm2_tree_sha256"]) == 64
    assert resolved["calls"] == {
        "downloads_by_this_script": 0,
        "model_loads_by_this_script": 0,
        "evaluator_calls_by_this_script": 0,
        "outcome_calls": 0,
    }


def test_asset_attestor_rejects_dependency_or_adapter_drift(tmp_path):
    module = _module()
    esc, rank, base = _fake_assets(tmp_path, module)
    template = _template(module.sha_file(esc / "score.py"))
    (rank / module.REQUIRED_ADAPTERS[-1] / "adapter_config.json").unlink()
    with pytest.raises(RuntimeError, match="missing"):
        module.resolve_manifest(
            template,
            esc_eval=esc,
            rank_path=rank,
            base_path=base,
            actual_dependencies={"torch": "2.3.1", "transformers": "4.41.2"},
            observed_esc_eval_commit="esc-commit",
        )


def test_cloud_readiness_does_not_claim_local_execution_or_select_judges():
    readiness = json.loads(READINESS.read_text(encoding="utf-8"))
    assert readiness["current_local_gpu"]["eligible"] is False
    assert readiness["current_local_gpu"]["total_mib"] == 8192
    assert readiness["evaluator_calls"] == readiness["outcome_calls"] == 0
    assert readiness["formal_ESC_Eval"] is False
    assert set(readiness["locks"].values()) == {"CLOSED"}
    assert all(
        "BLOCKED" in status
        for candidate, status in readiness["identity_status"].items()
        if candidate != "ESC_RANK"
    )
