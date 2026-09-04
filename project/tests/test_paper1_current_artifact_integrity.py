import hashlib
import json
from pathlib import Path

import yaml


PROJECT = Path(__file__).resolve().parents[1]
AUTHORITY = PROJECT / "data" / "paper1_authority"


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_current_public_1427_identity_is_hash_bound_and_text_free():
    identity = _json(AUTHORITY / "es_memeval_public_v1_0_0_1427_identity_decision_v1.json")
    manifest = AUTHORITY / "es_memeval_public_v1_0_0_1427_row_identity_v1.jsonl"
    rows = _jsonl(manifest)
    assert identity["primary_task_name"] == "ES-MemEval-Public-v1.0.0-1427"
    assert identity["formal_paper_boundary"]["paper_qa"] == 1209
    assert identity["formal_paper_boundary"]["public_qa"] == 1427
    assert len(rows) == len({row["row_id"] for row in rows}) == 1427
    assert all("question" not in row and "answer" not in row for row in rows)
    assert _sha(manifest) == identity["identity_manifest"]["sha256"]
    assert _sha(PROJECT / "data/external/evo_emo.json") == identity["source"]["sha256"]


def test_current_esc_overlap_slices_are_hash_bound_and_outcome_blind():
    summary = _json(AUTHORITY / "esc_eval_english331_source_overlap_summary_v1.json")
    manifest = AUTHORITY / "esc_eval_english331_source_overlap_v1.jsonl"
    rows = _jsonl(manifest)
    assert len(rows) == 331
    assert sum(row["analysis_slice"] == "primary_non_esconv_transfer" for row in rows) == 173
    assert sum(row["analysis_slice"] == "esconv_source_overlap" for row in rows) == 158
    assert summary["contains_outcomes"] is False
    assert _sha(manifest) == summary["manifest_sha256"]


def test_current_rs_canonical_top8_artifacts_are_hash_bound_and_complete():
    report = _json(PROJECT / "data/paper1_public_rs/esconv_rs_canonical_bge_top8_report_v1.json")
    catalog = PROJECT / "data/paper1_public_rs/esconv_rs_exact_canonical_treatments_v1.jsonl"
    top8 = PROJECT / "data/paper1_public_rs/esconv_rs_canonical_bge_top8_v1.jsonl"
    assert report["counts"] == {
        "raw_atomic_units": 15061,
        "exact_canonical_treatments": 13172,
        "exact_alias_instances_beyond_first": 1889,
        "decision_states": 11883,
    }
    assert _sha(catalog) == report["identities"]["canonical_catalog_sha256"]
    assert _sha(top8) == report["identities"]["canonical_top8_sha256"]
    for k in (1, 2, 3, 4, 6, 8):
        cell = report["k_surface"][str(k)]
        assert cell["coverage"] == 1.0
        assert cell["truncation_rate_common_cap384"] == 0.0
    assert report["compute"]["outcome_calls"] == 0
    assert report["compute"]["Generator_calls"] == 0


def test_current_config_does_not_list_completed_freezes_as_pending():
    config = yaml.safe_load((PROJECT / "configs/paper1_public_only.yaml").read_text())
    pending = set(config["pending_zero_outcome_freeze"])
    assert "active_multi_view_extractor_runtime_and_401_artifact" not in pending
    assert "task_specific_material_better_and_equivalence_rules" not in pending
    assert "exact_feature_schema" in pending
    assert "generator_step2_runtime_manifest" in pending


def test_teacher_reference_denominators_are_exact_before_rating():
    design = _json(
        AUTHORITY / "paper1_pairwise_teacher_human_reference_design_20260904_v1.json"
    )
    units = design["measurement_units"]
    allocation = design["task_allocation"]
    assert units["base_semantic_pairs"] == 80
    assert units["reversed_pair_presentations"] == 16
    assert units["total_blinded_pair_presentations"] == 96
    assert units["independent_primary_raters"] == 2
    assert units["primary_rater_pair_judgements"] == 192
    assert sum(row["base_semantic_pairs"] for row in allocation.values()) == 80
    assert sum(row["reversed_presentations"] for row in allocation.values()) == 16
    assert sum(row["total_presentations"] for row in allocation.values()) == 96
    dg_design = design["dg_matched_scenario_design"]
    assert dg_design["scenario_clusters"] == 9
    assert dg_design["heads_per_scenario"] == ["MP", "ME", "MS"]
    assert dg_design["new_paid_seeker_calls_executed"] == 8
    assert dg_design["authorization_ceiling_usd"] == 0.11
    assert dg_design["paid_calls_authorized"] is True
    assert dg_design["settled_seeker_cost_usd"] == 0.10133
    assert dg_design["analysis_must_cluster_by_scenario"] is True
    identity = design["identity_and_blinding"]
    assert identity["base_pair_identity_manifest"] == (
        "paper1_pairwise_teacher_base_pair_preflight_20260904_v1.jsonl"
    )
    assert identity["base_pair_identity_manifest_sha256"] == _sha(
        AUTHORITY / identity["base_pair_identity_manifest"]
    )
    assert identity["presentation_plan_sha256"] == _sha(
        AUTHORITY / identity["presentation_plan"]
    )
    assert identity["blind_key_sha256"] == _sha(AUTHORITY / identity["blind_key"])
    assert set(design["locks"].values()) == {"CLOSED"}


def test_teacher_preflight_and_gemini_identity_are_zero_outcome_and_exact():
    preflight = _json(AUTHORITY / "paper1_pairwise_teacher_preflight_20260904_v1.json")
    base_rows = _jsonl(
        AUTHORITY / "paper1_pairwise_teacher_base_pair_preflight_20260904_v1.jsonl"
    )
    gemini = _json(AUTHORITY / "paper1_gemini_pairwise_teacher_identity_20260904_v1.json")
    assert preflight["base_semantic_pairs"] == 80
    assert preflight["base_by_task"] == {"DG": 27, "ESC": 27, "QA": 13, "Summary": 13}
    assert preflight["presentations"] == 96
    assert preflight["reverse_presentations"] == 16
    assert preflight["dg_scenario_clusters"] == 9
    assert preflight["dg_existing_first_turn_seeker_success_reused"] == 1
    assert preflight["dg_first_turn_seeker_calls_pending"] == 8
    dg_budget = preflight["dg_first_turn_seeker_budget"]
    assert dg_budget["physical_attempts_per_logical_turn"] == 1
    assert dg_budget["estimated_input_tokens"] == 39640
    assert dg_budget["maximum_output_tokens"] == 480
    assert dg_budget["worst_case_estimated_usd"] == 0.1039
    assert dg_budget["authorization_ceiling_usd"] == 0.11
    assert dg_budget["paid_calls_authorized"] is False
    assert len(dg_budget["calls"]) == 8
    assert preflight["local_generator_outputs_pending"] == 142
    assert preflight["paid_api_calls"] == preflight["formal_outcome_calls"] == 0
    assert gemini["model"]["request_model"] == "gemini-2.5-flash-lite"
    assert gemini["model"]["models_get_version"] == "001"
    assert gemini["generation"]["temperature"] == 0
    assert gemini["generation"]["thinking_config"]["thinkingBudget"] == 0
    assert gemini["budget"]["teacher_qualification_hard_cap_usd"] == 0.1
    assert gemini["budget"]["paid_calls_authorized_by_this_identity"] is False
    assert set(gemini["locks"].values()) == {"CLOSED"}

    dg_rows = [row for row in base_rows if row["task"] == "DG"]
    dg_by_target = {}
    for row in dg_rows:
        dg_by_target.setdefault(row["target_id"], []).append(row)
    assert len(dg_by_target) == 9
    assert all(len(rows) == 3 for rows in dg_by_target.values())
    assert all({row["head"] for row in rows} == {"MP", "ME", "MS"} for rows in dg_by_target.values())
    assert all({row["qualification_probe_k"] for row in rows} == {1, 2, 4} for rows in dg_by_target.values())
    assert all(
        len({row["dg_seeker_request"]["request_messages_sha256"] for row in rows}) == 1
        for rows in dg_by_target.values()
    )
    assert sum(
        all(row["dg_seeker_request"]["existing_success_reused"] for row in rows)
        for rows in dg_by_target.values()
    ) == 1


def test_teacher_reference_generation_is_hash_bound_complete_and_still_pre_outcome():
    plan = _json(AUTHORITY / "paper1_pairwise_teacher_qualification_plan_v2.json")
    authorization = _json(
        AUTHORITY
        / "paper1_pairwise_teacher_dg_first_turn_authorization_20260904_v1.json"
    )
    dg_result_path = (
        AUTHORITY / "paper1_pairwise_teacher_dg_first_turn_result_20260904_v1.json"
    )
    dg_result = _json(dg_result_path)
    binding_path = (
        AUTHORITY
        / "paper1_pairwise_teacher_generator_request_binding_20260904_v1.json"
    )
    binding = _json(binding_path)
    local_result_path = (
        AUTHORITY
        / "paper1_pairwise_teacher_local_generation_result_20260904_v1.json"
    )
    local_result = _json(local_result_path)
    sheet_manifest = _json(
        AUTHORITY / "paper1_pairwise_teacher_human_sheet_manifest_20260904_v1.json"
    )
    design = _json(
        AUTHORITY / "paper1_pairwise_teacher_human_reference_design_20260904_v1.json"
    )

    grant = authorization["researcher_authorization"]
    assert grant["authorized_usd"] == 0.11
    assert grant["authorized_new_physical_calls"] == 8
    assert grant["authorized_model"] == "gpt-4o-2024-11-20"
    assert grant["retries_in_this_authorization"] == 0
    assert grant["gemini_calls_authorized"] == 0
    assert dg_result["authorization"]["sha256"] == _sha(
        AUTHORITY
        / "paper1_pairwise_teacher_dg_first_turn_authorization_20260904_v1.json"
    )
    assert dg_result["execution"]["new_calls_succeeded"] == 8
    assert dg_result["execution"]["new_calls_failed"] == 0
    assert dg_result["execution"]["finish_reason_counts"] == {"stop": 8}
    assert dg_result["execution"]["tracked_response_text_retained"] is False
    assert dg_result["budget"]["actual_prompt_tokens"] == 39648
    assert dg_result["budget"]["actual_completion_tokens"] == 221
    assert dg_result["budget"]["settled_new_call_cost_usd"] == "0.1013300"
    assert dg_result["formal_outcome_calls"] == dg_result["evaluator_calls"] == 0
    assert dg_result["pm_training_runs"] == 0

    assert binding["source"]["dg_first_turn_result_sha256"] == _sha(dg_result_path)
    assert binding["counts"] == {
        "base_pairs": 80,
        "unique_generator_requests": 142,
        "by_task": {"DG": 36, "ESC": 54, "QA": 26, "Summary": 26},
        "dg_scenario_clusters": 9,
        "dg_shared_off_requests": 9,
        "dg_head_specific_on_requests": 27,
    }
    assert len(binding["request_identities"]) == 142
    assert len({row["request_id"] for row in binding["request_identities"]}) == 142
    assert binding["embedding_identity"]["query_count"] == 9
    assert binding["selection_read_response_quality"] is False

    assert local_result["request_binding_sha256"] == _sha(binding_path)
    health = local_result["local_health"]
    assert health["gpu"] == "NVIDIA RTX A6000"
    assert health["model"] == "meta/llama-3.1-8b-instruct"
    assert local_result["execution"]["unique_requests"] == 142
    assert local_result["execution"]["new_calls_this_run"] == 142
    assert local_result["execution"]["terminal_empty_outputs"] == 0
    assert local_result["execution"]["tracked_response_text_retained"] is False
    pairs = local_result["base_pair_response_map"]
    assert len(pairs) == len({row["base_pair_id"] for row in pairs}) == 80
    assert all(set(row) == {"base_pair_id", "OFF", "ON"} for row in pairs)

    assert sheet_manifest["source_sha256"]["local_generation_result"] == _sha(
        local_result_path
    )
    assert set(sheet_manifest["sheets"]) == {"RATER_A", "RATER_B"}
    assert all(
        sheet["presentations"] == 96
        for sheet in sheet_manifest["sheets"].values()
    )
    assert sheet_manifest["primary_judgements_after_completion"] == 192
    assert sheet_manifest["blinding"]["on_off_hidden"] is True
    assert sheet_manifest["blinding"]["head_and_k_hidden"] is True
    assert design["identity_and_blinding"]["rater_A_sheet_hash"] == (
        sheet_manifest["sheets"]["RATER_A"]["sha256"]
    )
    assert design["identity_and_blinding"]["rater_B_sheet_hash"] == (
        sheet_manifest["sheets"]["RATER_B"]["sha256"]
    )
    assert plan["human_sheet_manifest_authority"] == (
        "paper1_pairwise_teacher_human_sheet_manifest_20260904_v1.json"
    )
    assert plan["reference_generation"] == {
        "dg_first_turn_paid_calls": 8,
        "dg_first_turn_settled_cost_usd": 0.10133,
        "local_generator_calls": 142,
        "local_generator_api_cost_usd": 0,
        "human_sheets_ready": True,
        "human_ratings_observed": 0,
    }
    assert plan["candidate_teacher_paid_calls"] == 0
    for artifact in (dg_result, binding, local_result, sheet_manifest):
        assert set(artifact["locks"].values()) == {"CLOSED"}


def test_teacher_human_instrument_teaches_material_equivalence_and_blinding():
    instrument = _json(
        AUTHORITY / "paper1_pairwise_teacher_human_instrument_20260904_v1.json"
    )
    assert instrument["not_a_pass_gate"] is True
    assert set(instrument["task_rubrics"]) == {"ESC", "QA", "Summary", "DG"}
    assert set(instrument["verdicts"]) == {
        "A_better",
        "B_better",
        "equivalent",
        "uncertain",
    }
    common = " ".join(instrument["common_instruction"])
    assert "more empathy" in common
    assert "not by itself an advantage" in common
    assert instrument["blinding"]["on_off_hidden"] is True
    assert instrument["blinding"]["resource_bundle_hidden_from_effect_judge"] is True
    assert instrument["rating_design"]["presentations_per_primary_rater"] == 96
    assert instrument["rating_design"]["primary_judgements"] == 192


def test_mistral_formal_schedule_is_balanced_and_still_pre_outcome():
    schedule = _json(
        AUTHORITY / "paper1_official_mistral24b_formal_schedule_contract_20260904_v1.json"
    )
    algorithm = schedule["schedule_algorithm"]
    assert schedule["official_scorer"]["temperature"] == "official_provider_default_omitted"
    assert schedule["execution"]["concurrency"] == 8
    assert schedule["execution"]["server_seed"] == 0
    assert schedule["execution"]["server_command_must_pass_explicit_seed"] is True
    assert schedule["execution"]["pilot_server_seed_was_explicitly_bound"] is False
    assert len(algorithm["canonical_arms"]) == 6
    assert algorithm["one_arm_complete_before_next_arm"] == "FORBIDDEN"
    assert algorithm["all_six_arms_contiguous_per_matched_unit"] is True
    assert algorithm["evaluator_prompt_contains_arm_identity"] is False
    assert algorithm["final_request_manifest_sha256"].startswith("PENDING")
    assert schedule["interpretation"]["guarantees_per_item_determinism"] is False
    assert set(schedule["locks"].values()) == {"CLOSED"}


def test_active_generator_binding_keeps_v3_as_unopened_provenance_only():
    binding = _json(
        AUTHORITY / "paper1_active_generator_selection_binding_20260904_v1.json"
    )
    assert binding["selection"]["model"] == "meta/llama-3.1-8b-instruct"
    assert binding["selection"]["pm_effect_generation_authorized"] is True
    assert binding["archived_provenance"]["routine_ci_reopens_archived_files"] is False
    assert binding["active_runtime"]["authority_sha256"] == _sha(
        AUTHORITY / "paper1_generator_backend_retirement_local_amendment_20260903_v1.json"
    )
    assert set(binding["locks"].values()) == {"CLOSED"}
