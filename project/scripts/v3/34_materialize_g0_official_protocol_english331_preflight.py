#!/usr/bin/env python3
"""Create the content-addressed zero-call preflight for official English-331 generation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = ROOT / "data" / "v3_authority"
CONTRACT = AUTHORITY / "g0_official_protocol_english331_contract_v1.json"
MANIFEST = AUTHORITY / "g0_official_protocol_english331_manifest_v1.jsonl"
RUNNER = ROOT / "scripts" / "v3" / "33_run_g0_official_protocol_english331.py"
BASE = ROOT / "scripts" / "v3" / "16_run_g0_research_aligned_esc.py"
API = ROOT / "src" / "metacom_pm" / "api.py"
OUT = AUTHORITY / "g0_official_protocol_english331_preflight_v1.json"


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in MANIFEST.read_text(encoding="utf-8").splitlines() if line]
    if len(rows) != 331 or len({row["card_key"] for row in rows}) != 331:
        raise RuntimeError("English-331 manifest is incomplete")
    hashes = {
        CONTRACT.name: sha_bytes(CONTRACT.read_bytes()),
        MANIFEST.name: sha_bytes(MANIFEST.read_bytes()),
        f"executable::{RUNNER.name}": sha_bytes(RUNNER.read_bytes()),
        f"executable::{BASE.name}": sha_bytes(BASE.read_bytes()),
        "executable::metacom_pm/api.py": sha_bytes(API.read_bytes())
    }
    identity_payload = {
        "protocol": "metacom-v3-g0-official-protocol-english331-run-identity-v1",
        "input_hashes": hashes,
        "esc_eval_commit": contract["primary_sources"]["repository_commit"],
        "esc_role_revision": contract["primary_sources"]["role_player_revision"],
        "candidate_configurations": [
            {key: row.get(key) for key in ("candidate_id", "base_url", "model", "enable_thinking", "max_output_tokens")}
            for row in contract["candidates"]
        ],
        "cards": 331,
        "turns": 5,
        "logical_supporter_calls": 3310,
        "qwen_paid_logical_calls": 1655,
        "judge_calls": 0
    }
    identity = sha_bytes(canonical(identity_payload).encode("utf-8"))
    preflight = {
        "protocol": "metacom-v3-g0-official-protocol-english331-preflight-v1",
        "date": "2026-08-14",
        "status": "ZERO_CALL_PASS_EXPLICIT_IDENTITY_AND_COST_APPROVAL_REQUIRED",
        "run_identity": identity,
        "api_calls": 0,
        "contains_role_card_or_dialogue_text": False,
        "official_surface": {
            "cards": 331,
            "turns": 5,
            "supporter_system_prompt_sha256": sha_bytes(contract["official_interaction_surface"]["supporter_system_prompt"].encode("utf-8")),
            "official_pass_line": None,
            "output_caps": {row["candidate_id"]: row["max_output_tokens"] for row in contract["candidates"]}
        },
        "logical_calls": {"supporter": 3310, "local_role": 3310, "qwen_paid": 1655, "judge": 0},
        "budget": {
            "qwen_point_estimate_usd": 0.68,
            "recommended_approval_ceiling_usd": 1.25,
            "ceiling_not_part_of_identity": True,
            "strict_pre_call_rule": "Observed Qwen spend plus conservative capped-call reserve must fit before every call."
        },
        "input_hashes": hashes,
        "identity_payload": identity_payload,
        "claim_boundary": "Official-protocol English profile for current hosted candidates; no official pass line, PM value, clinical-safety, or real-user claim."
    }
    OUT.write_text(json.dumps(preflight, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "run_identity": identity, "cards": 331, "supporter_calls": 3310, "qwen_paid_calls": 1655, "recommended_max_usd": 1.25}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
