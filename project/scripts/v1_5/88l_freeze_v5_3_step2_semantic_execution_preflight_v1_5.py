#!/usr/bin/env python3
"""Freeze a zero-API execution identity and conservative cost ceiling for Step2 Q64."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.config import endpoint_from_config, load_config  # noqa: E402
from metacom_pm.io import canonical_json, read_json, sha256_file, sha256_text, write_json  # noqa: E402


CONFIG = ROOT / "configs/experiment.yaml"
PLAN_DIR = ROOT / "outputs/pm_v1_5_v5_3_step2_semantic_qualification_plan_v1"
OUT_DIR = ROOT / "outputs/pm_v1_5_v5_3_step2_semantic_execution_preflight_v1"
EXPECTED_PLAN_IDENTITY = "v53step2semplan_4a644f74b60d633d9b1b15c1"

INPUT_TOKEN_CEILING_PER_CALL = 8192
OUTPUT_TOKEN_CEILING_PER_CALL = 512
LOGICAL_CALLS = 64
TRANSPORT_ATTEMPTS_PER_LOGICAL_CALL = 2
PRICE_INPUT_PER_MTOK = 0.15
PRICE_OUTPUT_PER_MTOK = 0.60


def build_preflight() -> dict[str, object]:
    plan_manifest = read_json(PLAN_DIR / "plan_manifest.json")
    if plan_manifest.get("plan_identity") != EXPECTED_PLAN_IDENTITY:
        raise RuntimeError("Step2 semantic plan identity drift")
    if int(plan_manifest.get("logical_call_count") or 0) != LOGICAL_CALLS:
        raise RuntimeError("Step2 semantic logical call count drift")
    config = load_config(CONFIG)
    endpoint = endpoint_from_config(config, "generator")
    endpoint_contract = {
        "endpoint_key": "generator",
        "base_url": endpoint.base_url,
        "model": endpoint.model,
        "family": endpoint.family,
        "transport": endpoint.transport,
        "timeout_seconds": endpoint.timeout_seconds,
        "api_key_env_name_only": endpoint.api_key_env,
    }
    max_physical_calls = LOGICAL_CALLS * TRANSPORT_ATTEMPTS_PER_LOGICAL_CALL
    maximum_proxy_cost = max_physical_calls * (
        INPUT_TOKEN_CEILING_PER_CALL / 1_000_000 * PRICE_INPUT_PER_MTOK
        + OUTPUT_TOKEN_CEILING_PER_CALL / 1_000_000 * PRICE_OUTPUT_PER_MTOK
    )
    binding = {
        "protocol": "pm-v1.5-v5.3-step2-semantic-execution-preflight-v1",
        "qualification_plan_identity": EXPECTED_PLAN_IDENTITY,
        "plan_manifest_sha256": sha256_file(PLAN_DIR / "plan_manifest.json"),
        "cases_sha256": sha256_file(PLAN_DIR / "cases.jsonl"),
        "content_disjoint_audit_sha256": sha256_file(PLAN_DIR / "content_disjoint_audit.json"),
        "config_sha256": sha256_file(CONFIG),
        "endpoint": endpoint_contract,
        "generation": {
            "temperature": 0.0,
            "max_output_tokens": OUTPUT_TOKEN_CEILING_PER_CALL,
            "logical_calls": LOGICAL_CALLS,
            "maximum_physical_calls": max_physical_calls,
            "transport_attempts_per_logical_call": TRANSPORT_ATTEMPTS_PER_LOGICAL_CALL,
            "retry_scope": "one_retry_only_when_no_valid_completion_was_received",
            "free_rewrite_or_semantic_retry_allowed": False,
            "recovery_after_guard_failure": "deterministic_fallback",
        },
        "cost": {
            "input_token_ceiling_per_physical_call": INPUT_TOKEN_CEILING_PER_CALL,
            "output_token_ceiling_per_physical_call": OUTPUT_TOKEN_CEILING_PER_CALL,
            "pricing_usd_per_mtok_proxy": {
                "input": PRICE_INPUT_PER_MTOK,
                "output": PRICE_OUTPUT_PER_MTOK,
            },
            "maximum_proxy_cost_usd": round(maximum_proxy_cost, 9),
            "requested_authorization_ceiling_usd": 0.20,
        },
        "outcome_firewall": {
            "catalog_generation_may_continue_in_parallel": True,
            "formal_paired_effect_generation_before_completion": False,
            "qualification_reply_quality_or_risk_may_change_training_data": False,
        },
    }
    run_identity = "v53step2semexec_" + sha256_text(canonical_json(binding))[:32]
    return {
        **binding,
        "run_identity": run_identity,
        "status": "AWAITING_EXPLICIT_IDENTITY_AND_COST_AUTHORIZATION",
        "api_calls": 0,
        "generated_response_or_outcome_read": False,
    }


def main() -> None:
    contract = build_preflight()
    write_json(OUT_DIR / "execution_preflight.json", contract)
    print(json.dumps(contract, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
