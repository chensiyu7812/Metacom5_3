#!/usr/bin/env python3
"""Outcome-blind repair of the one V4 pair with an absent target MP candidate."""

from __future__ import annotations

import argparse
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from pydantic import Field  # noqa: E402
from metacom_pm.api import Endpoint, make_client  # noqa: E402
from metacom_pm.attempt_ledger import PersistentAttemptLedger  # noqa: E402
from metacom_pm.contracts import StrictModel  # noqa: E402
from metacom_pm.io import canonical_json, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402


PROTOCOL = "pm-v1.5-v5.4-v4-rank1-absent-pair-repair-v1"
PAIR_ID = "v54v4pair_278d8eadbcf9412949"
DIR = ROOT / "outputs/pm_v1_5_v5_4_state_local_authoring_v4_20260810"
PACKET = DIR / "authoring_v4_packet_private_outcome_blind.jsonl"
AUTHORED = DIR / "authored_pairs_v4_outcome_blind.jsonl"
RANK1 = ROOT / "outputs/pm_v1_5_v5_4_v4_state_local_actual_rank1_20260810/report.json"
CONTRACT = ROOT / "data/pm_v1_5_contracts/v5_4_state_local_rank1_factorial_oracle_v1.json"
ENDPOINTS = ROOT / "configs/pm_v1_5_role_decomposed_judge_qualification_v1.json"
REPAIR = DIR / "rank1_absent_pair_repair_v1_outcome_blind.jsonl"
MERGED = DIR / "authored_pairs_v4_after_rank1_repair_outcome_blind.jsonl"


class Pair(StrictModel):
    pair_id: str = Field(min_length=1)
    variant_A_current_user_turn: str = Field(min_length=1)
    variant_B_current_user_turn: str = Field(min_length=1)


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _endpoint(raw: dict) -> Endpoint:
    return Endpoint(
        base_url=str(raw["base_url"]), model=str(raw["model"]), api_key_env=str(raw["api_key_env"]),
        timeout_seconds=240.0, family=str(raw["family"]), transport=str(raw["transport"]),
        supports_strict_json_schema=bool(raw["supports_strict_json_schema"]),
        temperature_mode=str(raw.get("temperature_mode") or "explicit"),
        max_output_tokens_parameter=str(raw.get("max_output_tokens_parameter") or "max_tokens"),
        anthropic_strict_tool_use=bool(raw.get("anthropic_strict_tool_use", False)),
        openai_reasoning_effort=raw.get("openai_reasoning_effort"),
    )


def _norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", text.casefold()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--accept-usd-cap", type=float)
    args = parser.parse_args()
    packet = {row["pair_id"]: row for row in _rows(PACKET)}
    authored = {row["pair_id"]: row for row in _rows(AUTHORED)}
    source = packet[PAIR_ID]
    old = authored[PAIR_ID]
    rank1 = json.loads(RANK1.read_text())
    contract = json.loads(CONTRACT.read_text())
    if rank1["status"] != "STATE_LOCAL_RANK1_MACHINE_FAIL_REPLENISH_BEFORE_FIDELITY":
        raise RuntimeError("repair requires the frozen Rank-1 failure")
    if not contract["current_authorization"]["outcome_blind_v4_state_authoring"]:
        raise RuntimeError("outcome-blind repair not authorized")
    endpoint_configs = json.loads(ENDPOINTS.read_text())
    endpoint_key = source["assigned_author_endpoint"]
    endpoint = _endpoint(endpoint_configs["candidates"][endpoint_key])
    system = """Repair exactly one outcome-blind CURRENT USER minimal pair. Keep the supplied public prefix unchanged and write no assistant response. The trusted past fact is that Nick and best friend Henry had a falling out due to an argument about jokes.

Variant A must keep the Henry/jokes topic visible but make the immediate goal unrelated to repairing that relationship. Variant B must keep the same Henry/jokes topic but leave a response-relevant relationship slot for prior personalization. Include the exact natural word "jokes" in BOTH turns so the production MP candidate pool is nonempty. Keep the same user, entity, topic, tone, syntax, and similar length; change one current-goal factor only. Invent no new event/result and do not copy the full candidate. Return only the strict schema."""
    payload = {
        "pair_id": PAIR_ID,
        "exact_locked_prefix": source["exact_public_source_visible_prefix_locked"],
        "original_public_current_turn_world_tone": source["original_current_user_turn_for_world_and_tone_only"],
        "old_failed_pair_for_repair_context": {
            "A": old["variant_A_current_user_turn"],
            "B": old["variant_B_current_user_turn"],
        },
        "response_effect_or_oracle_outcome_visible": False,
    }
    messages = [{"role": "system", "content": system}, {"role": "user", "content": canonical_json(payload)}]
    preflight = {
        "protocol": PROTOCOL,
        "status": "LIVE_READY",
        "logical_calls": 1,
        "maximum_physical_attempts": 2,
        "accepted_usd_cap_required": 0.05,
        "pair_id": PAIR_ID,
        "source_authored_sha256": sha256_file(AUTHORED),
        "rank1_failure_report_sha256": sha256_file(RANK1),
        "response_effect_or_oracle_outcome_read": False,
    }
    write_json(DIR / "rank1_absent_pair_repair_v1_preflight.json", preflight)
    print(json.dumps(preflight, ensure_ascii=False, indent=2), flush=True)
    if not args.live:
        return
    if args.accept_usd_cap is None or args.accept_usd_cap < 0.05:
        raise SystemExit("live repair requires --accept-usd-cap 0.05")
    call_key = "v4rank1repair_" + sha256_text(PROTOCOL + PAIR_ID)[:20]
    ledger = PersistentAttemptLedger(
        DIR / "rank1_absent_pair_repair_v1_attempt_ledger.jsonl",
        stage=PROTOCOL,
        expected_calls={call_key: 2},
        maximum_total_attempts=2,
    )
    client = make_client(endpoint)
    repaired = None
    try:
        while not ledger.exhausted(call_key) and not ledger.succeeded(call_key):
            reservation = ledger.reserve(call_key, record_ids={"pair_id": PAIR_ID}, prompt_sha256=sha256_text(canonical_json(messages)))
            response = None
            try:
                response, parsed = client.chat(messages, temperature=0.0, max_tokens=500, seed=20260810, response_schema=Pair, retries=1)
                if parsed is None or parsed.pair_id != PAIR_ID:
                    raise ValueError("repair schema/identity")
                a = " ".join(parsed.variant_A_current_user_turn.split())
                b = " ".join(parsed.variant_B_current_user_turn.split())
                if "jokes" not in _norm(a).split() or "jokes" not in _norm(b).split():
                    raise ValueError("exact jokes token absent")
                aw, bw = len(a.split()), len(b.split())
                similarity = SequenceMatcher(None, _norm(a), _norm(b)).ratio()
                if not 8 <= aw <= 80 or not 8 <= bw <= 80 or max(aw, bw) / min(aw, bw) > 1.5 or similarity < 0.25:
                    raise ValueError("minimal pair surface")
                repaired = {
                    **old,
                    "protocol": PROTOCOL,
                    "variant_A_current_user_turn": a,
                    "variant_B_current_user_turn": b,
                    "pair_character_similarity": similarity,
                    "pair_word_length_ratio": max(aw, bw) / min(aw, bw),
                    "supersedes_authored_sha256": sha256_text(canonical_json(old)),
                    "repair_reason": "TARGET_MP_CANDIDATE_ABSENT_BOTH_STATES_AFTER_PRODUCTION_RECOMPUTATION",
                    "repair_constraint": "exact jokes token in both current turns",
                    "response_effect_or_oracle_outcome_read": False,
                }
                ledger.finish(reservation, succeeded=True, request_hash=response.request_hash, usage=response.usage, error=None, result=repaired, metadata={"endpoint": endpoint_key, "model": endpoint.model})
            except Exception as exc:
                ledger.finish(reservation, succeeded=False, request_hash=response.request_hash if response else None, usage=response.usage if response else None, error=f"{type(exc).__name__}: {exc}", metadata={"endpoint": endpoint_key, "model": endpoint.model})
                messages += [{"role": "user", "content": "Return both complete turns again and include the exact standalone word jokes naturally in both."}]
    finally:
        client.close()
    if repaired is None:
        raise SystemExit("rank1 absent pair repair exhausted")
    write_jsonl(REPAIR, [repaired])
    authored[PAIR_ID] = repaired
    write_jsonl(MERGED, list(authored.values()))
    report = {
        "protocol": PROTOCOL,
        "status": "ONE_PAIR_REPAIRED_OUTCOME_BLIND_AWAITING_FULL_RANK1_RERUN",
        "pair_id": PAIR_ID,
        "attempts": ledger.started_attempts,
        "merged_pairs": len(authored),
        "response_effect_or_oracle_outcome_read": False,
        "repair_sha256": sha256_file(REPAIR),
        "merged_sha256": sha256_file(MERGED),
    }
    write_json(DIR / "rank1_absent_pair_repair_v1_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
