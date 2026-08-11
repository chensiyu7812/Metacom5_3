#!/usr/bin/env python3
"""Run only the candidate-suitability role for calibration V2.

Claude Haiku 4.5 and GPT-5 mini independently judge the same fresh 64 items.
No reply, Q/F/risk judgment, arm identity, or private historical outcome is
available to this script.  Calls are single-item because the prior calibration
showed that batching can duplicate or omit identities.
"""

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


PROTOCOL = "pm-v1.5-v5.3-role-decomposed-calibration-v2"
EXECUTION_PROTOCOL = "pm-v1.5-v5.3-candidate-suitability-calibration-v2-single-item"
STAGE = "v5_3_candidate_suitability_calibration_v2_single_item"
DIR = ROOT / "outputs/pm_v1_5_v5_3_role_decomposed_calibration_v2_20260810"
PACKET = DIR / "candidate_suitability_packet_blind.jsonl"
ENDPOINTS = ROOT / "configs/pm_v1_5_role_decomposed_judge_qualification_v1.json"
MAX_OUTPUT_TOKENS = 900
MAX_ATTEMPTS = 2
USD_CAP = 2.0


CandidateTruth = Literal[
    "VALID_APPLICABLE",
    "VALID_REDUNDANT",
    "VALID_NOT_USEFUL",
    "INVALID_WRONG_OWNER_TIME_EVENT",
    "UNRESOLVED",
]


class CandidateJudgment(StrictModel):
    calibration_id: str = Field(min_length=1)
    candidate_truth: CandidateTruth
    current_evidence_ids: list[str] = Field(min_length=1, max_length=3)
    candidate_evidence_id: Literal["CANDIDATE_TEXT"]
    rationale: str = Field(min_length=1)
    uncertainty_note: str


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _endpoint(raw: dict[str, Any]) -> Endpoint:
    return Endpoint(
        base_url=str(raw["base_url"]),
        model=str(raw["model"]),
        api_key_env=str(raw["api_key_env"]),
        timeout_seconds=240.0,
        family=str(raw["family"]),
        transport=str(raw["transport"]),
        supports_strict_json_schema=bool(raw["supports_strict_json_schema"]),
        temperature_mode=str(raw.get("temperature_mode") or "explicit"),
        max_output_tokens_parameter=str(raw.get("max_output_tokens_parameter") or "max_tokens"),
        anthropic_strict_tool_use=bool(raw.get("anthropic_strict_tool_use", False)),
        gemini_thinking_budget=raw.get("gemini_thinking_budget"),
        openai_reasoning_effort=raw.get("openai_reasoning_effort"),
    )


def _messages(item: dict[str, Any], *, reviewer_id: str) -> list[dict[str, str]]:
    system = f"""You are {reviewer_id}, an independent candidate-suitability reviewer.
You see only the deployment-visible dialogue and one frozen actual Rank-1 candidate. You do not see replies, ON/OFF outcomes, quality, function, risk, cost, construction labels, or another reviewer.

Judge exactly one label:
- VALID_APPLICABLE: right owner/time/event and the candidate can add a specific nonredundant contribution to the current response.
- VALID_REDUNDANT: valid fact, but its material contribution is already explicit in the visible current dialogue.
- VALID_NOT_USEFUL: valid fact, but it would not materially help the current response act or goal.
- INVALID_WRONG_OWNER_TIME_EVENT: wrong person, time, event, version, or epistemic scope.
- UNRESOLVED: the supplied evidence cannot support a reliable decision.

Topical similarity and Rank-1 status are not proof of applicability. Do not assume the user wants advice. Select 1-3 supplied TURN evidence IDs and CANDIDATE_TEXT. The evidence IDs ground the rationale but do not force a positive label. Return only the strict schema for the supplied calibration_id.
"""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": canonical_json(item)},
    ]


def _validate(parsed: CandidateJudgment, item: dict[str, Any], *, reviewer_id: str) -> dict[str, Any]:
    if parsed.calibration_id != item["calibration_id"]:
        raise ValueError("calibration identity mismatch")
    turns = {str(row["evidence_id"]): str(row["text"]) for row in item["visible_dialogue"]}
    if len(parsed.current_evidence_ids) != len(set(parsed.current_evidence_ids)):
        raise ValueError("duplicate current evidence id")
    if not set(parsed.current_evidence_ids).issubset(turns):
        raise ValueError("unknown current evidence id")
    row = parsed.model_dump(mode="json")
    row["current_evidence"] = [
        {"evidence_id": evidence_id, "text": turns[evidence_id]}
        for evidence_id in row.pop("current_evidence_ids")
    ]
    row["candidate_evidence"] = {
        "evidence_id": row.pop("candidate_evidence_id"),
        "text": item["candidate"]["text"],
    }
    row.update({
        "protocol": PROTOCOL,
        "execution_protocol": EXECUTION_PROTOCOL,
        "reviewer_id": reviewer_id,
    })
    return row


def _call_key(reviewer_id: str, calibration_id: str) -> str:
    return "candv2_" + sha256_text(f"{EXECUTION_PROTOCOL}:{reviewer_id}:{calibration_id}")[:24]


def _estimate(packet: list[dict[str, Any]], configs: dict[str, Any]) -> dict[str, Any]:
    total = 0.0
    reviewers = {}
    for reviewer_id, endpoint_key in (
        ("REVIEWER_A", "anthropic_claude_haiku_4_5"),
        ("REVIEWER_B", "openai_gpt_5_mini"),
    ):
        raw = configs["candidates"][endpoint_key]
        chars = sum(len(canonical_json(_messages(item, reviewer_id=reviewer_id))) for item in packet)
        input_tokens = int(chars / 4 * 1.5)
        output_tokens = len(packet) * MAX_OUTPUT_TOKENS
        one_pass = (
            input_tokens * float(raw["input_usd_per_million_tokens"])
            + output_tokens * float(raw["output_usd_per_million_tokens"])
        ) / 1_000_000
        reviewers[reviewer_id] = {
            "endpoint": endpoint_key,
            "logical_calls": len(packet),
            "input_token_upper_proxy": input_tokens,
            "output_token_upper_proxy": output_tokens,
            "two_attempt_usd_upper_proxy": 2 * one_pass,
        }
        total += 2 * one_pass
    return {"reviewers": reviewers, "two_attempt_total_usd_upper_proxy": total}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--accept-usd-cap", type=float)
    parser.add_argument("--reviewer", choices=["A", "B", "both"], default="both")
    parser.add_argument("--limit-new-calls", type=int)
    args = parser.parse_args()

    packet = _jsonl(PACKET)
    manifest = json.loads((DIR / "manifest.json").read_text())
    configs = json.loads(ENDPOINTS.read_text())
    if len(packet) != 64 or sha256_file(PACKET) != manifest["hashes"]["candidate"]:
        raise SystemExit("frozen candidate packet identity mismatch")
    estimate = _estimate(packet, configs)
    preflight = {
        "protocol": PROTOCOL,
        "execution_protocol": EXECUTION_PROTOCOL,
        "status": "LIVE_READY" if estimate["two_attempt_total_usd_upper_proxy"] <= USD_CAP else "COST_BLOCKED",
        "packet_sha256": sha256_file(PACKET),
        "endpoint_config_sha256": sha256_file(ENDPOINTS),
        "single_item_calls": True,
        "logical_calls": 128,
        "maximum_physical_attempts": 256,
        "cost_estimate": estimate,
        "accepted_usd_cap_required": USD_CAP,
        "other_role_packets_read": False,
        "private_key_read": False,
    }
    write_json(DIR / "candidate_live_preflight.json", preflight)
    print(json.dumps(preflight, ensure_ascii=False, indent=2), flush=True)
    if not args.live:
        return
    if args.accept_usd_cap is None or args.accept_usd_cap < USD_CAP:
        raise SystemExit(f"live execution requires --accept-usd-cap {USD_CAP:g}")

    choices = []
    if args.reviewer in {"A", "both"}:
        choices.append(("REVIEWER_A", "anthropic_claude_haiku_4_5"))
    if args.reviewer in {"B", "both"}:
        choices.append(("REVIEWER_B", "openai_gpt_5_mini"))
    expected = {
        _call_key(reviewer_id, str(item["calibration_id"])): MAX_ATTEMPTS
        for reviewer_id in ("REVIEWER_A", "REVIEWER_B")
        for item in packet
    }
    ledger = PersistentAttemptLedger(
        DIR / "candidate_physical_attempt_ledger.jsonl",
        stage=STAGE,
        expected_calls=expected,
        maximum_total_attempts=256,
    )

    for reviewer_id, endpoint_key in choices:
        endpoint = _endpoint(configs["candidates"][endpoint_key])
        client = make_client(endpoint)
        completed_path = DIR / f"candidate_reviewer_{reviewer_id[-1]}_completed.jsonl"
        completed = {str(row["calibration_id"]): row for row in _jsonl(completed_path)}
        new_calls = 0
        try:
            for index, item in enumerate(packet, start=1):
                calibration_id = str(item["calibration_id"])
                if calibration_id in completed:
                    continue
                if args.limit_new_calls is not None and new_calls >= args.limit_new_calls:
                    break
                call_key = _call_key(reviewer_id, calibration_id)
                terminal = ledger.terminal_row(call_key)
                if ledger.succeeded(call_key) and terminal and terminal.get("result"):
                    completed[calibration_id] = terminal["result"]
                    write_jsonl(completed_path, list(completed.values()))
                    continue
                if ledger.exhausted(call_key):
                    continue
                messages = _messages(item, reviewer_id=reviewer_id)
                prompt_hash = sha256_text(canonical_json(messages))
                while not ledger.exhausted(call_key) and not ledger.succeeded(call_key):
                    reservation = ledger.reserve(
                        call_key,
                        record_ids={"reviewer_id": reviewer_id, "calibration_id": calibration_id},
                        prompt_sha256=prompt_hash,
                    )
                    response = None
                    try:
                        response, parsed = client.chat(
                            messages,
                            temperature=0.0,
                            max_tokens=MAX_OUTPUT_TOKENS,
                            seed=20260810 + index,
                            response_schema=CandidateJudgment,
                            retries=1,
                        )
                        if parsed is None:
                            raise ValueError("structured candidate judgment missing")
                        row = _validate(parsed, item, reviewer_id=reviewer_id)
                        ledger.finish(
                            reservation,
                            succeeded=True,
                            request_hash=response.request_hash,
                            usage=response.usage,
                            error=None,
                            result=row,
                            metadata={"endpoint": endpoint_key, "model": endpoint.model},
                        )
                        completed[calibration_id] = row
                        write_jsonl(completed_path, list(completed.values()))
                    except Exception as exc:
                        ledger.finish(
                            reservation,
                            succeeded=False,
                            request_hash=response.request_hash if response else None,
                            usage=response.usage if response else None,
                            error=f"{type(exc).__name__}: {exc}",
                            metadata={"endpoint": endpoint_key, "model": endpoint.model},
                        )
                        messages = messages + [{
                            "role": "user",
                            "content": "The prior output failed exact schema or evidence-ID validation. Return one complete corrected judgment for the same calibration_id using only supplied IDs.",
                        }]
                        prompt_hash = sha256_text(canonical_json(messages))
                new_calls += 1
                if index % 8 == 0 or index == len(packet):
                    print(f"{reviewer_id} progress {len(completed)}/64 attempts={ledger.started_attempts}", flush=True)
        finally:
            client.close()

    report = {
        "protocol": PROTOCOL,
        "execution_protocol": EXECUTION_PROTOCOL,
        "status": "CANDIDATE_REVIEW_PROGRESS",
        "reviewer_A_complete": len(_jsonl(DIR / "candidate_reviewer_A_completed.jsonl")),
        "reviewer_B_complete": len(_jsonl(DIR / "candidate_reviewer_B_completed.jsonl")),
        "attempts_started": ledger.started_attempts,
        "private_key_read": False,
    }
    if report["reviewer_A_complete"] == report["reviewer_B_complete"] == 64:
        report["status"] = "BOTH_CANDIDATE_REVIEWS_COMPLETE_AWAITING_FREEZE_ANALYSIS"
    write_json(DIR / "candidate_live_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
