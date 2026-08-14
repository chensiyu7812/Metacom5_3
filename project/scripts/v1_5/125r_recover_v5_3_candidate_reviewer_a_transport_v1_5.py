#!/usr/bin/env python3
"""One-shot transport recovery for two missing reviewer-A candidate rows.

The semantic rubric, model, packet, and identities are unchanged.  Only the
evidence cardinality is narrowed from 1-3 to exactly one after Claude twice
returned 4-5 IDs.  Original failed attempts remain in the primary ledger.
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


PROTOCOL = "pm-v1.5-v5.3-role-decomposed-calibration-v2"
EXECUTION_PROTOCOL = "pm-v1.5-v5.3-candidate-suitability-v2-reviewer-a-transport-recovery-exactly-one-evidence"
DIR = ROOT / "outputs/pm_v1_5_v5_3_role_decomposed_calibration_v2_20260810"
PACKET = DIR / "candidate_suitability_packet_blind.jsonl"
COMPLETED = DIR / "candidate_reviewer_A_completed.jsonl"
CONFIG = ROOT / "configs/pm_v1_5_role_decomposed_judge_qualification_v1.json"
MISSING = {"rdcal_3190f80a6eb8ab85781f", "rdcal_4b4522f534d349c606a9"}


CandidateTruth = Literal[
    "VALID_APPLICABLE", "VALID_REDUNDANT", "VALID_NOT_USEFUL",
    "INVALID_WRONG_OWNER_TIME_EVENT", "UNRESOLVED",
]


class RecoveryJudgment(StrictModel):
    calibration_id: str = Field(min_length=1)
    candidate_truth: CandidateTruth
    current_evidence_id: str = Field(min_length=1)
    candidate_evidence_id: Literal["CANDIDATE_TEXT"]
    rationale: str = Field(min_length=1)
    uncertainty_note: str


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
    )


def _messages(item: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": """You are REVIEWER_A. This is a transport-only recovery of the same frozen candidate-suitability task.
Use the unchanged labels: VALID_APPLICABLE means a valid, current, nonredundant contribution; VALID_REDUNDANT means already explicit; VALID_NOT_USEFUL means valid but not useful for the current response; INVALID_WRONG_OWNER_TIME_EVENT means wrong owner/time/event/version/scope; UNRESOLVED means insufficient evidence.
Rank-1 or topical overlap is not proof. Return exactly ONE supplied TURN id in current_evidence_id and CANDIDATE_TEXT. Do not return a list. You see no replies or outcomes."""},
        {"role": "user", "content": canonical_json(item)},
    ]


def main() -> None:
    packet = {str(row["calibration_id"]): row for row in _jsonl(PACKET)}
    completed = {str(row["calibration_id"]): row for row in _jsonl(COMPLETED)}
    missing = sorted(MISSING - set(completed))
    if set(missing) != MISSING:
        raise SystemExit(f"expected exactly the two documented missing identities; got {missing}")
    raw = json.loads(CONFIG.read_text())["candidates"]["anthropic_claude_haiku_4_5"]
    endpoint = _endpoint(raw)
    ledger = PersistentAttemptLedger(
        DIR / "candidate_reviewer_A_transport_recovery_ledger.jsonl",
        stage="v5_3_candidate_reviewer_a_transport_recovery",
        expected_calls={"recovery_" + key: 1 for key in missing},
        maximum_total_attempts=2,
    )
    client = make_client(endpoint)
    try:
        for calibration_id in missing:
            item = packet[calibration_id]
            call_key = "recovery_" + calibration_id
            messages = _messages(item)
            reservation = ledger.reserve(
                call_key,
                record_ids={"reviewer_id": "REVIEWER_A", "calibration_id": calibration_id},
                prompt_sha256=sha256_text(canonical_json(messages)),
            )
            response = None
            try:
                response, parsed = client.chat(
                    messages, temperature=0.0, max_tokens=900, seed=20260810,
                    response_schema=RecoveryJudgment, retries=1,
                )
                if parsed is None or parsed.calibration_id != calibration_id:
                    raise ValueError("missing or mismatched recovery judgment")
                turns = {row["evidence_id"]: row["text"] for row in item["visible_dialogue"]}
                if parsed.current_evidence_id not in turns:
                    raise ValueError("unknown recovery evidence id")
                row = parsed.model_dump(mode="json")
                row["current_evidence"] = [{
                    "evidence_id": row.pop("current_evidence_id"),
                    "text": turns[parsed.current_evidence_id],
                }]
                row["candidate_evidence"] = {
                    "evidence_id": row.pop("candidate_evidence_id"),
                    "text": item["candidate"]["text"],
                }
                row.update({
                    "protocol": PROTOCOL, "execution_protocol": EXECUTION_PROTOCOL,
                    "reviewer_id": "REVIEWER_A", "transport_recovery": True,
                })
                ledger.finish(
                    reservation, succeeded=True, request_hash=response.request_hash,
                    usage=response.usage, error=None, result=row,
                    metadata={"model": endpoint.model},
                )
                completed[calibration_id] = row
                write_jsonl(COMPLETED, list(completed.values()))
            except Exception as exc:
                ledger.finish(
                    reservation, succeeded=False,
                    request_hash=response.request_hash if response else None,
                    usage=response.usage if response else None,
                    error=f"{type(exc).__name__}: {exc}", metadata={"model": endpoint.model},
                )
    finally:
        client.close()
    report = {
        "protocol": PROTOCOL,
        "execution_protocol": EXECUTION_PROTOCOL,
        "status": "RECOVERY_COMPLETE" if len(completed) == 64 else "RECOVERY_INCOMPLETE",
        "recovered_ids": missing,
        "reviewer_A_complete": len(completed),
        "semantic_rubric_changed": False,
        "evidence_cardinality_only_changed": True,
        "private_key_read": False,
    }
    write_json(DIR / "candidate_reviewer_A_transport_recovery_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
