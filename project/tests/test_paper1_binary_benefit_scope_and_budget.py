import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "data"
    / "paper1_authority"
    / "paper1_binary_benefit_scope_and_api_budget_amendment_20260903_v1.json"
)


def _load():
    return json.loads(CONTRACT.read_text(encoding="utf-8"))


def test_paper1_claim_is_binary_benefit_not_request_level_utility():
    doc = _load()
    assert doc["status"] == "ACTIVE_RESEARCHER_AUTHORIZED_SCOPED_PRE_OUTCOME_AMENDMENT"
    assert doc["paper1_scope"]["prediction_target"] == (
        "probability_of_task_defined_material_positive_effect"
    )
    assert doc["paper1_scope"]["threshold_calibration_does_not_create_magnitude_model"] is True
    assert "request-level expected quality gain" in doc["paper1_claim"]["not_claimed"]
    assert "sequential policy learning or reinforcement learning" in doc["paper1_claim"]["future_work"]


def test_magnitude_diagnostics_are_oof_local_task_specific_and_call_free():
    analysis = _load()["secondary_magnitude_analysis"]
    assert analysis["new_api_calls_authorized"] is False
    assert analysis["reporting_grain"] == "task_by_head_only"
    assert analysis["cross_task_delta_Q_composite"] == "FORBIDDEN"
    assert analysis["probability_bins"]["predictions"] == "grouped_OOF_or_sealed_held_out_only"
    assert analysis["probability_bins"]["in_sample_predictions"] == "FORBIDDEN"
    assert analysis["benefit_capture"]["denominator_zero"] == "NA"
    companions = set(analysis["benefit_capture"]["required_companions"])
    assert {"realized_ON_rate", "harmful_open_rate", "false_open_harm"} <= companions
    assert analysis["local_regret"]["global_policy_regret_claim"] == "FORBIDDEN"


def test_cumulative_paid_api_budget_has_a_true_hard_stop():
    budget = _load()["api_budget"]
    assert budget["absolute_hard_cap"] == 50.0
    assert budget["expected_total_range"] == [25.0, 35.0]
    assert budget["known_v9_actual"] == 0.0307993
    assert round(sum(budget["stage_caps"].values()), 2) == 48.63
    assert budget["optional_stop_threshold"] == 43.0
    assert budget["minimum_retry_reserve"] == 5.0
    assert budget["successful_prompt_hash_rebilling"] == "FORBIDDEN"
    assert budget["maximum_parser_or_transport_retry_per_call"] == 1


def test_teacher_is_residual_gemini_with_claude_substitute_only():
    doc = _load()["paid_teacher_policy"]
    assert doc["human_reference_total_pairs_including_reverse_duplicates"] == 96
    assert doc["default_paid_candidate"].startswith("Gemini_Flash_Lite")
    assert doc["claude_and_gemini_full_sample_additive_run"] == "FORBIDDEN"
    assert doc["candidate_selection_by_ON_label_rate_or_PM_result"] == "FORBIDDEN"


def test_amendment_is_highest_scoped_authority_and_locks_stay_closed():
    agents = (ROOT.parent / "AGENTS.md").read_text(encoding="utf-8")
    new = agents.index("PM_PAPER1_BINARY_BENEFIT_SCOPE_AND_API_BUDGET_AMENDMENT_20260903_ZH.md")
    prior = agents.index("PM_PAPER1_V2_1_CONSISTENCY_AMENDMENT_20260903_ZH.md")
    assert new < prior
    assert "USD 50 hard cap" in agents
    assert set(_load()["locks"].values()) == {"CLOSED"}
