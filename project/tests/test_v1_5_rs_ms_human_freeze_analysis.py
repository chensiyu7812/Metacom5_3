import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "outputs/pm_v1_5_paper1_v3_rs_ms_pi_adjudicated_analysis_20260811/analysis.json"
FREEZE = ROOT / "outputs/pm_v1_5_paper1_v3_rs_ms_two_human_freeze_20260811"


def test_human_freeze_analysis_keeps_function_and_closure_responsibility_separate():
    report = json.loads(ANALYSIS.read_text(encoding="utf-8"))
    assert report["status"] == "PI_ADJUDICATED_HUMAN_B_ANALYSIS_COMPLETE_NO_INDEPENDENT_IAA"
    assert report["grain"] == {"states": 16, "connected_groups": 8, "learned_ms_on_states": 7}
    assert report["function"]["functional_any_reviewer_learned_on_7"] == 0
    assert report["function"]["learned_ms_on_7"] == {
        "HUMAN_A": {"NOT_USED_FINAL": 7},
        "HUMAN_B": {"NOT_USED_FINAL": 7},
    }
    assert report["closure_limitation"]["both_learned_ms_off"] is True
    assert report["closure_limitation"]["changes_incremental_ms_contrast"] is False
    assert report["decision"].startswith("MS_RS_SLICE_FAILS_VERIFIED_FUNCTION")
    assert report["pi_adjudicated_final"]["quality_learned_ms_on_7"] == {
        "MS_ON_BETTER": 5,
        "RS_ONLY_BETTER": 2,
    }
    assert report["pi_adjudicated_final"]["function_stratification"]["source_availability_rate"] == "8/16"
    assert report["pi_adjudicated_final"]["function_stratification"]["conditional_execution_success"] == "0/8"


def test_human_b_is_pi_final_and_human_a_is_sensitivity_not_independent_iaa():
    human_a = json.loads((FREEZE / "human_A_raw_frozen.json").read_text(encoding="utf-8"))
    human_b = json.loads((FREEZE / "human_B_raw_frozen.json").read_text(encoding="utf-8"))
    report = json.loads(ANALYSIS.read_text(encoding="utf-8"))

    assert "adjudication" not in human_a
    assert human_b["adjudication"]["adjudicated_by"] == "PI (study owner)"
    assert human_b["function_stratification"]["overall_realized_function"] == "0/16"
    assert report["review_validity"]["human_B_contains_PI_adjudication"] is True
    assert report["review_validity"]["independent_human_IAA_eligible"] is False
