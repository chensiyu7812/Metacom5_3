#!/usr/bin/env python3
"""Run authorized outcome-blind V5.4 paired current-state authoring."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Literal


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from pydantic import Field  # noqa: E402

from metacom_pm.api import Endpoint, make_client  # noqa: E402
from metacom_pm.attempt_ledger import PersistentAttemptLedger  # noqa: E402
from metacom_pm.contracts import StrictModel  # noqa: E402
from metacom_pm.io import canonical_json, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402


PROTOCOL = "pm-v1.5-v5.4-state-variant-authoring-v1"
STAGE = "v5_4_state_variant_authoring_pair"
DIR = ROOT / "outputs/pm_v1_5_v5_4_state_variant_authoring_20260810"
PACKET = DIR / "authoring_packet_private.jsonl"
PLAN_REPORT = DIR / "authoring_plan_report.json"
CONTRACT = ROOT / "data/pm_v1_5_contracts/v5_4_factorial_outcome_oracle_learning_v1.json"
ENDPOINTS = ROOT / "configs/pm_v1_5_role_decomposed_judge_qualification_v1.json"
COMPLETED = DIR / "authored_pairs_outcome_blind.jsonl"
MAX_ATTEMPTS = 2
MAX_OUTPUT_TOKENS = 1000
USD_CAP = 1.5


class PrefixTurn(StrictModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)


class AuthoredPair(StrictModel):
    pair_id: str = Field(min_length=1)
    shared_prefix: list[PrefixTurn] = Field(min_length=2, max_length=4)
    variant_A_current_user_turn: str = Field(min_length=1)
    variant_B_current_user_turn: str = Field(min_length=1)


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _endpoint(raw: dict[str, Any]) -> Endpoint:
    return Endpoint(
        base_url=str(raw["base_url"]), model=str(raw["model"]),
        api_key_env=str(raw["api_key_env"]), timeout_seconds=240.0,
        family=str(raw["family"]), transport=str(raw["transport"]),
        supports_strict_json_schema=bool(raw["supports_strict_json_schema"]),
        temperature_mode=str(raw.get("temperature_mode") or "explicit"),
        max_output_tokens_parameter=str(raw.get("max_output_tokens_parameter") or "max_tokens"),
        anthropic_strict_tool_use=bool(raw.get("anthropic_strict_tool_use", False)),
        openai_reasoning_effort=raw.get("openai_reasoning_effort"),
    )


def _messages(item: dict[str, Any]) -> list[dict[str, str]]:
    system = """You are authoring one controlled pair of CURRENT dialogue states for a research development set. You are not writing the assistant's final response and you are not judging which resource should be used.

Follow the private A/B role instructions exactly, but never mention those roles, labels, components, resources, experiments, or expected outcomes in the dialogue. Produce one shared natural prefix and two alternative next USER turns. The prefix must alternate user/assistant, begin with user, end with assistant, and contain 2 or 4 turns. The two alternatives must be a minimal pair: same user, topic, entities, tone, and similar length; change only the requested response-need or boundary factor.

Stay faithful to the supplied public anchor and frozen prior candidate. You may paraphrase known facts, but do not invent a new past event, result, diagnosis, identity, future fact, or relationship. Do not copy any source assistant response. Do not place an assistant answer after either alternative user turn. Return only the strict schema."""
    return [{"role": "system", "content": system}, {"role": "user", "content": canonical_json(item)}]


def _validate(parsed: AuthoredPair, item: dict[str, Any], author: str) -> dict[str, Any]:
    if parsed.pair_id != item["pair_id"]:
        raise ValueError("pair identity mismatch")
    rows = parsed.model_dump(mode="json")
    prefix = rows["shared_prefix"]
    expected_roles = ["user" if index % 2 == 0 else "assistant" for index in range(len(prefix))]
    if [row["role"] for row in prefix] != expected_roles or prefix[-1]["role"] != "assistant":
        raise ValueError("shared prefix role order invalid")
    a = rows["variant_A_current_user_turn"].strip()
    b = rows["variant_B_current_user_turn"].strip()
    if a == b:
        raise ValueError("variant texts are identical")
    for label, text in (("A", a), ("B", b)):
        words = text.split()
        if not 6 <= len(words) <= 90:
            raise ValueError(f"variant {label} word count outside 6-90")
        lower = text.lower()
        forbidden = ("candidate_text", "resource_id", "low_opportunity", "incremental:", "construction assignment", "oracle action")
        if any(token in lower for token in forbidden):
            raise ValueError(f"variant {label} exposes authoring scaffold")
    full_surface = " ".join(row["content"] for row in prefix) + " " + a + " " + b
    candidate_text = str(item["frozen_candidate_text"]).strip()
    if candidate_text and candidate_text.lower() in full_surface.lower():
        raise ValueError("candidate text copied verbatim")
    resource_id = str(item["frozen_candidate"].get("resource_id") or "")
    if resource_id and resource_id in full_surface:
        raise ValueError("resource id leaked")
    rows.update({
        "protocol": PROTOCOL,
        "semantic_family_id": item["semantic_family_id"],
        "component_private_lineage": item["component"],
        "assigned_author_endpoint": author,
        "frozen_candidate": item["frozen_candidate"],
        "frozen_candidate_text": item["frozen_candidate_text"],
        "source_dataset": item["source_dataset"],
        "effect_quality_risk_function_oracle_outcome_read": False,
        "requires_independent_fidelity_review": True,
        "requires_actual_rank1_recomputation": True,
    })
    return rows


def _call_key(pair_id: str) -> str:
    return "author_" + sha256_text(f"{PROTOCOL}:{pair_id}")[:24]


def _estimate(packet: list[dict[str, Any]], configs: dict[str, Any]) -> dict[str, Any]:
    by_endpoint: dict[str, dict[str, float | int]] = {}
    total = 0.0
    for endpoint_key in sorted({str(row["assigned_author_endpoint"]) for row in packet}):
        subset = [row for row in packet if row["assigned_author_endpoint"] == endpoint_key]
        raw = configs["candidates"][endpoint_key]
        chars = sum(len(canonical_json(_messages(item))) for item in subset)
        input_tokens = int(chars / 4 * 1.5)
        output_tokens = len(subset) * MAX_OUTPUT_TOKENS
        one_pass = (
            input_tokens * float(raw["input_usd_per_million_tokens"])
            + output_tokens * float(raw["output_usd_per_million_tokens"])
        ) / 1_000_000
        by_endpoint[endpoint_key] = {
            "logical_calls": len(subset),
            "two_attempt_usd_upper_proxy": 2 * one_pass,
        }
        total += 2 * one_pass
    return {"by_endpoint": by_endpoint, "two_attempt_total_usd_upper_proxy": total}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--accept-usd-cap", type=float)
    args = parser.parse_args()
    packet = _jsonl(PACKET)
    plan = json.loads(PLAN_REPORT.read_text())
    contract = json.loads(CONTRACT.read_text())
    configs = json.loads(ENDPOINTS.read_text())
    if len(packet) != 48 or plan["pairs"] != 48:
        raise SystemExit("authoring plan must contain 48 pairs")
    if not contract["current_authorization"]["state_variant_authoring"]:
        raise SystemExit("state variant authoring is not authorized")
    if contract["current_authorization"]["new_response_effect_calls"]:
        raise SystemExit("authoring runner refuses a contract that also authorizes effects")
    estimate = _estimate(packet, configs)
    preflight = {
        "protocol": PROTOCOL,
        "status": "LIVE_READY" if estimate["two_attempt_total_usd_upper_proxy"] <= USD_CAP else "COST_BLOCKED",
        "packet_sha256": sha256_file(PACKET),
        "contract_sha256": sha256_file(CONTRACT),
        "logical_calls": 48,
        "maximum_physical_attempts": 96,
        "cost_estimate": estimate,
        "accepted_usd_cap_required": USD_CAP,
        "response_effect_or_judge_calls": 0,
        "private_paired_outcome_key_read": False,
    }
    write_json(DIR / "authoring_live_preflight.json", preflight)
    print(json.dumps(preflight, ensure_ascii=False, indent=2), flush=True)
    if not args.live:
        return
    if args.accept_usd_cap is None or args.accept_usd_cap < USD_CAP:
        raise SystemExit(f"live execution requires --accept-usd-cap {USD_CAP:g}")
    expected = {_call_key(str(item["pair_id"])): MAX_ATTEMPTS for item in packet}
    ledger = PersistentAttemptLedger(
        DIR / "authoring_physical_attempt_ledger.jsonl",
        stage=STAGE,
        expected_calls=expected,
        maximum_total_attempts=96,
    )
    completed = {str(row["pair_id"]): row for row in _jsonl(COMPLETED)}
    clients: dict[str, Any] = {}
    try:
        for index, item in enumerate(packet, start=1):
            pair_id = str(item["pair_id"])
            if pair_id in completed:
                continue
            endpoint_key = str(item["assigned_author_endpoint"])
            if endpoint_key not in clients:
                clients[endpoint_key] = make_client(_endpoint(configs["candidates"][endpoint_key]))
            client = clients[endpoint_key]
            endpoint = _endpoint(configs["candidates"][endpoint_key])
            call_key = _call_key(pair_id)
            terminal = ledger.terminal_row(call_key)
            if ledger.succeeded(call_key) and terminal and terminal.get("result"):
                completed[pair_id] = terminal["result"]
                write_jsonl(COMPLETED, list(completed.values()))
                continue
            if ledger.exhausted(call_key):
                continue
            messages = _messages(item)
            while not ledger.exhausted(call_key) and not ledger.succeeded(call_key):
                reservation = ledger.reserve(
                    call_key,
                    record_ids={"pair_id": pair_id, "author": endpoint_key},
                    prompt_sha256=sha256_text(canonical_json(messages)),
                )
                response = None
                try:
                    response, parsed = client.chat(
                        messages, temperature=0.0, max_tokens=MAX_OUTPUT_TOKENS,
                        seed=20260810 + index, response_schema=AuthoredPair, retries=1,
                    )
                    if parsed is None:
                        raise ValueError("structured authored pair missing")
                    row = _validate(parsed, item, endpoint_key)
                    ledger.finish(
                        reservation, succeeded=True, request_hash=response.request_hash,
                        usage=response.usage, error=None, result=row,
                        metadata={"endpoint": endpoint_key, "model": endpoint.model},
                    )
                    completed[pair_id] = row
                    write_jsonl(COMPLETED, list(completed.values()))
                except Exception as exc:
                    ledger.finish(
                        reservation, succeeded=False,
                        request_hash=response.request_hash if response else None,
                        usage=response.usage if response else None,
                        error=f"{type(exc).__name__}: {exc}",
                        metadata={"endpoint": endpoint_key, "model": endpoint.model},
                    )
                    messages = messages + [{"role": "user", "content": "The previous output failed the strict pair schema or scaffold validation. Return the complete minimal pair only."}]
            if index % 8 == 0 or index == 48:
                print(f"authoring progress {len(completed)}/48 attempts={ledger.started_attempts}", flush=True)
    finally:
        for client in clients.values():
            client.close()
    report = {
        "protocol": PROTOCOL,
        "status": "AUTHORING_COMPLETE_AWAITING_FIDELITY_REVIEW" if len(completed) == 48 else "AUTHORING_INCOMPLETE",
        "completed_pairs": len(completed),
        "completed_variants": len(completed) * 2,
        "attempts_started": ledger.started_attempts,
        "response_effect_or_judge_calls": 0,
        "private_paired_outcome_key_read": False,
        "construction_assignment_joined_to_visible_output": False,
    }
    write_json(DIR / "authoring_live_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
