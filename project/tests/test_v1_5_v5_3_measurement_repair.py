from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from metacom_pm.v1_5_v5_3_measurement_repair import (
    CandidateTruth,
    FinalExecutionTruth,
    GuardTruth,
    OpportunityTruth,
    RawExecutionTruth,
    ResponsibilityOwner,
    derive_execution_truth,
    opportunity_from_quality,
    primary_mechanism_owner,
    semantic_value_label_eligible,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT / "data/pm_v1_5_contracts/v5_3_measurement_accountability_repair_v1.json"
)
DERIVATIVE = ROOT / "outputs/pm_v1_5_v5_3_formal_accountability_derivative_20260810"
CALIBRATION = ROOT / "outputs/pm_v1_5_v5_3_dual_reviewer_calibration_20260810"


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_fallback_cannot_be_functional_and_missing_raw_stays_unresolved() -> None:
    final, raw, guard = derive_execution_truth(
        on_status="fell_back_to_m0", raw_first_pass_saved=False
    )
    assert final is FinalExecutionTruth.NOT_USED_FINAL
    assert raw is RawExecutionTruth.UNRESOLVED_RAW_MISSING
    assert guard is GuardTruth.UNRESOLVED_RAW_MISSING


def test_positive_quality_alone_never_becomes_on_gold() -> None:
    eligible = semantic_value_label_eligible(
        candidate_truth=CandidateTruth.VALID_APPLICABLE,
        final_execution_truth=FinalExecutionTruth.PENDING_SEMANTIC_REVIEW,
        risk_resolved_safe=True,
    )
    assert not eligible
    assert opportunity_from_quality(q_uplift=0.9, eligible=eligible) is OpportunityTruth.UNRESOLVED


def test_resolved_safe_functional_effect_uses_frozen_margin() -> None:
    eligible = semantic_value_label_eligible(
        candidate_truth=CandidateTruth.VALID_APPLICABLE,
        final_execution_truth=FinalExecutionTruth.FUNCTIONAL,
        risk_resolved_safe=True,
    )
    assert opportunity_from_quality(q_uplift=0.11, eligible=eligible) is OpportunityTruth.ON_ONLY
    assert opportunity_from_quality(q_uplift=-0.11, eligible=eligible) is OpportunityTruth.OFF_ONLY
    assert opportunity_from_quality(q_uplift=0.10, eligible=eligible) is OpportunityTruth.EITHER


def test_pm_blame_requires_resolved_pre_action_oracle() -> None:
    unresolved = primary_mechanism_owner(
        candidate_truth=CandidateTruth.VALID_APPLICABLE,
        opportunity_truth=OpportunityTruth.UNRESOLVED,
        requested_on=False,
        final_execution_truth=FinalExecutionTruth.PENDING_SEMANTIC_REVIEW,
        guard_truth=GuardTruth.PENDING_SEMANTIC_REVIEW,
    )
    resolved = primary_mechanism_owner(
        candidate_truth=CandidateTruth.VALID_APPLICABLE,
        opportunity_truth=OpportunityTruth.ON_ONLY,
        requested_on=False,
        final_execution_truth=FinalExecutionTruth.PENDING_SEMANTIC_REVIEW,
        guard_truth=GuardTruth.PENDING_SEMANTIC_REVIEW,
    )
    assert unresolved is ResponsibilityOwner.UNRESOLVED
    assert resolved is ResponsibilityOwner.PM_STEP1


def test_contract_keeps_all_16_actions_and_caps_memory_capacity() -> None:
    contract = json.loads(CONTRACT.read_text())
    assert len(contract["action_and_oracle"]["actions"]) == 16
    assert len(set(contract["action_and_oracle"]["actions"])) == 16
    assert contract["small_sample_capacity"]["maximum_effective_free_parameters_per_memory_head"] == 3
    assert contract["current_stop_rules"]["new_paid_paired_effect_generation"] is False
    assert contract["current_stop_rules"]["new_pm_training"] is False


def test_full_derivative_accounts_for_every_group_and_repairs_fallback() -> None:
    report = json.loads((DERIVATIVE / "report.json").read_text())
    groups = _jsonl(DERIVATIVE / "group_accountability.jsonl")
    replicates = _jsonl(DERIVATIVE / "replicate_accountability.jsonl")
    assert report["groups"] == len(groups) == 576
    assert report["replicates"] == len(replicates) == 1728
    fallback = [row for row in replicates if row["on_final_status"] == "fell_back_to_m0"]
    assert len(fallback) == 70
    assert all(row["final_execution_truth"] == "NOT_USED_FINAL" for row in fallback)
    assert all(row["semantic_value_label_eligible"] is False for row in replicates)
    assert report["hard_findings"]["all_risk_labels_unresolved"] is True


def test_calibration_packet_is_balanced_and_does_not_expose_private_identity() -> None:
    manifest = json.loads((CALIBRATION / "manifest.json").read_text())
    packet = _jsonl(CALIBRATION / "review_packet_blind.jsonl")
    reviewer_a = _jsonl(CALIBRATION / "reviewer_A_template_blank.jsonl")
    reviewer_b = _jsonl(CALIBRATION / "reviewer_B_template_blank.jsonl")
    assert manifest["groups"] == len(packet) == 64
    assert Counter(row["component"] for row in packet) == {
        "MP": 16,
        "MS": 16,
        "ME": 16,
        "RS": 16,
    }
    assert all("effect_group_id" not in row for row in packet)
    assert all(row["candidate_truth"] == "" for row in reviewer_a + reviewer_b)
    assert {row["calibration_id"] for row in reviewer_a} == {
        row["calibration_id"] for row in packet
    }
