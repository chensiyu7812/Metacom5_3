from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = (
    ROOT
    / "data"
    / "pm_v1_5_contracts"
    / "paper1_p1_public_source_group_manifest_candidate_v1.json"
)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_p1_candidate_is_content_addressed_but_cannot_self_authorize() -> None:
    manifest = _read(MANIFEST_PATH)
    binding = manifest["method_binding"]
    authority_path = ROOT / binding["parent_authority_path"]
    contract_path = ROOT / binding["active_contract_path"]
    authority = _read(authority_path)
    candidate_record = authority["validated_p1_design_candidate"]

    assert manifest["status"] == (
        "P1_DESIGN_CANDIDATE_NOT_EXECUTION_AUTHORITY"
    )
    assert binding["parent_authority_sha256"] == candidate_record[
        "validated_under_parent_authority_sha256"
    ]
    assert _sha256(MANIFEST_PATH) == candidate_record["sha256"]
    assert _sha256(contract_path) == binding["active_contract_sha256"]
    assert manifest["authorization"]["design_and_validation_only"] is True
    assert not any(
        manifest["authorization"][key]
        for key in (
            "public_state_materialization",
            "candidate_materialization",
            "suitability_or_safe_yield_annotation",
            "response_generation",
            "reviewer_or_generator_api_calls",
            "pm_training",
            "baseline_execution",
            "external_outcome_scoring",
            "paid_execution",
        )
    )


def test_public_source_roles_and_gold_boundaries_are_explicit() -> None:
    manifest = _read(MANIFEST_PATH)
    boundary = manifest["observability_boundary"]
    roles = manifest["dataset_roles"]

    assert "dialog[].annotation" in boundary["ESConv_runtime_forbidden"]
    assert "observed supporter response selected as target gold" in boundary[
        "ESConv_runtime_forbidden"
    ]
    assert "event_experience" in boundary["EvoEmo_runtime_forbidden"]
    assert "summary" in boundary["EvoEmo_runtime_forbidden"]
    assert "observation" in boundary["EvoEmo_runtime_forbidden"]
    assert "answer" in boundary["ES_MemEval_evaluator_only"]
    assert "evidence" in boundary["ES_MemEval_evaluator_only"]
    assert roles["ES_MemEval"]["response_pm_training_labels"] is False
    assert roles["ES_MemEval"]["pooled_with_response_outcomes"] is False


def test_shared_session_binds_split_without_merging_runtime_owner() -> None:
    manifest = _read(MANIFEST_PATH)
    grouping = manifest["canonical_identity_and_grouping"]["EvoEmo"]
    folds = manifest["frozen_outer_folds"]["folds"]
    p13_fold = next(row["fold"] for row in folds if "p13" in row["held_out_users"])
    p18_fold = next(row["fold"] for row in folds if "p18" in row["held_out_users"])

    assert grouping["shared_raw_session_owners"] == {
        "esc1198": ["p13", "p18"]
    }
    assert grouping["runtime_owner_key"] != grouping["split_group_key"]
    assert "private catalogs remain separate" in grouping[
        "shared_session_rule"
    ]
    assert p13_fold == p18_fold


def test_candidate_design_uses_raw_exact_spans_and_frozen_six_cards() -> None:
    manifest = _read(MANIFEST_PATH)
    design = manifest["candidate_construction_design"]

    assert "literal source turn" in design["MS_SESSION"]["materialization"]
    assert "literal within-turn action-result spans" in design[
        "ME_REUSABLE_OUTCOME"
    ]["materialization"]
    assert "event timeline" in design["ME_REUSABLE_OUTCOME"][
        "materialization"
    ]
    assert design["RS_ATOMIC_MOVE"]["card_count"] == 6
    bank_path = ROOT / design["RS_ATOMIC_MOVE"]["bank_path"]
    assert _sha256(bank_path) == design["RS_ATOMIC_MOVE"]["bank_sha256"]
    assert "never promote Rank-2" in design["common"]["actual_rank1"]


def test_p1_manifest_validator_passes_without_materializing_data(
    tmp_path: Path,
) -> None:
    output = tmp_path / "report.json"
    script = (
        ROOT
        / "scripts"
        / "v1_5"
        / "173l_validate_paper1_p1_public_source_group_manifest_v1_5.py"
    )
    subprocess.run(
        [sys.executable, str(script), "--output", str(output)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    report = _read(output)

    assert report["status"] == (
        "P1_MANIFEST_DESIGN_PASS_EXECUTION_STILL_NOT_AUTHORIZED"
    )
    assert report["failed_checks"] == []
    assert report["observed_counts"]["esconv_nonoverlap"] == {
        "train": 875,
        "validation": 172,
        "test": 169,
    }
    assert report["observed_counts"]["evoemo_composite_sessions"] == 401
    assert report["observed_counts"]["es_memeval_questions"] == 1427
    assert report["mutating_authorizations"] == {}
    assert report["api_calls"] == 0
    assert report["responses_generated"] == 0
    assert report["labels_created"] == 0
    assert report["pm_trained"] is False
    assert report["external_outcomes_read"] is False


def test_raw_candidate_support_audit_is_read_only_and_reproducible(
    tmp_path: Path,
) -> None:
    output = tmp_path / "support.json"
    script = (
        ROOT
        / "scripts"
        / "v1_5"
        / "174l_audit_paper1_public_raw_candidate_support_v1_5.py"
    )
    subprocess.run(
        [sys.executable, str(script), "--output", str(output)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    report = _read(output)

    assert report["status"] == (
        "RAW_SUPPORT_PRESENT_ACTUAL_RANK1_AND_LEARNABILITY_NOT_YET_ESTABLISHED"
    )
    assert report["evoemo"]["users"] == 18
    assert report["evoemo"]["seeker_turn_states"] == 4689
    assert report["evoemo"]["states_with_mp_source"] == 4689
    assert report["evoemo"]["ms_literal_items"] == 4564
    assert report["evoemo"]["states_with_strict_past_ms_source"] == 4442
    assert report["evoemo"]["me_literal_action_result_items"] == 24
    assert report["evoemo"]["users_with_me_literal_item"] == 15
    assert report["evoemo"]["states_with_strict_past_me_source"] == 1916
    assert report["esconv"]["nonoverlap_dialogues"] == {
        "train": 875,
        "validation": 172,
        "test": 169,
    }
    assert report["esconv"][
        "eligible_seeker_turn_states_with_later_supporter"
    ] == {"train": 13235, "validation": 2638, "test": 2468}
    assert report["api_calls"] == 0
    assert report["responses_generated"] == 0
    assert report["labels_created"] == 0
    assert report["pm_trained"] is False
    assert report["external_outcomes_read"] is False
