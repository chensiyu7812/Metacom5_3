#!/usr/bin/env python3
"""Rerun only the 14 Q64 rows whose original provider text was not retained."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.api import (  # noqa: E402
    OpenAICompatibleClient, RetryableProviderError, StructuredOutputValidationError,
)
from metacom_pm.config import endpoint_from_config, load_config  # noqa: E402
from metacom_pm.contracts import StrictModel  # noqa: E402
from metacom_pm.io import append_jsonl, read_json, sha256_file, utc_now, write_json  # noqa: E402
from metacom_pm.v1_5_v5_3_step2_semantic_qualification import (  # noqa: E402
    build_semantic_qualification_plan, semantic_qualification_programs,
)
from metacom_pm.v1_5_v5_3_typed_response_program import (  # noqa: E402
    RewritePolicy, execute_typed_response,
)


PREFLIGHT = ROOT / "outputs/pm_v1_5_v5_3_step2_q64_measurement_continuation_preflight_v1/execution_preflight.json"
CONFIG = ROOT / "configs/experiment.yaml"
DEFAULT_OUT = ROOT / "outputs/pm_v1_5_v5_3_step2_q64_measurement_continuation_v1"
TRANSPORT_RETRY_CLASSES = {"rate_limited_429", "request_timeout_408", "http_5xx", "network_timeout"}


class _Schema(StrictModel):
    reply: str
    used_evidence_ids: list[str]
    realized_response_act: str


class _Recorder:
    def __init__(self, client: OpenAICompatibleClient, calls: list[Any]):
        self.client = client
        self.calls = calls

    def chat(self, messages, *, response_schema):
        try:
            result, parsed = self.client.chat(
                messages, response_schema=response_schema, temperature=0.0,
                max_tokens=512, seed=None, retries=1,
            )
            self.calls.append(result)
            return result, parsed
        except StructuredOutputValidationError as exc:
            self.calls.append(exc.call)
            return exc.call, None


def _cost(usage: dict[str, int], preflight: dict[str, Any]) -> float:
    prices = preflight["pricing_usd_per_mtok_proxy"]
    return (
        int(usage.get("prompt_tokens") or 0) / 1_000_000 * float(prices["input"])
        + int(usage.get("completion_tokens") or 0) / 1_000_000 * float(prices["output"])
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--run-identity", required=True)
    parser.add_argument("--maximum-usd", required=True, type=float)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    preflight = read_json(PREFLIGHT)
    if args.run_identity != preflight["run_identity"]:
        raise RuntimeError("continuation identity mismatch")
    if abs(args.maximum_usd - float(preflight["requested_authorization_ceiling_usd"])) > 1e-12:
        raise RuntimeError("continuation cost ceiling mismatch")
    if not args.run:
        print(json.dumps({"status": "DRY_RUN", "api_calls": 0, "run_identity": args.run_identity}))
        return
    if args.out_dir.exists() and any(args.out_dir.iterdir()):
        raise RuntimeError("continuation output directory is not fresh")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    plan_by_id = {case.case_id: case for case in build_semantic_qualification_plan().cases}
    programs = semantic_qualification_programs()
    case_ids = list(preflight["affected_case_ids"])
    if any(case_id not in plan_by_id or case_id not in programs for case_id in case_ids):
        raise RuntimeError("continuation case binding drift")
    endpoint = endpoint_from_config(load_config(CONFIG), "generator")
    if endpoint.model != preflight["model"]:
        raise RuntimeError("continuation model drift")
    client = OpenAICompatibleClient(endpoint)
    attempts = args.out_dir / "physical_attempt_ledger.jsonl"
    outcomes = args.out_dir / "outcomes.jsonl"
    usage_total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    spent = 0.0
    completed = 0
    terminal_error = None
    try:
        for ordinal, case_id in enumerate(case_ids, 1):
            case = plan_by_id[case_id]
            calls: list[Any] = []
            execution = None
            for attempt in range(1, 3):
                before = len(calls)
                try:
                    execution = execute_typed_response(
                        _Recorder(client, calls), _Schema, case.messages, programs[case_id],
                        rewrite_policy=RewritePolicy.DETERMINISTIC_FALLBACK,
                    )
                    result = calls[-1] if len(calls) > before else None
                    row = {
                        "case_id": case_id, "ordinal": ordinal, "attempt": attempt,
                        "status": "completed", "usage": result.usage if result else {},
                        "request_hash": result.request_hash if result else None,
                        "provider_finish_reason": result.provider_finish_reason if result else None,
                        "provider_text": result.text if result else None,
                        "structured_output_audit": result.structured_output_audit if result else None,
                    }
                    append_jsonl(attempts, row)
                    if result:
                        for key in usage_total:
                            usage_total[key] += int(result.usage.get(key) or 0)
                        spent += _cost(result.usage, preflight)
                    break
                except RetryableProviderError as exc:
                    retryable = exc.last_retry_class in TRANSPORT_RETRY_CLASSES and attempt < 2
                    failure_usage = dict(exc.usage or {})
                    for key in usage_total:
                        usage_total[key] += int(failure_usage.get(key) or 0)
                    spent += _cost(failure_usage, preflight)
                    append_jsonl(attempts, {
                        "case_id": case_id, "ordinal": ordinal, "attempt": attempt,
                        "status": "transport_retry" if retryable else "terminal_error",
                        "retry_class": exc.last_retry_class, "usage": failure_usage,
                    })
                    if not retryable:
                        terminal_error = {"case_id": case_id, "error": str(exc)}
                        break
                    time.sleep(30.0 if exc.last_retry_class == "rate_limited_429" else 2.0)
            if spent > args.maximum_usd:
                raise RuntimeError("continuation exceeded authorized ceiling")
            if terminal_error or execution is None:
                break
            completed += 1
            append_jsonl(outcomes, {
                "case_id": case_id,
                "semantic_family": case.semantic_family,
                "requested_action_id": case.action_id,
                "realized_action_id": execution.realized_action_id,
                "status": execution.status,
                "reply": execution.response.reply if execution.response else None,
                "reported_used_evidence_ids": list(execution.reported_used_evidence_ids),
                "normalized_used_evidence_ids": list(execution.used_evidence_ids),
                "first_pass_errors": list(execution.first_pass_errors),
                "final_guard_errors": list(execution.final_guard_errors),
            })
    finally:
        client.close()

    manifest = {
        "protocol": "pm-v1.5-v5.3-step2-q64-measurement-continuation-execution-v1",
        "status": "COMPLETE_AWAITING_SINGLE_SEMANTIC_REVIEW" if completed == 14 else "INCOMPLETE_TERMINAL",
        "run_identity": args.run_identity,
        "logical_calls_planned": 14,
        "logical_calls_completed": completed,
        "physical_attempts": sum(1 for _ in open(attempts, encoding="utf-8")) if attempts.exists() else 0,
        "usage": usage_total,
        "proxy_cost_usd": round(spent, 9),
        "authorized_ceiling_usd": args.maximum_usd,
        "terminal_error": terminal_error,
        "preflight_sha256": sha256_file(PREFLIGHT),
        "api_calls": sum(1 for _ in open(attempts, encoding="utf-8")) if attempts.exists() else 0,
    }
    if attempts.exists():
        manifest["attempt_ledger_sha256"] = sha256_file(attempts)
    if outcomes.exists():
        manifest["outcomes_sha256"] = sha256_file(outcomes)
    write_json(args.out_dir / "run_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    if completed != 14:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
