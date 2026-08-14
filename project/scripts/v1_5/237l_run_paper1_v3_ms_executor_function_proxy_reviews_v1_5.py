#!/usr/bin/env python3
"""Sequentially qualify two Function proxies, then review 32 blind MS replies."""

from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.api import ProviderRequestError, RetryableProviderError, StructuredOutputValidationError, make_client  # noqa: E402
from metacom_pm.io import append_jsonl, canonical_json, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402
from metacom_pm.paid_run_release import require_paid_run_release  # noqa: E402
from metacom_pm.v1_5_ms_executor_function_review import MSExecutorFunctionReview, prompt_messages, validate_review  # noqa: E402


BASE_PATH = ROOT / "scripts/v1_5/209l_run_paper1_v3_g4b_reviews_v1_5.py"
spec = importlib.util.spec_from_file_location("frozen_function_proxy_raw_helpers", BASE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load frozen raw-first helpers")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_v3_ms_executor_function_proxy_execution_phase_v1.json"
CONFIG = ROOT / "configs/paper1_v3_ms_executor_function_proxy_execution_v1.json"
ENDPOINTS = ROOT / "configs/pm_v1_5_strict_judge_bakeoff_v1.json"
PREFLIGHT = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_function_proxy_preflight_20260811"
CONTROLS = PREFLIGHT / "fresh_controls_blind.jsonl"
GOLD = PREFLIGHT / "fresh_control_gold_private.jsonl"
PLAN = PREFLIGHT / "call_plan_private.jsonl"
PUBLIC = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_measurement_packet_20260811/function_packet_blind.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_function_proxy_reviews_20260811"
STAGE = "paper1_v3_ms_executor_function_proxy_review_v1"
CAP = 2.0
RETRYABLE = {"rate_limited_429", "request_timeout_408", "http_5xx", "network_timeout", "provider_output_format", "missing_field"}


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def require_authority() -> dict[str, Any]:
    authority = read(AUTHORITY)
    active = authority["active_v3_phase"]
    if active["id"] != "MS_EXECUTOR_FUNCTION_PROXY_EXECUTION":
        raise RuntimeError("Function proxy execution is not active")
    binding = active["active_phase_manifest"]
    if binding != {"path": str(PHASE.relative_to(ROOT)), "sha256": sha256_file(PHASE)}:
        raise RuntimeError("Function proxy phase binding drifted")
    phase = read(PHASE)
    for item in [*phase["input_bindings"], *phase["implementation_bindings"]]:
        if sha256_file(ROOT / item["path"]) != item["sha256"]:
            raise RuntimeError(f"bound artifact drifted: {item['path']}")
    return phase


def qualifies(reviews: list[dict[str, Any]], gold: dict[str, str]) -> dict[str, Any]:
    predicted = {row["blind_item_id"]: row["label"] for row in reviews}
    exact = sum(predicted.get(item) == label for item, label in gold.items())
    per_gold = Counter()
    correct = Counter()
    for item, label in gold.items():
        per_gold[label] += 1
        correct[label] += int(predicted.get(item) == label)
    passed = (
        len(predicted) == 12
        and exact >= 10
        and correct["FUNCTIONAL"] >= 3
        and correct["NOT_USED_FINAL"] >= 2
        and correct["SURFACE_ECHO_ONLY"] >= 1
        and correct["BOUNDARY_FAILURE"] == 2
        and correct["UNRESOLVED"] == 1
    )
    return {"passed": passed, "exact": exact, "n": 12, "correct_by_gold": dict(correct), "denominator_by_gold": dict(per_gold)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--run-identity")
    parser.add_argument("--accept-usd-cap", type=float)
    args = parser.parse_args()
    phase = require_authority()
    plan = rows(PLAN)
    controls = {row["blind_item_id"]: row for row in rows(CONTROLS)}
    public = {row["blind_item_id"]: row for row in rows(PUBLIC)}
    dry = {"protocol": "pm-v1.5-paper1-v3-ms-executor-function-proxy-live-v1", "status": "LIVE_READY", "control_calls": 24, "public_calls_if_both_qualify": 64, "maximum_calls": 88, "run_identity": phase["execution"]["run_identity"], "absolute_usd_cap": CAP, "api_calls": 0}
    print(json.dumps(dry, ensure_ascii=False, indent=2), flush=True)
    if not args.live:
        return
    if args.run_identity != phase["execution"]["run_identity"] or args.accept_usd_cap != CAP:
        raise RuntimeError("exact identity and cap are required")
    require_paid_run_release(read(CONFIG), config_path=CONFIG, stage=STAGE, run=True, run_identity=args.run_identity)
    OUT.mkdir(parents=True, exist_ok=True)
    endpoints = read(ENDPOINTS)
    clients: dict[str, Any] = {}
    raw_path = OUT / "raw_attempts_before_gold.jsonl"
    completed_path = OUT / "reviews.jsonl"
    completed = {(row["reviewer_id"], row["stage"], row["blind_item_id"]): row for row in rows(completed_path)}

    def execute(selected: list[dict[str, Any]], surfaces: dict[str, dict[str, Any]]) -> None:
        for index, call_row in enumerate(selected, 1):
            key = (call_row["reviewer_id"], call_row["stage"], call_row["blind_item_id"])
            if key in completed:
                continue
            item = surfaces[call_row["blind_item_id"]]
            messages = prompt_messages(item, call_row["reviewer_id"])
            if sha256_text(canonical_json(messages)) != call_row["messages_sha256"]:
                raise RuntimeError("prompt drift")
            endpoint_key = call_row["endpoint_key"]
            if endpoint_key not in clients:
                clients[endpoint_key] = make_client(base.endpoint(endpoints["candidates"][endpoint_key]))
            terminal = None
            for attempt in (1, 2):
                result = parsed = None
                error: BaseException | None = None
                retry = False
                try:
                    result, parsed = clients[endpoint_key].chat(messages, temperature=0.0, max_tokens=600, seed=int(call_row["seed"]), response_schema=MSExecutorFunctionReview, retries=1)
                except StructuredOutputValidationError as exc:
                    error, result, retry = exc, exc.call, True
                except RetryableProviderError as exc:
                    error, retry = exc, exc.last_retry_class in RETRYABLE
                except ProviderRequestError as exc:
                    error = exc
                except Exception as exc:
                    error = exc
                append_jsonl(raw_path, {
                    "protocol": "pm-v1.5-paper1-v3-ms-executor-function-proxy-raw-v1",
                    "logical_call_id": call_row["logical_call_id"], "reviewer_id": call_row["reviewer_id"], "stage": call_row["stage"], "blind_item_id": call_row["blind_item_id"], "attempt": attempt,
                    "request_hash": result.request_hash if result is not None else getattr(error, "request_hash", None),
                    "raw_text": result.text if result is not None else None,
                    "raw_response": result.raw_response if result is not None else None,
                    "parsed_before_gold": parsed.model_dump(mode="json") if parsed is not None else None,
                    "usage": result.usage if result is not None else getattr(error, "usage", None) or {},
                    "error": None if error is None else f"{type(error).__name__}: {error}",
                })
                if error is None and parsed is not None:
                    try:
                        reviewed = validate_review(parsed, item)
                        reviewed.update({"protocol": "pm-v1.5-paper1-v3-ms-executor-function-proxy-review-v1", "reviewer_id": call_row["reviewer_id"], "endpoint_key": endpoint_key, "model": call_row["model"], "stage": call_row["stage"], "request_hash": result.request_hash})
                        completed[key] = reviewed
                        write_jsonl(completed_path, list(completed.values()))
                        terminal = "success"
                        break
                    except ValueError as exc:
                        error, retry = exc, False
                if not retry:
                    terminal = f"failed:{error}"
                    break
            if terminal != "success":
                raise RuntimeError(f"Function proxy call failed closed: {call_row['logical_call_id']} {terminal}")
            if len(completed) % 12 == 0:
                print(f"Function proxy reviews {len(completed)}/88", flush=True)

    try:
        control_plan = [row for row in plan if row["stage"] == "CONTROL"]
        execute(control_plan, controls)
        gold = {row["blind_item_id"]: row["gold_label"] for row in rows(GOLD)}
        qualifications = {
            reviewer: qualifies([row for row in completed.values() if row["stage"] == "CONTROL" and row["reviewer_id"] == reviewer], gold)
            for reviewer in sorted({row["reviewer_id"] for row in control_plan})
        }
        write_json(OUT / "control_qualification.json", qualifications)
        if not all(row["passed"] for row in qualifications.values()):
            write_json(OUT / "live_report.json", {"protocol": dry["protocol"], "status": "CONTROL_QUALIFICATION_FAIL_PUBLIC_CALLS_ZERO", "qualifications": qualifications, "control_calls_completed": 24, "public_calls_completed": 0})
            print(json.dumps(read(OUT / "live_report.json"), ensure_ascii=False, indent=2))
            return
        execute([row for row in plan if row["stage"] == "PUBLIC"], public)
    finally:
        for client in clients.values():
            client.close()

    public_rows = [row for row in completed.values() if row["stage"] == "PUBLIC"]
    by_item: dict[str, list[str]] = {}
    for row in public_rows:
        by_item.setdefault(row["blind_item_id"], []).append(row["label"])
    exact_agreement = sum(len(set(labels)) == 1 for labels in by_item.values()) / 32
    report = {
        "protocol": dry["protocol"],
        "status": "FUNCTION_PROXY_REVIEWS_COMPLETE_ZERO_API_ANALYSIS_REQUIRED",
        "qualifications": qualifications,
        "control_calls_completed": 24,
        "public_calls_completed": len(public_rows),
        "public_exact_label_agreement": exact_agreement,
        "public_label_counts_by_reviewer": {reviewer: dict(Counter(row["label"] for row in public_rows if row["reviewer_id"] == reviewer)) for reviewer in qualifications},
        "human_gold_claimed": False,
        "api_proxy_measurement_only": True,
        "artifacts": {"reviews": {"path": str(completed_path.relative_to(ROOT)), "sha256": sha256_file(completed_path)}, "raw": {"path": str(raw_path.relative_to(ROOT)), "sha256": sha256_file(raw_path)}},
        "next": "ZERO_API_PRE_ADJUDICATION_FUNCTION_ANALYSIS",
    }
    write_json(OUT / "live_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
