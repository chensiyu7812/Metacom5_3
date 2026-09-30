#!/usr/bin/env python3
"""Submit, poll and recover the official QA/Summary scoring as an OpenAI Batch.

Model, prompts and parsers are the same as the synchronous path: only the
delivery mechanism changes, so the official method identity is untouched. Batch
is priced at half the synchronous rate with a 24-hour completion window.

A batch is a liability from the moment it is submitted, not when it returns, so
the whole batch reserves its full worst case against the follow-up budget
before submission and stays counted until it settles. That is the part a serial
balance check gets wrong.

Halving an old synchronous estimate is not a promise that a batch will finish
inside a budget, so this refuses to submit until real predictions exist and the
cost has been computed from their measured tokens.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path

import httpx

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import canonical_json, iter_jsonl, read_json, sha256_file, sha256_text, utc_now, write_json
from metacom_pm.paper1.api_budget import CumulativePaper1ApiBudgetLedger
from metacom_pm.paper1.evaluation.static_official_scoring import OfficialParseError, parse_official_reply
from metacom_pm.paper1.followup_budget import FollowupBudget, FollowupBudgetExceeded
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config

import importlib.util as _ilu
_spec = _ilu.spec_from_file_location(
    "static_official_scoring_runner", Path(__file__).with_name("80_execute_official_static_scoring.py"))
sync_runner = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(sync_runner)

AUTHORITY = PROJECT / "data/paper1_authority/paper1_static_amount_calibration_execution_20260917_v1.json"
CONFIG = PROJECT / "configs/paper1_public_only.yaml"
LEDGER = PROJECT / "outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl"
FOLLOWUP_SNAPSHOT = PROJECT / "outputs/paper1_api_budget/followup_budget_boundary_20260918_v1.json"
PROTOCOL = "paper1-static-amount-official-scoring-batch-v1"
STAGE = "static_amount_calibration_official_scoring_batch_v1"
PROVIDER = "OpenAI Batch API"
BASE = "https://api.openai.com/v1"
# Batch is half the synchronous published rate.
BATCH_INPUT_USD_PER_MILLION = Decimal("1.25")
BATCH_OUTPUT_USD_PER_MILLION = Decimal("5")
TERMINAL_STATES = {"completed", "failed", "expired", "cancelled"}


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(path)


def batch_worst_case_usd(payloads: list[dict], scorer_config: dict) -> Decimal:
    """Whole-batch worst case: measured inputs plus a full native output each."""
    total = Decimal("0")
    allowance = Decimal(scorer_config["provider_max_output_tokens"])
    for payload in payloads:
        inputs = Decimal(payload["estimated_input_tokens_with_framing_reserve"])
        total += (inputs * BATCH_INPUT_USD_PER_MILLION + allowance * BATCH_OUTPUT_USD_PER_MILLION)
    return total / Decimal(1_000_000)


def observed_batch_usd(usage: dict) -> Decimal:
    return (Decimal(usage["prompt_tokens"]) * BATCH_INPUT_USD_PER_MILLION
            + Decimal(usage["completion_tokens"]) * BATCH_OUTPUT_USD_PER_MILLION) / Decimal(1_000_000)


def build_batch_lines(payloads: list[dict]) -> list[dict]:
    """One JSONL line per official call, keyed by request_id for recovery."""
    return [{"custom_id": p["request_id"], "method": "POST", "url": "/v1/chat/completions",
             "body": p["body"]} for p in payloads]


def liabilities_from(state_dir: Path) -> list[dict]:
    path = state_dir / "batches.json"
    return read_json(path)["batches"] if path.exists() else []


def record_liability(state_dir: Path, entry: dict) -> list[dict]:
    rows = {row["batch_id"]: row for row in liabilities_from(state_dir)}
    rows[entry["batch_id"]] = {**rows.get(entry["batch_id"], {}), **entry}
    ordered = sorted(rows.values(), key=lambda r: r["batch_id"])
    atomic_json(state_dir / "batches.json", {"protocol": PROTOCOL, "updated_at": utc_now(),
                                             "batches": ordered})
    return ordered


def parse_batch_output(lines: list[str], payloads: dict[str, dict]) -> tuple[list[dict], dict]:
    """Turn provider output lines into official scores, keeping failures visible."""
    records, usage_total = [], Counter()
    for line in lines:
        if not line.strip():
            continue
        row = json.loads(line)
        request_id = row.get("custom_id")
        payload = payloads.get(request_id)
        if payload is None:
            raise RuntimeError(f"batch returned an unknown custom_id: {request_id}")
        response = (row.get("response") or {})
        body = response.get("body") or {}
        base = {"protocol": PROTOCOL, "request_id": request_id, "target_id": payload["target_id"],
                "task": payload["task"], "call_hash": payload["call_hash"],
                "logical_call_id": payload["logical_call_id"],
                "prediction_sha256": payload["prediction_sha256"],
                "delivery": "batch", "completed_at": utc_now()}
        if row.get("error") or response.get("status_code") != 200 or "usage" not in body:
            records.append({**base, "status": "PROVIDER_ERROR",
                            "http_status": response.get("status_code"),
                            "error": json.dumps(row.get("error"), ensure_ascii=False)[:2000]})
            continue
        usage = body["usage"]
        usage_total["prompt_tokens"] += usage["prompt_tokens"]
        usage_total["completion_tokens"] += usage["completion_tokens"]
        reply = body["choices"][0]["message"].get("content") or ""
        record = {**base, "status": "SCORED", "raw_reply": reply, "usage": usage,
                  "official_finish_reason": body["choices"][0].get("finish_reason"),
                  "actual_cost_usd": str(observed_batch_usd(usage))}
        try:
            record["official"] = parse_official_reply(payload["task"], reply)
        except OfficialParseError as exc:
            # Same rule as the synchronous path: no score, never a zero.
            record.update(status="OFFICIAL_PARSE_FAILED", parse_error=str(exc), official=None)
        records.append(record)
    return records, dict(usage_total)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path,
                        default=PROJECT / "outputs/paper1_calibration/static_sample_20260917_v1")
    parser.add_argument("--bound", type=Path,
                        default=PROJECT / "outputs/paper1_calibration/static_official_scoring_20260917_v1")
    parser.add_argument("--out", type=Path,
                        default=PROJECT / "outputs/paper1_calibration/static_official_batch_20260918_v1")
    parser.add_argument("--action", choices=["preflight", "submit", "poll", "recover"],
                        default="preflight")
    parser.add_argument("--batch-id", help="poll or recover this specific batch")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    assert_pre_outcome_locked(load_public_only_config(CONFIG))
    authority = read_json(AUTHORITY)
    scorer_config = read_json(args.package / "scorer_config.json")
    manifest = read_json(args.bound / "manifest.json")
    if sha256_file(args.bound / "requests.jsonl") != manifest["request_file_sha256"]:
        raise RuntimeError("bound scorer payload file changed after 78 produced it")
    all_payloads = list(iter_jsonl(args.bound / "requests.jsonl"))
    # Byte-identical official prompts are scored once; see deduplicate() in 80.
    payloads, aliases = sync_runner.deduplicate(all_payloads)
    by_id = {p["request_id"]: p for p in payloads}

    ledger = CumulativePaper1ApiBudgetLedger(LEDGER)
    followup = FollowupBudget(ledger, FOLLOWUP_SNAPSHOT)
    args.out.mkdir(parents=True, exist_ok=True)
    liabilities = liabilities_from(args.out)

    worst_case = batch_worst_case_usd(payloads, scorer_config)
    stage = authority.get("paid_scoring_stage", {})
    authorized = bool(scorer_config.get("new_paid_execution_authorized")
                      and authority.get("new_paid_API_calls_authorized")
                      and stage.get("proposed_cap_authorized"))
    status = followup.status(liabilities)
    report = {
        "protocol": PROTOCOL, "generated_at": utc_now(), "action": args.action,
        "delivery": "OpenAI Batch API", "turnaround": "24 hours",
        "official_identity_unchanged": {
            "model": scorer_config["model"], "prompts": "unchanged upstream bytes",
            "parsers": "unchanged upstream parsers",
            "temperature": scorer_config["temperature"],
            "max_completion_tokens": scorer_config["max_completion_tokens"],
            "only_delivery_mechanism_differs": True},
        "calls_to_make": len(payloads),
        "submitted_rows_total_before_dedup": len(all_payloads),
        "requests_served_by_identical_payload_reuse": sum(len(v) for v in aliases.values()),
        "calls_by_task": dict(Counter(p["task"] for p in payloads)),
        "measured_input_tokens": sum(p["estimated_input_tokens_with_framing_reserve"] for p in payloads),
        "batch_price_per_million_usd": {"input": str(BATCH_INPUT_USD_PER_MILLION),
                                        "output": str(BATCH_OUTPUT_USD_PER_MILLION)},
        "whole_batch_worst_case_usd": str(worst_case),
        "worst_case_is_not_a_predicted_bill": True,
        "halving_an_old_estimate_is_not_a_completion_guarantee": True,
        "paid_execution_authorized": authorized,
        "followup_budget": status.as_dict(),
        "outstanding_batches": liabilities,
        "k_star_frozen": False, "formal_outcomes": 0, "PM_training_runs": 0,
    }

    if not payloads:
        report["blocked"] = ("no bound payloads: real natural-end generations must exist before a "
                             "batch can be priced or submitted")
        atomic_json(args.out / f"{args.action}.json", report)
        print(json.dumps({k: report[k] for k in ["action", "calls_to_make", "blocked"]},
                         ensure_ascii=False, indent=2))
        return

    if args.action == "preflight":
        report["fits_followup_cap"] = not followup.would_exceed(worst_case, liabilities=liabilities)
        lines = build_batch_lines(payloads)
        input_path = args.out / "batch_input.jsonl"
        input_path.write_text("".join(canonical_json(row) + "\n" for row in lines), encoding="utf-8")
        report["batch_input_sha256"] = sha256_file(input_path)
        atomic_json(args.out / "preflight.json", report)
        print(json.dumps({k: report[k] for k in
                          ["action", "calls_to_make", "measured_input_tokens",
                           "whole_batch_worst_case_usd", "fits_followup_cap", "followup_budget"]},
                         ensure_ascii=False, indent=2))
        return

    if not authorized:
        raise RuntimeError("paid batch scoring is not authorized; run --action preflight for the quote")
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is absent; no paid work is submitted")

    with httpx.Client(headers={"Authorization": f"Bearer {key}"}, timeout=args.timeout,
                      follow_redirects=False) as client:
        if args.action == "submit":
            if any(row["state"] not in {"SETTLED", "CANCELLED"} for row in liabilities):
                raise RuntimeError("an earlier batch is still outstanding; poll it before submitting another")
            # The liability exists from submission, so it is checked first.
            followup.check(worst_case, liabilities=liabilities, what="official scoring batch")
            input_path = args.out / "batch_input.jsonl"
            if not input_path.exists():
                raise RuntimeError("run --action preflight first to materialize the batch input")
            upload = client.post(f"{BASE}/files",
                                 files={"file": ("batch_input.jsonl", input_path.read_bytes())},
                                 data={"purpose": "batch"})
            upload.raise_for_status()
            file_id = upload.json()["id"]
            created = client.post(f"{BASE}/batches", json={
                "input_file_id": file_id, "endpoint": "/v1/chat/completions",
                "completion_window": "24h"})
            created.raise_for_status()
            batch = created.json()
            entry = {"batch_id": batch["id"], "input_file_id": file_id, "state": "IN_PROGRESS",
                     "provider_status": batch.get("status"), "submitted_at": utc_now(),
                     "worst_case_usd": str(worst_case), "calls": len(payloads),
                     "batch_input_sha256": sha256_file(input_path)}
            liabilities = record_liability(args.out, entry)
            report.update(submitted=entry, followup_budget=followup.status(liabilities).as_dict())
            atomic_json(args.out / "submit.json", report)
            print(json.dumps({"submitted": entry["batch_id"], "calls": len(payloads),
                              "worst_case_usd": str(worst_case),
                              "followup_budget": report["followup_budget"]},
                             ensure_ascii=False, indent=2))
            return

        target = args.batch_id or next((r["batch_id"] for r in liabilities
                                        if r["state"] not in {"SETTLED", "CANCELLED"}), None)
        if target is None:
            raise RuntimeError("no outstanding batch to poll or recover")
        fetched = client.get(f"{BASE}/batches/{target}")
        fetched.raise_for_status()
        batch = fetched.json()
        provider_status = batch.get("status")
        report["provider_status"] = provider_status
        if provider_status not in TERMINAL_STATES:
            record_liability(args.out, {"batch_id": target, "state": "IN_PROGRESS",
                                        "provider_status": provider_status,
                                        "polled_at": utc_now()})
            atomic_json(args.out / "poll.json", report)
            print(json.dumps({"batch_id": target, "provider_status": provider_status,
                              "still_outstanding": True}, ensure_ascii=False, indent=2))
            return

        records, usage_total = [], {}
        output_file_id = batch.get("output_file_id")
        if output_file_id:
            content = client.get(f"{BASE}/files/{output_file_id}/content")
            content.raise_for_status()
            raw_path = args.out / f"batch_output_{target}.jsonl"
            raw_path.write_bytes(content.content)
            records, usage_total = parse_batch_output(content.text.splitlines(), by_id)
            scores_dir = args.out / "scores"
            for record in records:
                atomic_json(scores_dir / (record["request_id"] + ".json"), record)

        actual = observed_batch_usd(usage_total) if usage_total else Decimal("0")
        reservation = ledger.reserve(
            reservation_id=f"{STAGE}:{target}", logical_call_id=f"{STAGE}:{target}",
            call_hash=sha256_text(target), stage=STAGE, provider=PROVIDER,
            model=scorer_config["model"], maximum_cost_usd=worst_case, call_class="PRIMARY")
        ledger.settle(reservation, actual_cost_usd=min(actual, worst_case),
                      outcome="SUCCEEDED" if provider_status == "completed" else "FAILED",
                      allow_overrun=actual > worst_case)
        liabilities = record_liability(args.out, {
            "batch_id": target, "state": "SETTLED", "provider_status": provider_status,
            "settled_at": utc_now(), "actual_cost_usd": str(actual),
            "worst_case_usd": str(worst_case), "scored": len(records)})
        missing = sorted(set(by_id) - {r["request_id"] for r in records})
        report.update(records=len(records), usage_total=usage_total,
                      actual_cost_usd=str(actual), missing_request_ids=missing,
                      statuses=dict(Counter(r["status"] for r in records)),
                      followup_budget=followup.status(liabilities).as_dict())
        atomic_json(args.out / f"recover_{target}.json", report)
        print(json.dumps({"batch_id": target, "provider_status": provider_status,
                          "scored": len(records), "missing": len(missing),
                          "actual_cost_usd": str(actual),
                          "followup_budget": report["followup_budget"]},
                         ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
