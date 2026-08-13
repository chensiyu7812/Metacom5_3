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


def test_v3_public_workspace_authority_is_consistent() -> None:
    result = _validator_module().validate(require_private_evidence=False)
    assert result["valid"], result["failures"]


def test_local_private_evidence_is_consistent_when_present() -> None:
    module = _validator_module()
    private_root = module.REPO_ROOT / module._load_json(
        module.AUTHORITY_DIR / "v3_asset_compatibility_manifest_v1.json"
    )["private_evidence"]["path"]
    result = module.validate(require_private_evidence=private_root.is_dir())
    assert result["valid"], result["failures"]
    assert result["private_evidence"]["present"] is private_root.is_dir()


def test_v3_execution_phases_do_not_authorize_api_calls() -> None:
    module = _validator_module()
    authority = module._load_json(
        module.AUTHORITY_DIR / "v3_research_authority_v1.json"
    )
    assert all(phase["api_authority"] is False for phase in authority["execution_phases"])


def test_evaluation_design_freeze_is_complete_and_binds_dataset_identity() -> None:
    result = _validator_module().validate(require_private_evidence=False)
    assert result["evaluation_freeze_status"] == "P0_EVIDENCE_ARCHITECTURE_FREEZE_COMPLETE_OFFICIAL_SCALE_MAPPING_REPAIRED_P1_MEASUREMENT_QUALIFICATION_REQUIRED"
    assert set(result["dataset_cards"]) == {"ESConv", "EvoEmo", "ES-MemEval", "ESC-Eval"}
    assert result["es_memeval_identity"] == {
        "formal_paper_qa": 1209,
        "public_v1_0_0_qa": 1427,
        "difference": 218,
    }


def test_official_benchmark_surfaces_are_pinned_but_not_overclaimed() -> None:
    result = _validator_module().validate(require_private_evidence=False)
    assert result["official_benchmark_surfaces"] == {
        "esc_eval_cards": 655,
        "esc_judge_public_roles": 100,
        "es_memeval_public_git_commits": 2,
    }
    assert result["p0_exit_now"] is True


def test_numeric_margins_remain_p1_calibration_values_not_formal_outcome_values() -> None:
    module = _validator_module()
    generator = module._load_json(
        module.AUTHORITY_DIR / "generator_qualification_measurement_contract_v1.json"
    )
    risk = module._load_json(
        module.AUTHORITY_DIR / "risk_adjudication_protocol_v1.json"
    )
    assert generator["primary_exam"]["pass_margin"].startswith("NO_SOLE_ESC_RANK_NUMERIC_CUTOFF")
    assert risk["statistics"]["noninferiority_margin"].startswith("NOT_NUMERICALLY_FROZEN")
    assert "uncertain" in risk["events"]


def test_esc_rank_public_calibration_boundary_and_same_stack_reference_are_frozen() -> None:
    result = _validator_module().validate(require_private_evidence=False)
    assert result["esc_rank_public_qualification"] == {
        "public_human_label_rows": 0,
        "primary_adapters": 14,
        "inference_calls": 0,
    }
    assert result["same_stack_reference"] == "meta/llama-3.3-70b-instruct"
    assert result["numeric_calibration_phase"] == "P1_PENDING_BEFORE_FORMAL_VERDICT"
    assert result["esc_rank_runtime_preflight"] == {
        "status": "STATIC_PASS",
        "weights_downloaded": 0,
        "inference_calls": 0,
    }


def test_es_memeval_public_1427_identity_is_complete_and_not_overclaimed() -> None:
    result = _validator_module().validate(require_private_evidence=False)
    assert result["es_memeval_primary_task"] == "ES-MemEval-Public-v1.0.0-1427"
    assert result["es_memeval_row_identity"] == {
        "rows": 1427,
        "sha256": "e530e58b489ee87641a80fed9da696a559cdfd50c5772eb50734bf5468ee730c",
    }


def test_official_benchmark_protocol_dry_run_is_text_free_and_zero_call() -> None:
    result = _validator_module().validate(require_private_evidence=False)
    assert result["benchmark_dry_run"] == {
        "esc_eval_cards": 655,
        "esc_judge_roles": 25,
        "esc_judge_units": 150,
        "api_calls": 0,
    }


def test_training_exam_overlap_freezes_a_contamination_aware_holdout() -> None:
    result = _validator_module().validate(require_private_evidence=False)
    assert result["esc_overlap"] == {
        "rows": 228,
        "clean_english_if_esconv_extes_sft": 103,
    }


def test_atomic_risk_design_gate_is_complete_but_human_qualification_remains_p1() -> None:
    result = _validator_module().validate(require_private_evidence=False)
    assert result["risk_instrument"] == {
        "packets": 18,
        "assignments": 36,
        "formal_replies_consumed": 0,
    }
    assert "atomic_risk_instrument_design" in result["p0_complete_gates"]
    module = _validator_module()
    qualification = module._load_json(
        module.AUTHORITY_DIR / "risk_instrument_qualification_v1.json"
    )
    assert qualification["public_identifier_contains_target_or_variant"] is False
    assert "HASH_COMMITMENT_ONLY" in qualification["gold_release_policy"]


def test_g0_qwen_screen_is_frozen_without_api_execution() -> None:
    result = _validator_module().validate(require_private_evidence=False)
    assert result["g0_generator_screen"] == {
        "cards": 24,
        "executor_packets": 16,
        "qwen_model": "qwen3.7-plus-2026-05-26",
        "qwen_paid_logical_calls": 152,
        "run_identity": "7a4d43f9049583d7151d0200f856ad04c8b2090f625171baa4b9868ecbd9de40",
    }


def test_generator_contract_uses_paper_dimensions_and_separate_guardrails() -> None:
    module = _validator_module()
    contract = module._load_json(
        module.AUTHORITY_DIR / "generator_qualification_measurement_contract_v1.json"
    )
    assert [row["paper_name"] for row in contract["primary_exam"]["official_reported_dimensions"]] == [
        "Fluency", "Expression", "Empathy", "Information", "Skill", "Humanoid", "Overall"
    ]
    assert "completion_rate" in contract["primary_exam"]["separate_project_metrics"]
