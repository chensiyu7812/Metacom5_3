#!/usr/bin/env python3
"""Run fresh dual fidelity V2 review for the complete V4 panel."""

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

PROTOCOL = "pm-v1.5-v5.4-v4-dual-fidelity-v2"
DIR = ROOT / "outputs/pm_v1_5_v5_4_v4_fidelity_v2_20260810"
PACKET = DIR / "fidelity_v2_packet_private_assignment_outcome_blind.jsonl"
PACKET_REPORT = DIR / "packet_report.json"
CONTRACT = ROOT / "data/pm_v1_5_contracts/v5_4_state_local_rank1_factorial_oracle_v1.json"
ENDPOINTS = ROOT / "configs/pm_v1_5_role_decomposed_judge_qualification_v1.json"
MAX_ATTEMPTS = 2
MAX_OUTPUT_TOKENS = 850
USD_CAP = 2.0

Tri = Literal["PASS", "FAIL", "UNRESOLVED"]
Event = Literal["ABSENT", "PRESENT", "UNRESOLVED"]


class Judgment(StrictModel):
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
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def endpoint(raw: dict[str, Any]) -> Endpoint:
    return Endpoint(
        base_url=str(raw["base_url"]), model=str(raw["model"]), api_key_env=str(raw["api_key_env"]),
        timeout_seconds=240.0, family=str(raw["family"]), transport=str(raw["transport"]),
        supports_strict_json_schema=bool(raw["supports_strict_json_schema"]),
        temperature_mode=str(raw.get("temperature_mode") or "explicit"),
        max_output_tokens_parameter=str(raw.get("max_output_tokens_parameter") or "max_tokens"),
        anthropic_strict_tool_use=bool(raw.get("anthropic_strict_tool_use", False)),
        openai_reasoning_effort=raw.get("openai_reasoning_effort"),
    )


def messages(item: dict[str, Any], reviewer: str) -> list[dict[str, str]]:
    system = f"""You are {reviewer}, independently auditing construction fidelity. You see no author identity, actual post-authoring Rank-1 identity, assistant response, requested action, paired outcome, quality, risk, function, cost, oracle, or other reviewer. This is NOT a should-open/usefulness task.

Trusted world evidence is the UNION of the exact locked public prefix, the original public current turn supplied as a world/tone reference, and the verified strictly-prior source candidate. Candidate omission or current irrelevance is NOT world-fidelity failure and must not be judged here.

Judge only:
- WORLD_FIDELITY A/B: no newly invented or strengthened past action/result, time, diagnosis, identity/owner, relationship, motive, acute-safety fact, or future fact beyond the trusted union. Ordinary present feeling/request wording is allowed.
- DIALOGUE_COHERENCE A/B: natural current-user continuation of the exact prefix, preserving public segmentation as given.
- ASSIGNMENT_FIDELITY A/B: wording follows its descriptive construction instruction. This is compliance, never action value.
- SINGLE_AXIS_MINIMALITY: same user, entity, central topic, tone, goal frame, and approximate burden, changing only the instructed current need/redundancy/self-containment/resolution/boundary factor.
- UNSUPPORTED_CRITICAL_FACT: PRESENT only for a concrete unsupported or strengthened critical fact as defined above; omission is never PRESENT.
- RESPONSE_OR_SCAFFOLD_LEAK: PRESENT only if a variant writes the assistant's final response or exposes resource/component/construction/route/evaluator/outcome scaffolding.

For RS, the selected card is a PROSPECTIVE assistant move. The user turn creates, resolves, or declines the opportunity; it must not itself be required to perform the assistant move. A/B are different states and need not share a post-authoring candidate. Return only the strict schema."""
    return [{"role": "system", "content": system}, {"role": "user", "content": canonical_json(item)}]


def call_key(reviewer: str, pair_id: str) -> str:
    return "v4fid_" + sha256_text(f"{PROTOCOL}:{reviewer}:{pair_id}")[:22]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--accept-usd-cap", type=float)
    args = parser.parse_args()
    packet = rows(PACKET)
    packet_report = json.loads(PACKET_REPORT.read_text())
    contract = json.loads(CONTRACT.read_text())
    configs = json.loads(ENDPOINTS.read_text())
    if len(packet) != 48 or packet_report["status"] != "V4_FIDELITY_V2_PACKET_FROZEN_READY":
        raise SystemExit("V4 fidelity packet invalid")
    if not contract["current_authorization"]["fresh_fidelity_review_after_complete_machine_pass"]:
        raise SystemExit("fidelity V2 not authorized")
    cost = 0.0
    for reviewer, endpoint_key in (("REVIEWER_A", "anthropic_claude_haiku_4_5"), ("REVIEWER_B", "openai_gpt_5_mini")):
        raw = configs["candidates"][endpoint_key]
        inp = int(sum(len(canonical_json(messages(item, reviewer))) for item in packet) / 4 * 1.5)
        cost += 2 * (inp * float(raw["input_usd_per_million_tokens"]) + 48 * MAX_OUTPUT_TOKENS * float(raw["output_usd_per_million_tokens"])) / 1_000_000
    preflight = {
        "protocol": PROTOCOL, "status": "LIVE_READY" if cost <= USD_CAP else "COST_BLOCKED",
        "logical_calls": 96, "maximum_physical_attempts": 192,
        "two_attempt_total_usd_upper_proxy": cost, "accepted_usd_cap_required": USD_CAP,
        "packet_sha256": sha256_file(PACKET), "contract_sha256": sha256_file(CONTRACT),
        "author_rank1_response_outcome_visible": False,
    }
    write_json(DIR / "fidelity_v2_preflight.json", preflight)
    print(json.dumps(preflight, ensure_ascii=False, indent=2), flush=True)
    if not args.live:
        return
    if args.accept_usd_cap is None or args.accept_usd_cap < USD_CAP:
        raise SystemExit(f"live review requires --accept-usd-cap {USD_CAP:g}")
    ledger = PersistentAttemptLedger(
        DIR / "fidelity_v2_attempt_ledger.jsonl", stage=PROTOCOL,
        expected_calls={call_key(reviewer, item["pair_id"]): MAX_ATTEMPTS for reviewer in ("REVIEWER_A", "REVIEWER_B") for item in packet},
        maximum_total_attempts=192,
    )
    for reviewer, endpoint_key in (("REVIEWER_A", "anthropic_claude_haiku_4_5"), ("REVIEWER_B", "openai_gpt_5_mini")):
        output = DIR / f"fidelity_v2_{reviewer}.jsonl"
        completed = {row["pair_id"]: row for row in rows(output)}
        ep = endpoint(configs["candidates"][endpoint_key])
        client = make_client(ep)
        try:
            for index, item in enumerate(packet, start=1):
                pair_id = item["pair_id"]
                if pair_id in completed:
                    continue
                key = call_key(reviewer, pair_id)
                prompt = messages(item, reviewer)
                while not ledger.exhausted(key) and not ledger.succeeded(key):
                    reservation = ledger.reserve(key, record_ids={"pair_id": pair_id, "reviewer": reviewer}, prompt_sha256=sha256_text(canonical_json(prompt)))
                    response = None
                    try:
                        response, parsed = client.chat(prompt, temperature=0.0, max_tokens=MAX_OUTPUT_TOKENS, seed=20260810 + index, response_schema=Judgment, retries=1)
                        if parsed is None or parsed.pair_id != pair_id:
                            raise ValueError("fidelity schema/identity")
                        row = parsed.model_dump(mode="json")
                        row.update({"protocol": PROTOCOL, "reviewer_id": reviewer, "component": item["component"], "response_or_outcome_visible": False, "should_open_label_created": False})
                        ledger.finish(reservation, succeeded=True, request_hash=response.request_hash, usage=response.usage, error=None, result=row, metadata={"endpoint": endpoint_key, "model": ep.model})
                        completed[pair_id] = row
                        write_jsonl(output, list(completed.values()))
                    except Exception as exc:
                        ledger.finish(reservation, succeeded=False, request_hash=response.request_hash if response else None, usage=response.usage if response else None, error=f"{type(exc).__name__}: {exc}", metadata={"endpoint": endpoint_key, "model": ep.model})
                        prompt += [{"role": "user", "content": "Return all strict fidelity fields. Do not answer should-open, usefulness, Rank-1, or outcome questions."}]
                if index % 8 == 0 or index == 48:
                    print(f"{reviewer} V2 fidelity {len(completed)}/48 attempts={ledger.started_attempts}", flush=True)
        finally:
            client.close()
    a = len(rows(DIR / "fidelity_v2_REVIEWER_A.jsonl"))
    b = len(rows(DIR / "fidelity_v2_REVIEWER_B.jsonl"))
    report = {
        "protocol": PROTOCOL,
        "status": "V4_FIDELITY_V2_COMPLETE_AWAITING_ANALYSIS" if a == b == 48 else "V4_FIDELITY_V2_INCOMPLETE",
        "reviewer_A": a, "reviewer_B": b, "attempts": ledger.started_attempts,
        "response_or_outcome_visible": False,
    }
    write_json(DIR / "fidelity_v2_live_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
