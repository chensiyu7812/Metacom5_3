#!/usr/bin/env python3
"""Outcome-blind third-family adjudication for the two single-reviewer flags."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Literal


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from pydantic import Field  # noqa: E402
from metacom_pm.api import Endpoint, make_client  # noqa: E402
from metacom_pm.attempt_ledger import PersistentAttemptLedger  # noqa: E402
from metacom_pm.contracts import StrictModel  # noqa: E402
from metacom_pm.io import canonical_json, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402

PROTOCOL = "pm-v1.5-v5.4-v4-fidelity-v2-single-flag-adjudication-v1"
DIR = ROOT / "outputs/pm_v1_5_v5_4_v4_fidelity_v2_20260810"
PACKET = DIR / "fidelity_v2_packet_private_assignment_outcome_blind.jsonl"
A = DIR / "fidelity_v2_REVIEWER_A.jsonl"
B = DIR / "fidelity_v2_REVIEWER_B.jsonl"
REPORT = DIR / "fidelity_v2_report.json"
ENDPOINTS = ROOT / "configs/pm_v1_5_role_decomposed_judge_qualification_v1.json"
IDS = ("v54v4pair_5af0620d4bfad3e37a", "v54v4pair_f58fd8f19371663cdb")

Tri = Literal["PASS", "FAIL", "UNRESOLVED"]
Event = Literal["ABSENT", "PRESENT", "UNRESOLVED"]


class Adjudication(StrictModel):
    pair_id: str = Field(min_length=1)
    world_fidelity_B: Tri
    assignment_fidelity_B: Tri
    unsupported_critical_fact: Event
    adjudicated_pair_projection: Tri
    concise_rationale: str = Field(min_length=1)


def rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def endpoint(raw: dict) -> Endpoint:
    return Endpoint(
        base_url=str(raw["base_url"]), model=str(raw["model"]), api_key_env=str(raw["api_key_env"]),
        timeout_seconds=240.0, family=str(raw["family"]), transport=str(raw["transport"]),
        supports_strict_json_schema=bool(raw["supports_strict_json_schema"]),
        temperature_mode=str(raw.get("temperature_mode") or "explicit"),
        max_output_tokens_parameter=str(raw.get("max_output_tokens_parameter") or "max_tokens"),
        anthropic_strict_tool_use=bool(raw.get("anthropic_strict_tool_use", False)),
        gemini_thinking_budget=raw.get("gemini_thinking_budget"),
        openai_reasoning_effort=raw.get("openai_reasoning_effort"),
    )


def messages(item: dict) -> list[dict[str, str]]:
    system = """You are the predeclared third-family outcome-blind adjudicator for exactly one disputed construction-fidelity pair. You see no author, actual Rank-1, response, requested action, quality, risk, function, cost, oracle, or outcome. Do not judge should-open or usefulness.

Apply these definitions exactly:
1. Trusted world evidence is the UNION of locked prefix, original public current turn, and verified strictly-prior source candidate.
2. A current user turn MAY explicitly restate a fact entailed by the verified prior candidate. That is not unsupported and is required by an ALREADY_VISIBLE low construction when applicable.
3. Candidate omission or current irrelevance is never world-fidelity failure.
4. A new past action/result, disclosure/non-disclosure history, time, diagnosis, identity/relationship, motive, acute-safety fact, future fact, or strengthened specificity not entailed by the trusted union is unsupported.
5. Assignment fidelity asks only whether the supplied descriptive instruction is realized, never whether a resource should be used.

Only variant B and the unsupported-critical field are disputed; all other required fields were agreed PASS/ABSENT. Return PASS projection only when world_fidelity_B and assignment_fidelity_B are PASS and unsupported_critical_fact is ABSENT. Preserve UNRESOLVED. Return only the strict schema."""
    return [{"role": "system", "content": system}, {"role": "user", "content": canonical_json(item)}]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--accept-usd-cap", type=float)
    args = parser.parse_args()
    packet = {row["pair_id"]: row for row in rows(PACKET)}
    a = {row["pair_id"]: row for row in rows(A)}
    b = {row["pair_id"]: row for row in rows(B)}
    report = json.loads(REPORT.read_text())
    if set(report["critical_pair_ids"]) != set(IDS) or report["status"] != "V4_FIDELITY_V2_FAIL_NO_REPRESENTATION_OR_EFFECT":
        raise RuntimeError("adjudication identity differs from frozen failure")
    adjudication_packet = [
        {
            "protocol": PROTOCOL,
            "pair": packet[pair_id],
            "reviewer_A_disputed_judgment": a[pair_id],
            "reviewer_B_disputed_judgment": b[pair_id],
            "other_pair_fields_agreed_pass_or_absent": True,
            "response_effect_or_oracle_outcome_visible": False,
        }
        for pair_id in IDS
    ]
    packet_path = DIR / "single_flag_adjudication_packet_outcome_blind.jsonl"
    write_jsonl(packet_path, adjudication_packet)
    preflight = {
        "protocol": PROTOCOL, "status": "LIVE_READY", "logical_calls": 2,
        "maximum_physical_attempts": 4, "accepted_usd_cap_required": 0.10,
        "adjudicator": "google_gemini_2_5_flash", "packet_sha256": sha256_file(packet_path),
        "response_effect_or_oracle_outcome_visible": False,
    }
    write_json(DIR / "single_flag_adjudication_preflight.json", preflight)
    print(json.dumps(preflight, ensure_ascii=False, indent=2), flush=True)
    if not args.live:
        return
    if args.accept_usd_cap is None or args.accept_usd_cap < 0.10:
        raise SystemExit("live adjudication requires --accept-usd-cap 0.10")
    configs = json.loads(ENDPOINTS.read_text())
    endpoint_key = "google_gemini_2_5_flash"
    ep = endpoint(configs["candidates"][endpoint_key])
    ledger = PersistentAttemptLedger(
        DIR / "single_flag_adjudication_attempt_ledger.jsonl", stage=PROTOCOL,
        expected_calls={"adjud_" + sha256_text(PROTOCOL + pair_id)[:20]: 2 for pair_id in IDS},
        maximum_total_attempts=4,
    )
    completed = {row["pair_id"]: row for row in rows(DIR / "single_flag_adjudication_completed.jsonl")}
    client = make_client(ep)
    try:
        for index, item in enumerate(adjudication_packet, start=1):
            pair_id = item["pair"]["pair_id"]
            key = "adjud_" + sha256_text(PROTOCOL + pair_id)[:20]
            prompt = messages(item)
            while pair_id not in completed and not ledger.exhausted(key):
                reservation = ledger.reserve(key, record_ids={"pair_id": pair_id}, prompt_sha256=sha256_text(canonical_json(prompt)))
                response = None
                try:
                    response, parsed = client.chat(prompt, temperature=0.0, max_tokens=700, seed=20260810 + index, response_schema=Adjudication, retries=1)
                    if parsed is None or parsed.pair_id != pair_id:
                        raise ValueError("adjudication schema/identity")
                    row = parsed.model_dump(mode="json")
                    expected_projection = "PASS" if row["world_fidelity_B"] == "PASS" and row["assignment_fidelity_B"] == "PASS" and row["unsupported_critical_fact"] == "ABSENT" else "UNRESOLVED" if "UNRESOLVED" in (row["world_fidelity_B"], row["assignment_fidelity_B"], row["unsupported_critical_fact"]) else "FAIL"
                    if row["adjudicated_pair_projection"] != expected_projection:
                        raise ValueError("projection inconsistent with adjudicated axes")
                    row.update({"protocol": PROTOCOL, "adjudicator": endpoint_key, "response_effect_or_oracle_outcome_visible": False})
                    ledger.finish(reservation, succeeded=True, request_hash=response.request_hash, usage=response.usage, error=None, result=row, metadata={"endpoint": endpoint_key, "model": ep.model})
                    completed[pair_id] = row
                    write_jsonl(DIR / "single_flag_adjudication_completed.jsonl", list(completed.values()))
                except Exception as exc:
                    ledger.finish(reservation, succeeded=False, request_hash=response.request_hash if response else None, usage=response.usage if response else None, error=f"{type(exc).__name__}: {exc}", metadata={"endpoint": endpoint_key, "model": ep.model})
                    prompt += [{"role": "user", "content": "Return all adjudication fields and make projection deterministic from the three disputed fields."}]
    finally:
        client.close()
    if len(completed) != 2:
        raise SystemExit("adjudication incomplete")
    outcome = {
        "protocol": PROTOCOL,
        "status": "ADJUDICATION_COMPLETE_OUTCOME_BLIND",
        "pair_projections": {pair_id: completed[pair_id]["adjudicated_pair_projection"] for pair_id in IDS},
        "all_disputed_pairs_pass": all(completed[pair_id]["adjudicated_pair_projection"] == "PASS" for pair_id in IDS),
        "response_effect_or_oracle_outcome_visible": False,
        "completed_sha256": sha256_file(DIR / "single_flag_adjudication_completed.jsonl"),
    }
    write_json(DIR / "single_flag_adjudication_report.json", outcome)
    print(json.dumps(outcome, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
