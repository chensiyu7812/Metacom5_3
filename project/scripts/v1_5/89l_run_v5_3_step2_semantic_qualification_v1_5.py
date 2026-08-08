#!/usr/bin/env python3
"""Execute the authorized V5.3 Step2 Q64 qualification with a durable ledger."""

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
    OpenAICompatibleClient,
    RetryableProviderError,
    StructuredOutputValidationError,
)
from metacom_pm.config import endpoint_from_config, load_config  # noqa: E402
from metacom_pm.contracts import StrictModel  # noqa: E402
from metacom_pm.io import append_jsonl, read_json, sha256_file, utc_now, write_json  # noqa: E402
from metacom_pm.v1_5_v5_3_step2_semantic_qualification import (  # noqa: E402
    build_semantic_qualification_plan,
    semantic_qualification_programs,
)
from metacom_pm.v1_5_v5_3_typed_response_program import (  # noqa: E402
    RewritePolicy,
    execute_typed_response,
)


PREFLIGHT = (
    ROOT
    / "outputs/pm_v1_5_v5_3_step2_semantic_execution_preflight_v1/execution_preflight.json"
)
CONFIG = ROOT / "configs/experiment.yaml"
DEFAULT_OUT = ROOT / "outputs/pm_v1_5_v5_3_step2_semantic_execution_v1"
STAGE = "v5_3_step2_semantic_qualification_q64_v1"
TRANSPORT_RETRY_CLASSES = {
    "rate_limited_429", "request_timeout_408", "http_5xx", "network_timeout"
}


class _GeneratorSchema(StrictModel):
    reply: str
    used_evidence_ids: list[str]
    realized_response_act: str


class _RecordingClient:
    """Force one provider attempt and preserve any completed response usage."""

    def __init__(self, client: OpenAICompatibleClient, ledger: list[Any]):
        self.client = client
        self.ledger = ledger

    def chat(self, messages, *, response_schema):
        try:
            result, parsed = self.client.chat(
                messages,
                response_schema=response_schema,
                temperature=0.0,
                max_tokens=512,
                seed=None,
                retries=1,
            )
            self.ledger.append(result)
            return result, parsed
        except StructuredOutputValidationError as exc:
            self.ledger.append(exc.call)
            return exc.call, None


def _cost(usage: dict[str, int], preflight: dict[str, Any]) -> float:
    pricing = preflight["cost"]["pricing_usd_per_mtok_proxy"]
    return (
        int(usage.get("prompt_tokens") or 0) / 1_000_000 * float(pricing["input"])
        + int(usage.get("completion_tokens") or 0) / 1_000_000 * float(pricing["output"])
    )


def _ensure_fresh_out_dir(out_dir: Path) -> None:
    if out_dir.exists() and any(out_dir.iterdir()):
        raise RuntimeError(f"output directory is not fresh: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--run-identity", required=True)
    parser.add_argument("--maximum-usd", type=float, required=True)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    preflight = read_json(PREFLIGHT)
    if args.run_identity != preflight["run_identity"]:
        raise RuntimeError("run identity does not match frozen preflight")
    frozen_ceiling = float(preflight["cost"]["requested_authorization_ceiling_usd"])
    if abs(args.maximum_usd - frozen_ceiling) > 1e-12:
        raise RuntimeError("authorized maximum differs from frozen preflight ceiling")
    if not args.run:
        print(json.dumps({"status": "DRY_RUN", "run_identity": args.run_identity, "api_calls": 0}))
        return

    _ensure_fresh_out_dir(args.out_dir)
    approval = {
        "protocol": "pm-v1.5-v5.3-step2-semantic-approval-receipt-v1",
        "stage": STAGE,
        "run_identity": args.run_identity,
        "maximum_usd": args.maximum_usd,
        "authorized_user_phrase": (
            "我明确批准v53step2semexec_8f51ee42c67e85c41b3721b9d1b731fe，最高 $0.20。"
        ),
        "recorded_at_utc": utc_now(),
    }
    write_json(args.out_dir / "approval_receipt.json", approval)

    plan = build_semantic_qualification_plan()
    programs = semantic_qualification_programs()
    config = load_config(CONFIG)
    endpoint = endpoint_from_config(config, "generator")
    bound_endpoint = preflight["endpoint"]
    if endpoint.model != bound_endpoint["model"] or endpoint.base_url != bound_endpoint["base_url"]:
        raise RuntimeError("generator endpoint drifted from frozen preflight")

    outcomes_path = args.out_dir / "outcomes.jsonl"
    attempts_path = args.out_dir / "physical_attempt_ledger.jsonl"
    usage_total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    proxy_cost = 0.0
    physical_attempts = 0
    clean = 0
    fallback = 0
    client = OpenAICompatibleClient(endpoint)
    started = utc_now()
    terminal_error: dict[str, Any] | None = None
    try:
        for ordinal, case in enumerate(plan.cases, 1):
            program = programs[case.case_id]
            execution = None
            case_results: list[Any] = []
            for attempt in range(1, 3):
                physical_attempts += 1
                before = len(case_results)
                try:
                    execution = execute_typed_response(
                        _RecordingClient(client, case_results),
                        _GeneratorSchema,
                        case.messages,
                        program,
                        rewrite_policy=RewritePolicy.DETERMINISTIC_FALLBACK,
                    )
                    result = case_results[-1] if len(case_results) > before else None
                    attempt_row = {
                        "case_id": case.case_id,
                        "ordinal": ordinal,
                        "attempt": attempt,
                        "status": "completed",
                        "request_hash": result.request_hash if result else None,
                        "usage": result.usage if result else {},
                        "provider_finish_reason": result.provider_finish_reason if result else None,
                        "normalized_finish_reason": result.normalized_finish_reason if result else None,
                        "latency_ms": result.latency_ms if result else None,
                        "provider_text": result.text if result else None,
                        "structured_output_audit": result.structured_output_audit if result else None,
                    }
                    append_jsonl(attempts_path, attempt_row)
                    if result:
                        for key in usage_total:
                            usage_total[key] += int(result.usage.get(key) or 0)
                        proxy_cost += _cost(result.usage, preflight)
                    break
                except RetryableProviderError as exc:
                    retryable = exc.last_retry_class in TRANSPORT_RETRY_CLASSES and attempt < 2
                    usage = dict(exc.usage or {})
                    for key in usage_total:
                        usage_total[key] += int(usage.get(key) or 0)
                    proxy_cost += _cost(usage, preflight)
                    append_jsonl(
                        attempts_path,
                        {
                            "case_id": case.case_id,
                            "ordinal": ordinal,
                            "attempt": attempt,
                            "status": "transport_retry" if retryable else "terminal_error",
                            "retry_class": exc.last_retry_class,
                            "status_code": exc.last_status_code,
                            "usage": usage,
                            "request_hash": exc.request_hash,
                        },
                    )
                    if not retryable:
                        terminal_error = {
                            "case_id": case.case_id,
                            "ordinal": ordinal,
                            "error": str(exc),
                            "retry_class": exc.last_retry_class,
                        }
                        break
                    time.sleep(30.0 if exc.last_retry_class == "rate_limited_429" else 2.0)
            if proxy_cost > args.maximum_usd:
                raise RuntimeError("actual proxy cost exceeded the authorized hard ceiling")
            if terminal_error is not None or execution is None:
                break
            clean += int(execution.status == "clean")
            fallback += int(execution.status == "fell_back_to_m0")
            append_jsonl(
                outcomes_path,
                {
                    "case_id": case.case_id,
                    "ordinal": ordinal,
                    "semantic_family": case.semantic_family,
                    "requested_action_id": case.action_id,
                    "realized_action_id": execution.realized_action_id,
                    "status": execution.status,
                    "reply": execution.response.reply if execution.response else None,
                    "normalized_used_evidence_ids": list(execution.used_evidence_ids),
                    "reported_used_evidence_ids": list(execution.reported_used_evidence_ids),
                    "first_pass_errors": list(execution.first_pass_errors),
                    "final_guard_errors": list(execution.final_guard_errors),
                    "calls_made": execution.calls_made,
                    "rewrite_attempted": execution.rewrite_attempted,
                },
            )
    finally:
        client.close()

    completed = clean + fallback
    manifest = {
        "protocol": "pm-v1.5-v5.3-step2-semantic-qualification-execution-v1",
        "status": "COMPLETE_AWAITING_SINGLE_SEMANTIC_REVIEW" if completed == 64 else "INCOMPLETE_TERMINAL",
        "stage": STAGE,
        "run_identity": args.run_identity,
        "started_at_utc": started,
        "completed_at_utc": utc_now(),
        "logical_calls_planned": 64,
        "logical_calls_completed": completed,
        "clean": clean,
        "deterministic_fallback": fallback,
        "physical_attempts": physical_attempts,
        "usage": usage_total,
        "proxy_cost_usd": round(proxy_cost, 9),
        "authorized_ceiling_usd": args.maximum_usd,
        "terminal_error": terminal_error,
        "plan_manifest_sha256": preflight["plan_manifest_sha256"],
        "cases_sha256": preflight["cases_sha256"],
        "preflight_sha256": sha256_file(PREFLIGHT),
        "api_calls": physical_attempts,
        "formal_fit_or_external_outcome_used": False,
    }
    if outcomes_path.exists():
        manifest["outcomes_sha256"] = sha256_file(outcomes_path)
    if attempts_path.exists():
        manifest["physical_attempt_ledger_sha256"] = sha256_file(attempts_path)
    write_json(args.out_dir / "run_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    if completed != 64:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
