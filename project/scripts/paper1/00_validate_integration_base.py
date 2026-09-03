#!/usr/bin/env python3
"""Validate the serial Paper-1 integration base without opening outcomes."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


PROJECT = Path(__file__).resolve().parents[2]
REPO = PROJECT.parent
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.paper1.execution import (
    PACKING_PROTOCOL,
    RQ2_PROMPT_PROTOCOL,
    STEP2_RESOURCE_PROTOCOL,
    VISIBLE_STATE_PROTOCOL,
)
from metacom_pm.paper1.execution.rq2_prompts import (
    DG_SUPPORTER_SYSTEM_PROMPT_TEMPLATE,
    QA_SYSTEM_PROMPT,
    SUMMARY_SYSTEM_PROMPT,
)
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config
from metacom_pm.paper1.core.threshold import THRESHOLD_PROTOCOL
from metacom_pm.paper1.api_budget import (
    PAPER1_API_HARD_CAP_USD,
    PAPER1_KNOWN_V9_COST_USD,
    PAPER1_OPTIONAL_STOP_USD,
    PAPER1_RETRY_RESERVE_USD,
)
from metacom_pm.paper1.multi_view_memory import MULTI_VIEW_MEMORY_SCHEMA_VERSION
from metacom_pm.paper1.multi_view_memory.runtime import MULTI_VIEW_COMPILER_VERSION
from metacom_pm.paper1.semantic_memory import HISTORICAL_ONLY


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate() -> dict[str, Any]:
    checks: dict[str, bool] = {}
    config_path = PROJECT / "configs" / "paper1_public_only.yaml"
    config = load_public_only_config(config_path)
    assert_pre_outcome_locked(config)
    checks["outcome_lock"] = True

    reconciliation = _load(PROJECT / "data" / "paper1_authority" / "paper1_execution_reconciliation_20260816_v1.json")
    checks["highest_precedence_reconciliation"] = (
        reconciliation["status"] == "ACTIVE_HIGHEST_PRECEDENCE_PRE_OUTCOME_OVERRIDE"
        and reconciliation["learning_route"]["cost_in_label_or_loss"] is False
        and reconciliation["repeated_effect"]["qualification_pass_gate"] is False
        and reconciliation["formal_evidence"]["binary_paper_pass_fail_forbidden"] is True
    )
    threshold_policy_base = _load(
        PROJECT
        / "data"
        / "paper1_authority"
        / "paper1_threshold_policy_calibration_amendment_20260831_v1.json"
    )
    latency_policy = _load(
        PROJECT
        / "data"
        / "paper1_authority"
        / "paper1_latency_constrained_selective_policy_amendment_20260903_v1.json"
    )
    client_latency_policy = _load(
        PROJECT
        / "data"
        / "paper1_authority"
        / "paper1_client_observed_latency_and_frontier_amendment_20260903_v2.json"
    )
    v2_1 = _load(
        PROJECT
        / "data"
        / "paper1_authority"
        / "paper1_v2_1_consistency_amendment_20260903_v1.json"
    )
    binary_scope_budget = _load(
        PROJECT
        / "data"
        / "paper1_authority"
        / "paper1_binary_benefit_scope_and_api_budget_amendment_20260903_v1.json"
    )
    configured_threshold = config["learning"]["primary_operating_point"]
    checks["latency_constrained_policy_scoped_override"] = (
        threshold_policy_base["status"]
        == "ACTIVE_RESEARCHER_AUTHORIZED_SCOPED_AMENDMENT_PRE_OUTCOME"
        and threshold_policy_base["preserved_research"]["cost_in_label_or_loss"] is False
        and threshold_policy_base["isolation"]["confirmatory_outcome_selection"] == "FORBIDDEN"
        and threshold_policy_base["isolation"]["held_out_outer_target_outcome_selection"]
        == "FORBIDDEN"
        and latency_policy["status"]
        == "ACTIVE_RESEARCHER_AUTHORIZED_SCOPED_PRE_OUTCOME_AMENDMENT"
        and latency_policy["estimands"]["cost_in_quality_effect_label_or_loss"] is False
        and latency_policy["estimands"]["latency_in_deployment_action"] is True
        and set(latency_policy["locks"].values()) == {"CLOSED"}
        and client_latency_policy["status"]
        == "ACTIVE_RESEARCHER_AUTHORIZED_SCOPED_PRE_OUTCOME_AMENDMENT"
        and client_latency_policy["primary_metrics"]["cost_outcome"]
        == "p95_client_send_to_final_visible_text_ms"
        and client_latency_policy["primary_metrics"]["experience_guardrail"]
        == "p95_client_send_to_first_visible_text_ms"
        and client_latency_policy["paper_primary_selection"]["order"][0]
        == "catastrophic_p95_client_completion_below_60000ms"
        and client_latency_policy["paper_primary_selection"][
            "tighter_sla_required_for_paper_primary"
        ]
        is False
        and set(client_latency_policy["locks"].values()) == {"CLOSED"}
        and v2_1["status"] == "ACTIVE_PRE_OUTCOME_CONSISTENCY_REPAIR"
        and v2_1["threshold"]["protocol"] == THRESHOLD_PROTOCOL
        and set(v2_1["locks"].values()) == {"CLOSED"}
        and configured_threshold["protocol"] == THRESHOLD_PROTOCOL
        and configured_threshold["primary_latency_percentile"] == 0.95
        and configured_threshold["latency_measurement_protocol"]
        == "paper1-client-latency-measurement-v3"
        and configured_threshold["catastrophic_client_completion_ceiling_ms"] == 60000
        and configured_threshold["tighter_deployment_scenario"] is None
        and configured_threshold["tighter_sla_required_for_paper_primary"] is False
        and 0.5 in configured_threshold["probability_grid"]
        and configured_threshold["include_eligible_always_on"] is True
        and configured_threshold["include_always_off"] is True
    )
    stage_caps = binary_scope_budget["api_budget"]["stage_caps"]
    checks["binary_benefit_scope_and_api_hard_cap"] = (
        binary_scope_budget["status"]
        == "ACTIVE_RESEARCHER_AUTHORIZED_SCOPED_PRE_OUTCOME_AMENDMENT"
        and binary_scope_budget["paper1_scope"]["prediction_target"]
        == "probability_of_task_defined_material_positive_effect"
        and binary_scope_budget["paper1_scope"][
            "threshold_calibration_does_not_create_magnitude_model"
        ]
        is True
        and binary_scope_budget["secondary_magnitude_analysis"][
            "new_api_calls_authorized"
        ]
        is False
        and binary_scope_budget["secondary_magnitude_analysis"]["reporting_grain"]
        == "task_by_head_only"
        and binary_scope_budget["secondary_magnitude_analysis"][
            "cross_task_delta_Q_composite"
        ]
        == "FORBIDDEN"
        and binary_scope_budget["api_budget"]["absolute_hard_cap"]
        == float(PAPER1_API_HARD_CAP_USD)
        and binary_scope_budget["api_budget"]["optional_stop_threshold"]
        == float(PAPER1_OPTIONAL_STOP_USD)
        and binary_scope_budget["api_budget"]["minimum_retry_reserve"]
        == float(PAPER1_RETRY_RESERVE_USD)
        and binary_scope_budget["api_budget"]["known_v9_actual"]
        == float(PAPER1_KNOWN_V9_COST_USD)
        and round(sum(stage_caps.values()), 2)
        == binary_scope_budget["api_budget"]["stage_caps_total"]
        and set(binary_scope_budget["locks"].values()) == {"CLOSED"}
    )

    contract_names = (
        "paper1_training_evaluation_alignment_contract_v1.json",
        "paper1_pairwise_effect_oracle_contract_v1.json",
        "paper1_pairwise_teacher_qualification_plan_v1.json",
        "paper1_task_effect_coding_v1.json",
        "paper1_decision_correctness_evaluation_v1.json",
        "paper1_end_to_end_latency_policy_contract_v1.json",
        "paper1_client_latency_measurement_contract_v3.json",
        "paper1_natural_turn_appropriateness_rubric_v1.json",
        "paper1_binary_benefit_scope_and_api_budget_amendment_20260903_v1.json",
    )
    contracts = {
        name: _load(PROJECT / "data" / "paper1_authority" / name)
        for name in contract_names
    }
    checks["effect_action_latency_contracts_present_pre_outcome"] = (
        all(contract["status"].startswith("ACTIVE") for contract in contracts.values())
        and all(
            contract.get("formal_outcome_calls", 0) == 0
            for contract in contracts.values()
        )
        and contracts["paper1_task_effect_coding_v1.json"]["common"][
            "current_unweighted_exact_difference_pareto_rule"
        ]
        == "SUPERSEDED"
        and contracts["paper1_client_latency_measurement_contract_v3.json"]["primary"][
            "primary_cost_outcome"
        ]
        == "p95 client_send_to_final_visible_text_ms"
        and contracts["paper1_client_latency_measurement_contract_v3.json"][
            "cross_machine_absolute_timestamp_subtraction"
        ]
        == "FORBIDDEN"
        and contracts["paper1_client_latency_measurement_contract_v3.json"][
            "successful_fallback"
        ]["artificial_60000ms_floor"]
        == "FORBIDDEN"
        and contracts["paper1_natural_turn_appropriateness_rubric_v1.json"][
            "decoded_r0_m0_sufficiency"
        ].startswith("after arm decoding")
    )

    authority = PROJECT / "data" / "v3_authority"
    preflight = _load(authority / "rq0_llama31_8b_esc_eval_exact_preflight_v1.json")
    score_preflight = _load(authority / "rq0_llama31_8b_esc_eval_exact_score_preflight_v1.json")
    generation = _load(authority / "rq0_llama31_8b_esc_eval_exact_generation_closeout_v1.json")
    qualification = _load(authority / "rq0_llama31_8b_esc_eval_exact_qualification_v1.json")
    checks["rq0_selected_generator"] = (
        qualification["status"] == "RQ0_COMPLETE_LLAMA31_8B_FROZEN_FOR_PM_EFFECT_GENERATION"
        and qualification["candidate"]["model"] == "meta/llama-3.1-8b-instruct"
        and qualification["decision"]["pm_effect_generation_authorized"] is True
    )
    checks["rq0_complete_shape"] = (
        generation["complete_dialogues"] == 331
        and generation["successful_turns"] == 1655
        and qualification["scoring_integrity"]["dimension_calls"] == 2317
    )
    checks["rq0_contract_hash"] = _sha(authority / "rq0_llama31_8b_esc_eval_exact_contract_v1.json") == preflight["input_hashes"]["rq0_llama31_8b_esc_eval_exact_contract_v1.json"]
    checks["rq0_runner_hash"] = _sha(PROJECT / "scripts" / "v3" / "46_run_rq0_llama31_8b_esc_eval_exact.py") == preflight["input_hashes"]["46_run_rq0_llama31_8b_esc_eval_exact.py"]
    checks["rq0_scorer_hash"] = _sha(PROJECT / "scripts" / "v3" / "48_score_rq0_llama31_8b_esc_eval_exact.py") == score_preflight["measurement"]["scorer_sha256"]
    checks["rq0_evidence_hashes_reconciled"] = (
        qualification["evidence_hashes"]["generation_ledger_sha256"] == generation["evidence_hashes"]["private_turn_ledger_sha256"]
        and qualification["evidence_hashes"]["official_result_sha256"] == score_preflight["result_sha256"]
        and qualification["evidence_hashes"]["score_ledger_sha256"] == "d6d51b97d902c642e3b0f0f46a5d572ee12577bbac2287cf3ac60afaface7e4b"
    )
    checks["private_ledgers_not_committed"] = not any(PROJECT.rglob("private_*_ledger.jsonl"))
    dependency_closure = _load(authority / "rq0_llama31_8b_integration_dependency_closure_v1.json")
    checks["rq0_transitive_dependency_disclosure"] = all(
        _sha(PROJECT.parent / path) == expected
        for path, expected in dependency_closure["exactly_ported_dependencies"].items()
    ) and (
        _sha(PROJECT / "src/metacom_pm/api.py")
        == dependency_closure["historical_runtime_dependency_not_bound_by_preflight"][
            "origin_main_integration_base_sha256"
        ]
    )

    identity = _load(authority / "es_memeval_public_v1_0_0_1427_identity_decision_v1.json")
    evo = PROJECT / "data" / "external" / "evo_emo.json"
    row_manifest = authority / "es_memeval_public_v1_0_0_1427_row_identity_v1.jsonl"
    rows = _jsonl(row_manifest)
    checks["es_memeval_artifact_hash"] = _sha(evo) == identity["source"]["sha256"]
    checks["es_memeval_1427_identity"] = (
        len(rows) == 1427
        and len({row["row_id"] for row in rows}) == 1427
        and _sha(row_manifest) == identity["identity_manifest"]["sha256"]
        and identity["formal_paper_boundary"]["paper_qa"] == 1209
        and identity["formal_paper_boundary"]["public_qa"] == 1427
    )
    checks["es_memeval_identity_is_text_free"] = all(
        "question" not in row and "answer" not in row for row in rows
    )

    overlap_summary = _load(PROJECT / "data" / "paper1_authority" / "esc_eval_english331_source_overlap_summary_v1.json")
    overlap_path = PROJECT / "data" / "paper1_authority" / "esc_eval_english331_source_overlap_v1.jsonl"
    overlap = _jsonl(overlap_path)
    checks["esc_eval_overlap_identity"] = (
        len(overlap) == 331
        and _sha(overlap_path) == overlap_summary["manifest_sha256"]
        and sum(row["analysis_slice"] == "primary_non_esconv_transfer" for row in overlap) == 173
        and sum(row["analysis_slice"] == "esconv_source_overlap" for row in overlap) == 158
    )

    active_source = PROJECT / "src" / "metacom_pm" / "paper1"
    active_text = "\n".join(path.read_text(encoding="utf-8") for path in active_source.rglob("*.py"))
    forbidden_tokens = (
        "MP_" + "PREFERENCE",
        "background_" + "MP_on",
        "background_" + "MS_on",
        "background_" + "ME_on",
        "background_" + "RS_on",
        "Cost" + "WorthIt",
    )
    checks["active_namespace_forbidden_tokens_absent"] = not any(token in active_text for token in forbidden_tokens)
    checks["active_namespace_legacy_prompt_imports_absent"] = not any(
        token in active_text
        for token in (
            "from metacom_pm.prompts import",
            "from ..prompts import",
            "v1_5_strategy_rag_runtime",
        )
    )
    multi_view_config = config["memory_ontology"]
    checks["active_multi_view_ontology"] = (
        MULTI_VIEW_MEMORY_SCHEMA_VERSION == "paper1-multi-view-memory-schema-v1"
        and HISTORICAL_ONLY is True
        and multi_view_config["MP"] == "target_time_current_stable_profile_slots"
        and multi_view_config["ME"] == "strict_past_atomic_event_experience_timeline"
        and multi_view_config["MS"] == "one_complete_strict_past_raw_session_transcript"
        and multi_view_config["action_observed_outcome"] == "ME_subtype"
    )
    multi_view_manifest = _load(
        PROJECT
        / "data"
        / "paper1_authority"
        / "paper1_multi_view_401_call_manifest_preflight_20260903_v8.json"
    )
    checks["active_multi_view_401_zero_outcome_preflight"] = (
        multi_view_manifest["status"]
        == "PASS_ZERO_OUTCOME_ROLLING_BUDGET_PREFLIGHT"
        and multi_view_manifest["compiler_version"] == MULTI_VIEW_COMPILER_VERSION
        and multi_view_manifest["source"]["sessions"] == 401
        and multi_view_manifest["source"]["turns"] == 9368
        and multi_view_manifest["budget"]["maximum_provider_calls"] == 802
        and float(multi_view_manifest["budget"]["maximum_single_call_reservation_usd"])
        <= float(multi_view_manifest["budget"]["stage_hard_cap_usd"])
        and multi_view_manifest["budget"]["rolling_hard_cap_may_stop_before_401"]
        and multi_view_manifest["method_boundary"]["formal_outcomes_read"] == 0
        and multi_view_manifest["method_boundary"]["paid_api_calls"] == 0
    )
    multi_view_authorization_path = (
        PROJECT
        / "data"
        / "paper1_authority"
        / "paper1_multi_view_401_live_authorization_20260903_v9.json"
    )
    multi_view_authorization = _load(multi_view_authorization_path)
    checks["active_multi_view_401_live_authorization"] = (
        multi_view_authorization["status"]
        == "RESEARCHER_AUTHORIZED_ZERO_OUTCOME_COMPILATION"
        and multi_view_authorization["maximum_sessions"] == 401
        and multi_view_authorization["maximum_provider_calls"] == 802
        and multi_view_authorization["stage_hard_cap_usd"] == "1.42149913"
        and multi_view_authorization["cumulative_paper1_hard_cap_usd"] == "50.00"
        and float(multi_view_authorization["historical_settled_cost_usd"])
        + float(multi_view_authorization["maximum_single_call_reservation_usd"])
        <= float(multi_view_authorization["researcher_authorized_total_usd"])
        and multi_view_authorization["config_sha256"]
        == _sha(PROJECT / "configs" / "paper1_multi_view_compiler_v7.yaml")
        and multi_view_authorization["source_sha256"]
        == _sha(
            PROJECT
            / "data"
            / "paper1_public_memory"
            / "es_memeval_public_sanitized_runtime_artifact_v1.json"
        )
        and multi_view_authorization["manifest_summary_sha256"]
        == _sha(
            PROJECT
            / "data"
            / "paper1_authority"
            / "paper1_multi_view_401_call_manifest_preflight_20260903_v8.json"
        )
        and multi_view_authorization["runner_sha256"]
        == _sha(PROJECT / "scripts" / "paper1" / "40_run_multi_view_401_compiler.py")
        and multi_view_authorization["runtime_sha256"]
        == _sha(PROJECT / "src" / "metacom_pm" / "paper1" / "multi_view_memory" / "runtime.py")
        and multi_view_authorization["batch_sha256"]
        == _sha(PROJECT / "src" / "metacom_pm" / "paper1" / "multi_view_memory" / "batch.py")
        and set(multi_view_authorization["locks"].values()) == {"CLOSED"}
        and multi_view_authorization["formal_outcome_calls"] == 0
        and multi_view_authorization["pm_training_runs"] == 0
    )
    multi_view_closeout = _load(
        PROJECT
        / "data"
        / "paper1_authority"
        / "paper1_multi_view_401_closeout_20260903_v1.json"
    )
    checks["active_multi_view_401_closeout"] = (
        multi_view_closeout["status"] == "COMPLETE_CENSUS_PASS"
        and multi_view_closeout["coverage"]["owners"] == 18
        and multi_view_closeout["coverage"]["sessions"] == 401
        and multi_view_closeout["attempts"]["logical_calls"] == 802
        and multi_view_closeout["attempts"]["successful_terminal_attempts"] == 802
        and multi_view_closeout["attempts"]["exhausted_failed_calls"] == 0
        and float(multi_view_closeout["budget_usd"]["compiler_stage_all_versions_cost"])
        <= float(multi_view_closeout["budget_usd"]["compiler_stage_authorized_cap"])
        and multi_view_closeout["method_boundary"]["formal_outcome_calls"] == 0
        and multi_view_closeout["method_boundary"]["pm_training_runs"] == 0
    )
    multi_view_census_path = (
        PROJECT
        / "data"
        / "paper1_public_memory"
        / "es_memeval_public_multi_view_candidate_census_summary_v1.json"
    )
    multi_view_census = _load(multi_view_census_path)
    promoted_multi_view_results = (
        PROJECT
        / "data"
        / "paper1_public_memory"
        / multi_view_census["source"]["promoted_session_results_filename"]
    )
    candidate_pool = (
        PROJECT
        / "data"
        / "paper1_public_memory"
        / multi_view_census["artifacts"]["candidate_pool"]["filename"]
    )
    target_head_census = (
        PROJECT
        / "data"
        / "paper1_public_memory"
        / multi_view_census["artifacts"]["target_head_census"]["filename"]
    )
    checks["active_multi_view_target_candidate_census"] = (
        multi_view_census["status"]
        == "ZERO_OUTCOME_MULTI_VIEW_CANDIDATE_CENSUS_COMPLETE"
        and multi_view_census["population"]["targets"] == 1586
        and multi_view_census["eligible_pool"]["MP"]["candidates"] == 388
        and multi_view_census["eligible_pool"]["MS"]["candidates"] == 401
        and multi_view_census["eligible_pool"]["ME"]["candidates"] == 1523
        and multi_view_census["source"]["promoted_session_results_sha256"]
        == _sha(promoted_multi_view_results)
        == multi_view_closeout["identity"]["session_results_sha256"]
        and multi_view_census["artifacts"]["candidate_pool"]["sha256"]
        == _sha(candidate_pool)
        and multi_view_census["artifacts"]["target_head_census"]["sha256"]
        == _sha(target_head_census)
        and all(
            multi_view_census["target_coverage"]["per_head"][head][
                "targets_with_candidates"
            ]
            == 1586
            for head in ("MP", "MS", "ME")
        )
        and multi_view_census["source_lineage_census"]["candidate_ids_unique"]
        and multi_view_census["source_lineage_census"]["all_owner_bound"]
        and multi_view_census["source_lineage_census"]["all_strict_past"]
        and multi_view_census["source_lineage_census"]["all_content_hashes_match"]
        and multi_view_census["method_boundary"]["formal_outcome_calls"] == 0
        and multi_view_census["method_boundary"]["pm_training_runs"] == 0
        and multi_view_census["method_boundary"]["paid_api_calls"] == 0
        and multi_view_census["method_boundary"]["top_k_or_final_bundle_selected"]
        is False
    )
    checks["paper1_visible_state_contract_ready"] = (
        VISIBLE_STATE_PROTOCOL == "pm-paper1-visible-state-projection-v1"
    )
    checks["paper1_step2_delivery_contract_ready"] = (
        STEP2_RESOURCE_PROTOCOL == "pm-paper1-typed-step2-resource-envelope-v2"
    )
    multi_view_bge_packing = _load(
        PROJECT
        / "data"
        / "paper1_authority"
        / "paper1_active_multi_view_bge_packing_binding_20260903_v1.json"
    )
    checks["active_multi_view_bge_packing_authority_selected"] = (
        config["authority"]["multi_view_bge_packing_prompt"]
        == "project/data/paper1_authority/"
        "paper1_active_multi_view_bge_packing_binding_20260903_v1.json"
    )
    top8_path = PROJECT / multi_view_bge_packing["artifacts"]["static_top8"]["path"]
    amount_surface_path = (
        PROJECT / multi_view_bge_packing["artifacts"]["amount_surface"]["path"]
    )
    amount_build_report_path = (
        PROJECT / multi_view_bge_packing["artifacts"]["build_report"]["path"]
    )
    top8_rows = _jsonl(top8_path)
    amount_surface = _load(amount_surface_path)
    amount_build_report = _load(amount_build_report_path)
    checks["active_multi_view_bge_and_packing_surface"] = (
        multi_view_bge_packing["status"]
        == "ACTIVE_ZERO_OUTCOME_RETRIEVAL_PACKING_PROMPT_BINDING_NO_K_OR_FINAL_CAP_SELECTED"
        and multi_view_bge_packing["packing_binding"]["protocol"]
        == PACKING_PROTOCOL
        and multi_view_bge_packing["step2_binding"]["protocol"]
        == STEP2_RESOURCE_PROTOCOL
        and len(top8_rows)
        == multi_view_bge_packing["artifacts"]["static_top8"]["rows"]
        == 4656
        and all(
            row["contains_query_or_candidate_text"] is False
            and row["formal_outcome_calls"] == 0
            and row["task_type"] in {"qa", "summary"}
            and len(row["ranked_candidates"])
            == min(8, row["eligible_candidate_count"])
            and 0 < len(row["ranked_candidates"]) <= 8
            for row in top8_rows
        )
        and _sha(top8_path)
        == multi_view_bge_packing["artifacts"]["static_top8"]["sha256"]
        and _sha(amount_surface_path)
        == multi_view_bge_packing["artifacts"]["amount_surface"]["sha256"]
        and _sha(amount_build_report_path)
        == multi_view_bge_packing["artifacts"]["build_report"]["sha256"]
        and amount_surface["status"]
        == "ZERO_OUTCOME_SURFACE_READY_NOT_A_K_OR_FINAL_CAP_FREEZE"
        and amount_surface["packing"]["protocol"] == PACKING_PROTOCOL
        and amount_surface["packing"]["step2_protocol"]
        == STEP2_RESOURCE_PROTOCOL
        and amount_surface["packing"]["final_k_selected"] is False
        and amount_surface["packing"]["final_resource_token_cap_selected"]
        is False
        and amount_surface["method_boundary"]["formal_outcome_calls"] == 0
        and amount_surface["method_boundary"]["paid_api_calls"] == 0
        and amount_surface["method_boundary"]["pm_training_runs"] == 0
        and amount_build_report["top8_sha256"] == _sha(top8_path)
        and amount_build_report["surface_sha256"] == _sha(amount_surface_path)
        and multi_view_bge_packing["rq2_generator_prompt_binding"]["protocol"]
        == RQ2_PROMPT_PROTOCOL
        and multi_view_bge_packing["rq2_generator_prompt_binding"][
            "implementation"
        ]["sha256"]
        == _sha(PROJECT / "src/metacom_pm/paper1/execution/rq2_prompts.py")
        and multi_view_bge_packing["rq2_generator_prompt_binding"][
            "official_base_prompt_sha256"
        ]["QA"]
        == hashlib.sha256(QA_SYSTEM_PROMPT.encode("utf-8")).hexdigest()
        and multi_view_bge_packing["rq2_generator_prompt_binding"][
            "official_base_prompt_sha256"
        ]["Summary"]
        == hashlib.sha256(SUMMARY_SYSTEM_PROMPT.encode("utf-8")).hexdigest()
        and multi_view_bge_packing["rq2_generator_prompt_binding"][
            "official_base_prompt_sha256"
        ]["DG_supporter_template_with_display_name_placeholder"]
        == hashlib.sha256(
            DG_SUPPORTER_SYSTEM_PROMPT_TEMPLATE.encode("utf-8")
        ).hexdigest()
        and set(multi_view_bge_packing["research_integrity"]["locks"].values())
        == {"CLOSED"}
    )
    natural_summary = _load(
        PROJECT
        / "data/paper1_public_memory/paper1_natural_turn_sample_proposal_summary_v1.json"
    )
    natural_base_path = (
        PROJECT
        / "data/paper1_public_memory"
        / natural_summary["artifacts"]["base_sample"]["filename"]
    )
    natural_review_path = (
        PROJECT
        / "data/paper1_public_memory"
        / natural_summary["artifacts"]["review_slot_plan"]["filename"]
    )
    natural_base = _jsonl(natural_base_path)
    natural_review = _jsonl(natural_review_path)
    checks["natural_turn_zero_outcome_sample_proposal"] = (
        natural_summary["status"]
        == "ZERO_OUTCOME_SAMPLE_PROPOSAL_READY_RESEARCHER_REVIEW_REQUIRED"
        and len(natural_base)
        == natural_summary["artifacts"]["base_sample"]["rows"]
        == 80
        and len(natural_review)
        == natural_summary["artifacts"]["review_slot_plan"]["rows"]
        == 96
        and natural_summary["reverse_duplicates"] == 16
        and _sha(natural_base_path)
        == natural_summary["artifacts"]["base_sample"]["sha256"]
        and _sha(natural_review_path)
        == natural_summary["artifacts"]["review_slot_plan"]["sha256"]
        and all(row["target_supporter_response_included"] is False for row in natural_base)
        and all(row["effect_or_capability_outcome_read"] is False for row in natural_base)
        and all(row["paid_api_calls"] == 0 for row in natural_base)
        and all(
            row["response_A"] is None
            and row["response_B"] is None
            and row["verdict"] is None
            for row in natural_review
        )
        and natural_summary["boundaries"]["sample_size_is_final"] is False
        and natural_summary["boundaries"]["paid_machine_judging_authorized"]
        is False
    )

    failed = [name for name, passed in checks.items() if not passed]
    return {
        "protocol": "pm-paper1-integration-base-validation-v1",
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
        "outcome_calls": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = validate()
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
