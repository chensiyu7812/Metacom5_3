import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_v5_3_formal_failure_is_preserved_and_v5_4_cannot_requalify_it():
    integrated = json.loads(
        (ROOT / "data/pm_v1_5_contracts/v5_3_integrated_evidence_execution_v1.json").read_text()
    )
    recovery = json.loads(
        (ROOT / "data/pm_v1_5_contracts/v5_4_semantic_contrast_learnability_recovery_v1.json").read_text()
    )
    assert integrated["status"] == "V5_3_FORMAL_HEADS_FAILED_FAIL_CLOSED"
    assert integrated["v5_3_formal_outcome_20260809"]["passed_heads"] == []
    assert set(integrated["v5_3_formal_outcome_20260809"]["failed_heads"]) == {
        "MP", "MS", "ME", "RS"
    }
    assert recovery["why_new_version_is_required"]["v5_3_is_not_requalified"] is True
    assert recovery["status"].endswith("NO_NEW_EFFECT_CALLS_AUTHORIZED")


def test_v5_4_requires_semantic_and_effect_feasibility_before_confirmation():
    recovery = json.loads(
        (ROOT / "data/pm_v1_5_contracts/v5_4_semantic_contrast_learnability_recovery_v1.json").read_text()
    )
    assert recovery["pre_effect_semantic_gate"]["gates"]["condition_macro_f1"] == ">=0.80 on family-held-out variants"
    assert recovery["development_effect_feasibility_gate"]["panel"].endswith("128 effect groups total")
    assert recovery["fresh_confirmation_freeze"]["only_after_both_pre_effect_and_feasibility_gates_pass"] is True
    assert "384 total" in recovery["fresh_confirmation_freeze"]["minimum"]
    assert recovery["fresh_confirmation_freeze"]["failed_head_action"].startswith("fail closed")


def test_failure_diagnosis_is_posthoc_and_does_not_claim_requalification():
    report = json.loads(
        (ROOT / "outputs/pm_v1_5_v5_3_formal_head_failure_diagnosis_20260809/report.json").read_text()
    )
    assert report["status"] == "OUTCOME_OPEN_POSTHOC_DIAGNOSIS_NOT_REQUALIFICATION"
    assert report["formal_conclusion_unchanged"] == "ALL_FOUR_V5_3_HEADS_FAILED_AND_FAIL_CLOSED"
    assert all(not row["formal_result"]["formal_head_pass"] for row in report["components"].values())
    assert report["api_calls"] == 0
