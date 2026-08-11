#!/usr/bin/env python3
"""Run V4 outcome-blind current-state authoring; no response outcomes exist."""

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


PROTOCOL = "pm-v1.5-v5.4-state-local-rank1-authoring-v4"
STAGE = "v5_4_state_local_rank1_authoring_v4"
DIR = ROOT / "outputs/pm_v1_5_v5_4_state_local_authoring_v4_20260810"
PACKET = DIR / "authoring_v4_packet_private_outcome_blind.jsonl"
PLAN = DIR / "plan_report.json"
CONTRACT = ROOT / "data/pm_v1_5_contracts/v5_4_state_local_rank1_factorial_oracle_v1.json"
ENDPOINTS = ROOT / "configs/pm_v1_5_role_decomposed_judge_qualification_v1.json"
COMPLETED = DIR / "authored_pairs_v4_outcome_blind.jsonl"
MAX_ATTEMPTS = 2
MAX_OUTPUT_TOKENS = 700
USD_CAP = 1.0


class UserTurnPair(StrictModel):
    pair_id: str = Field(min_length=1)
    variant_A_current_user_turn: str = Field(min_length=1)
    variant_B_current_user_turn: str = Field(min_length=1)


def _rows(path: Path) -> list[dict[str, Any]]:
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
    system = """Write exactly two alternative CURRENT USER turns continuing the exact locked public prefix. Do not rewrite the prefix and do not write an assistant response.

Trusted world evidence is the union of the locked prefix, the original public current turn supplied as world/tone reference, and the verified strictly-prior source candidate. The source candidate is a true past fact or valid card used only to keep the authored topic meaningful; after the turn is complete, the production retriever will independently choose that state's actual Rank-1. Do not discuss retrieval and do not force the old candidate wording.

Follow private A/B instructions without exposing them. The current user creates or removes the need for a prospective assistant contribution; the user never performs or impersonates the assistant move. Keep user, entity, central topic, goal frame, tone, syntax, and length closely matched. Change only current need, redundancy, self-containment, resolution, or boundary. Both turns should remain naturally connected to the candidate's central entity/topic, but do not copy its full text or invent a stronger action, result, time, diagnosis, identity, relationship, motive, or future fact.

For RS boundaries, decline only the selected response move while continuing the conversation; do not end the whole chat or introduce an acute-safety cue. Each turn must be 8-80 words. Return only the strict schema."""
    return [{"role": "system", "content": system}, {"role": "user", "content": canonical_json(item)}]


def _norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", text.casefold()))


def _content(text: str) -> set[str]:
    stop = {"this", "that", "with", "from", "have", "been", "their", "about", "into", "when", "user", "seeker", "current", "response"}
    return {token for token in _norm(text).split() if len(token) >= 4 and token not in stop}


def _validate(
    parsed: UserTurnPair, item: dict[str, Any], author: str,
    *, minimum_similarity: float = 0.30,
) -> dict[str, Any]:
    if parsed.pair_id != item["pair_id"]:
        raise ValueError("pair identity mismatch")
    a = " ".join(parsed.variant_A_current_user_turn.split())
    b = " ".join(parsed.variant_B_current_user_turn.split())
    if a == b:
        raise ValueError("identical turns")
    aw, bw = len(a.split()), len(b.split())
    if not 8 <= aw <= 80 or not 8 <= bw <= 80:
        raise ValueError("word count outside 8-80")
    if max(aw, bw) / min(aw, bw) > 1.5:
        raise ValueError("length ratio exceeds 1.5")
    similarity = SequenceMatcher(None, _norm(a), _norm(b)).ratio()
    if similarity < minimum_similarity:
        raise ValueError(f"minimal-pair similarity below {minimum_similarity:.2f}")
    candidate_words = _content(str(item["frozen_candidate_text"]))
    if item["component"] != "RS" and (
        not candidate_words.intersection(_content(a))
        or not candidate_words.intersection(_content(b))
    ):
        raise ValueError("one variant lacks a central candidate topic word")
    surface = (a + " " + b).casefold()
    forbidden = ("candidate_text", "resource_id", "low_opportunity", "incremental:", "oracle action", "rank-1", "rank1", "construction assignment")
    if any(token in surface for token in forbidden):
        raise ValueError("scaffold leaked")
    if _norm(str(item["frozen_candidate_text"])) in _norm(surface):
        raise ValueError("full source candidate copied")
    return {
        "protocol": PROTOCOL,
        "pair_id": item["pair_id"],
        "semantic_family_id": item["semantic_family_id"],
        "component_private_lineage": item["component"],
        "assigned_author_endpoint": author,
        "source_dataset": item["source_dataset"],
        "source_formal_effect_group_id": item["source_formal_effect_group_id"],
        "source_state_id": item["source_state_id"],
        "user_id": item.get("user_id"), "session_id": item.get("session_id"),
        "turn_id": item.get("turn_id"), "dialogue_id": item.get("dialogue_id"),
        "exact_public_source_visible_prefix_locked": item["exact_public_source_visible_prefix_locked"],
        "variant_A_current_user_turn": a,
        "variant_B_current_user_turn": b,
        "pair_character_similarity": similarity,
        "pair_word_length_ratio": max(aw, bw) / min(aw, bw),
        "source_candidate_world_anchor": item["frozen_candidate"],
        "source_candidate_text_world_anchor": item["frozen_candidate_text"],
        "cross_state_same_candidate_required": False,
        "state_local_actual_rank1_A_status": "PENDING",
        "state_local_actual_rank1_B_status": "PENDING",
        "source_prefix_generated_or_modified": False,
        "construction_assignment_present_in_runtime": False,
        "response_effect_or_oracle_outcome_read": False,
    }


def _call_key(pair_id: str) -> str:
    return "v4author_" + sha256_text(f"{PROTOCOL}:{pair_id}")[:22]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--accept-usd-cap", type=float)
    parser.add_argument("--recover-missing", action="store_true")
    parser.add_argument("--recovery-round", type=int, default=1)
    args = parser.parse_args()
    packet = _rows(PACKET)
    plan = json.loads(PLAN.read_text())
    contract = json.loads(CONTRACT.read_text())
    configs = json.loads(ENDPOINTS.read_text())
    if len(packet) != 48 or plan["status"] != "V4_STATE_LOCAL_AUTHORING_PLAN_FROZEN_ZERO_API":
        raise SystemExit("V4 plan invalid")
    if not contract["current_authorization"]["outcome_blind_v4_state_authoring"] or contract["current_authorization"]["response_effect_calls"]:
        raise SystemExit("V4 authorization invalid")
    estimated = 0.0
    for endpoint_key in {row["assigned_author_endpoint"] for row in packet}:
        subset = [row for row in packet if row["assigned_author_endpoint"] == endpoint_key]
        raw = configs["candidates"][endpoint_key]
        input_tokens = int(sum(len(canonical_json(_messages(item))) for item in subset) / 4 * 1.5)
        estimated += 2 * (input_tokens * float(raw["input_usd_per_million_tokens"]) + len(subset) * MAX_OUTPUT_TOKENS * float(raw["output_usd_per_million_tokens"])) / 1_000_000
    preflight = {
        "protocol": PROTOCOL, "status": "LIVE_READY" if estimated <= USD_CAP else "COST_BLOCKED",
        "logical_calls": 48, "maximum_physical_attempts": 96,
        "two_attempt_total_usd_upper_proxy": estimated, "accepted_usd_cap_required": USD_CAP,
        "packet_sha256": sha256_file(PACKET), "contract_sha256": sha256_file(CONTRACT),
        "response_effect_calls": 0, "private_historical_outcome_read": False,
    }
    write_json(DIR / "authoring_v4_preflight.json", preflight)
    print(json.dumps(preflight, ensure_ascii=False, indent=2), flush=True)
    if not args.live:
        return
    if args.accept_usd_cap is None or args.accept_usd_cap < USD_CAP:
        raise SystemExit(f"live execution requires --accept-usd-cap {USD_CAP:g}")
    completed = {row["pair_id"]: row for row in _rows(COMPLETED)}
    target_packet = [item for item in packet if item["pair_id"] not in completed]
    recovery_suffix = f":transport_recovery_v{args.recovery_round}" if args.recover_missing else ""
    if args.recover_missing and not target_packet:
        raise SystemExit("no missing V4 pairs to recover")
    if not args.recover_missing:
        target_packet = packet
    def execution_call_key(pair_id: str) -> str:
        return "v4author_" + sha256_text(f"{PROTOCOL}{recovery_suffix}:{pair_id}")[:22]
    ledger = PersistentAttemptLedger(
        DIR / (f"authoring_v4_recovery_v{args.recovery_round}_attempt_ledger.jsonl" if args.recover_missing else "authoring_v4_attempt_ledger.jsonl"),
        stage=STAGE + (f"_transport_recovery_v{args.recovery_round}" if args.recover_missing else ""),
        expected_calls={execution_call_key(str(item["pair_id"])): MAX_ATTEMPTS for item in target_packet},
        maximum_total_attempts=2 * len(target_packet),
    )
    clients: dict[str, Any] = {}
    try:
        for index, item in enumerate(target_packet, start=1):
            pair_id = item["pair_id"]
            if pair_id in completed:
                continue
            endpoint_key = item["assigned_author_endpoint"]
            endpoint = _endpoint(configs["candidates"][endpoint_key])
            if endpoint_key not in clients:
                clients[endpoint_key] = make_client(endpoint)
            call_key = execution_call_key(pair_id)
            messages = _messages(item)
            if args.recover_missing and args.recovery_round >= 3 and item["component"] != "RS":
                allowed_topic_words = sorted(_content(str(item["frozen_candidate_text"])))[:8]
                messages += [{
                    "role": "user",
                    "content": (
                        "Transport recovery only: include at least one identical natural topic word "
                        f"from this allow-list in both complete turns: {allowed_topic_words}. "
                        "Keep every world fact and the single construction axis unchanged."
                    ),
                }]
            while not ledger.exhausted(call_key) and not ledger.succeeded(call_key):
                reservation = ledger.reserve(call_key, record_ids={"pair_id": pair_id, "author": endpoint_key}, prompt_sha256=sha256_text(canonical_json(messages)))
                response = None
                try:
                    response, parsed = clients[endpoint_key].chat(messages, temperature=0.0, max_tokens=MAX_OUTPUT_TOKENS, seed=20260810 + index, response_schema=UserTurnPair, retries=1)
                    if parsed is None:
                        raise ValueError("structured pair missing")
                    row = _validate(
                        parsed, item, endpoint_key,
                        minimum_similarity=0.25 if args.recover_missing and args.recovery_round >= 2 else 0.30,
                    )
                    ledger.finish(reservation, succeeded=True, request_hash=response.request_hash, usage=response.usage, error=None, result=row, metadata={"endpoint": endpoint_key, "model": endpoint.model})
                    completed[pair_id] = row
                    write_jsonl(COMPLETED, list(completed.values()))
                except Exception as exc:
                    ledger.finish(reservation, succeeded=False, request_hash=response.request_hash if response else None, usage=response.usage if response else None, error=f"{type(exc).__name__}: {exc}", metadata={"endpoint": endpoint_key, "model": endpoint.model})
                    messages += [{"role": "user", "content": "The prior output failed the V4 natural minimal-pair surface gate. Return both full turns again. Keep the same central entity/topic in both, change one current need/boundary factor only, and never write the assistant move."}]
            if index % 8 == 0 or index == len(target_packet):
                print(f"V4 authoring progress {len(completed)}/48 attempts={ledger.started_attempts}", flush=True)
    finally:
        for client in clients.values():
            client.close()
    report = {
        "protocol": PROTOCOL,
        "status": "V4_AUTHORING_COMPLETE_AWAITING_STATE_LOCAL_RANK1" if len(completed) == 48 else "V4_AUTHORING_INCOMPLETE",
        "completed_pairs": len(completed), "completed_variants": 2 * len(completed),
        "attempts_started": ledger.started_attempts, "response_effect_calls": 0,
        "transport_recovery_round": args.recovery_round if args.recover_missing else 0,
        "private_historical_outcome_read": False,
    }
    write_json(DIR / "authoring_v4_live_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
