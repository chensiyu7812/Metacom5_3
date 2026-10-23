#!/usr/bin/env python3
"""Execute or preflight the official QA/Summary scoring of generated predictions.

Consumes the offline payload manifest built by 78 from real natural-end
Generator responses. Official upstream prompts and parsers are used unchanged;
a local judge can never substitute for them.

The default is a free preflight that produces the exact call list and the real
cost manifest. A paid run additionally requires a researcher record that sets
`new_paid_execution_authorized` together with an explicit stage cap, and every
request reserves its full worst case (complete input plus the provider's native
maximum output) in the cumulative Paper-1 ledger before it is sent. Answers are
never shortened to fit a budget: execution stops before the reservation that
would breach the stage or cumulative cap.
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
from metacom_pm.paper1.api_budget import (
    CumulativePaper1ApiBudgetLedger, PAPER1_API_HARD_CAP_USD, PAPER1_RETRY_RESERVE_USD,
)
from metacom_pm.paper1.evaluation.static_official_scoring import OfficialParseError, parse_official_reply
from metacom_pm.paper1.followup_budget import (
    FOLLOWUP_HARD_CAP_USD, FOLLOWUP_TARGET_USD, FollowupBudget,
)
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config

AUTHORITY = PROJECT / "data/paper1_authority/paper1_static_amount_calibration_execution_20260917_v1.json"
CONFIG = PROJECT / "configs/paper1_public_only.yaml"
LEDGER = PROJECT / "outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl"
FOLLOWUP_SNAPSHOT = PROJECT / "outputs/paper1_api_budget/followup_budget_boundary_20260918_v1.json"
PROTOCOL = "paper1-static-amount-official-scoring-v1"
STAGE = "static_amount_calibration_official_scoring_v1"
ENDPOINT = "https://api.openai.com/v1/chat/completions"
PROVIDER = "OpenAI Chat Completions"
INPUT_USD_PER_MILLION = Decimal("2.5")
OUTPUT_USD_PER_MILLION = Decimal("10")


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(path)


def worst_case_usd(payload: dict, scorer_config: dict) -> Decimal:
    """Complete observed input plus the provider's native maximum output."""
    inputs = Decimal(payload["estimated_input_tokens_with_framing_reserve"])
    outputs = Decimal(scorer_config["provider_max_output_tokens"])
    return (inputs * INPUT_USD_PER_MILLION + outputs * OUTPUT_USD_PER_MILLION) / Decimal(1_000_000)


def observed_usd(usage: dict) -> Decimal:
    return (Decimal(usage["prompt_tokens"]) * INPUT_USD_PER_MILLION
            + Decimal(usage["completion_tokens"]) * OUTPUT_USD_PER_MILLION) / Decimal(1_000_000)


def deduplicate(payloads: list[dict]) -> tuple[list[dict], dict[str, list[str]]]:
    """Score each byte-identical official payload once and reuse the result.

    Different k values sometimes make the Generator produce the same answer for
    the same target, so their scorer prompts are identical down to the byte.
    The ledger already refuses to pay twice for one call hash, and paying twice
    would buy nothing, so the first request carrying a hash is the one sent and
    the others are mapped onto its score.

    This is a disclosed deviation from one-call-per-row: the official scorer
    omits temperature, so a second call on the same prompt could have returned a
    different score. Reuse removes that within-duplicate variance.
    """
    unique, aliases = [], {}
    for payload in payloads:
        digest = payload["call_hash"]
        if digest in aliases:
            aliases[digest].append(payload["request_id"])
            continue
        aliases[digest] = []
        unique.append(payload)
    return unique, {h: ids for h, ids in aliases.items() if ids}


def load_payloads(bound: Path) -> tuple[dict, list[dict], dict[str, list[str]]]:
    manifest = read_json(bound / "manifest.json")
    if sha256_file(bound / "requests.jsonl") != manifest["request_file_sha256"]:
        raise RuntimeError("bound scorer payload file changed after 78 produced it")
    payloads = list(iter_jsonl(bound / "requests.jsonl"))
    if len(payloads) != manifest["naturally_complete_scorer_payloads"]:
        raise RuntimeError("payload count disagrees with the binding manifest")
    if len({p["request_id"] for p in payloads}) != len(payloads):
        raise RuntimeError("duplicate request identity in the bound payloads")
    unique, aliases = deduplicate(payloads)
    return manifest, unique, aliases


def cost_manifest(manifest: dict, payloads: list[dict], scorer_config: dict, ledger) -> dict:
    per_task = Counter(p["task"] for p in payloads)
    reservations = {p["call_hash"]: worst_case_usd(p, scorer_config) for p in payloads}
    total_worst = sum(reservations.values(), Decimal(0))
    observed_inputs = Counter()
    for p in payloads:
        observed_inputs[p["task"]] += p["estimated_input_tokens_with_framing_reserve"]
    return {
        "protocol": PROTOCOL,
        "stage": STAGE,
        "model": scorer_config["model"],
        "official_calls_to_make": len(payloads),
        "calls_by_task": dict(per_task),
        "observed_input_tokens_by_task": dict(observed_inputs),
        "observed_total_input_tokens": sum(observed_inputs.values()),
        "input_token_counts_are_measured_from_real_predictions": True,
        "sum_of_full_worst_case_reservations_usd": str(total_worst),
        "largest_single_reservation_usd": str(max(reservations.values())) if reservations else "0",
        "worst_case_output_allowance_tokens_per_call": scorer_config["provider_max_output_tokens"],
        "input_only_cost_at_observed_tokens_usd": str(
            (Decimal(sum(observed_inputs.values())) * INPUT_USD_PER_MILLION) / Decimal(1_000_000)),
        "output_cost_is_unknown_until_executed": True,
        "price_per_million_usd": {"input": str(INPUT_USD_PER_MILLION), "output": str(OUTPUT_USD_PER_MILLION)},
        "cumulative_accounted_usd": str(ledger.accounted_cost_usd),
        "cumulative_remaining_usd": str(ledger.remaining_usd),
        "stage_accounted_usd": str(ledger.accounted_stage_cost_usd(STAGE)),
        "note": ("Reservations are sequential worst cases, not a prediction of the settled bill. "
                 "Execution stops before a reservation that would breach the stage or cumulative cap; "
                 "no answer is truncated to fit a budget."),
    }


def call_official_judge(client: httpx.Client, body: dict, timeout: float) -> tuple[int, dict | None, str]:
    response = client.post(ENDPOINT, json=body, timeout=timeout)
    text = response.text
    try:
        return response.status_code, response.json(), text
    except ValueError:
        return response.status_code, None, text


def execute_payloads(pending: list[dict], *, scorer_config: dict, ledger, stage_cap: Decimal,
                     scores_dir: Path, send, on_record=None, followup=None,
                     liabilities: list[dict] | None = None) -> tuple[dict | None, list[dict], list[dict]]:
    """Reserve, send, settle, parse and persist one payload at a time.

    `send(body) -> (status, parsed_json_or_None, raw_text)` isolates transport so
    the whole money path can be exercised without a provider. Every attempt is
    reserved at its full worst case before it is sent and settled afterwards; an
    unknown-cost outcome stays accounted at that maximum. Execution stops before
    the reservation that would breach the stage or cumulative cap rather than
    shortening any answer.
    """
    stopped, records, skipped = None, [], []
    for payload in pending:
        if ledger.has_successful_call_hash(payload["call_hash"]):
            # Recovery after a lost result file: the call was already paid for,
            # so re-sending it would be a second charge for the same request.
            skipped.append({"request_id": payload["request_id"], "call_hash": payload["call_hash"],
                            "reason": "already_settled_successfully_in_ledger"})
            continue
        maximum = worst_case_usd(payload, scorer_config)
        projected_stage = ledger.accounted_stage_cost_usd(STAGE) + maximum
        if projected_stage > stage_cap:
            stopped = {"reason": "stage_cap_reached", "request_id": payload["request_id"],
                       "would_be_stage_usd": str(projected_stage), "stage_cap_usd": str(stage_cap)}
            break
        # A non-retry call must also leave the USD 5 primary-retry reserve intact,
        # which is the ceiling the ledger itself enforces. Stop before it rather
        # than letting the reservation raise mid-run.
        primary_ceiling = PAPER1_API_HARD_CAP_USD - PAPER1_RETRY_RESERVE_USD
        if ledger.accounted_cost_usd + maximum > primary_ceiling:
            stopped = {"reason": "cumulative_cap_reached", "request_id": payload["request_id"],
                       "remaining_usd": str(ledger.remaining_usd), "next_reservation_usd": str(maximum),
                       "primary_ceiling_usd": str(primary_ceiling)}
            break
        logical_call_id = f"{STAGE}:{payload['request_id']}"
        unsettled = ledger.unsettled_reservations(logical_call_id)
        if unsettled:
            # An earlier process died between reserving and settling. The money is
            # already held at the maximum, but whether the provider served the
            # request is genuinely unknown, so it is reconciled, never re-sent.
            stopped = {"reason": "unsettled_reservation_requires_reconciliation",
                       "request_id": payload["request_id"],
                       "reservation_ids": [r["reservation_id"] for r in unsettled]}
            break
        # Resume continues the attempt count instead of restarting at one, which
        # would collide with a reservation the interrupted run already wrote.
        attempt = ledger.attempts_for(logical_call_id) + 1
        allowed_attempts = 1 + int(scorer_config["project_retry_max"])
        outcome = None
        while attempt <= allowed_attempts:
            if followup is not None and followup.would_exceed(maximum, liabilities=liabilities):
                stopped = {"reason": "followup_budget_cap_reached", "request_id": payload["request_id"],
                           "attempt": attempt,
                           **followup.status(liabilities).as_dict()}
                break
            # A retry is subject to the same caps as a first attempt. Checking
            # here keeps the stop clean instead of letting reserve() raise with a
            # request half-way through.
            if ledger.accounted_stage_cost_usd(STAGE) + maximum > stage_cap:
                stopped = {"reason": "stage_cap_reached_before_retry",
                           "request_id": payload["request_id"], "attempt": attempt,
                           "stage_cap_usd": str(stage_cap)}
                break
            if ledger.accounted_cost_usd + maximum > PAPER1_API_HARD_CAP_USD - PAPER1_RETRY_RESERVE_USD:
                stopped = {"reason": "cumulative_cap_reached_before_retry",
                           "request_id": payload["request_id"], "attempt": attempt}
                break
            reservation = ledger.reserve(
                reservation_id=f"{STAGE}:{payload['request_id']}:{attempt}",
                logical_call_id=logical_call_id,
                call_hash=payload["call_hash"], stage=STAGE, provider=PROVIDER,
                model=scorer_config["model"], maximum_cost_usd=maximum,
                call_class="PRIMARY" if attempt == 1 else "PRIMARY_RETRY",
                stage_hard_cap_usd=stage_cap)
            started = utc_now()
            start = time.monotonic()
            try:
                status, parsed_body, raw_text = send(payload["body"])
            except Exception as exc:
                ledger.settle(reservation, actual_cost_usd=None, outcome="UNKNOWN")
                outcome = {"status": "TRANSPORT_FAILED", "error": f"{type(exc).__name__}: {exc}",
                           "attempt": attempt, "cost_accounted_at_reserved_maximum": str(maximum)}
                attempt += 1
                continue
            if status != 200 or parsed_body is None or "usage" not in parsed_body:
                ledger.settle(reservation, actual_cost_usd=None, outcome="FAILED")
                outcome = {"status": "PROVIDER_ERROR", "http_status": status,
                           "response_excerpt": raw_text[:2000], "attempt": attempt,
                           "cost_accounted_at_reserved_maximum": str(maximum)}
                attempt += 1
                continue
            # The answer is paid for the moment it arrives, so persist the raw
            # provider response before settling. A crash after this point loses
            # bookkeeping, not the thing that was bought.
            usage = parsed_body["usage"]
            actual = observed_usd(usage)
            reply = parsed_body["choices"][0]["message"].get("content") or ""
            atomic_json(scores_dir / "raw" / (payload["request_id"] + f".attempt{attempt}.json"),
                        {"request_id": payload["request_id"], "call_hash": payload["call_hash"],
                         "attempt": attempt, "received_at": utc_now(), "http_status": status,
                         "response": parsed_body, "settled": False})
            overran = actual > maximum
            ledger.settle(reservation, actual_cost_usd=actual, outcome="SUCCEEDED",
                          allow_overrun=overran)
            outcome = {"status": "SCORED", "http_status": status, "attempt": attempt,
                       "official_finish_reason": parsed_body["choices"][0].get("finish_reason"),
                       "raw_reply": reply, "usage": usage, "actual_cost_usd": str(actual),
                       "reserved_maximum_usd": str(maximum), "seconds": time.monotonic() - start,
                       "started_at": started}
            if overran:
                # Never shrink a real bill to fit an estimate: record the true
                # cost, flag the estimator, and stop so it can be re-checked.
                outcome["reservation_overrun_usd"] = str(actual - maximum)
                outcome["estimator_underestimated_cost"] = True
            try:
                outcome["official"] = parse_official_reply(payload["task"], reply)
            except OfficialParseError as exc:
                # Upstream returns no score here. It is disclosed missingness, never a zero.
                outcome.update(status="OFFICIAL_PARSE_FAILED", parse_error=str(exc), official=None)
            break
        if outcome is None:
            # Stopped by a cap before any attempt of this payload was sent.
            break
        record = {"protocol": PROTOCOL, "request_id": payload["request_id"],
                  "target_id": payload["target_id"], "task": payload["task"],
                  "call_hash": payload["call_hash"], "logical_call_id": payload["logical_call_id"],
                  "prediction_sha256": payload["prediction_sha256"],
                  "model": scorer_config["model"], "completed_at": utc_now(), **outcome}
        atomic_json(scores_dir / (payload["request_id"] + ".json"), record)
        records.append(record)
        if on_record is not None:
            on_record(record, ledger)
        if record.get("estimator_underestimated_cost"):
            stopped = {"reason": "observed_cost_exceeded_reservation",
                       "request_id": payload["request_id"],
                       "overrun_usd": record["reservation_overrun_usd"],
                       "note": "true cost recorded; re-check the token estimator before continuing"}
            break
        if stopped is not None:
            # A cap already gave the precise reason this payload could not finish;
            # do not overwrite it with the generic failure label.
            break
        if record["status"] in {"TRANSPORT_FAILED", "PROVIDER_ERROR"}:
            stopped = {"reason": "call_failed_after_allowed_retry", "request_id": payload["request_id"]}
            break
    return stopped, records, skipped


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path,
                        default=PROJECT / "outputs/paper1_calibration/static_sample_20260917_v1")
    parser.add_argument("--bound", type=Path,
                        default=PROJECT / "outputs/paper1_calibration/static_official_scoring_20260917_v1")
    parser.add_argument("--out", type=Path,
                        default=PROJECT / "outputs/paper1_calibration/static_official_scores_20260917_v1")
    parser.add_argument("--execute", action="store_true",
                        help="make paid official calls; requires an explicit researcher authorization record")
    parser.add_argument("--limit", type=int, help="attempt at most this many pending calls, then stop")
    parser.add_argument("--timeout", type=float, default=600.0)
    args = parser.parse_args()

    assert_pre_outcome_locked(load_public_only_config(CONFIG))
    authority = read_json(AUTHORITY)
    scorer_config = read_json(args.package / "scorer_config.json")
    summary = read_json(args.package / "preparation_summary.json")
    if sha256_file(args.package / "scorer_config.json") != summary["package_artifacts"]["scorer_config.json"]:
        raise RuntimeError("scorer config changed since preparation")
    manifest, payloads, aliases = load_payloads(args.bound)
    ledger = CumulativePaper1ApiBudgetLedger(LEDGER)
    followup = FollowupBudget(ledger, FOLLOWUP_SNAPSHOT)

    args.out.mkdir(parents=True, exist_ok=True)
    costs = cost_manifest(manifest, payloads, scorer_config, ledger)
    scores_dir = args.out / "scores"

    pending = []
    settled_calls = 0
    for payload in payloads:
        saved_path = scores_dir / (payload["request_id"] + ".json")
        if not saved_path.exists():
            pending.append(payload)
            continue
        saved = read_json(saved_path)
        if saved["call_hash"] != payload["call_hash"]:
            raise RuntimeError(f"cached official score is bound to a different call: {payload['request_id']}")
        settled_calls += 1

    stage = authority.get("paid_scoring_stage", {})
    authorized = bool(scorer_config.get("new_paid_execution_authorized")
                      and authority.get("new_paid_API_calls_authorized")
                      and stage.get("proposed_cap_authorized"))
    report = {
        "protocol": PROTOCOL, "generated_at": utc_now(),
        "status": "EXECUTED" if args.execute else "PREFLIGHT_NO_PAID_CALLS",
        "paid_execution_authorized": authorized,
        "authorization_sources": {
            "scorer_config.new_paid_execution_authorized": scorer_config.get("new_paid_execution_authorized"),
            "authority.new_paid_API_calls_authorized": authority.get("new_paid_API_calls_authorized"),
            "authority.paid_scoring_stage.proposed_cap_authorized": stage.get("proposed_cap_authorized"),
            "proposed_stage_hard_cap_including_retries_usd": stage.get(
                "proposed_stage_hard_cap_including_retries_usd"),
        },
        "already_settled_calls": settled_calls, "pending_calls": len(pending),
        "identical_payload_reuse": {
            "distinct_official_calls": len(payloads),
            "requests_served_by_reuse": sum(len(v) for v in aliases.values()),
            "rule": ("byte-identical official prompts are scored once and the score is reused; "
                     "the scorer omits temperature, so this removes within-duplicate variance"),
        },
        "cost_manifest": costs,
        "official_identity": {
            "prompts": "unchanged upstream bytes", "parsers": "unchanged upstream parsers",
            "source_sha256": scorer_config["source_sha256"],
            "temperature": scorer_config["temperature"],
            "max_completion_tokens": scorer_config["max_completion_tokens"],
            "local_judge_substitution": "forbidden",
        },
        "followup_budget": followup.status().as_dict(),
        "k_star_frozen": False, "formal_outcomes": 0, "PM_training_runs": 0,
    }

    if not args.execute:
        atomic_json(args.out / "preflight.json", report)
        print(json.dumps({k: report[k] for k in
                          ["status", "paid_execution_authorized", "already_settled_calls", "pending_calls"]}
                         | {"sum_of_worst_case_reservations_usd": costs["sum_of_full_worst_case_reservations_usd"],
                            "observed_total_input_tokens": costs["observed_total_input_tokens"],
                            "cumulative_remaining_usd": costs["cumulative_remaining_usd"]},
                         ensure_ascii=False, indent=2))
        return

    if not authorized:
        raise RuntimeError(
            "paid official scoring is not authorized: the researcher has not approved this stage's cap. "
            f"Preflight cost manifest is at {args.out / 'preflight.json'}")
    if "authorized_stage_hard_cap_usd" not in stage:
        raise RuntimeError("the authorization record must name the approved stage hard cap in USD")
    stage_cap = Decimal(str(stage["authorized_stage_hard_cap_usd"]))
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY is absent; no paid call is attempted")
    if args.limit is not None:
        pending = pending[:args.limit]

    def progress(record, led):
        print(json.dumps({"request_id": record["request_id"], "task": record["task"],
                          "status": record["status"],
                          "quality": (record.get("official") or {}).get("quality"),
                          "stage_usd": str(led.accounted_stage_cost_usd(STAGE))}), flush=True)

    with httpx.Client(headers={"Authorization": f"Bearer {key}"}, follow_redirects=False) as client:
        def send(body):
            return call_official_judge(client, body, args.timeout)

        stopped, _, skipped = execute_payloads(pending, scorer_config=scorer_config, ledger=ledger,
                                               stage_cap=stage_cap, scores_dir=scores_dir, send=send,
                                               on_record=progress, followup=followup)

    if scores_dir.exists():
        by_hash = {}
        for path in sorted(scores_dir.glob("*.json")):
            record = read_json(path)
            by_hash[record["call_hash"]] = record
        for digest, alias_ids in aliases.items():
            source = by_hash.get(digest)
            if source is None:
                continue
            for alias in alias_ids:
                atomic_json(scores_dir / (alias + ".json"),
                            {**source, "request_id": alias, "scored_via_identical_payload_of":
                             source["request_id"], "paid_call": False})
    saved = [read_json(p) for p in sorted(scores_dir.glob("*.json"))] if scores_dir.exists() else []
    raw_dir = scores_dir / "raw"
    raw_ids = {p.name.split(".attempt")[0] for p in raw_dir.glob("*.json")} if raw_dir.exists() else set()
    paid_without_answer = sorted(raw_ids - {r["request_id"] for r in saved})
    report.update(status="EXECUTED", stopped=stopped, settled_calls=len(saved),
                  statuses=dict(Counter(r["status"] for r in saved)),
                  skipped_already_paid=skipped,
                  paid_but_answer_missing=paid_without_answer,
                  raw_provider_responses_retained=len(raw_ids),
                  followup_budget=followup.status().as_dict(),
                  stage_accounted_usd=str(ledger.accounted_stage_cost_usd(STAGE)),
                  cumulative_accounted_usd=str(ledger.accounted_cost_usd),
                  cumulative_remaining_usd=str(ledger.remaining_usd))
    atomic_json(args.out / "execution_report.json", report)
    print(json.dumps({k: report[k] for k in
                      ["status", "settled_calls", "statuses", "stopped", "skipped_already_paid",
                       "paid_but_answer_missing", "followup_budget", "stage_accounted_usd"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
