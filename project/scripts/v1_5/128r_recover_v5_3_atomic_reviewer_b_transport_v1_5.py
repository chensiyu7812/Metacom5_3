#!/usr/bin/env python3
"""One-shot transport recovery for the three missing atomic reviewer-B rows.

The frozen packet, reviewer, model, temperature, four semantic axes, and
projection remain unchanged.  The prompt only makes the already-supplied TURN
identifier allow-list explicit after both original attempts cited unknown ids.
Original failed attempts remain in the primary physical-attempt ledger.
"""

from __future__ import annotations

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
from metacom_pm.io import canonical_json, sha256_text, write_json, write_jsonl  # noqa: E402


PROTOCOL = "pm-v1.5-v5.3-atomic-semantic-suitability-development-v1"
EXECUTION_PROTOCOL = "pm-v1.5-v5.3-atomic-reviewer-b-transport-recovery-explicit-turn-allowlist-v1"
DIR = ROOT / "outputs/pm_v1_5_v5_3_role_decomposed_calibration_v2_20260810"
PACKET = DIR / "candidate_suitability_packet_blind.jsonl"
COMPLETED = DIR / "atomic_semantic_reviewer_B_completed.jsonl"
CONFIG = ROOT / "configs/pm_v1_5_role_decomposed_judge_qualification_v1.json"
EXPECTED_MISSING = {
    "rdcal_17b8f5553676c75749ad",
    "rdcal_30e809ecfcd0da7d2557",
    "rdcal_3419f59d2f06ac5890ab",
}


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


def _messages(item: dict[str, Any]) -> list[dict[str, str]]:
    component = str(item["component"])
    allowed = [str(row["evidence_id"]) for row in item["visible_dialogue"]]
    system = f"""You are REVIEWER_B, independently reviewing the same frozen four atomic semantic axes. This is transport-only recovery: the prior outputs cited ids outside the supplied dialogue. You see no response, outcome, function, risk, cost, composite label, or other reviewer.

Treat CANDIDATE_TEXT and typed metadata as machine-verified, same-user, strictly-prior. For each axis return YES, NO, or UNRESOLVED and exactly one id from this allow-list: {json.dumps(allowed)}.
1. current_goal_entity_fit: can the candidate's specific contribution bear on the current entity, goal, tension, or response need, rather than merely share a topic?
2. specific_contribution_already_visible: is its material contribution already explicit in the visible dialogue?
3. component_function_can_change_response: can it change response content or act in a grounded way under the component definition?
4. current_boundary_permits_component: does the current boundary permit it, considering advice/listen, repetition, burden, and acute safety?

Component={component}. Minimum: {COMPONENT_MINIMUMS[component]}
Do not output a composite label or infer outcomes. Evidence selection never forces YES. Use UNRESOLVED when needed. candidate_evidence_id must be CANDIDATE_TEXT."""
    return [{"role": "system", "content": system}, {"role": "user", "content": canonical_json(item)}]


def _validated_row(parsed: AtomicJudgment, item: dict[str, Any]) -> dict[str, Any]:
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
    row.update({
        "protocol": PROTOCOL,
        "execution_protocol": EXECUTION_PROTOCOL,
        "reviewer_id": "REVIEWER_B",
        "transport_recovery": True,
    })
    return row


def main() -> None:
    packet = {str(row["calibration_id"]): row for row in _jsonl(PACKET)}
    completed = {str(row["calibration_id"]): row for row in _jsonl(COMPLETED)}
    missing = sorted(set(packet) - set(completed))
    if set(missing) != EXPECTED_MISSING:
        raise SystemExit(f"expected documented missing identities {sorted(EXPECTED_MISSING)}; got {missing}")
    raw = json.loads(CONFIG.read_text())["candidates"]["openai_gpt_5_mini"]
    endpoint = _endpoint(raw)
    ledger = PersistentAttemptLedger(
        DIR / "atomic_semantic_reviewer_B_transport_recovery_ledger.jsonl",
        stage="v5_3_atomic_semantic_reviewer_b_transport_recovery",
        expected_calls={"recovery_" + key: 1 for key in missing},
        maximum_total_attempts=len(missing),
    )
    client = make_client(endpoint)
    try:
        for calibration_id in missing:
            item = packet[calibration_id]
            messages = _messages(item)
            reservation = ledger.reserve(
                "recovery_" + calibration_id,
                record_ids={"reviewer_id": "REVIEWER_B", "calibration_id": calibration_id},
                prompt_sha256=sha256_text(canonical_json(messages)),
            )
            response = None
            try:
                response, parsed = client.chat(
                    messages, temperature=0.0, max_tokens=1400, seed=20260810,
                    response_schema=AtomicJudgment, retries=1,
                )
                if parsed is None:
                    raise ValueError("structured recovery judgment missing")
                row = _validated_row(parsed, item)
                ledger.finish(
                    reservation, succeeded=True, request_hash=response.request_hash,
                    usage=response.usage, error=None, result=row,
                    metadata={"endpoint": "openai_gpt_5_mini", "model": endpoint.model},
                )
                completed[calibration_id] = row
                write_jsonl(COMPLETED, list(completed.values()))
            except Exception as exc:
                ledger.finish(
                    reservation, succeeded=False,
                    request_hash=response.request_hash if response else None,
                    usage=response.usage if response else None,
                    error=f"{type(exc).__name__}: {exc}",
                    metadata={"endpoint": "openai_gpt_5_mini", "model": endpoint.model},
                )
    finally:
        client.close()
    report = {
        "protocol": PROTOCOL,
        "execution_protocol": EXECUTION_PROTOCOL,
        "status": "RECOVERY_COMPLETE" if len(completed) == 64 else "RECOVERY_INCOMPLETE",
        "recovered_ids": missing,
        "reviewer_B_complete": len(completed),
        "semantic_rubric_changed": False,
        "explicit_existing_turn_allowlist_only": True,
        "original_failures_preserved": True,
        "private_outcome_key_read": False,
    }
    write_json(DIR / "atomic_semantic_reviewer_B_transport_recovery_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
