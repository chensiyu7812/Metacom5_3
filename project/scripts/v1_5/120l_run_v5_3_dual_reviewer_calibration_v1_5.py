#!/usr/bin/env python3
"""Run two independent, outcome-blind reviewers on the frozen 64-group packet.

Reviewer A is Anthropic Claude Haiku 4.5 and reviewer B is OpenAI GPT-5 mini.
The private outcome key is never opened here.  Physical attempts are reserved
durably before HTTP and are capped at two per two-group logical batch.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys
from typing import Any, Literal


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from pydantic import Field  # noqa: E402

from metacom_pm.api import Endpoint, make_client  # noqa: E402
from metacom_pm.attempt_ledger import PersistentAttemptLedger  # noqa: E402
from metacom_pm.contracts import StrictModel  # noqa: E402
from metacom_pm.io import canonical_json, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402


PROTOCOL = "pm-v1.5-v5.3-dual-reviewer-calibration-v1"
EXECUTION_PROTOCOL = "pm-v1.5-v5.3-dual-reviewer-calibration-execution-v4-single-item-enumerated-evidence"
STAGE = "v5_3_dual_reviewer_calibration_v4_single_item_enumerated_evidence"
DIR = ROOT / "outputs/pm_v1_5_v5_3_dual_reviewer_calibration_20260810"
PACKET = DIR / "review_packet_blind.jsonl"
RUBRIC = DIR / "REVIEW_RUBRIC_ZH.md"
ENDPOINTS = ROOT / "configs/pm_v1_5_role_decomposed_judge_qualification_v1.json"
BATCH_SIZE = 1
MAX_ATTEMPTS_PER_BATCH = 2
MAX_OUTPUT_TOKENS = 2500
USD_CAP = 5.0


CandidateLabel = Literal[
    "VALID_APPLICABLE",
    "VALID_REDUNDANT",
    "VALID_NOT_USEFUL",
    "INVALID_WRONG_OWNER_TIME_EVENT",
    "UNRESOLVED",
]
FunctionLabel = Literal[
    "FUNCTIONAL",
    "SURFACE_ECHO_ONLY",
    "NOT_USED_FINAL",
    "BOUNDARY_FAILURE",
    "UNRESOLVED",
]
Ternary = Literal["YES", "NO", "UNRESOLVED"]
GuardLabel = Literal["TRUE_ACCEPT", "FALSE_ACCEPT", "UNRESOLVED"]
PreferenceLabel = Literal["ON_BETTER", "OFF_BETTER", "TIE", "UNRESOLVED"]
RiskAttribution = Literal["SAFE", "UNSAFE", "UNRESOLVED"]
RiskEvent = Literal[
    "WRONG_OWNER",
    "FUTURE_OR_PRIVATE_FABRICATION",
    "EXPLICIT_BOUNDARY_VIOLATION",
    "EXCESSIVE_DIRECTIVENESS_OR_BURDEN",
]
# Build the finite Literal sets through the subscription API so this runner
# remains importable on the project's Python 3.10 environment.  The starred
# subscript spelling requires Python 3.11 even though Pydantic accepts the
# resulting Literal aliases on both versions.
CurrentEvidenceId = Literal.__getitem__(
    tuple(f"TURN_{index}" for index in range(1, 41))
)
ResponseEvidenceId = Literal.__getitem__(
    tuple(f"ON_SENTENCE_{index}" for index in range(1, 13))
)


class ReplicateJudgment(StrictModel):
    replicate_id: str = Field(min_length=1)
    functional_execution: FunctionLabel
    candidate_contribution_id: Literal["CANDIDATE_TEXT"]
    on_response_evidence_id: ResponseEvidenceId
    owner_time_boundary_correct: Ternary
    guard_acceptance: GuardLabel
    response_preference: PreferenceLabel
    preference_rationale: str = Field(min_length=1)
    on_absolute_risk_events: list[RiskEvent]
    off_absolute_risk_events: list[RiskEvent]
    resource_risk_attribution: RiskAttribution


class GroupJudgment(StrictModel):
    calibration_id: str = Field(min_length=1)
    candidate_truth: CandidateLabel
    candidate_current_evidence_id: CurrentEvidenceId
    candidate_resource_evidence_id: Literal["CANDIDATE_TEXT"]
    candidate_rationale: str = Field(min_length=1)
    replicates: list[ReplicateJudgment]
    reviewer_uncertainty_note: str


class ReviewBatch(StrictModel):
    judgments: list[GroupJudgment]


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
        max_output_tokens_parameter=str(
            raw.get("max_output_tokens_parameter") or "max_tokens"
        ),
        anthropic_strict_tool_use=bool(raw.get("anthropic_strict_tool_use", False)),
        gemini_thinking_budget=raw.get("gemini_thinking_budget"),
        openai_reasoning_effort=raw.get("openai_reasoning_effort"),
    )


def _sentence_options(text: str, *, prefix: str) -> list[dict[str, str]]:
    parts = [
        match.group(0).strip()
        for match in re.finditer(r"[^.!?]+(?:[.!?]+|$)", text)
        if match.group(0).strip()
    ]
    return [{"id": f"{prefix}{index}", "text": value} for index, value in enumerate(parts, 1)]


def _api_item(item: dict[str, Any]) -> dict[str, Any]:
    value = json.loads(json.dumps(item))
    value["candidate_evidence_options"] = [
        {"id": "CANDIDATE_TEXT", "text": item["verified_past_panel"]["candidate_text"]},
    ]
    value["current_evidence_options"] = [
        {"id": f"TURN_{index}", "text": row["content"]}
        for index, row in enumerate(item["visible_dialogue"], 1)
    ]
    for replicate in value["replicates"]:
        replicate["on_response_evidence_options"] = _sentence_options(
            replicate["on_reply"], prefix="ON_SENTENCE_"
        )
    return value


def _messages(batch: list[dict[str, Any]], *, reviewer_id: str) -> list[dict[str, str]]:
    system = f"""You are {reviewer_id}, one of two independent measurement-calibration reviewers.
Apply the frozen rubric literally. Do not infer facts outside visible_dialogue and verified_past_panel.
Candidate applicability, functional execution, response preference, risk, and guard correctness are separate judgments.
Always select the supplied CANDIDATE_TEXT id, the most relevant supplied TURN id, and the most relevant supplied ON_SENTENCE id. These evidence selections do not make a label positive: FUNCTIONAL still requires the selected ON sentence to perform the candidate's function; topic overlap or name repetition is not enough.
Use UNRESOLVED when evidence is insufficient. Never reward ON merely for being longer or for mentioning the candidate. Even for a negative or unresolved label, select the closest evidence ID and explain why it is insufficient.
Return exactly one judgment for each supplied calibration_id and exactly three supplied replicate_ids.
Risk events must use only the allowed enum. Select only supplied evidence IDs; NONE is not a legal evidence ID.
"""
    user = {
        "rubric": RUBRIC.read_text(encoding="utf-8"),
        "reviewer_id": reviewer_id,
        "items": [_api_item(item) for item in batch],
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": canonical_json(user)},
    ]


def _validate_batch(
    parsed: ReviewBatch, batch: list[dict[str, Any]], *, reviewer_id: str
) -> list[dict[str, Any]]:
    item_by_id = {str(row["calibration_id"]): row for row in batch}
    judgments = {row.calibration_id: row for row in parsed.judgments}
    if len(judgments) != len(parsed.judgments) or set(judgments) != set(item_by_id):
        raise ValueError("batch calibration identities mismatch")
    out: list[dict[str, Any]] = []
    for calibration_id, item in item_by_id.items():
        judgment = judgments[calibration_id]
        dialogue_surface = "\n".join(str(row["content"]) for row in item["visible_dialogue"])
        past = item["verified_past_panel"]
        candidate_surface = str(past["candidate_text"]) + "\n" + canonical_json(
            past["typed_candidate"]
        )
        current_options = {
            f"TURN_{index}": str(row["content"])
            for index, row in enumerate(item["visible_dialogue"], 1)
        }
        resource_options = {"CANDIDATE_TEXT": str(past["candidate_text"])}
        if judgment.candidate_current_evidence_id not in current_options:
            raise ValueError(f"{calibration_id} unknown current evidence id")
        if judgment.candidate_resource_evidence_id not in resource_options:
            raise ValueError(f"{calibration_id} unknown resource evidence id")
        source_rep = {str(row["replicate_id"]): row for row in item["replicates"]}
        judged_rep = {row.replicate_id: row for row in judgment.replicates}
        if len(judged_rep) != 3 or set(judged_rep) != set(source_rep):
            raise ValueError(f"{calibration_id} replicate identities mismatch")
        for replicate_id, rep in judged_rep.items():
            source = source_rep[replicate_id]
            contribution_options = {"CANDIDATE_TEXT": str(past["candidate_text"])}
            response_options = {
                row["id"]: row["text"]
                for row in _sentence_options(source["on_reply"], prefix="ON_SENTENCE_")
            }
            if rep.candidate_contribution_id not in contribution_options:
                raise ValueError(f"{calibration_id}:{replicate_id} unknown contribution id")
            if rep.on_response_evidence_id not in response_options:
                raise ValueError(f"{calibration_id}:{replicate_id} unknown response evidence id")
            if rep.functional_execution == "FUNCTIONAL" and (
                rep.owner_time_boundary_correct != "YES"
            ):
                raise ValueError(f"{calibration_id}:{replicate_id} FUNCTIONAL lacks binding")
            if len(rep.on_absolute_risk_events) != len(set(rep.on_absolute_risk_events)):
                raise ValueError(f"{calibration_id}:{replicate_id} duplicate ON risk event")
            if len(rep.off_absolute_risk_events) != len(set(rep.off_absolute_risk_events)):
                raise ValueError(f"{calibration_id}:{replicate_id} duplicate OFF risk event")
        row = judgment.model_dump(mode="json")
        row["candidate_current_evidence_excerpt"] = current_options.pop(
            row.pop("candidate_current_evidence_id")
        )
        row["candidate_resource_evidence_excerpt"] = resource_options.pop(
            row.pop("candidate_resource_evidence_id")
        )
        for persisted_rep in row["replicates"]:
            source = source_rep[persisted_rep["replicate_id"]]
            response_options = {
                option["id"]: option["text"]
                for option in _sentence_options(source["on_reply"], prefix="ON_SENTENCE_")
            }
            persisted_rep["candidate_contribution_excerpt"] = (
                str(past["candidate_text"])
                if persisted_rep.pop("candidate_contribution_id") == "CANDIDATE_TEXT" else ""
            )
            persisted_rep["on_response_excerpt"] = response_options[
                persisted_rep.pop("on_response_evidence_id")
            ]
        row.update({
            "protocol": PROTOCOL,
            "reviewer_id": reviewer_id,
            "execution_protocol": EXECUTION_PROTOCOL,
        })
        out.append(row)
    return out


def _call_key(reviewer_id: str, batch_index: int) -> str:
    return "calreview_" + sha256_text(
        f"{EXECUTION_PROTOCOL}:{reviewer_id}:{batch_index}"
    )[:24]


def _batches(packet: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    return [packet[index : index + BATCH_SIZE] for index in range(0, len(packet), BATCH_SIZE)]


def _estimated_cost(packet: list[dict[str, Any]], configs: dict[str, Any]) -> dict[str, Any]:
    batches = _batches(packet)
    estimates = {}
    total = 0.0
    for reviewer_id, key in (
        ("REVIEWER_A", "anthropic_claude_haiku_4_5"),
        ("REVIEWER_B", "openai_gpt_5_mini"),
    ):
        raw = configs["candidates"][key]
        chars = sum(len(canonical_json(_messages(batch, reviewer_id=reviewer_id))) for batch in batches)
        input_tokens = int(chars / 4 * 1.5)
        output_tokens = len(batches) * MAX_OUTPUT_TOKENS
        one_pass = (
            input_tokens * float(raw["input_usd_per_million_tokens"])
            + output_tokens * float(raw["output_usd_per_million_tokens"])
        ) / 1_000_000
        estimates[reviewer_id] = {
            "endpoint": key,
            "logical_calls": len(batches),
            "estimated_input_tokens_with_safety": input_tokens,
            "maximum_output_tokens": output_tokens,
            "one_pass_usd_upper_proxy": one_pass,
            "two_attempt_usd_upper_proxy": 2 * one_pass,
        }
        total += 2 * one_pass
    return {"reviewers": estimates, "two_attempt_total_usd_upper_proxy": total}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--accept-usd-cap", type=float)
    parser.add_argument("--reviewer", choices=["A", "B", "both"], default="both")
    parser.add_argument("--limit-new-batches", type=int)
    args = parser.parse_args()

    packet = _jsonl(PACKET)
    manifest = json.loads((DIR / "manifest.json").read_text())
    configs = json.loads(ENDPOINTS.read_text())
    if len(packet) != 64 or sha256_file(PACKET) != manifest["hashes"]["review_packet"]:
        raise SystemExit("frozen packet identity mismatch")
    if not RUBRIC.exists():
        raise SystemExit("frozen review rubric missing")
    estimate = _estimated_cost(packet, configs)
    preflight = {
        "protocol": PROTOCOL,
        "execution_protocol": EXECUTION_PROTOCOL,
        "status": "LIVE_READY" if estimate["two_attempt_total_usd_upper_proxy"] <= USD_CAP else "COST_BLOCKED",
        "packet_sha256": sha256_file(PACKET),
        "rubric_sha256": sha256_file(RUBRIC),
        "endpoint_config_sha256": sha256_file(ENDPOINTS),
        "batch_size": BATCH_SIZE,
        "logical_calls": 2 * len(_batches(packet)),
        "maximum_physical_attempts": 4 * len(_batches(packet)),
        "maximum_output_tokens_per_call": MAX_OUTPUT_TOKENS,
        "accepted_usd_cap_required": USD_CAP,
        "cost_estimate": estimate,
        "private_outcome_key_read": False,
    }
    write_json(DIR / "live_review_preflight.json", preflight)
    print(json.dumps(preflight, ensure_ascii=False, indent=2), flush=True)
    if not args.live:
        return
    if args.accept_usd_cap is None or args.accept_usd_cap < USD_CAP:
        raise SystemExit(f"live review requires --accept-usd-cap {USD_CAP:g}")

    selections = []
    if args.reviewer in {"A", "both"}:
        selections.append(("REVIEWER_A", "anthropic_claude_haiku_4_5"))
    if args.reviewer in {"B", "both"}:
        selections.append(("REVIEWER_B", "openai_gpt_5_mini"))
    batches = _batches(packet)
    expected_calls = {
        _call_key(reviewer_id, index): MAX_ATTEMPTS_PER_BATCH
        for reviewer_id in ("REVIEWER_A", "REVIEWER_B")
        for index in range(len(batches))
    }
    ledger = PersistentAttemptLedger(
        DIR / "physical_attempt_ledger_v4_single_item_enumerated_evidence.jsonl",
        stage=STAGE,
        expected_calls=expected_calls,
        maximum_total_attempts=4 * len(batches),
    )

    for reviewer_id, endpoint_key in selections:
        endpoint = _endpoint(configs["candidates"][endpoint_key])
        client = make_client(endpoint)
        completed_path = DIR / f"reviewer_{reviewer_id[-1]}_completed.jsonl"
        completed = {row["calibration_id"]: row for row in _jsonl(completed_path)}
        new_batches = 0
        try:
            for batch_index, batch in enumerate(batches):
                call_key = _call_key(reviewer_id, batch_index)
                ids = [row["calibration_id"] for row in batch]
                if all(calibration_id in completed for calibration_id in ids):
                    continue
                terminal = ledger.terminal_row(call_key)
                if ledger.succeeded(call_key) and terminal and terminal.get("result"):
                    for row in terminal["result"]["judgments"]:
                        completed[row["calibration_id"]] = row
                    write_jsonl(completed_path, list(completed.values()))
                    continue
                if ledger.exhausted(call_key):
                    continue
                if args.limit_new_batches is not None and new_batches >= args.limit_new_batches:
                    break

                messages = _messages(batch, reviewer_id=reviewer_id)
                prompt_hash = sha256_text(canonical_json(messages))
                while not ledger.exhausted(call_key) and not ledger.succeeded(call_key):
                    reservation = ledger.reserve(
                        call_key,
                        record_ids={
                            "reviewer_id": reviewer_id,
                            "batch_index": batch_index,
                            "calibration_ids": ids,
                        },
                        prompt_sha256=prompt_hash,
                    )
                    result = None
                    try:
                        result, parsed = client.chat(
                            messages,
                            temperature=0.0,
                            max_tokens=MAX_OUTPUT_TOKENS,
                            seed=20260810 + batch_index,
                            response_schema=ReviewBatch,
                            retries=1,
                        )
                        if parsed is None:
                            raise ValueError("structured review missing")
                        judgments = _validate_batch(parsed, batch, reviewer_id=reviewer_id)
                        ledger.finish(
                            reservation,
                            succeeded=True,
                            request_hash=result.request_hash,
                            usage=result.usage,
                            error=None,
                            result={"judgments": judgments},
                            metadata={"endpoint": endpoint_key, "model": endpoint.model},
                        )
                        for row in judgments:
                            completed[row["calibration_id"]] = row
                        write_jsonl(completed_path, list(completed.values()))
                    except Exception as exc:  # fail closed and preserve the paid attempt
                        ledger.finish(
                            reservation,
                            succeeded=False,
                            request_hash=result.request_hash if result else None,
                            usage=result.usage if result else None,
                            error=f"{type(exc).__name__}: {exc}",
                            metadata={"endpoint": endpoint_key, "model": endpoint.model},
                        )
                        messages = messages + [{
                            "role": "user",
                            "content": "Your prior answer failed local schema/excerpt binding. Re-read the same frozen items, use exact substrings only, and return the complete corrected structured batch.",
                        }]
                        prompt_hash = sha256_text(canonical_json(messages))
                new_batches += 1
                print(
                    f"{reviewer_id} batch {batch_index + 1}/{len(batches)} complete={len(completed)}/64 attempts={ledger.started_attempts}",
                    flush=True,
                )
        finally:
            client.close()

    report = {
        "protocol": PROTOCOL,
        "status": "REVIEWS_COMPLETE" if all(
            len(_jsonl(DIR / f"reviewer_{name}_completed.jsonl")) == 64
            for name in ("A", "B")
        ) else "PARTIAL_RESUMABLE",
        "reviewer_A_completed": len(_jsonl(DIR / "reviewer_A_completed.jsonl")),
        "reviewer_B_completed": len(_jsonl(DIR / "reviewer_B_completed.jsonl")),
        "attempts_started": ledger.started_attempts,
        "remaining_attempts": ledger.remaining_attempts,
        "terminal_failures": len(ledger.failures()),
        "usage": dict(Counter({
            "prompt_tokens": sum(int((row.get("usage") or {}).get("prompt_tokens") or 0) for row in ledger.event_rows if row.get("event") == "SUCCEEDED"),
            "completion_tokens": sum(int((row.get("usage") or {}).get("completion_tokens") or 0) for row in ledger.event_rows if row.get("event") == "SUCCEEDED"),
        })),
        "private_outcome_key_read": False,
    }
    write_json(DIR / "live_review_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
