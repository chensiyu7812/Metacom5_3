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


def test_evaluation_freeze_blocks_head_tuning_and_binds_dataset_identity() -> None:
    result = _validator_module().validate(require_private_evidence=True)
    assert result["evaluation_freeze_status"] == "P0_NOT_COMPLETE_BLOCKS_HEAD_TUNING_AND_FORMAL_JUDGING"
    assert set(result["dataset_cards"]) == {"ESConv", "EvoEmo", "ES-MemEval", "ESC-Eval"}
    assert result["es_memeval_identity"] == {
        "formal_paper_qa": 1209,
        "public_v1_0_0_qa": 1427,
        "difference": 218,
    }


def test_official_benchmark_surfaces_are_pinned_but_not_overclaimed() -> None:
    result = _validator_module().validate(require_private_evidence=True)
    assert result["official_benchmark_surfaces"] == {
        "esc_eval_cards": 655,
        "esc_judge_public_roles": 100,
        "es_memeval_public_git_commits": 2,
    }
    assert result["p0_exit_now"] is False


def test_margins_remain_unset_until_measurement_qualification() -> None:
    module = _validator_module()
    generator = module._load_json(
        module.AUTHORITY_DIR / "generator_qualification_measurement_contract_v1.json"
    )
    risk = module._load_json(
        module.AUTHORITY_DIR / "risk_adjudication_protocol_v1.json"
    )
    assert generator["primary_exam"]["pass_margin"] == "NOT_NUMERICALLY_FROZEN"
    assert risk["statistics"]["noninferiority_margin"].startswith("NOT_NUMERICALLY_FROZEN")
    assert "uncertain" in risk["events"]
