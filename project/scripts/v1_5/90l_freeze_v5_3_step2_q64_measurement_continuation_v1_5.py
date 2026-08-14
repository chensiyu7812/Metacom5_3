#!/usr/bin/env python3
"""Freeze the 14-case measurement-only continuation after Q64 text loss."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import canonical_json, read_jsonl, sha256_file, sha256_text, write_json  # noqa: E402


SOURCE = ROOT / "outputs/pm_v1_5_v5_3_step2_semantic_execution_v1"
RUNNER = ROOT / "scripts/v1_5/89l_run_v5_3_step2_semantic_qualification_v1_5.py"
CONTINUATION_RUNNER = ROOT / "scripts/v1_5/93l_run_v5_3_step2_q64_measurement_continuation_v1_5.py"
OUT = ROOT / "outputs/pm_v1_5_v5_3_step2_q64_measurement_continuation_preflight_v1"


def build_contract() -> dict[str, object]:
    rows = read_jsonl(SOURCE / "outcomes.jsonl")
    affected = [str(row["case_id"]) for row in rows if row["status"] == "fell_back_to_m0"]
    if len(affected) != 14 or len(set(affected)) != 14:
        raise RuntimeError("source Q64 fallback set is not the expected 14 unique cases")
    binding = {
        "protocol": "pm-v1.5-v5.3-step2-q64-measurement-continuation-preflight-v1",
        "source_run_identity": "v53step2semexec_8f51ee42c67e85c41b3721b9d1b731fe",
        "source_outcomes_sha256": sha256_file(SOURCE / "outcomes.jsonl"),
        "source_attempt_ledger_sha256": sha256_file(SOURCE / "physical_attempt_ledger.jsonl"),
        "corrected_runner_sha256": sha256_file(RUNNER),
        "continuation_runner_sha256": sha256_file(CONTINUATION_RUNNER),
        "affected_case_ids": affected,
        "logical_calls": 14,
        "maximum_physical_calls": 28,
        "model": "meta/llama-3.1-8b-instruct",
        "temperature": 0.0,
        "max_output_tokens": 512,
        "retry_scope": "one_transport_only_retry_when_no_valid_completion_received",
        "provider_text_must_be_persisted_before_guard_fallback": True,
        "prompt_guard_or_method_change_allowed": False,
        "pricing_usd_per_mtok_proxy": {"input": 0.15, "output": 0.60},
        "maximum_proxy_cost_usd": 0.043008,
        "requested_authorization_ceiling_usd": 0.05,
    }
    identity = "v53step2q64cont_" + sha256_text(canonical_json(binding))[:32]
    return {
        **binding,
        "run_identity": identity,
        "status": "AWAITING_EXPLICIT_IDENTITY_AND_COST_AUTHORIZATION",
        "api_calls": 0,
        "quality_risk_or_function_outcome_used_to_change_method": False,
    }


def main() -> None:
    contract = build_contract()
    write_json(OUT / "execution_preflight.json", contract)
    print(json.dumps(contract, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
