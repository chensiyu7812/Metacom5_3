#!/usr/bin/env python3
"""Materialize the zero-call research-aligned G0 generator identity."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
AUTHORITY_DIR = PROJECT_ROOT / "data" / "v3_authority"
CONTRACT_PATH = AUTHORITY_DIR / "g0_research_aligned_generator_contract_v2.json"
PROMPT_PATH = AUTHORITY_DIR / "g0_research_aligned_supporter_prompt_v1.json"
SOURCE_MANIFEST_PATH = AUTHORITY_DIR / "g0_esc_eval_screening_manifest_v1.jsonl"
PREFLIGHT_PATH = AUTHORITY_DIR / "g0_research_aligned_generator_preflight_v2.json"
MANIFEST_PATH = AUTHORITY_DIR / "g0_research_aligned_screening_manifest_v2.jsonl"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _supporter_prompt(prompt: dict[str, Any]) -> str:
    sections = prompt.get("prompt_sections")
    if not isinstance(sections, list) or not sections or not all(isinstance(x, str) and x.strip() for x in sections):
        raise ValueError("supporter prompt must contain non-empty prompt_sections")
    return "\n\n".join(section.strip() for section in sections)


def materialize() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    contract = _load_json(CONTRACT_PATH)
    prompt = _load_json(PROMPT_PATH)
    source_rows = _read_jsonl(SOURCE_MANIFEST_PATH)
    if contract["shared_generation_contract"]["researcher_output_token_cap"] is not None:
        raise ValueError("research-aligned comparison must not impose an output cap")
    if prompt["output_length_policy"]["researcher_token_cap"] is not None:
        raise ValueError("prompt artifact unexpectedly imposes an output cap")
    if len(source_rows) != 24 or len({row["card_key"] for row in source_rows}) != 24:
        raise ValueError("source development screen must contain 24 unique cards")

    rows = []
    for index, row in enumerate(source_rows, start=1):
        rows.append(
            {
                "screen_id": "g0r2_" + _sha_text(row["card_key"])[:16],
                "card_key": row["card_key"],
                "source": row["source"],
                "source_rank": row["source_rank"],
                "role_card_sha256": row["role_card_sha256"],
                "annotation_sha256": row["annotation_sha256"],
                "development_order": index,
                "canary": index <= int(contract["dialogue_surface"]["canary_cards"]),
            }
        )
    prompt_text = _supporter_prompt(prompt)
    manifest_bytes = "".join(_canonical(row) + "\n" for row in rows).encode("utf-8")
    executable_paths = {
        "16_run_g0_research_aligned_esc.py": PROJECT_ROOT / "scripts" / "v3" / "16_run_g0_research_aligned_esc.py",
        "metacom_pm/api.py": PROJECT_ROOT / "src" / "metacom_pm" / "api.py",
    }
    candidate_count = len(contract["candidates"])
    qwen_count = sum(row["provider"].startswith("Alibaba Cloud") for row in contract["candidates"])
    turns = int(contract["shared_generation_contract"]["turns_per_dialogue"])
    canary_cards = int(contract["dialogue_surface"]["canary_cards"])
    report = {
        "protocol": "metacom-v3-g0-research-aligned-generator-preflight-v2",
        "date": "2026-08-14",
        "status": "ZERO_CALL_PREFLIGHT_PASS_EXECUTION_REQUIRES_IDENTITY_SPECIFIC_APPROVAL",
        "api_calls": 0,
        "contains_role_card_or_dialogue_text": False,
        "prompt": {
            "artifact": PROMPT_PATH.name,
            "joined_prompt_sha256": _sha_text(prompt_text),
            "researcher_output_token_cap": None,
            "provider_output_parameter": "OMITTED",
        },
        "sample": {
            "development_cards": len(rows),
            "canary_cards": canary_cards,
            "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            "prior_use": "The 24-card G0 sample has already been inspected and is development-only; it is not held out.",
        },
        "logical_calls": {
            "canary_supporter_all_configurations": canary_cards * turns * candidate_count,
            "canary_qwen_paid_calls": canary_cards * turns * qwen_count,
            "full_supporter_all_configurations": len(rows) * turns * candidate_count,
            "full_qwen_paid_calls": len(rows) * turns * qwen_count,
            "local_role_calls_match_supporter_calls": True,
            "judge_calls": 0,
        },
        "budget": {
            "approval_ceiling_is_external_to_identity": True,
            "strict_pre_call_reserve": contract["qwen_budget_contract"]["strict_budget_rule"],
            "reason_no_fixed_full_run_ceiling": "With no per-call output cap, a low fixed total cannot guarantee both completion of every call and a hard cost ceiling. The runner instead refuses to start a call unless its worst-case documented reserve fits inside the user-approved ceiling.",
        },
        "input_hashes": {
            CONTRACT_PATH.name: _sha_file(CONTRACT_PATH),
            PROMPT_PATH.name: _sha_file(PROMPT_PATH),
            SOURCE_MANIFEST_PATH.name: _sha_file(SOURCE_MANIFEST_PATH),
            **{f"executable::{name}": _sha_file(path) for name, path in executable_paths.items()},
        },
        "run_identity": "PENDING_RENDER",
    }
    identity_payload = {key: value for key, value in report.items() if key not in {"date", "status", "api_calls", "run_identity"}}
    report["run_identity"] = _sha_text(_canonical(identity_payload))
    return report, rows


def main() -> int:
    report, rows = materialize()
    PREFLIGHT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    MANIFEST_PATH.write_text("".join(_canonical(row) + "\n" for row in rows), encoding="utf-8")
    print(json.dumps({"api_calls": 0, "cards": len(rows), "run_identity": report["run_identity"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
