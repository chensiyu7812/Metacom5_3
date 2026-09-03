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

from metacom_pm.paper1.execution import STEP2_RESOURCE_PROTOCOL, VISIBLE_STATE_PROTOCOL
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config
from metacom_pm.paper1.core.threshold import THRESHOLD_PROTOCOL


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
        and configured_threshold["protocol"] == THRESHOLD_PROTOCOL
        and configured_threshold["primary_latency_percentile"] == 0.95
        and configured_threshold["latency_measurement_protocol"]
        == "paper1-client-latency-measurement-v2"
        and configured_threshold["catastrophic_client_completion_ceiling_ms"] == 60000
        and configured_threshold["tighter_deployment_scenario"] is None
        and configured_threshold["tighter_sla_required_for_paper_primary"] is False
        and 0.5 in configured_threshold["probability_grid"]
        and configured_threshold["include_eligible_always_on"] is True
        and configured_threshold["include_always_off"] is True
    )

    contract_names = (
        "paper1_training_evaluation_alignment_contract_v1.json",
        "paper1_pairwise_effect_oracle_contract_v1.json",
        "paper1_pairwise_teacher_qualification_plan_v1.json",
        "paper1_task_effect_coding_v1.json",
        "paper1_decision_correctness_evaluation_v1.json",
        "paper1_end_to_end_latency_policy_contract_v1.json",
        "paper1_client_latency_measurement_contract_v2.json",
        "paper1_natural_turn_appropriateness_rubric_v1.json",
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
        and contracts["paper1_client_latency_measurement_contract_v2.json"]["primary"][
            "primary_cost_outcome"
        ]
        == "p95 client_send_to_final_visible_text_ms"
        and contracts["paper1_client_latency_measurement_contract_v2.json"][
            "cross_machine_absolute_timestamp_subtraction"
        ]
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
    checks["paper1_visible_state_contract_ready"] = (
        VISIBLE_STATE_PROTOCOL == "pm-paper1-visible-state-projection-v1"
    )
    checks["paper1_step2_delivery_contract_ready"] = (
        STEP2_RESOURCE_PROTOCOL == "pm-paper1-typed-step2-resource-envelope-v1"
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
