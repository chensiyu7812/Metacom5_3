#!/usr/bin/env python3
"""Run one frozen G4B review stage with raw-first, bounded attempts.

This runner cannot read control gold or private case keys.  Controls and
public reviews are separate authority phases; a public run additionally
requires a frozen component-specific qualification report.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.api import (  # noqa: E402
    Endpoint,
    ProviderRequestError,
    RetryableProviderError,
    StructuredOutputValidationError,
    make_client,
)
from metacom_pm.attempt_ledger import PersistentAttemptLedger  # noqa: E402
from metacom_pm.io import (  # noqa: E402
    append_jsonl,
    canonical_json,
    sha256_file,
    sha256_text,
    write_json,
    write_jsonl,
)
from metacom_pm.paid_run_release import require_paid_run_release  # noqa: E402
from metacom_pm.v1_5_g4b_nonexclusive_suitability_review import (  # noqa: E402
    G4BSuitabilityReview,
    prompt_messages,
    validate_review,
)


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
CONTROL_PHASE = ROOT / "data/pm_v1_5_contracts/paper1_v3_g4b1_control_execution_phase_v1.json"
PUBLIC_PHASE = ROOT / "data/pm_v1_5_contracts/paper1_v3_g4b2_public_execution_phase_v1.json"
CONFIG = ROOT / "configs/paper1_v3_g4b_review_execution_v1.json"
ENDPOINTS = ROOT / "configs/pm_v1_5_strict_judge_bakeoff_v1.json"
PREFLIGHT = ROOT / "outputs/pm_v1_5_paper1_v3_g4b_review_preflight_v2_20260811"
PACKET = ROOT / "outputs/pm_v1_5_paper1_v3_g4a_packet_v2_20260811"
QUALIFICATION = ROOT / "outputs/pm_v1_5_paper1_v3_g4b1_control_qualification_20260811/report.json"
DEFAULT_OUT = ROOT / "outputs/pm_v1_5_paper1_v3_g4b_reviews_20260811"
STAGE = "paper1_v3_g4b_nonexclusive_suitability_review_v1"
REVIEWERS = {
    "REVIEWER_A": ("anthropic_claude_haiku_4_5", "reviewer_a"),
    "REVIEWER_B": ("openai_gpt_5_mini", "reviewer_b"),
}
MAX_ATTEMPTS = 2
MAX_OUTPUT_TOKENS = 500
RETRYABLE_CLASSES = {
    "rate_limited_429",
    "request_timeout_408",
    "http_5xx",
    "network_timeout",
    "missing_field",
    "provider_output_format",
}


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def endpoint(raw: Mapping[str, Any]) -> Endpoint:
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
        openai_reasoning_effort=raw.get("openai_reasoning_effort"),
    )


def _require_authority(run_stage: str) -> dict[str, Any]:
    authority = read(AUTHORITY)
    expected_id = {
        "controls": "G4B1_CONTROL_REVIEW_EXECUTION",
        "public": "G4B2_PUBLIC_DUAL_REVIEW_EXECUTION",
    }[run_stage]
    phase_path = CONTROL_PHASE if run_stage == "controls" else PUBLIC_PHASE
    current = authority["active_v3_phase"]
    if current["id"] != expected_id:
        raise RuntimeError(f"{run_stage} review is not the active authority phase")
    binding = current["active_phase_manifest"]
    if (
        binding["path"] != str(phase_path.relative_to(ROOT))
        or binding["sha256"] != sha256_file(phase_path)
    ):
        raise RuntimeError("active phase manifest binding drifted")
    phase = read(phase_path)
    for binding in [*phase["input_bindings"], *phase["implementation_bindings"]]:
        if sha256_file(ROOT / binding["path"]) != binding["sha256"]:
            raise RuntimeError(f"bound artifact drifted: {binding['path']}")
    return phase


def _surface_maps() -> dict[tuple[str, str, str], dict[str, Any]]:
    result: dict[tuple[str, str, str], dict[str, Any]] = {}
    for reviewer_id, (_endpoint_key, stem) in REVIEWERS.items():
        for stage, filename in (
            ("CONTROL", f"{stem}_controls.jsonl"),
            ("PUBLIC", f"{stem}_packet.jsonl"),
        ):
            for item in rows(PACKET / filename):
                result[(stage, reviewer_id, item["review_item_id"])] = item
    return result


def _actual_cost(ledger: PersistentAttemptLedger, endpoints: Mapping[str, Any]) -> float:
    total = 0.0
    for row in ledger.event_rows:
        if row.get("event") not in {"SUCCEEDED", "FAILED"}:
            continue
        usage = row.get("usage") or {}
        endpoint_key = str((row.get("metadata") or {}).get("endpoint_key") or "")
        if endpoint_key not in endpoints["candidates"]:
            continue
        raw = endpoints["candidates"][endpoint_key]
        total += (
            int(usage.get("prompt_tokens") or 0)
            * float(raw["input_usd_per_million_tokens"])
            + int(usage.get("completion_tokens") or 0)
            * float(raw["output_usd_per_million_tokens"])
        ) / 1_000_000
    return total


def _raw_record(
    *,
    reservation: Any,
    plan_row: Mapping[str, Any],
    call: Any | None,
    error: BaseException | None,
) -> dict[str, Any]:
    provider_text = None
    raw_response = None
    request_hash = None
    usage = None
    finish_reason = None
    if call is not None:
        provider_text = call.text
        raw_response = call.raw_response
        request_hash = call.request_hash
        usage = call.usage
        finish_reason = call.normalized_finish_reason
    elif isinstance(error, RetryableProviderError):
        provider_text = error.provider_text
        request_hash = error.request_hash
        usage = error.usage
        raw_response = error.response_diagnostics
    elif isinstance(error, ProviderRequestError):
        request_hash = error.request_hash
        usage = error.usage
        raw_response = error.response_diagnostics
    return {
        "protocol": "pm-v1.5-paper1-v3-g4b-raw-physical-attempt-v1",
        "attempt_key": reservation.attempt_key,
        "attempt_index": reservation.attempt_index,
        "logical_call_key": reservation.call_key,
        "call_stage": plan_row["call_stage"],
        "reviewer_id": plan_row["reviewer_id"],
        "review_item_id": plan_row["review_item_id"],
        "endpoint_key": plan_row["endpoint_key"],
        "model": plan_row["model"],
        "request_hash": request_hash,
        "usage": usage,
        "normalized_finish_reason": finish_reason,
        "provider_text": provider_text,
        "provider_text_sha256": (
            hashlib.sha256(provider_text.encode("utf-8")).hexdigest()
            if isinstance(provider_text, str)
            else None
        ),
        "raw_response": raw_response,
        "error_type": type(error).__name__ if error is not None else None,
        "error": str(error) if error is not None else None,
    }


def _prior_terminal_nonretryable(
    ledger: PersistentAttemptLedger, call_key: str
) -> bool:
    terminal = ledger.terminal_row(call_key)
    return bool(
        terminal
        and terminal.get("event") == "FAILED"
        and not bool((terminal.get("metadata") or {}).get("retry_allowed", False))
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-stage", choices=["controls", "public"], required=True)
    parser.add_argument("--run-identity", required=True)
    parser.add_argument("--accept-usd-cap", type=float, required=True)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    phase = _require_authority(args.run_stage)
    cap = float(phase["execution"]["absolute_usd_cap"])
    if args.accept_usd_cap != cap:
        raise RuntimeError(f"must accept exact frozen cap {cap:g}")
    config = read(CONFIG)
    release_stage = f"{STAGE}_{args.run_stage}"
    require_paid_run_release(
        config,
        config_path=CONFIG,
        stage=release_stage,
        run=True,
        run_identity=args.run_identity,
    )

    endpoints = read(ENDPOINTS)
    surfaces = _surface_maps()
    all_plan = rows(PREFLIGHT / "call_plan.jsonl")
    frozen_stage = "CONTROL" if args.run_stage == "controls" else "PUBLIC"
    selected = [row for row in all_plan if row["call_stage"] == frozen_stage]
    eligible = {"MP", "MS", "ME"}
    if args.run_stage == "public":
        qualification = read(QUALIFICATION)
        if qualification["status"] != "G4B1_CONTROL_QUALIFICATION_PASS_PUBLIC_PHASE_MAY_BE_DESIGNED":
            raise RuntimeError("public reviews require passing frozen controls")
        eligible = set(qualification["eligible_components"])
        selected = [row for row in selected if row["component"] in eligible]
    expected_count = 72 if args.run_stage == "controls" else sum(
        count for component, count in {"MP": 408, "MS": 408, "ME": 198}.items() if component in eligible
    )
    if len(selected) != expected_count or not selected:
        raise RuntimeError(
            f"selected call count drifted: {len(selected)} expected {expected_count}"
        )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    ledger = PersistentAttemptLedger(
        args.out_dir / "physical_attempt_ledger.jsonl",
        stage=STAGE,
        expected_calls={row["logical_call_key"]: MAX_ATTEMPTS for row in all_plan},
        maximum_total_attempts=len(all_plan) * MAX_ATTEMPTS,
    )
    raw_path = args.out_dir / "raw_physical_attempts.jsonl"
    clients: dict[str, Any] = {}
    try:
        for index, plan_row in enumerate(selected, 1):
            call_key = plan_row["logical_call_key"]
            reviewer_id = plan_row["reviewer_id"]
            _endpoint_key, stem = REVIEWERS[reviewer_id]
            output_path = args.out_dir / f"{stem}_{args.run_stage}_reviews.jsonl"
            completed = {
                row["review_item_id"]: row for row in rows(output_path)
            }
            if plan_row["review_item_id"] in completed or ledger.succeeded(call_key):
                continue
            if ledger.exhausted(call_key) or _prior_terminal_nonretryable(ledger, call_key):
                continue

            item = surfaces[(frozen_stage, reviewer_id, plan_row["review_item_id"])]
            messages = prompt_messages(item, reviewer_id)
            if sha256_text(canonical_json(messages)) != plan_row["prompt_sha256"]:
                raise RuntimeError("provider-visible prompt drift")
            endpoint_key = plan_row["endpoint_key"]
            if reviewer_id not in clients:
                clients[reviewer_id] = make_client(
                    endpoint(endpoints["candidates"][endpoint_key])
                )

            while not ledger.succeeded(call_key) and not ledger.exhausted(call_key):
                if _prior_terminal_nonretryable(ledger, call_key):
                    break
                reservation = ledger.reserve(
                    call_key,
                    record_ids={
                        "reviewer_id": reviewer_id,
                        "review_item_id": plan_row["review_item_id"],
                        "call_stage": frozen_stage,
                    },
                    prompt_sha256=plan_row["prompt_sha256"],
                )
                call = None
                parsed = None
                error: BaseException | None = None
                retry_allowed = False
                semantic_complete = False
                try:
                    call, parsed = clients[reviewer_id].chat(
                        messages,
                        temperature=0.0,
                        max_tokens=MAX_OUTPUT_TOKENS,
                        seed=int(plan_row["request_parameters"]["seed"]),
                        response_schema=G4BSuitabilityReview,
                        retries=1,
                    )
                except StructuredOutputValidationError as exc:
                    error = exc
                    call = exc.call
                    retry_allowed = True
                except RetryableProviderError as exc:
                    error = exc
                    retry_allowed = exc.last_retry_class in RETRYABLE_CLASSES
                except ProviderRequestError as exc:
                    error = exc
                    retry_allowed = False
                except Exception as exc:  # fail closed on unknown local/provider errors
                    error = exc
                    retry_allowed = False

                # Persist the exact provider return (or bounded failure
                # diagnostics) before local semantic validation or gold access.
                append_jsonl(
                    raw_path,
                    _raw_record(
                        reservation=reservation,
                        plan_row=plan_row,
                        call=call,
                        error=error,
                    ),
                )

                result = None
                if error is None and parsed is not None:
                    try:
                        result = validate_review(parsed, item)
                        semantic_complete = True
                    except ValueError as exc:
                        error = exc
                        # A complete strict-schema judgment that violates the
                        # frozen semantic contract is terminal. Never prompt-
                        # repair or retry it after seeing its decision.
                        retry_allowed = False

                metadata = {
                    "endpoint_key": endpoint_key,
                    "model": plan_row["model"],
                    "retry_allowed": retry_allowed,
                    "semantic_complete": semantic_complete,
                    "raw_persisted_before_semantic_validation": True,
                }
                if semantic_complete and result is not None and call is not None:
                    result.update(
                        {
                            "protocol": "pm-v1.5-paper1-v3-g4b-review-result-v1",
                            "reviewer_id": reviewer_id,
                            "component": plan_row["component"],
                            "call_stage": frozen_stage,
                            "endpoint_key": endpoint_key,
                            "model": plan_row["model"],
                            "request_hash": call.request_hash,
                            "raw_response_text_sha256": hashlib.sha256(
                                call.text.encode("utf-8")
                            ).hexdigest(),
                            "review_position": plan_row["review_position"],
                        }
                    )
                    ledger.finish(
                        reservation,
                        succeeded=True,
                        request_hash=call.request_hash,
                        usage=call.usage,
                        error=None,
                        result=result,
                        metadata=metadata,
                    )
                    completed[result["review_item_id"]] = result
                    write_jsonl(
                        output_path,
                        sorted(completed.values(), key=lambda row: row["review_position"]),
                    )
                else:
                    request_hash = call.request_hash if call is not None else getattr(error, "request_hash", None)
                    usage = call.usage if call is not None else getattr(error, "usage", None)
                    ledger.finish(
                        reservation,
                        succeeded=False,
                        request_hash=request_hash,
                        usage=usage,
                        error=f"{type(error).__name__}: {error}",
                        result=None,
                        metadata=metadata,
                    )
                    if not retry_allowed:
                        break

                if _actual_cost(ledger, endpoints) > cap:
                    raise RuntimeError("observed G4B stage cost exceeded frozen cap")
            if index % 12 == 0 or index == len(selected):
                print(
                    f"{args.run_stage} progress {index}/{len(selected)} attempts={ledger.started_attempts}",
                    flush=True,
                )
    finally:
        for client in clients.values():
            client.close()

    completed = sum(ledger.succeeded(row["logical_call_key"]) for row in selected)
    nonretryable = sum(
        _prior_terminal_nonretryable(ledger, row["logical_call_key"])
        for row in selected
    )
    report = {
        "protocol": "pm-v1.5-paper1-v3-g4b-live-stage-report-v1",
        "stage": args.run_stage,
        "status": (
            f"G4B_{frozen_stage}_REVIEWS_COMPLETE"
            if completed == len(selected)
            else f"G4B_{frozen_stage}_REVIEWS_INCOMPLETE"
        ),
        "planned_logical_calls": len(selected),
        "completed_valid_reviews": completed,
        "terminal_nonretryable_invalid": nonretryable,
        "physical_attempts_started": ledger.started_attempts,
        "observed_cost_usd": _actual_cost(ledger, endpoints),
        "absolute_usd_cap": cap,
        "raw_attempts_persisted": len(rows(raw_path)),
        "gold_or_private_key_read": False,
        "labels_created": 0,
        "public_components": sorted(eligible) if args.run_stage == "public" else [],
    }
    write_json(args.out_dir / f"{args.run_stage}_live_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
