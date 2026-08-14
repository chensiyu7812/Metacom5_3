#!/usr/bin/env python3
"""Materialize the zero-call full four-generator G0 identity."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
AUTHORITY_DIR = PROJECT_ROOT / "data" / "v3_authority"
CONTRACT_PATH = AUTHORITY_DIR / "g0_four_generator_full_screen_contract_v1.json"
PROMPT_PATH = AUTHORITY_DIR / "g0_research_aligned_supporter_prompt_v1.json"
MANIFEST_PATH = AUTHORITY_DIR / "g0_research_aligned_screening_manifest_v2.jsonl"
NEMOTRON_CLOSEOUT_PATH = AUTHORITY_DIR / "g0_nemotron30b_transport_canary_closeout_v1.json"
BASE_RUNNER_PATH = PROJECT_ROOT / "scripts" / "v3" / "16_run_g0_research_aligned_esc.py"
RUNNER_PATH = PROJECT_ROOT / "scripts" / "v3" / "22_run_g0_four_generator_full_screen.py"
API_PATH = PROJECT_ROOT / "src" / "metacom_pm" / "api.py"
PREFLIGHT_PATH = AUTHORITY_DIR / "g0_four_generator_full_screen_preflight_v1.json"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def materialize() -> dict[str, Any]:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    prompt = json.loads(PROMPT_PATH.read_text(encoding="utf-8"))
    nemotron = json.loads(NEMOTRON_CLOSEOUT_PATH.read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines() if line]
    candidate_ids = [row["candidate_id"] for row in contract["candidates"]]
    models = [row["model"] for row in contract["candidates"]]
    if len(candidate_ids) != 4 or len(set(candidate_ids)) != 4:
        raise ValueError("four unique candidate configurations are required")
    if "meta/llama-3.3-70b-instruct" in models:
        raise ValueError("the corrected full screen cannot contain the wrong 70B route")
    if "nvidia/nemotron-3-nano-30b-a3b" not in models:
        raise ValueError("the corrected Nemotron route is missing")
    if not nemotron["frozen_gate_evaluation"]["all_operational_thresholds_pass"]:
        raise ValueError("Nemotron cannot enter the full screen without its operational pass")
    if len(rows) != 24 or len({row["card_key"] for row in rows}) != 24:
        raise ValueError("full screen requires 24 unique frozen cards")
    if contract["shared_generation_contract"]["researcher_output_token_cap"] is not None:
        raise ValueError("full screen must not impose an output cap")
    prompt_text = "\n\n".join(section.strip() for section in prompt["prompt_sections"])
    report = {
        "protocol": "metacom-v3-g0-four-generator-full-screen-preflight-v1",
        "date": "2026-08-14",
        "status": "ZERO_CALL_PREFLIGHT_PASS_EXECUTION_REQUIRES_IDENTITY_SPECIFIC_APPROVAL",
        "api_calls": 0,
        "contains_role_card_or_dialogue_text": False,
        "candidate_ids": candidate_ids,
        "models": models,
        "cards": 24,
        "sample": {
            "development_cards": 24,
            "manifest_sha256": _sha_file(MANIFEST_PATH),
            "prior_use": "The cards were previously inspected and remain development-only."
        },
        "turns_per_dialogue": 5,
        "logical_supporter_calls": 480,
        "local_role_player_calls": 480,
        "qwen_paid_logical_calls": 240,
        "judge_calls": 0,
        "researcher_output_token_cap": None,
        "prompt_sha256": _sha_text(prompt_text),
        "prompt": {
            "artifact": PROMPT_PATH.name,
            "joined_prompt_sha256": _sha_text(prompt_text),
            "researcher_output_token_cap": None,
            "provider_output_parameter": "OMITTED"
        },
        "manifest_sha256": _sha_file(MANIFEST_PATH),
        "budget": {
            "approval_ceiling_external_to_identity": True,
            "two_card_observed_qwen_usd": contract["qwen_budget_contract"]["two_card_observed_cost_usd"],
            "linear_24_card_point_estimate_usd": contract["qwen_budget_contract"]["linear_24_card_point_estimate_usd"],
            "strict_pre_call_reserve": contract["qwen_budget_contract"]["strict_budget_rule"],
            "suggested_ceiling_usd": 0.5
        },
        "input_hashes": {
            path.name: _sha_file(path)
            for path in (
                CONTRACT_PATH, PROMPT_PATH, MANIFEST_PATH, NEMOTRON_CLOSEOUT_PATH,
                BASE_RUNNER_PATH, RUNNER_PATH, API_PATH,
            )
        },
        "run_identity": "PENDING_RENDER"
    }
    identity_payload = {key: value for key, value in report.items() if key not in {"date", "status", "api_calls", "run_identity"}}
    report["run_identity"] = _sha_text(_canonical(identity_payload))
    return report


def main() -> int:
    report = materialize()
    PREFLIGHT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"api_calls": 0, "run_identity": report["run_identity"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
