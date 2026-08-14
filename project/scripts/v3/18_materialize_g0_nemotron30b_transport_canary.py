#!/usr/bin/env python3
"""Materialize the zero-call corrected Nemotron transport identity."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
AUTHORITY_DIR = PROJECT_ROOT / "data" / "v3_authority"
CONTRACT_PATH = AUTHORITY_DIR / "g0_nemotron30b_transport_canary_contract_v1.json"
CORRECTION_PATH = AUTHORITY_DIR / "g0_wrong_70b_reference_correction_v1.json"
PROMPT_PATH = AUTHORITY_DIR / "g0_research_aligned_supporter_prompt_v1.json"
MANIFEST_PATH = AUTHORITY_DIR / "g0_research_aligned_screening_manifest_v2.jsonl"
BASE_RUNNER_PATH = PROJECT_ROOT / "scripts" / "v3" / "16_run_g0_research_aligned_esc.py"
RUNNER_PATH = PROJECT_ROOT / "scripts" / "v3" / "19_run_g0_nemotron30b_transport_canary.py"
API_PATH = PROJECT_ROOT / "src" / "metacom_pm" / "api.py"
PREFLIGHT_PATH = AUTHORITY_DIR / "g0_nemotron30b_transport_canary_preflight_v1.json"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def materialize() -> dict[str, Any]:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    prompt = json.loads(PROMPT_PATH.read_text(encoding="utf-8"))
    manifest_rows = [
        json.loads(line)
        for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines()
        if line
    ]
    if contract["candidate"]["model"] != "nvidia/nemotron-3-nano-30b-a3b":
        raise ValueError("wrong corrected model route")
    if contract["same_surface_lock"]["researcher_output_token_cap"] is not None:
        raise ValueError("Nemotron canary must remain uncapped")
    canary_rows = [row for row in manifest_rows if row["canary"]]
    if len(canary_rows) != 2:
        raise ValueError("expected exactly two frozen canary rows")
    prompt_text = "\n\n".join(section.strip() for section in prompt["prompt_sections"])
    report = {
        "protocol": "metacom-v3-g0-nemotron30b-transport-preflight-v1",
        "date": "2026-08-14",
        "status": "ZERO_CALL_PREFLIGHT_PASS_EXECUTION_REQUIRES_IDENTITY_SPECIFIC_APPROVAL",
        "api_calls": 0,
        "contains_role_card_or_dialogue_text": False,
        "model": contract["candidate"]["model"],
        "reasoning_mode": contract["candidate"]["reasoning_mode"],
        "prompt_sha256": _sha_text(prompt_text),
        "canary_card_identities": [row["screen_id"] for row in canary_rows],
        "logical_supporter_calls": 10,
        "maximum_cost_usd": 0,
        "input_hashes": {
            path.name: _sha_file(path)
            for path in (
                CONTRACT_PATH, CORRECTION_PATH, PROMPT_PATH, MANIFEST_PATH,
                BASE_RUNNER_PATH, RUNNER_PATH, API_PATH,
            )
        },
        "run_identity": "PENDING_RENDER",
    }
    payload = {key: value for key, value in report.items() if key not in {"date", "status", "api_calls", "run_identity"}}
    report["run_identity"] = _sha_text(_canonical(payload))
    return report


def main() -> int:
    report = materialize()
    PREFLIGHT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"api_calls": 0, "run_identity": report["run_identity"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
