import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_amendment_is_scoped_and_both_outcome_locks_are_closed():
    doc = _load(
        "data/paper1_authority/"
        "paper1_resource_amount_and_evaluator_calibration_amendment_20260820_v1.json"
    )
    assert doc["unchanged_core_research"]["heads"] == ["RS", "MP", "MS", "ME"]
    assert doc["unchanged_core_research"]["primary_policy_threshold"] == 0.5
    assert doc["outcome_locks"]["CALIBRATION_OUTCOME_LOCK"]["current_status"] == "CLOSED"
    assert doc["outcome_locks"]["CONFIRMATORY_OUTCOME_LOCK"]["current_status"] == "CLOSED"
    assert doc["current_activity"]["formal_outcome_calls"] == 0
    assert doc["current_activity"]["pm_training_runs"] == 0
    threshold = _load(
        "data/paper1_authority/"
        "paper1_threshold_policy_calibration_amendment_20260831_v1.json"
    )
    assert "fixed-0.5-primary-policy" in threshold["precedence"]
    assert threshold["scoped_override"]["fixed_point_five_new_role"].startswith(
        "mandatory_transparent_reference"
    )


def test_rs_surface_uses_exact_aliases_and_never_adds_a_step2_filter():
    doc = _load("data/paper1_public_rs/esconv_rs_resource_amount_surface_20260820_v1.json")
    assert doc["catalog"]["raw_atomic_move_units"] == 15061
    assert doc["catalog"]["exact_canonical_treatments"] == 13172
    assert doc["catalog"]["near_duplicate_policy"] == "REPORT_ONLY_NO_SEMANTIC_THRESHOLD_DELETION"
    assert [cell["requested_k"] for cell in doc["cells"]] == [0, 1, 2, 3, 4]
    protocol = doc["pure_k_calibration_protocol"]
    assert protocol["initial_k_values"] == [0, 1, 2, 3, 4]
    assert protocol["fixed_nonbinding_generator_input_token_cap"] == 384
    assert all(row["states_truncated"] == 0 for row in protocol["zero_outcome_truncation"].values())
    assert "k={6,8}" in protocol["expansion_rule"]
    assert protocol["step2_utility_filter"] == "FORBIDDEN"
    assert doc["outcome_calls"] == 0


def test_memory_surface_reports_current_counts_and_blocks_unfrozen_dg_query():
    doc = _load(
        "data/paper1_public_memory/"
        "es_memeval_typed_memory_resource_amount_surface_20260820_v1.json"
    )
    assert {
        head: doc["current_local_counts"][head]["unique_candidates"]
        for head in ("MP", "MS", "ME")
    } == {"MP": 378, "MS": 1411, "ME": 80}
    assert doc["old_remote_artifact_check"]["matches_current_local"] is False
    assert doc["task_surfaces"]["dialogue_generation"]["selection_surface"] is None
    assert "IMPLEMENTATION_BLOCKER" in doc["task_surfaces"]["dialogue_generation"]["status"]
    assert doc["outcome_calls"] == 0


def test_esc_split_scenarios_are_disjoint_complete_and_outcome_blind():
    doc = _load("data/paper1_authority/paper1_esc_split_feasibility_20260820_v1.json")
    assert doc["rules"]["outcomes_read"] is False
    assert doc["rules"]["ratio_selected"] is False
    for scenario in doc["scenarios"].values():
        rows = scenario["assignments"]
        assert len(rows) == 173
        assert len({row["card_key"] for row in rows}) == 173
        assert {row["split"] for row in rows} == {"calibration", "confirmatory"}
        assert sum(row["split"] == "calibration" for row in rows) == scenario["calibration_cards"]


def test_evaluator_and_fold_plans_fail_closed_without_seed_or_judge_shopping():
    evaluator = _load(
        "data/paper1_authority/paper1_esc_evaluator_qualification_plan_20260820_v1.json"
    )
    folds = _load("data/paper1_authority/paper1_rq2_fold_feasibility_20260820_v1.json")
    assert evaluator["official_asset_audit"]["raw_item_level_human_validation_labels_found"] is False
    runtime = evaluator["official_esc_rank_runtime_feasibility"]
    assert runtime["reference_role"].startswith("official ESC-RANK")
    assert runtime["actual_initialization_test"]["gpu_process_or_allocation_observed"] is False
    assert ">=24 GiB" in runtime["decision"]
    assert evaluator["human_label_feasibility"]["status"] == "NOT_AN_ESC_EVALUATION_BLOCKER"
    assert evaluator["candidate_set"]["qwen_status"].startswith("PROXY_ONLY")
    assert evaluator["candidate_set"]["no_silent_selection"] is True
    assert "Ours" in evaluator["comparison"]["forbidden_selection_basis"]
    primary = folds["requested_primary_structure"]
    assert (primary["n_outer_folds"], primary["seed"]) == (5, 0)
    assert [row["target_count"] for row in primary["folds"]] == [317, 317, 317, 317, 318]
    assert folds["rules"]["seed_shopping"] == "FORBIDDEN"


def test_budget_is_only_a_planning_envelope_and_authorizes_nothing():
    doc = _load(
        "data/paper1_authority/paper1_expected_api_gpu_call_budget_20260820_v1.json"
    )
    assert doc["status"] == "PLANNING_ENVELOPE_NOT_AUTHORIZATION"
    assert doc["current_round_actual"]["paid_api_calls"] == 0
    assert doc["price_policy"]["usd_hard_cap"] is None
    assert doc["locks"] == {
        "CALIBRATION_OUTCOME_LOCK": "CLOSED",
        "CONFIRMATORY_OUTCOME_LOCK": "CLOSED",
    }


def test_precalibration_memory_audit_separates_structural_pass_from_semantic_failure():
    doc = _load(
        "data/paper1_authority/"
        "paper1_precalibration_memory_candidate_audit_20260820_v1.json"
    )
    assert doc["hard_isolation_proof"]["complete_ordered_sessions_replayed"] == 401
    assert doc["hard_isolation_proof"]["source_sha256_matches"] == 401
    assert doc["hard_isolation_proof"]["prior_memory_table_sha256_matches"] == 401
    assert doc["hard_isolation_proof"]["forbidden_projection_key_hits"] == []
    assert set(doc["hard_isolation_proof"]["read_counts"].values()) == {0}
    assert doc["decision"] == {
        "structural_lineage": "PASS",
        "semantic_candidate_catalog": "NO_GO_FOR_CALIBRATION_AS_CURRENTLY_MATERIALIZED",
        "reason": doc["decision"]["reason"],
    }
    assert doc["fixed_seed_stratified_examples"]["MP"]["verdict_counts"]["FAIL"] > 0
    assert doc["fixed_seed_stratified_examples"]["ME"]["verdict_counts"]["FAIL"] > 0
    assert doc["outcome_calls"] == 0
