from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "data/pm_v1_5_contracts/v5_3_complete_training_data_generation_v2.json"
WAVE1 = ROOT / "data/pm_v1_5_contracts/v5_3_wave1_sentinel_assignments_v1.json"


def test_v2_separates_planning_counts_from_scientific_acceptance() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["formal_longitudinal_users"] == 80
    assert contract["population_target_not_power_guarantee"] is True
    assert contract["current_state_planning_targets"]["counts_are_capacity_targets_not_scientific_pass_gates"] is True
    assert contract["formal_paired_effect_subset"]["v1_effect_states_total_1088_is_not_a_hard_gate"] is True
    assert contract["formal_paired_effect_subset"]["quality_risk_function_and_cost_remain_separate_targets"] is True


def test_v2_interactions_are_within_state_full_factorial() -> None:
    interaction = json.loads(CONTRACT.read_text(encoding="utf-8"))["interaction_factorial"]
    assert interaction["coherent_four_candidate_state_target_range"] == [32, 48]
    assert interaction["each_qualified_state_runs_all_16_actions"] is True
    assert interaction["same_context_candidates_and_seed_within_state"] is True
    assert interaction["state_action_confounding_allowed"] is False


def test_v2_shortcut_and_rank1_rules_do_not_chase_semantic_rates() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["actual_rank1_distribution"]["query_or_source_rewrite_to_hit_a_rate_allowed"] is False
    assert contract["shortcut_and_identifiability_audit"]["raw_semantic_text_predicting_semantic_condition_is_not_a_shortcut_failure"] is True
    assert contract["shortcut_and_identifiability_audit"]["all_available_feature_columns_may_not_be_added_automatically"] is True


def test_wave1_has_thirteen_unique_cross_domain_assignments() -> None:
    value = json.loads(WAVE1.read_text(encoding="utf-8"))
    rows = value["rows"]
    assert len(rows) == 13
    assert len({row["user_id"] for row in rows}) == 13
    assert {row["content_author"] for row in rows} == {"chatgpt_pro", "claude"}
    assert len({row["primary_superdomain"] for row in rows}) == 7
    assert all(row["session_count"] in {13, 15} for row in rows)
