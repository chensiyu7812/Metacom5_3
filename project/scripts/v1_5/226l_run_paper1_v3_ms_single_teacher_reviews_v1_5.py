#!/usr/bin/env python3
"""Execute exactly 204 raw-first MS reviews from the one qualified teacher."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.attempt_ledger import PersistentAttemptLedger  # noqa: E402
from metacom_pm.io import append_jsonl, canonical_json, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402
from metacom_pm.paid_run_release import require_paid_run_release  # noqa: E402
from metacom_pm.v1_5_g4b_anchored_review_v2 import G4BSuitabilityReview, prompt_messages, validate_review  # noqa: E402
from metacom_pm.api import ProviderRequestError, RetryableProviderError, StructuredOutputValidationError, make_client  # noqa: E402


BASE_PATH = ROOT / "scripts/v1_5/209l_run_paper1_v3_g4b_reviews_v1_5.py"
spec = importlib.util.spec_from_file_location("g4b_frozen_raw_helpers_for_ms_teacher", BASE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load frozen raw-first helper")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_v3_ms_single_teacher_execution_phase_v1.json"
CONFIG = ROOT / "configs/paper1_v3_ms_single_teacher_execution_v1.json"
ENDPOINTS = ROOT / "configs/pm_v1_5_strict_judge_bakeoff_v1.json"
PREFLIGHT = ROOT / "outputs/pm_v1_5_paper1_v3_ms_single_teacher_preflight_20260811"
PACKET = ROOT / "outputs/pm_v1_5_paper1_v3_g4a_packet_v2_20260811/reviewer_a_packet.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_ms_single_teacher_reviews_20260811"
STAGE = "paper1_v3_ms_single_qualified_teacher_review_v1"
REVIEWER_ID = "REVIEWER_A"
ENDPOINT_KEY = "anthropic_claude_haiku_4_5"
MAX_ATTEMPTS = 2
MAX_OUTPUT_TOKENS = 500


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def require_authority() -> dict[str, Any]:
    authority = read(AUTHORITY)
    current = authority["active_v3_phase"]
    if current["id"] != "MS_SINGLE_TEACHER_PUBLIC_EXECUTION":
        raise RuntimeError("MS teacher execution is not active")
    binding = current["active_phase_manifest"]
    if binding["path"] != str(PHASE.relative_to(ROOT)) or binding["sha256"] != sha256_file(PHASE):
        raise RuntimeError("MS teacher phase binding drifted")
    phase = read(PHASE)
    for item in [*phase["input_bindings"], *phase["implementation_bindings"]]:
        if sha256_file(ROOT / item["path"]) != item["sha256"]:
            raise RuntimeError(f"bound artifact drifted: {item['path']}")
    return phase


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-identity", required=True)
    parser.add_argument("--accept-usd-cap", type=float, required=True)
    args = parser.parse_args()
    phase = require_authority()
    cap = float(phase["execution"]["absolute_usd_cap"])
    if args.accept_usd_cap != cap:
        raise RuntimeError(f"must accept exact frozen cap {cap:g}")
    require_paid_run_release(
        read(CONFIG), config_path=CONFIG, stage=STAGE, run=True,
        run_identity=args.run_identity,
    )

    endpoints = read(ENDPOINTS)
    endpoint = base.endpoint(endpoints["candidates"][ENDPOINT_KEY])
    plan = rows(PREFLIGHT / "call_plan.jsonl")
    packet = {row["review_item_id"]: row for row in rows(PACKET) if row["component"] == "MS"}
    if len(plan) != 204 or len(packet) != 204:
        raise RuntimeError("MS teacher denominator drifted")

    OUT.mkdir(parents=True, exist_ok=True)
    ledger = PersistentAttemptLedger(
        OUT / "physical_attempt_ledger.jsonl",
        stage=STAGE,
        expected_calls={row["logical_call_key"]: MAX_ATTEMPTS for row in plan},
        maximum_total_attempts=204 * MAX_ATTEMPTS,
    )
    raw_path = OUT / "raw_physical_attempts.jsonl"
    output_path = OUT / "teacher_reviews.jsonl"
    client = make_client(endpoint)
    try:
        for index, plan_row in enumerate(plan, 1):
            call_key = plan_row["logical_call_key"]
            completed = {row["review_item_id"]: row for row in rows(output_path)}
            if plan_row["review_item_id"] in completed or ledger.succeeded(call_key):
                continue
            if ledger.exhausted(call_key) or base._prior_terminal_nonretryable(ledger, call_key):
                continue
            item = packet[plan_row["review_item_id"]]
            messages = prompt_messages(item, REVIEWER_ID)
            if sha256_text(canonical_json(messages)) != plan_row["prompt_sha256"]:
                raise RuntimeError("provider-visible prompt drift")
            while not ledger.succeeded(call_key) and not ledger.exhausted(call_key):
                if base._prior_terminal_nonretryable(ledger, call_key):
                    break
                reservation = ledger.reserve(
                    call_key,
                    record_ids={"reviewer_id": REVIEWER_ID, "review_item_id": plan_row["review_item_id"], "call_stage": "MS_TEACHER"},
                    prompt_sha256=plan_row["prompt_sha256"],
                )
                call = parsed = None
                error: BaseException | None = None
                retry_allowed = semantic_complete = False
                try:
                    call, parsed = client.chat(
                        messages,
                        temperature=0.0,
                        max_tokens=MAX_OUTPUT_TOKENS,
                        seed=int(plan_row["request_parameters"]["seed"]),
                        response_schema=G4BSuitabilityReview,
                        retries=1,
                    )
                except StructuredOutputValidationError as exc:
                    error, call, retry_allowed = exc, exc.call, True
                except RetryableProviderError as exc:
                    error = exc
                    retry_allowed = exc.last_retry_class in base.RETRYABLE_CLASSES
                except ProviderRequestError as exc:
                    error, retry_allowed = exc, False
                except Exception as exc:
                    error, retry_allowed = exc, False

                append_jsonl(raw_path, base._raw_record(reservation=reservation, plan_row=plan_row, call=call, error=error))
                result = None
                if error is None and parsed is not None:
                    try:
                        result = validate_review(parsed, item)
                        semantic_complete = True
                    except ValueError as exc:
                        error, retry_allowed = exc, False
                metadata = {
                    "endpoint_key": ENDPOINT_KEY,
                    "model": plan_row["model"],
                    "retry_allowed": retry_allowed,
                    "semantic_complete": semantic_complete,
                    "raw_persisted_before_semantic_validation": True,
                }
                if semantic_complete and result is not None and call is not None:
                    result.update({
                        "protocol": "pm-v1.5-paper1-v3-ms-single-teacher-review-result-v1",
                        "reviewer_id": REVIEWER_ID,
                        "component": "MS",
                        "call_stage": "MS_TEACHER",
                        "endpoint_key": ENDPOINT_KEY,
                        "model": plan_row["model"],
                        "request_hash": call.request_hash,
                        "review_position": plan_row["review_position"],
                    })
                    ledger.finish(reservation, succeeded=True, request_hash=call.request_hash, usage=call.usage, error=None, result=result, metadata=metadata)
                    completed[result["review_item_id"]] = result
                    write_jsonl(output_path, sorted(completed.values(), key=lambda row: row["review_position"]))
                else:
                    ledger.finish(
                        reservation,
                        succeeded=False,
                        request_hash=call.request_hash if call is not None else getattr(error, "request_hash", None),
                        usage=call.usage if call is not None else getattr(error, "usage", None),
                        error=f"{type(error).__name__}: {error}",
                        result=None,
                        metadata=metadata,
                    )
                    if not retry_allowed:
                        break
                if base._actual_cost(ledger, endpoints) > cap:
                    raise RuntimeError("observed MS teacher cost exceeded frozen cap")
            if index % 12 == 0 or index == len(plan):
                print(f"MS teacher progress {index}/{len(plan)} attempts={ledger.started_attempts}", flush=True)
    finally:
        client.close()

    completed = sum(ledger.succeeded(row["logical_call_key"]) for row in plan)
    report = {
        "protocol": "pm-v1.5-paper1-v3-ms-single-teacher-live-report-v1",
        "status": "MS_SINGLE_TEACHER_REVIEWS_COMPLETE_LABEL_FREEZE_MAY_BEGIN" if completed == 204 else "MS_SINGLE_TEACHER_REVIEWS_INCOMPLETE",
        "planned_logical_calls": 204,
        "completed_valid_reviews": completed,
        "physical_attempts_started": ledger.started_attempts,
        "observed_cost_usd": base._actual_cost(ledger, endpoints),
        "absolute_usd_cap": cap,
        "raw_attempts_persisted": len(rows(raw_path)),
        "teacher_not_human_gold": True,
        "private_mapping_or_outcome_read": False,
        "labels_created": 0,
    }
    write_json(OUT / "live_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
