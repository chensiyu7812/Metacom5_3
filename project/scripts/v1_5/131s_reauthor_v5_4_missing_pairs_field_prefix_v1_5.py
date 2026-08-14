#!/usr/bin/env python3
"""Re-author the six remaining V5.4 pairs with role-free prefix fields."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from pydantic import Field  # noqa: E402

from metacom_pm.api import Endpoint, make_client  # noqa: E402
from metacom_pm.attempt_ledger import PersistentAttemptLedger  # noqa: E402
from metacom_pm.contracts import StrictModel  # noqa: E402
from metacom_pm.io import canonical_json, sha256_text, write_json, write_jsonl  # noqa: E402


PROTOCOL = "pm-v1.5-v5.4-state-variant-authoring-v1"
EXECUTION_PROTOCOL = "pm-v1.5-v5.4-missing-pair-reauthor-field-prefix-v1"
DIR = ROOT / "outputs/pm_v1_5_v5_4_state_variant_authoring_20260810"
PACKET = DIR / "authoring_packet_private.jsonl"
COMPLETED = DIR / "authored_pairs_outcome_blind.jsonl"
CONFIG = ROOT / "configs/pm_v1_5_role_decomposed_judge_qualification_v1.json"


class FieldPair(StrictModel):
    pair_id: str = Field(min_length=1)
    prefix_user_text: str = Field(min_length=1)
    prefix_assistant_text: str = Field(min_length=1)
    variant_A_current_user_turn: str = Field(min_length=1)
    variant_B_current_user_turn: str = Field(min_length=1)


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _endpoint(raw: dict[str, Any]) -> Endpoint:
    return Endpoint(
        base_url=str(raw["base_url"]), model=str(raw["model"]), api_key_env=str(raw["api_key_env"]),
        timeout_seconds=240.0, family=str(raw["family"]), transport=str(raw["transport"]),
        supports_strict_json_schema=bool(raw["supports_strict_json_schema"]),
        temperature_mode=str(raw.get("temperature_mode") or "explicit"),
        max_output_tokens_parameter=str(raw.get("max_output_tokens_parameter") or "max_tokens"),
        anthropic_strict_tool_use=bool(raw.get("anthropic_strict_tool_use", False)),
        openai_reasoning_effort=raw.get("openai_reasoning_effort"),
    )


def _messages(item: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": """Re-author the same frozen controlled CURRENT-state pair. Use four role-free text fields: one opening USER text, one following ASSISTANT text, then two alternative next USER turns. The alternatives must follow the unchanged private A/B instructions and form a minimal pair: same user, topic, entities, tone, and similar length; only the response-need/boundary factor changes. Never mention roles, labels, components, resources, experiments, or outcomes. Stay faithful to the public anchor and candidate; invent no new past event, result, diagnosis, identity, relationship, or future fact. Do not copy a source assistant response or the exact candidate text."""},
        {"role": "user", "content": canonical_json(item)},
    ]


def _validate(parsed: FieldPair, item: dict[str, Any]) -> dict[str, Any]:
    if parsed.pair_id != item["pair_id"]:
        raise ValueError("pair identity mismatch")
    raw = parsed.model_dump(mode="json")
    texts = [raw["prefix_user_text"].strip(), raw["prefix_assistant_text"].strip(), raw["variant_A_current_user_turn"].strip(), raw["variant_B_current_user_turn"].strip()]
    if texts[2] == texts[3] or any(not 4 <= len(text.split()) <= 90 for text in texts):
        raise ValueError("invalid field-pair surface")
    surface = " ".join(texts)
    if str(item["frozen_candidate_text"]).lower() in surface.lower():
        raise ValueError("candidate text copied verbatim")
    resource_id = str(item["frozen_candidate"].get("resource_id") or "")
    if resource_id and resource_id in surface:
        raise ValueError("resource id leaked")
    return {
        "pair_id": item["pair_id"],
        "shared_prefix": [
            {"role": "user", "content": texts[0]},
            {"role": "assistant", "content": texts[1]},
        ],
        "variant_A_current_user_turn": texts[2],
        "variant_B_current_user_turn": texts[3],
        "protocol": PROTOCOL,
        "execution_protocol": EXECUTION_PROTOCOL,
        "implementation_reauthor": True,
        "semantic_family_id": item["semantic_family_id"],
        "component_private_lineage": item["component"],
        "assigned_author_endpoint": item["assigned_author_endpoint"],
        "frozen_candidate": item["frozen_candidate"],
        "frozen_candidate_text": item["frozen_candidate_text"],
        "source_dataset": item["source_dataset"],
        "effect_quality_risk_function_oracle_outcome_read": False,
        "requires_independent_fidelity_review": True,
        "requires_actual_rank1_recomputation": True,
    }


def main() -> None:
    packet = {str(row["pair_id"]): row for row in _jsonl(PACKET)}
    completed = {str(row["pair_id"]): row for row in _jsonl(COMPLETED)}
    missing = sorted(set(packet) - set(completed))
    if len(missing) != 6:
        raise SystemExit(f"expected six remaining role-order failures; got {len(missing)}")
    if {packet[key]["assigned_author_endpoint"] for key in missing} != {"anthropic_claude_haiku_4_5"}:
        raise SystemExit("remaining missing set differs from documented Claude failures")
    raw = json.loads(CONFIG.read_text())["candidates"]["anthropic_claude_haiku_4_5"]
    endpoint = _endpoint(raw)
    ledger = PersistentAttemptLedger(
        DIR / "authoring_missing_field_prefix_ledger.jsonl",
        stage="v5_4_missing_pair_reauthor_field_prefix",
        expected_calls={"reauthor_" + key: 1 for key in missing}, maximum_total_attempts=len(missing),
    )
    client = make_client(endpoint)
    try:
        for index, pair_id in enumerate(missing, start=1):
            item = packet[pair_id]; messages = _messages(item)
            reservation = ledger.reserve("reauthor_" + pair_id, record_ids={"pair_id": pair_id, "author": "anthropic_claude_haiku_4_5"}, prompt_sha256=sha256_text(canonical_json(messages)))
            response = None
            try:
                response, parsed = client.chat(messages, temperature=0.0, max_tokens=1000, seed=20260810 + index, response_schema=FieldPair, retries=1)
                if parsed is None: raise ValueError("structured field pair missing")
                row = _validate(parsed, item)
                ledger.finish(reservation, succeeded=True, request_hash=response.request_hash, usage=response.usage, error=None, result=row, metadata={"model": endpoint.model})
                completed[pair_id] = row; write_jsonl(COMPLETED, list(completed.values()))
            except Exception as exc:
                ledger.finish(reservation, succeeded=False, request_hash=response.request_hash if response else None, usage=response.usage if response else None, error=f"{type(exc).__name__}: {exc}", metadata={"model": endpoint.model})
    finally:
        client.close()
    report = {
        "protocol": PROTOCOL, "execution_protocol": EXECUTION_PROTOCOL,
        "status": "REAUTHOR_COMPLETE" if len(completed) == 48 else "REAUTHOR_INCOMPLETE",
        "attempted_pairs": missing, "completed_pairs": len(completed),
        "semantic_instructions_changed": False, "role_fields_removed_from_model_output": True,
        "original_failures_preserved": True, "response_effect_or_judge_calls": 0,
        "private_paired_outcome_key_read": False,
    }
    write_json(DIR / "authoring_missing_field_prefix_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
