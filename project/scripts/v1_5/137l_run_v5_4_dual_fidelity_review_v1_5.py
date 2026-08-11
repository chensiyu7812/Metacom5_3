#!/usr/bin/env python3
"""Run two independent outcome-blind V5.4 construction-fidelity reviews."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Literal


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from pydantic import Field  # noqa: E402
from metacom_pm.api import Endpoint, make_client  # noqa: E402
from metacom_pm.attempt_ledger import PersistentAttemptLedger  # noqa: E402
from metacom_pm.contracts import StrictModel  # noqa: E402
from metacom_pm.io import canonical_json, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402

PROTOCOL = "pm-v1.5-v5.4-dual-fidelity-review-v1"
STAGE = "v5_4_construction_fidelity_single_pair"
DIR = ROOT / "outputs/pm_v1_5_v5_4_fidelity_review_20260810"
PACKET = DIR / "fidelity_packet_private_assignment_outcome_blind.jsonl"
PACKET_REPORT = DIR / "fidelity_packet_report.json"
CONTRACT = ROOT / "data/pm_v1_5_contracts/v5_4_fidelity_and_rank1_gate_v1.json"
ENDPOINTS = ROOT / "configs/pm_v1_5_role_decomposed_judge_qualification_v1.json"
MAX_ATTEMPTS = 2; MAX_OUTPUT_TOKENS = 850; USD_CAP = 2.0

Tri = Literal["PASS", "FAIL", "UNRESOLVED"]
Event = Literal["ABSENT", "PRESENT", "UNRESOLVED"]


class FidelityJudgment(StrictModel):
    pair_id: str = Field(min_length=1)
    world_fidelity_A: Tri
    world_fidelity_B: Tri
    dialogue_coherence_A: Tri
    dialogue_coherence_B: Tri
    assignment_fidelity_A: Tri
    assignment_fidelity_B: Tri
    single_axis_minimality: Tri
    unsupported_critical_fact: Event
    response_or_scaffold_leak: Event
    concise_rationale: str = Field(min_length=1)


def rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists(): return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def endpoint(raw: dict[str, Any]) -> Endpoint:
    return Endpoint(base_url=str(raw["base_url"]), model=str(raw["model"]), api_key_env=str(raw["api_key_env"]), timeout_seconds=240.0, family=str(raw["family"]), transport=str(raw["transport"]), supports_strict_json_schema=bool(raw["supports_strict_json_schema"]), temperature_mode=str(raw.get("temperature_mode") or "explicit"), max_output_tokens_parameter=str(raw.get("max_output_tokens_parameter") or "max_tokens"), anthropic_strict_tool_use=bool(raw.get("anthropic_strict_tool_use", False)), openai_reasoning_effort=raw.get("openai_reasoning_effort"))


def messages(item: dict[str, Any], reviewer_id: str) -> list[dict[str, str]]:
    system = f"""You are {reviewer_id}, independently auditing construction fidelity. You see no author identity, assistant response, requested action, paired outcome, quality, risk, function, cost, or other reviewer.

This is NOT a should-open or usefulness task. Do not decide whether a component ought to be used and do not predict which response wins.

Judge only:
- WORLD_FIDELITY A/B: can each variant be a faithful current continuation using the locked public prefix, original turn as world/tone reference, and verified prior candidate, without inventing a past result, diagnosis, identity/owner, relationship, acute-safety fact, or future fact? Present emotion/request wording is allowed.
- DIALOGUE_COHERENCE A/B: is each a natural continuation of the exact prefix? Empty prefixes and consecutive same-role public segmentation are allowed.
- ASSIGNMENT_FIDELITY A/B: does the wording implement its supplied descriptive construction instruction? This checks authoring compliance, not action value.
- SINGLE_AXIS_MINIMALITY: do A/B keep the same user, entity, topic, tone, goal frame, and burden while changing only the instructed response-need/redundancy/boundary factor?
- UNSUPPORTED_CRITICAL_FACT is PRESENT only for a newly asserted unsupported past event/result, diagnosis, identity/owner, relationship, acute-safety fact, or future fact.
- RESPONSE_OR_SCAFFOLD_LEAK is PRESENT only if a variant writes an assistant final response or exposes component/resource/construction/route/evaluator/outcome scaffolding.

The verified candidate is strictly-prior truth; its absence from the visible dialogue is not an invention. Return only the strict schema and a concise rationale."""
    return [{"role": "system", "content": system}, {"role": "user", "content": canonical_json(item)}]


def call_key(reviewer: str, pair_id: str) -> str:
    return "fid_" + sha256_text(f"{PROTOCOL}:{reviewer}:{pair_id}")[:24]


def estimate(packet: list[dict[str, Any]], configs: dict[str, Any]) -> dict[str, Any]:
    total = 0.0; result = {}
    for reviewer, endpoint_key in (("REVIEWER_A", "anthropic_claude_haiku_4_5"), ("REVIEWER_B", "openai_gpt_5_mini")):
        raw = configs["candidates"][endpoint_key]; chars = sum(len(canonical_json(messages(item, reviewer))) for item in packet); inp = int(chars / 4 * 1.5); out = len(packet) * MAX_OUTPUT_TOKENS
        two = 2 * (inp * float(raw["input_usd_per_million_tokens"]) + out * float(raw["output_usd_per_million_tokens"])) / 1_000_000; result[reviewer] = {"endpoint": endpoint_key, "logical_calls": 48, "two_attempt_usd_upper_proxy": two}; total += two
    return {"reviewers": result, "two_attempt_total_usd_upper_proxy": total}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--live", action="store_true"); parser.add_argument("--accept-usd-cap", type=float); args = parser.parse_args()
    packet = rows(PACKET); report = json.loads(PACKET_REPORT.read_text()); contract = json.loads(CONTRACT.read_text()); configs = json.loads(ENDPOINTS.read_text())
    if len(packet) != 48 or report["status"] != "FIDELITY_PACKET_FROZEN_READY" or not contract["downstream_authorization"]["fidelity_review"]: raise SystemExit("fidelity identity not ready")
    cost = estimate(packet, configs); preflight = {"protocol": PROTOCOL, "status": "LIVE_READY" if cost["two_attempt_total_usd_upper_proxy"] <= USD_CAP else "COST_BLOCKED", "packet_sha256": sha256_file(PACKET), "contract_sha256": sha256_file(CONTRACT), "logical_calls": 96, "maximum_physical_attempts": 192, "cost_estimate": cost, "accepted_usd_cap_required": USD_CAP, "author_identity_visible": False, "response_or_outcome_visible": False, "should_open_question_present": False, "private_paired_outcome_key_read": False}
    write_json(DIR / "fidelity_live_preflight.json", preflight); print(json.dumps(preflight, ensure_ascii=False, indent=2), flush=True)
    if not args.live: return
    if args.accept_usd_cap is None or args.accept_usd_cap < USD_CAP: raise SystemExit(f"live execution requires --accept-usd-cap {USD_CAP:g}")
    expected = {call_key(reviewer, str(item["pair_id"])): MAX_ATTEMPTS for reviewer in ("REVIEWER_A", "REVIEWER_B") for item in packet}; ledger = PersistentAttemptLedger(DIR / "fidelity_attempt_ledger.jsonl", stage=STAGE, expected_calls=expected, maximum_total_attempts=192)
    for reviewer, endpoint_key in (("REVIEWER_A", "anthropic_claude_haiku_4_5"), ("REVIEWER_B", "openai_gpt_5_mini")):
        output = DIR / f"fidelity_{reviewer}.jsonl"; completed = {str(row["pair_id"]): row for row in rows(output)}; ep = endpoint(configs["candidates"][endpoint_key]); client = make_client(ep)
        try:
            for index, item in enumerate(packet, start=1):
                pair_id = str(item["pair_id"])
                if pair_id in completed: continue
                key = call_key(reviewer, pair_id)
                if ledger.exhausted(key): continue
                prompt = messages(item, reviewer)
                while not ledger.exhausted(key) and not ledger.succeeded(key):
                    reservation = ledger.reserve(key, record_ids={"pair_id": pair_id, "reviewer": reviewer}, prompt_sha256=sha256_text(canonical_json(prompt))); response = None
                    try:
                        response, parsed = client.chat(prompt, temperature=0.0, max_tokens=MAX_OUTPUT_TOKENS, seed=20260810 + index, response_schema=FidelityJudgment, retries=1)
                        if parsed is None or parsed.pair_id != pair_id: raise ValueError("missing or mismatched fidelity judgment")
                        row = parsed.model_dump(mode="json"); row.update({"protocol": PROTOCOL, "reviewer_id": reviewer, "component": item["component"], "semantic_family_id": item["semantic_family_id"], "response_or_outcome_visible": False, "should_open_label_created": False})
                        ledger.finish(reservation, succeeded=True, request_hash=response.request_hash, usage=response.usage, error=None, result=row, metadata={"endpoint": endpoint_key, "model": ep.model}); completed[pair_id] = row; write_jsonl(output, list(completed.values()))
                    except Exception as exc:
                        ledger.finish(reservation, succeeded=False, request_hash=response.request_hash if response else None, usage=response.usage if response else None, error=f"{type(exc).__name__}: {exc}", metadata={"endpoint": endpoint_key, "model": ep.model}); prompt += [{"role": "user", "content": "The prior output failed strict schema validation. Return all fidelity fields and no should-open or outcome judgment."}]
                if index % 8 == 0 or index == 48: print(f"{reviewer} fidelity progress {len(completed)}/48 attempts={ledger.started_attempts}", flush=True)
        finally: client.close()
    a = len(rows(DIR / "fidelity_REVIEWER_A.jsonl")); b = len(rows(DIR / "fidelity_REVIEWER_B.jsonl")); final = {"protocol": PROTOCOL, "status": "FIDELITY_REVIEWS_COMPLETE_AWAITING_ANALYSIS" if a == b == 48 else "FIDELITY_REVIEWS_INCOMPLETE", "reviewer_A_complete": a, "reviewer_B_complete": b, "attempts_started": ledger.started_attempts, "response_or_outcome_visible": False, "private_paired_outcome_key_read": False}
    write_json(DIR / "fidelity_live_report.json", final); print(json.dumps(final, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__": main()
