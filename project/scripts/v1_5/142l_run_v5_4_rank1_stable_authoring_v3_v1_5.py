#!/usr/bin/env python3
"""Run outcome-blind V5.4 V3 authoring with an explicit shared retrieval cue."""

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


PROTOCOL = "pm-v1.5-v5.4-rank1-stable-authoring-v3"
STAGE = "v5_4_rank1_stable_authoring_v3"
DIR = ROOT / "outputs/pm_v1_5_v5_4_rank1_stable_authoring_v3_20260810"
PACKET = DIR / "authoring_v3_packet_private_outcome_blind.jsonl"
PLAN = DIR / "plan_report.json"
GATE = ROOT / "data/pm_v1_5_contracts/v5_4_fidelity_and_rank1_gate_v2.json"
ENDPOINTS = ROOT / "configs/pm_v1_5_role_decomposed_judge_qualification_v1.json"
COMPLETED = DIR / "authored_pairs_v3_outcome_blind.jsonl"
MAX_ATTEMPTS = 2
MAX_OUTPUT_TOKENS = 750
USD_CAP = 1.25


class UserTurnPairV3(StrictModel):
    pair_id: str = Field(min_length=1)
    shared_retrieval_cue: str = Field(min_length=1, max_length=80)
    variant_A_current_user_turn: str = Field(min_length=1)
    variant_B_current_user_turn: str = Field(min_length=1)


def _rows(path: Path) -> list[dict[str, Any]]:
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
    system = """Write exactly two alternative CURRENT USER turns continuing the exact locked public prefix. Never rewrite the prefix and never write an assistant response.

Trusted world evidence is the union of: (1) locked prefix, (2) original public current turn supplied for world/tone, and (3) verified strictly-prior candidate. The candidate is a trusted past fact/card, but it need not be copied into the turn. Invent no stronger action, result, time, diagnosis, identity, relationship, motive, or future fact.

Follow the private A/B construction instructions without naming them. The user turn creates or removes an opportunity for a PROSPECTIVE assistant contribution; the user must not impersonate or perform the assistant move. Preserve the same user, entity, topic, goal frame, tone, syntax, and approximate length. Change only the instructed current need, redundancy, resolution, or boundary factor.

Rank-1 stability is a hard pre-outcome construction gate. Choose one short natural shared_retrieval_cue of 1-6 words connected to the verified candidate and original current topic. Include that exact cue naturally in BOTH A and B. It is private construction metadata and must not mention retrieval, memory, candidates, resources, labels, components, routing, experiments, or outcomes. Do not copy the full candidate. Each turn must be 8-80 words. Return only the strict schema."""
    return [{"role": "system", "content": system}, {"role": "user", "content": canonical_json(item)}]


def _norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", text.casefold()))


def _content_tokens(text: str) -> set[str]:
    return {token for token in _norm(text).split() if len(token) >= 4}


def _validate(parsed: UserTurnPairV3, item: dict[str, Any], author: str) -> dict[str, Any]:
    if parsed.pair_id != item["pair_id"]:
        raise ValueError("pair identity mismatch")
    cue = " ".join(parsed.shared_retrieval_cue.split())
    a = " ".join(parsed.variant_A_current_user_turn.split())
    b = " ".join(parsed.variant_B_current_user_turn.split())
    if not 1 <= len(cue.split()) <= 6:
        raise ValueError("shared retrieval cue must be 1-6 words")
    if _norm(cue) not in _norm(a) or _norm(cue) not in _norm(b):
        raise ValueError("exact shared retrieval cue absent from A or B")
    if not (_content_tokens(cue) & _content_tokens(str(item["frozen_candidate_text"]))):
        raise ValueError("shared retrieval cue lacks a candidate content word")
    if a == b:
        raise ValueError("variant texts identical")
    aw, bw = len(a.split()), len(b.split())
    if not 8 <= aw <= 80 or not 8 <= bw <= 80:
        raise ValueError("variant word count outside 8-80")
    if max(aw, bw) / min(aw, bw) > 1.5:
        raise ValueError("variant word length ratio exceeds 1.5")
    similarity = SequenceMatcher(None, _norm(a), _norm(b)).ratio()
    if similarity < 0.35:
        raise ValueError("variant similarity below V3 minimum")
    surface = f"{cue} {a} {b}".casefold()
    forbidden = (
        "candidate_text", "resource_id", "low_opportunity", "incremental:",
        "construction assignment", "oracle action", "rank-1", "rank1", "retrieval cue",
    )
    if any(token in surface for token in forbidden):
        raise ValueError("authoring scaffold leaked")
    if _norm(str(item["frozen_candidate_text"])) in _norm(a + " " + b):
        raise ValueError("full candidate copied")
    return {
        "protocol": PROTOCOL,
        "pair_id": item["pair_id"],
        "semantic_family_id": item["semantic_family_id"],
        "component_private_lineage": item["component"],
        "assigned_author_endpoint": author,
        "source_dataset": item["source_dataset"],
        "source_formal_effect_group_id": item["source_formal_effect_group_id"],
        "source_state_id": item["source_state_id"],
        "user_id": item.get("user_id"),
        "session_id": item.get("session_id"),
        "turn_id": item.get("turn_id"),
        "dialogue_id": item.get("dialogue_id"),
        "exact_public_source_visible_prefix_locked": item["exact_public_source_visible_prefix_locked"],
        "shared_retrieval_cue_private_do_not_join_to_pm_features": cue,
        "variant_A_current_user_turn": a,
        "variant_B_current_user_turn": b,
        "pair_character_similarity": similarity,
        "pair_word_length_ratio": max(aw, bw) / min(aw, bw),
        "frozen_candidate": item["frozen_candidate"],
        "frozen_candidate_text": item["frozen_candidate_text"],
        "candidate_subtype": item["candidate_subtype"],
        "source_candidate_bge_m3_cosine_selection_diagnostic": item["source_candidate_bge_m3_cosine_selection_diagnostic"],
        "source_prefix_generated_or_modified": False,
        "construction_assignment_present_in_runtime": False,
        "paired_response_effect_or_oracle_outcome_read": False,
        "actual_rank1_status": "PENDING_MACHINE_RECOMPUTATION",
        "independent_fidelity_status": "PENDING_FRESH_V2_REVIEW",
    }


def _call_key(pair_id: str) -> str:
    return "v3author_" + sha256_text(f"{PROTOCOL}:{pair_id}")[:22]


def _estimate(packet: list[dict[str, Any]], configs: dict[str, Any]) -> dict[str, Any]:
    total = 0.0
    endpoints = {}
    for endpoint_key in sorted({row["assigned_author_endpoint"] for row in packet}):
        subset = [row for row in packet if row["assigned_author_endpoint"] == endpoint_key]
        raw = configs["candidates"][endpoint_key]
        input_tokens = int(sum(len(canonical_json(_messages(item))) for item in subset) / 4 * 1.5)
        output_tokens = len(subset) * MAX_OUTPUT_TOKENS
        upper = 2 * (
            input_tokens * float(raw["input_usd_per_million_tokens"])
            + output_tokens * float(raw["output_usd_per_million_tokens"])
        ) / 1_000_000
        endpoints[endpoint_key] = {"logical_calls": len(subset), "two_attempt_usd_upper_proxy": upper}
        total += upper
    return {"by_endpoint": endpoints, "two_attempt_total_usd_upper_proxy": total}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--accept-usd-cap", type=float)
    args = parser.parse_args()
    packet = _rows(PACKET)
    plan = json.loads(PLAN.read_text())
    gate = json.loads(GATE.read_text())
    configs = json.loads(ENDPOINTS.read_text())
    if len(packet) != 48 or plan["status"] != "V3_RANK1_STABLE_AUTHORING_PLAN_FROZEN_ZERO_API":
        raise SystemExit("V3 plan identity invalid")
    if not gate["authorization"]["outcome_blind_repair"] or gate["authorization"]["response_effect_calls"]:
        raise SystemExit("V3 authoring authorization invalid")
    estimate = _estimate(packet, configs)
    preflight = {
        "protocol": PROTOCOL,
        "status": "LIVE_READY" if estimate["two_attempt_total_usd_upper_proxy"] <= USD_CAP else "COST_BLOCKED",
        "logical_calls": 48,
        "maximum_physical_attempts": 96,
        "cost_estimate": estimate,
        "accepted_usd_cap_required": USD_CAP,
        "packet_sha256": sha256_file(PACKET),
        "plan_sha256": sha256_file(PLAN),
        "gate_sha256": sha256_file(GATE),
        "response_effect_calls": 0,
        "private_paired_outcome_key_read": False,
    }
    write_json(DIR / "authoring_v3_preflight.json", preflight)
    print(json.dumps(preflight, ensure_ascii=False, indent=2), flush=True)
    if not args.live:
        return
    if args.accept_usd_cap is None or args.accept_usd_cap < USD_CAP:
        raise SystemExit(f"live execution requires --accept-usd-cap {USD_CAP:g}")

    ledger = PersistentAttemptLedger(
        DIR / "authoring_v3_attempt_ledger.jsonl",
        stage=STAGE,
        expected_calls={_call_key(str(item["pair_id"])): MAX_ATTEMPTS for item in packet},
        maximum_total_attempts=96,
    )
    completed = {str(row["pair_id"]): row for row in _rows(COMPLETED)}
    clients: dict[str, Any] = {}
    try:
        for index, item in enumerate(packet, start=1):
            pair_id = str(item["pair_id"])
            if pair_id in completed:
                continue
            endpoint_key = str(item["assigned_author_endpoint"])
            endpoint = _endpoint(configs["candidates"][endpoint_key])
            if endpoint_key not in clients:
                clients[endpoint_key] = make_client(endpoint)
            call_key = _call_key(pair_id)
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
                    response, parsed = clients[endpoint_key].chat(
                        messages, temperature=0.0, max_tokens=MAX_OUTPUT_TOKENS,
                        seed=20260810 + index, response_schema=UserTurnPairV3, retries=1,
                    )
                    if parsed is None:
                        raise ValueError("structured V3 pair missing")
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
                    messages += [{"role": "user", "content": "The previous output failed the frozen V3 surface/cue gate. Return both complete turns again. Use one exact natural 1-6 word cue, connected to the verified candidate, verbatim in both turns; preserve a strict one-factor minimal pair."}]
            if index % 8 == 0 or index == 48:
                print(f"V3 authoring progress {len(completed)}/48 attempts={ledger.started_attempts}", flush=True)
    finally:
        for client in clients.values():
            client.close()
    report = {
        "protocol": PROTOCOL,
        "status": "V3_AUTHORING_COMPLETE_AWAITING_RANK1_AND_FIDELITY" if len(completed) == 48 else "V3_AUTHORING_INCOMPLETE",
        "completed_pairs": len(completed),
        "completed_variants": 2 * len(completed),
        "attempts_started": ledger.started_attempts,
        "response_effect_calls": 0,
        "private_paired_outcome_key_read": False,
    }
    write_json(DIR / "authoring_v3_live_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
