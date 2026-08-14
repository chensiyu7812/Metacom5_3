#!/usr/bin/env python3
"""Run source-prefix-locked, user-turn-only V5.4 authoring V2."""

from __future__ import annotations

import argparse
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from pydantic import Field  # noqa: E402
from metacom_pm.api import Endpoint, make_client  # noqa: E402
from metacom_pm.attempt_ledger import PersistentAttemptLedger  # noqa: E402
from metacom_pm.contracts import StrictModel  # noqa: E402
from metacom_pm.io import canonical_json, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402


PROTOCOL = "pm-v1.5-v5.4-source-prefix-locked-authoring-v2"
STAGE = "v5_4_source_prefix_locked_authoring_v2"
DIR = ROOT / "outputs/pm_v1_5_v5_4_source_prefix_locked_authoring_v2_20260810"
PACKET = DIR / "source_prefix_locked_authoring_packet_private.jsonl"
CONTRACT = ROOT / "data/pm_v1_5_contracts/v5_4_factorial_outcome_oracle_learning_v1.json"
ENDPOINTS = ROOT / "configs/pm_v1_5_role_decomposed_judge_qualification_v1.json"
COMPLETED = DIR / "authored_pairs_source_prefix_locked_outcome_blind.jsonl"
MAX_ATTEMPTS = 2
MAX_OUTPUT_TOKENS = 650
USD_CAP = 1.0


class UserTurnPair(StrictModel):
    pair_id: str = Field(min_length=1)
    variant_A_current_user_turn: str = Field(min_length=1)
    variant_B_current_user_turn: str = Field(min_length=1)


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists(): return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _endpoint(raw: dict[str, Any]) -> Endpoint:
    return Endpoint(base_url=str(raw["base_url"]), model=str(raw["model"]), api_key_env=str(raw["api_key_env"]), timeout_seconds=240.0, family=str(raw["family"]), transport=str(raw["transport"]), supports_strict_json_schema=bool(raw["supports_strict_json_schema"]), temperature_mode=str(raw.get("temperature_mode") or "explicit"), max_output_tokens_parameter=str(raw.get("max_output_tokens_parameter") or "max_tokens"), anthropic_strict_tool_use=bool(raw.get("anthropic_strict_tool_use", False)), openai_reasoning_effort=raw.get("openai_reasoning_effort"))


def _messages(item: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": """Write exactly two alternative CURRENT USER turns continuing the supplied exact public-source prefix. Do not rewrite or repeat the prefix and do not write an assistant response.

Follow the private A/B instructions but never expose them. The two turns must be a lexical minimal pair: same user, entity, topic, goal frame, tone, syntax, and similar length; change only the specified response-need, redundancy, or boundary factor. Each must be 8-80 words. Stay faithful to the source world and candidate. Invent no new past event, result, diagnosis, identity, relationship, or future fact. Do not copy the exact full candidate text. Do not mention candidates, resources, components, routing, experiments, labels, assignments, or expected outcomes. Return only the strict schema."""},
        {"role": "user", "content": canonical_json(item)},
    ]


def _normalize(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", text.lower()))


def _validate(parsed: UserTurnPair, item: dict[str, Any], author: str) -> dict[str, Any]:
    if parsed.pair_id != item["pair_id"]: raise ValueError("pair identity mismatch")
    a = parsed.variant_A_current_user_turn.strip(); b = parsed.variant_B_current_user_turn.strip()
    if a == b: raise ValueError("variant texts identical")
    aw, bw = len(a.split()), len(b.split())
    if not 8 <= aw <= 80 or not 8 <= bw <= 80: raise ValueError("variant word count outside 8-80")
    if max(aw, bw) / min(aw, bw) > 1.5: raise ValueError("variant word length ratio exceeds 1.5")
    similarity = SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()
    if similarity < 0.25: raise ValueError("variant character similarity below 0.25")
    surface = a + " " + b
    if _normalize(str(item["frozen_candidate_text"])) in _normalize(surface): raise ValueError("candidate text copied verbatim")
    forbidden = ("candidate_text", "resource_id", "low_opportunity", "incremental:", "construction assignment", "oracle action")
    if any(token in surface.lower() for token in forbidden): raise ValueError("authoring scaffold leaked")
    return {
        "protocol": PROTOCOL, "pair_id": item["pair_id"], "semantic_family_id": item["semantic_family_id"],
        "component_private_lineage": item["component"], "assigned_author_endpoint": author,
        "source_dataset": item["source_dataset"],
        "exact_public_source_visible_prefix_locked": item["exact_public_source_visible_prefix_locked"],
        "variant_A_current_user_turn": a, "variant_B_current_user_turn": b,
        "pair_character_similarity": similarity, "pair_word_length_ratio": max(aw, bw) / min(aw, bw),
        "frozen_candidate": item["frozen_candidate"], "frozen_candidate_text": item["frozen_candidate_text"],
        "construction_assignment_present": False, "effect_quality_risk_function_oracle_outcome_read": False,
        "source_prefix_generated_or_modified": False, "requires_independent_fidelity_review": True,
        "requires_actual_rank1_recomputation": True,
    }


def _call_key(pair_id: str) -> str:
    return "v2author_" + sha256_text(f"{PROTOCOL}:{pair_id}")[:22]


def _estimate(packet: list[dict[str, Any]], configs: dict[str, Any]) -> dict[str, Any]:
    total = 0.0; by_endpoint = {}
    for endpoint_key in sorted({row["assigned_author_endpoint"] for row in packet}):
        subset = [row for row in packet if row["assigned_author_endpoint"] == endpoint_key]; raw = configs["candidates"][endpoint_key]
        chars = sum(len(canonical_json(_messages(item))) for item in subset); input_tokens = int(chars / 4 * 1.5); output_tokens = len(subset) * MAX_OUTPUT_TOKENS
        two_pass = 2 * (input_tokens * float(raw["input_usd_per_million_tokens"]) + output_tokens * float(raw["output_usd_per_million_tokens"])) / 1_000_000
        by_endpoint[endpoint_key] = {"logical_calls": len(subset), "two_attempt_usd_upper_proxy": two_pass}; total += two_pass
    return {"by_endpoint": by_endpoint, "two_attempt_total_usd_upper_proxy": total}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--live", action="store_true"); parser.add_argument("--accept-usd-cap", type=float); args = parser.parse_args()
    packet = _jsonl(PACKET); contract = json.loads(CONTRACT.read_text()); configs = json.loads(ENDPOINTS.read_text())
    if len(packet) != 48 or contract["current_authorization"].get("only_authorized_authoring_revision") != "source-prefix-locked current-user-turn-only V2": raise SystemExit("frozen V2 authoring identity not authorized")
    estimate = _estimate(packet, configs)
    preflight = {"protocol": PROTOCOL, "status": "LIVE_READY" if estimate["two_attempt_total_usd_upper_proxy"] <= USD_CAP else "COST_BLOCKED", "packet_sha256": sha256_file(PACKET), "contract_sha256": sha256_file(CONTRACT), "logical_calls": 48, "maximum_physical_attempts": 96, "cost_estimate": estimate, "accepted_usd_cap_required": USD_CAP, "generated_assistant_turns": 0, "response_effect_or_judge_calls": 0, "private_paired_outcome_key_read": False}
    write_json(DIR / "authoring_v2_preflight.json", preflight); print(json.dumps(preflight, ensure_ascii=False, indent=2), flush=True)
    if not args.live: return
    if args.accept_usd_cap is None or args.accept_usd_cap < USD_CAP: raise SystemExit(f"live execution requires --accept-usd-cap {USD_CAP:g}")
    ledger = PersistentAttemptLedger(DIR / "authoring_v2_attempt_ledger.jsonl", stage=STAGE, expected_calls={_call_key(str(item["pair_id"])): MAX_ATTEMPTS for item in packet}, maximum_total_attempts=96)
    completed = {str(row["pair_id"]): row for row in _jsonl(COMPLETED)}; clients = {}
    try:
        for index, item in enumerate(packet, start=1):
            pair_id = str(item["pair_id"])
            if pair_id in completed: continue
            endpoint_key = str(item["assigned_author_endpoint"])
            if endpoint_key not in clients: clients[endpoint_key] = make_client(_endpoint(configs["candidates"][endpoint_key]))
            endpoint = _endpoint(configs["candidates"][endpoint_key]); call_key = _call_key(pair_id)
            if ledger.exhausted(call_key): continue
            messages = _messages(item)
            while not ledger.exhausted(call_key) and not ledger.succeeded(call_key):
                reservation = ledger.reserve(call_key, record_ids={"pair_id": pair_id, "author": endpoint_key}, prompt_sha256=sha256_text(canonical_json(messages))); response = None
                try:
                    response, parsed = clients[endpoint_key].chat(messages, temperature=0.0, max_tokens=MAX_OUTPUT_TOKENS, seed=20260810 + index, response_schema=UserTurnPair, retries=1)
                    if parsed is None: raise ValueError("structured user-turn pair missing")
                    row = _validate(parsed, item, endpoint_key); ledger.finish(reservation, succeeded=True, request_hash=response.request_hash, usage=response.usage, error=None, result=row, metadata={"endpoint": endpoint_key, "model": endpoint.model}); completed[pair_id] = row; write_jsonl(COMPLETED, list(completed.values()))
                except Exception as exc:
                    ledger.finish(reservation, succeeded=False, request_hash=response.request_hash if response else None, usage=response.usage if response else None, error=f"{type(exc).__name__}: {exc}", metadata={"endpoint": endpoint_key, "model": endpoint.model}); messages += [{"role": "user", "content": "The prior output failed strict minimal-pair validation. Return both complete user turns with the same lexical frame and only the assigned semantic difference."}]
            if index % 8 == 0 or index == 48: print(f"V2 authoring progress {len(completed)}/48 attempts={ledger.started_attempts}", flush=True)
    finally:
        for client in clients.values(): client.close()
    report = {"protocol": PROTOCOL, "status": "V2_AUTHORING_COMPLETE_AWAITING_MACHINE_AUDIT" if len(completed) == 48 else "V2_AUTHORING_INCOMPLETE", "completed_pairs": len(completed), "completed_variants": 2 * len(completed), "attempts_started": ledger.started_attempts, "generated_assistant_turns": 0, "response_effect_or_judge_calls": 0, "private_paired_outcome_key_read": False}
    write_json(DIR / "authoring_v2_live_report.json", report); print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__": main()
