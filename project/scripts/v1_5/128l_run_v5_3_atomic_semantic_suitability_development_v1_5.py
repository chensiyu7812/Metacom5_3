#!/usr/bin/env python3
"""Run two independent atomic-axis semantic reviews on the V2 dev packet."""

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


PROTOCOL = "pm-v1.5-v5.3-atomic-semantic-suitability-development-v1"
STAGE = "v5_3_atomic_semantic_suitability_development_single_item"
DIR = ROOT / "outputs/pm_v1_5_v5_3_role_decomposed_calibration_v2_20260810"
PACKET = DIR / "candidate_suitability_packet_blind.jsonl"
CONTRACT = ROOT / "data/pm_v1_5_contracts/v5_3_atomic_semantic_suitability_calibration_v1.json"
ENDPOINTS = ROOT / "configs/pm_v1_5_role_decomposed_judge_qualification_v1.json"
MAX_OUTPUT_TOKENS = 1400
MAX_ATTEMPTS = 2
USD_CAP = 3.0


AxisLabel = Literal["YES", "NO", "UNRESOLVED"]


class AxisJudgment(StrictModel):
    label: AxisLabel
    current_evidence_id: str = Field(min_length=1)
    rationale: str = Field(min_length=1)


class AtomicJudgment(StrictModel):
    calibration_id: str = Field(min_length=1)
    current_goal_entity_fit: AxisJudgment
    specific_contribution_already_visible: AxisJudgment
    component_function_can_change_response: AxisJudgment
    current_boundary_permits_component: AxisJudgment
    candidate_evidence_id: Literal["CANDIDATE_TEXT"]
    uncertainty_note: str


AXIS_FIELDS = (
    "current_goal_entity_fit",
    "specific_contribution_already_visible",
    "component_function_can_change_response",
    "current_boundary_permits_component",
)
COMPONENT_MINIMUMS = {
    "MP": "A verified preference, constraint, profile, or relationship fact must materially personalize or constrain the current response. A name or topical echo is insufficient.",
    "MS": "A specific strictly-prior observation must accurately bridge the current thread, unresolved distinction, or continuity need.",
    "ME": "A specific past episode or action-result must change whether or how a present action, warning, or option is framed. Same-topic context alone is insufficient.",
    "RS": "The selected card's one atomic move must fit the current dialogue phase and must not already have been performed or explicitly declined.",
}


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


def _messages(item: dict[str, Any], *, reviewer_id: str) -> list[dict[str, str]]:
    component = str(item["component"])
    system = f"""You are {reviewer_id}, independently reviewing four atomic semantic axes. You see no response, ON/OFF outcome, function, risk, cost, prior composite label, or other reviewer.

Treat CANDIDATE_TEXT and its typed metadata as a machine-verified, same-user, strictly-prior candidate. Do NOT call it invalid merely because the prior fact is absent from the current dialogue. Judge only current semantic suitability.

For each axis return YES, NO, or UNRESOLVED and exactly one supplied TURN evidence id:
1. current_goal_entity_fit: can the candidate's SPECIFIC contribution bear on the current entity, goal, tension, or response need, rather than merely share a topic?
2. specific_contribution_already_visible: is the material contribution the candidate would add already explicit in the visible dialogue?
3. component_function_can_change_response: can the contribution change response content or response act in a grounded way under this component definition?
4. current_boundary_permits_component: does the current boundary permit this component, considering advice/listen, repetition, burden, and acute safety?

Component={component}. Minimum: {COMPONENT_MINIMUMS[component]}

Do not output a composite OPEN/OFF label. Do not infer response outcomes. Evidence selection never forces YES. Use UNRESOLVED when the visible evidence cannot support the axis. Return only the strict schema for this calibration_id.
"""
    return [{"role": "system", "content": system}, {"role": "user", "content": canonical_json(item)}]


def _validate(parsed: AtomicJudgment, item: dict[str, Any], reviewer_id: str) -> dict[str, Any]:
    if parsed.calibration_id != item["calibration_id"]:
        raise ValueError("calibration identity mismatch")
    turns = {str(row["evidence_id"]): str(row["text"]) for row in item["visible_dialogue"]}
    row = parsed.model_dump(mode="json")
    for field in AXIS_FIELDS:
        evidence_id = str(row[field].pop("current_evidence_id"))
        if evidence_id not in turns:
            raise ValueError(f"{field} unknown evidence id")
        row[field]["current_evidence"] = {"evidence_id": evidence_id, "text": turns[evidence_id]}
    row["candidate_evidence"] = {
        "evidence_id": row.pop("candidate_evidence_id"),
        "text": item["candidate"]["text"],
    }
    row.update({"protocol": PROTOCOL, "reviewer_id": reviewer_id})
    return row


def _call_key(reviewer_id: str, calibration_id: str) -> str:
    return "atomic_" + sha256_text(f"{PROTOCOL}:{reviewer_id}:{calibration_id}")[:24]


def _estimate(packet: list[dict[str, Any]], configs: dict[str, Any]) -> dict[str, Any]:
    total = 0.0
    reviewers = {}
    for reviewer_id, endpoint_key in (("REVIEWER_A", "anthropic_claude_haiku_4_5"), ("REVIEWER_B", "openai_gpt_5_mini")):
        raw = configs["candidates"][endpoint_key]
        chars = sum(len(canonical_json(_messages(item, reviewer_id=reviewer_id))) for item in packet)
        input_tokens = int(chars / 4 * 1.5)
        output_tokens = len(packet) * MAX_OUTPUT_TOKENS
        one_pass = (input_tokens * float(raw["input_usd_per_million_tokens"]) + output_tokens * float(raw["output_usd_per_million_tokens"])) / 1_000_000
        reviewers[reviewer_id] = {"endpoint": endpoint_key, "logical_calls": 64, "two_attempt_usd_upper_proxy": 2 * one_pass}
        total += 2 * one_pass
    return {"reviewers": reviewers, "two_attempt_total_usd_upper_proxy": total}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--accept-usd-cap", type=float)
    parser.add_argument("--reviewer", choices=["A", "B", "both"], default="both")
    args = parser.parse_args()
    packet = _jsonl(PACKET)
    manifest = json.loads((DIR / "manifest.json").read_text())
    configs = json.loads(ENDPOINTS.read_text())
    if len(packet) != 64 or sha256_file(PACKET) != manifest["hashes"]["candidate"]:
        raise SystemExit("frozen packet mismatch")
    estimate = _estimate(packet, configs)
    preflight = {
        "protocol": PROTOCOL, "status": "LIVE_READY" if estimate["two_attempt_total_usd_upper_proxy"] <= USD_CAP else "COST_BLOCKED",
        "packet_sha256": sha256_file(PACKET), "atomic_contract_sha256": sha256_file(CONTRACT),
        "logical_calls": 128, "maximum_physical_attempts": 256,
        "cost_estimate": estimate, "accepted_usd_cap_required": USD_CAP,
        "prior_composite_labels_read": False, "other_roles_read": False, "private_outcome_key_read": False,
    }
    write_json(DIR / "atomic_semantic_live_preflight.json", preflight)
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
    expected = {_call_key(reviewer_id, str(item["calibration_id"])): MAX_ATTEMPTS for reviewer_id in ("REVIEWER_A", "REVIEWER_B") for item in packet}
    ledger = PersistentAttemptLedger(
        DIR / "atomic_semantic_physical_attempt_ledger.jsonl", stage=STAGE,
        expected_calls=expected, maximum_total_attempts=256,
    )
    for reviewer_id, endpoint_key in choices:
        endpoint = _endpoint(configs["candidates"][endpoint_key])
        client = make_client(endpoint)
        path = DIR / f"atomic_semantic_reviewer_{reviewer_id[-1]}_completed.jsonl"
        completed = {str(row["calibration_id"]): row for row in _jsonl(path)}
        try:
            for index, item in enumerate(packet, start=1):
                calibration_id = str(item["calibration_id"])
                if calibration_id in completed:
                    continue
                call_key = _call_key(reviewer_id, calibration_id)
                terminal = ledger.terminal_row(call_key)
                if ledger.succeeded(call_key) and terminal and terminal.get("result"):
                    completed[calibration_id] = terminal["result"]
                    write_jsonl(path, list(completed.values()))
                    continue
                if ledger.exhausted(call_key):
                    continue
                messages = _messages(item, reviewer_id=reviewer_id)
                prompt_hash = sha256_text(canonical_json(messages))
                while not ledger.exhausted(call_key) and not ledger.succeeded(call_key):
                    reservation = ledger.reserve(call_key, record_ids={"reviewer_id": reviewer_id, "calibration_id": calibration_id}, prompt_sha256=prompt_hash)
                    response = None
                    try:
                        response, parsed = client.chat(messages, temperature=0.0, max_tokens=MAX_OUTPUT_TOKENS, seed=20260810 + index, response_schema=AtomicJudgment, retries=1)
                        if parsed is None:
                            raise ValueError("structured atomic judgment missing")
                        row = _validate(parsed, item, reviewer_id)
                        ledger.finish(reservation, succeeded=True, request_hash=response.request_hash, usage=response.usage, error=None, result=row, metadata={"endpoint": endpoint_key, "model": endpoint.model})
                        completed[calibration_id] = row
                        write_jsonl(path, list(completed.values()))
                    except Exception as exc:
                        ledger.finish(reservation, succeeded=False, request_hash=response.request_hash if response else None, usage=response.usage if response else None, error=f"{type(exc).__name__}: {exc}", metadata={"endpoint": endpoint_key, "model": endpoint.model})
                        messages = messages + [{"role": "user", "content": "The prior output failed strict schema/evidence validation. Return the complete four-axis judgment with exactly one supplied TURN id per axis."}]
                        prompt_hash = sha256_text(canonical_json(messages))
                if index % 8 == 0 or index == 64:
                    print(f"{reviewer_id} atomic progress {len(completed)}/64 attempts={ledger.started_attempts}", flush=True)
        finally:
            client.close()
    report = {
        "protocol": PROTOCOL,
        "status": "ATOMIC_REVIEW_PROGRESS",
        "reviewer_A_complete": len(_jsonl(DIR / "atomic_semantic_reviewer_A_completed.jsonl")),
        "reviewer_B_complete": len(_jsonl(DIR / "atomic_semantic_reviewer_B_completed.jsonl")),
        "attempts_started": ledger.started_attempts,
        "private_outcome_key_read": False,
    }
    if report["reviewer_A_complete"] == report["reviewer_B_complete"] == 64:
        report["status"] = "BOTH_ATOMIC_REVIEWS_COMPLETE_AWAITING_FREEZE_ANALYSIS"
    write_json(DIR / "atomic_semantic_live_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
