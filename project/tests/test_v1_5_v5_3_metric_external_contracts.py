from __future__ import annotations

import json
from pathlib import Path

from metacom_pm.contracts import ALL_ACTION_IDS
from metacom_pm.v1_5_v5_3_accountability import StagewiseAccountabilityRow
from metacom_pm.v1_5_v5_3_response_baselines import POLICIES


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "data" / "pm_v1_5_contracts"


def _load(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text())


def test_metric_contract_replaces_only_obsolete_binary_learning_gate() -> None:
    contract = _load("v5_3_metric_responsibility_and_oracle_v1.json")
    supersedes = contract["authority"]["supersedes"]

    assert contract["status"] == "FROZEN_BEFORE_FORMAL_EFFECT_AGGREGATION"
    assert supersedes["contract"] == "minimum_publishable_metric_registry_v1.json"
    assert "component learnability target" in supersedes["only_for"]
    assert contract["component_learning"]["target"].startswith("continuous")
    assert contract["component_learning"]["ties"] == "remain zero"
    assert contract["separate_axes"]["C"]["enters_component_training_target"] is False


def test_metric_axes_and_resolved_call_labels_stay_separate() -> None:
    contract = _load("v5_3_metric_responsibility_and_oracle_v1.json")
    axes = contract["separate_axes"]
    labels = contract["component_correct_call_labels"]["labels"]

    assert set(axes) == {"Q", "R", "F", "C", "D"}
    assert set(labels) == {"ON_ONLY", "OFF_ONLY", "EITHER", "UNRESOLVED"}
    assert "cost" in axes["Q"]["not_equal_to"]
    assert axes["F"]["not_a_positive_quality_label"] is True
    assert "executor" in labels["UNRESOLVED"] or "fallback" in labels["UNRESOLVED"]
    assert any("UNKNOWN equals OFF" == item for item in contract["component_correct_call_labels"]["prohibitions"])


def test_joint_oracle_is_the_real_sixteen_action_space() -> None:
    contract = _load("v5_3_metric_responsibility_and_oracle_v1.json")
    oracle = contract["joint_action_oracle"]

    assert oracle["actions"] == list(ALL_ACTION_IDS)
    assert len(oracle["actions"]) == 16
    assert "all 16 actions" in oracle["same_state_requirement"]
    assert "oracle_set_inclusion_accuracy" in oracle["primary_decision_metrics"]
    assert "quality_regret" in oracle["primary_decision_metrics"]
    assert "excess_deterministic_cost_on_quality_frontier" in oracle["primary_decision_metrics"]
    assert oracle["cost_utility"]["no_hidden_composite_score"] is True


def test_responsibility_contract_preserves_itt_and_mechanism_blame() -> None:
    contract = _load("v5_3_metric_responsibility_and_oracle_v1.json")
    responsibility = contract["stagewise_responsibility"]
    fields = set(responsibility["required_ledger_fields"])
    owners = set(responsibility["failure_owner_rules"])

    assert {"exact_rank1_id", "requested_action", "realized_action", "primary_failure_owner"} <= fields
    assert {
        "catalog_or_adapter",
        "retriever",
        "eligibility_or_semantic_interface",
        "pm",
        "step2_or_generator",
        "resource_generator_interaction",
        "measurement",
        "scope_or_ood",
    } == owners
    assert responsibility["two_views"]["both_must_be_reported"] is True

    schema_fields = set(StagewiseAccountabilityRow.model_json_schema()["properties"])
    assert {
        "domain", "outer_fold", "effect_group_id", "candidate_source_time",
        "candidate_present", "pm_component_scores", "component_oracle_label",
        "joint_oracle_action_ids",
    } <= schema_fields


def test_three_external_tracks_are_complementary_and_complete() -> None:
    contract = _load("v5_3_external_complementary_evidence_v1.json")
    experiments = contract["experiments"]

    assert set(experiments) == {
        "ESConv_response",
        "EvoEmo_longitudinal_response",
        "ES_MemEval_QA",
    }
    assert contract["complementary_evidence_rule"]["all_three_required_for_complete_paper1_execution"] is True
    assert "all 169 official test dialogues" in experiments["ESConv_response"]["data"]
    assert experiments["ESConv_response"]["resource_mask"]["MP"] == "unavailable"
    assert "all 18 users" in experiments["EvoEmo_longitudinal_response"]["data"]
    assert "1,427" in experiments["ES_MemEval_QA"]["data"]
    assert len(experiments["ES_MemEval_QA"]["capabilities"]) == 5


def test_external_qa_gold_is_evaluator_only_and_response_is_not_appended() -> None:
    contract = _load("v5_3_external_complementary_evidence_v1.json")
    qa = contract["experiments"]["ES_MemEval_QA"]
    whole_response = contract["whole_response_generation_gate"]

    assert {"answer", "evidence", "capability"} <= set(qa["evaluator_only"])
    assert qa["generator_visible"] == [
        "question",
        "condition-authorized same-user history or typed candidates",
    ]
    assert "primary_response plus locked_clauses" in whole_response["forbidden"]
    assert "post-hoc concatenation of retrieved text" in whole_response["forbidden"]


def test_same_stack_rule_distinguishes_policy_and_representation_comparisons() -> None:
    contract = _load("v5_3_external_complementary_evidence_v1.json")
    stack = contract["shared_response_stack"]

    assert stack["only_policy_bits_may_change"] is True
    assert stack["rs_bank_shared_between_esconv_and_evoemo"] is True
    assert stack["two_domain_specific_pms_forbidden"] is True
    assert "representation baselines" in stack["task_specific_retrieval_boundary"]
    assert contract["leakage_and_shortcut_gates"]["external_outcomes_may_not_change_v5_3"] is True


def test_baseline_contract_matches_planner_and_scopes_old_results() -> None:
    contract = _load("v5_3_baseline_matrix_v1.json")
    response_ids = [row["id"] for row in contract["response_core"]["conditions"]]

    assert response_ids == list(POLICIES)
    assert contract["matched_controls"]["cost_matched_fixed"]["minimum_states_per_stratum"] == 12
    random_qualification = contract["matched_controls"]["cost_and_on_rate_matched_random"]["qualification"]
    assert any("25 percent" in rule for rule in random_qualification)
    assert "V5.2 locked-clause append responses" in contract["reuse_decision"]["historical_only_unless_exact_current_stack_replay"]
    assert contract["domain_matrix"]["ES_MemEval_QA"]["main"] == [
        "no_memory",
        "full_history",
        "official_session_rag_top4",
        "typed_memory_fixed_high",
        "typed_memory_learned_pm_qualified",
    ]
