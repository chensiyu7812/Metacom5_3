#!/usr/bin/env python3
"""Freeze the zero-API Wave-1 staged generation method, endpoints, and budget."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.config import endpoint_from_config, load_config  # noqa: E402
from metacom_pm.io import canonical_json, read_json, sha256_file, sha256_text, write_json  # noqa: E402


CONFIG = ROOT / "configs/experiment.yaml"
CONTRACT = ROOT / "data/pm_v1_5_contracts/v5_3_complete_training_data_generation_v2.json"
ASSIGNMENTS = ROOT / "data/pm_v1_5_contracts/v5_3_wave1_sentinel_assignments_v1.json"
VALIDATOR = ROOT / "scripts/v1_5/82l_validate_formal_longitudinal_user_v1_5.py"
RUNNER = ROOT / "scripts/v1_5/92l_run_v5_3_wave1_api_generation_v1_5.py"
GENERATION_MODULE = ROOT / "src/metacom_pm/v1_5_v5_3_wave1_generation.py"
OUT = ROOT / "outputs/pm_v1_5_v5_3_wave1_api_generation_preflight_v1"


def build_contract() -> dict[str, object]:
    config = load_config(CONFIG)
    assignments = read_json(ASSIGNMENTS)["rows"]
    if len(assignments) != 13:
        raise RuntimeError("Wave 1 assignment count drift")
    endpoints = {
        "chatgpt_pro": endpoint_from_config(config, "final_judge"),
        "claude": endpoint_from_config(config, "final_judge_claude"),
    }
    endpoint_rows = {
        author: {
            "operational_endpoint_key": "final_judge" if author == "chatgpt_pro" else "final_judge_claude",
            "model": endpoint.model,
            "base_url": endpoint.base_url,
            "family": endpoint.family,
            "transport": endpoint.transport,
            "api_key_env_name_only": endpoint.api_key_env,
            "content_author_label_is_family_provenance_not_claim_of_exact_web_ui_model": True,
        }
        for author, endpoint in endpoints.items()
    }
    # Each user: one compact world/chronology plan plus three session chunks.
    # The final canonical user is assembled deterministically and then passed
    # through the existing V2 validator; no fifth free-form repair is hidden.
    stage_shape = [
        {"stage": "world_chronology_plan", "max_output_tokens": 6000},
        {"stage": "session_chunk_1", "max_output_tokens": 8000},
        {"stage": "session_chunk_2", "max_output_tokens": 8000},
        {"stage": "session_chunk_3", "max_output_tokens": 12000},
    ]
    logical_calls = len(assignments) * len(stage_shape)
    maximum_physical_calls = logical_calls
    # Conservative bound: every physical call may consume 12k input tokens.
    input_cap_per_call = 12000
    prices = {
        "chatgpt_pro": {"input": 2.50, "output": 10.00},
        "claude": {"input": 3.00, "output": 15.00},
    }
    max_cost = 0.0
    per_author = {}
    for author in ("chatgpt_pro", "claude"):
        users = sum(row["content_author"] == author for row in assignments)
        one_attempt_input = users * len(stage_shape) * input_cap_per_call
        one_attempt_output = users * sum(row["max_output_tokens"] for row in stage_shape)
        physical_multiplier = 1
        cost = physical_multiplier * (
            one_attempt_input / 1_000_000 * prices[author]["input"]
            + one_attempt_output / 1_000_000 * prices[author]["output"]
        )
        per_author[author] = {
            "users": users,
            "logical_calls": users * len(stage_shape),
            "maximum_input_tokens": one_attempt_input * physical_multiplier,
            "maximum_output_tokens": one_attempt_output * physical_multiplier,
            "maximum_proxy_cost_usd": round(cost, 6),
        }
        max_cost += cost
    binding = {
        "protocol": "pm-v1.5-v5.3-wave1-api-generation-preflight-v1",
        "contract_sha256": sha256_file(CONTRACT),
        "assignments_sha256": sha256_file(ASSIGNMENTS),
        "validator_sha256": sha256_file(VALIDATOR),
        "runner_sha256": sha256_file(RUNNER),
        "generation_module_sha256": sha256_file(GENERATION_MODULE),
        "config_sha256": sha256_file(CONFIG),
        "endpoints": endpoint_rows,
        "pricing_usd_per_mtok": prices,
        "assignments": assignments,
        "stage_shape": stage_shape,
        "logical_calls": logical_calls,
        "maximum_physical_calls": maximum_physical_calls,
        "transport_attempts_per_logical_call": 1,
        "retry_scope": "no_retry_in_primary_identity_separate_continuation_if_needed",
        "sampling": {"temperature": 0.2, "seed": None},
        "input_token_ceiling_per_physical_call": input_cap_per_call,
        "per_author_maximums": per_author,
        "maximum_proxy_cost_usd": round(max_cost, 6),
        "requested_authorization_ceiling_usd": 7.50,
        "execution_order": {
            "canary_users_first": ["p2r_formal_gpt_u010", "p2r_formal_claude_u005"],
            "continue_remaining_eleven_only_after_both_canaries_machine_validate": True,
            "semantic_quality_review_does_not_modify_generation_method": True,
            "mechanical_schema_or_lineage_failure_stops_before_next_user": True,
        },
        "assembly": {
            "world_precedes_surface_text": True,
            "relationships_events_threads_profiles_preferences_are_bound_before_session_chunks": True,
            "candidate_literal_spans_must_be_exact_user_turn_substrings": True,
            "no_hidden_free_form_repair_call": True,
            "validator_is_authoritative_for_mechanical_acceptance": True,
        },
        "external_exam_text_or_outcome_read": False,
        "pricing_sources": {
            "chatgpt_pro": "https://developers.openai.com/api/docs/models/gpt-4o",
            "claude": "https://www.anthropic.com/claude/sonnet",
        },
    }
    identity = "v53wave1gen_" + sha256_text(canonical_json(binding))[:32]
    return {
        **binding,
        "run_identity": identity,
        "status": "SUPERSEDED_UNAPPROVED_FULL_BATCH_IDENTITY_WEB_FIRST_TWO_STAGE_SELECTED",
        "api_calls": 0,
    }


def main() -> None:
    contract = build_contract()
    write_json(OUT / "execution_preflight.json", contract)
    print(json.dumps(contract, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
