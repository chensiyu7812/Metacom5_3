#!/usr/bin/env python3
"""Run the eight authorized first-turn DG seeker calls for teacher reference.

The nine-scenario sample and request-message hashes were frozen outcome-blind.
One scenario reuses the identity-matched first turn from the completed A6000
compatibility trajectory.  Each other request gets exactly one physical
GPT-4o call.  No evaluator is called and no response is selected by quality.
Generated text is retained only under ignored ``outputs/``; the tracked result
contains hashes, finish reasons, usage, cost, and identity metadata.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.api import (  # noqa: E402
    Endpoint,
    OpenAICompatibleClient,
    chat_request_payload,
)
from metacom_pm.io import (  # noqa: E402
    canonical_json,
    iter_jsonl,
    read_json,
    sha256_file,
    sha256_text,
    utc_now,
    write_json,
)
from metacom_pm.paper1.api_budget import CumulativePaper1ApiBudgetLedger  # noqa: E402
from metacom_pm.paper1.execution.dg_official import (  # noqa: E402
    DG_OFFICIAL_MAX_OUTPUT_TOKENS,
    DG_REPRODUCIBLE_SEEKER_SNAPSHOT,
    build_official_dg_seeker_system_prompt,
    official_dg_seeker_messages,
    trim_to_last_complete_sentence,
)
from metacom_pm.paper1.outcome_lock import (  # noqa: E402
    assert_pre_outcome_locked,
    load_public_only_config,
)


PROTOCOL = "paper1-pairwise-teacher-dg-first-turn-live-result-v1"
AUTHORIZATION_PROTOCOL = "paper1-pairwise-teacher-dg-first-turn-authorization-v1"
STAGE = "pairwise_teacher_reference_dg_first_turns"
STAGE_HARD_CAP_USD = Decimal("0.11")
INPUT_USD_PER_MTOK = Decimal("2.50")
OUTPUT_USD_PER_MTOK = Decimal("10.00")
INPUT_RESERVATION_SAFETY_TOKENS = 200
OPENAI_BASE_URL = "https://api.openai.com/v1"
REUSED_TARGET = "p7::dg::1"


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--authorization",
        type=Path,
        default=PROJECT
        / "data/paper1_authority/paper1_pairwise_teacher_dg_first_turn_authorization_20260904_v1.json",
    )
    parser.add_argument(
        "--preflight",
        type=Path,
        default=PROJECT
        / "data/paper1_authority/paper1_pairwise_teacher_preflight_20260904_v1.json",
    )
    parser.add_argument(
        "--base-pairs",
        type=Path,
        default=PROJECT
        / "data/paper1_authority/paper1_pairwise_teacher_base_pair_preflight_20260904_v1.jsonl",
    )
    parser.add_argument(
        "--raw-data", type=Path, default=PROJECT / "data/external/evo_emo.json"
    )
    parser.add_argument(
        "--existing-private",
        type=Path,
        default=PROJECT
        / "outputs/paper1_dg_compatibility_pilot_v2/private_trajectory.json",
    )
    parser.add_argument(
        "--existing-authority",
        type=Path,
        default=PROJECT
        / "data/paper1_authority/paper1_official_dg_compatibility_pilot_live_result_20260904_v2.json",
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=PROJECT / "outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl",
    )
    parser.add_argument(
        "--private-out",
        type=Path,
        default=PROJECT
        / "outputs/paper1_pairwise_teacher/private_dg_first_turns_20260904_v1.json",
    )
    parser.add_argument(
        "--authority-out",
        type=Path,
        default=PROJECT
        / "data/paper1_authority/paper1_pairwise_teacher_dg_first_turn_result_20260904_v1.json",
    )
    return parser.parse_args()


def _scenario_messages(
    *, users: dict[str, dict[str, Any]], target_id: str
) -> tuple[dict[str, str], ...]:
    owner_id, task, topic_raw = target_id.split("::")
    if task != "dg":
        raise RuntimeError(f"not a DG target: {target_id}")
    user = users[owner_id]
    topic_index = int(topic_raw)
    topic = next(
        row
        for row in user["subsequent_topics"]
        if int(row["idx"]) == topic_index
    )
    system = build_official_dg_seeker_system_prompt(user=user, topic=topic)
    opening = f"Hi {user['basic_info']['name']}! How are you these days?"
    return official_dg_seeker_messages(
        system_prompt=system, first_supporter_message=opening, prior_turns=()
    )


def _load_frozen_requests(args: argparse.Namespace) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    config = load_public_only_config(PROJECT / "configs/paper1_public_only.yaml")
    assert_pre_outcome_locked(config)
    authorization = read_json(args.authorization)
    preflight = read_json(args.preflight)
    if authorization.get("protocol") != AUTHORIZATION_PROTOCOL:
        raise RuntimeError("DG first-turn authorization protocol mismatch")
    grant = authorization["researcher_authorization"]
    if (
        authorization.get("status") != "ACTIVE_RESEARCHER_AUTHORIZED_EXACT_EIGHT_CALLS"
        or Decimal(str(grant["authorized_usd"])) != STAGE_HARD_CAP_USD
        or int(grant["authorized_new_physical_calls"]) != 8
        or int(grant["retries_in_this_authorization"]) != 0
        or int(grant["gemini_calls_authorized"]) != 0
    ):
        raise RuntimeError("DG first-turn authorization is not the exact USD 0.11 grant")
    frozen = authorization["frozen_input"]
    if sha256_file(args.preflight) != frozen["preflight_sha256"]:
        raise RuntimeError("authorized teacher preflight hash mismatch")
    if sha256_file(args.base_pairs) != frozen["base_pair_manifest_sha256"]:
        raise RuntimeError("authorized teacher base-pair hash mismatch")
    if (
        preflight["paid_api_calls"] != 0
        or preflight["formal_outcome_calls"] != 0
        or preflight["pm_training_runs"] != 0
        or preflight["dg_first_turn_seeker_calls_pending"] != 8
    ):
        raise RuntimeError("teacher preflight is not the frozen zero-outcome state")

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in iter_jsonl(args.base_pairs):
        if row["task"] == "DG":
            groups[str(row["target_id"])].append(row)
    if len(groups) != 9 or any(len(rows) != 3 for rows in groups.values()):
        raise RuntimeError("DG sample is not nine three-head scenario clusters")
    users = {
        str(user["id"]): user for user in json.loads(args.raw_data.read_text(encoding="utf-8"))
    }
    budget_by_target = {
        str(row["target_id"]): row
        for row in preflight["dg_first_turn_seeker_budget"]["calls"]
    }
    requests: list[dict[str, Any]] = []
    for target_id, rows in groups.items():
        messages = _scenario_messages(users=users, target_id=target_id)
        message_hash = sha256_text(canonical_json(messages))
        row_hashes = {
            str(row["dg_seeker_request"]["request_messages_sha256"])
            for row in rows
        }
        if row_hashes != {message_hash}:
            raise RuntimeError(f"DG message hash drift for {target_id}")
        reused = all(
            bool(row["dg_seeker_request"]["existing_success_reused"])
            for row in rows
        )
        if reused != (target_id == REUSED_TARGET):
            raise RuntimeError("DG reused-target identity drift")
        budget = budget_by_target.get(target_id)
        if reused:
            if budget is not None:
                raise RuntimeError("reused DG target unexpectedly has a paid-call budget")
        elif (
            budget is None
            or budget["request_messages_sha256"] != message_hash
            or int(budget["maximum_output_tokens"]) != DG_OFFICIAL_MAX_OUTPUT_TOKENS
        ):
            raise RuntimeError(f"DG budget identity drift for {target_id}")
        requests.append(
            {
                "target_id": target_id,
                "messages": messages,
                "request_messages_sha256": message_hash,
                "reused": reused,
                "estimated_input_tokens": (
                    None if budget is None else int(budget["estimated_input_tokens"])
                ),
            }
        )
    pending = [row for row in requests if not row["reused"]]
    if len(pending) != 8 or set(budget_by_target) != {row["target_id"] for row in pending}:
        raise RuntimeError("authorized DG pending-call set is not exactly eight")
    return authorization, requests


def _reused_response(args: argparse.Namespace) -> dict[str, Any]:
    private = read_json(args.existing_private)
    authority = read_json(args.existing_authority)
    if (
        private.get("status") != "PASS"
        or authority.get("status") != "PASS"
        or authority["identity"]["owner_id"] != "p7"
        or int(authority["identity"]["topic_index"]) != 1
    ):
        raise RuntimeError("identity-matched reused DG trajectory is unavailable")
    text = str(private["turns"][0]["seeker"])
    attempt = next(
        row
        for row in authority["trajectory"]["attempts"]
        if row["role"] == "seeker" and int(row["turn"]) == 1 and int(row["attempt"]) == 1
    )
    if sha256_text(text) != attempt["response_sha256"]:
        raise RuntimeError("reused DG private response hash mismatch")
    return {
        "target_id": REUSED_TARGET,
        "text": text,
        "response_sha256": sha256_text(text),
        "source_authority_sha256": sha256_file(args.existing_authority),
        "finish_reason": attempt["finish_reason"],
        "usage": attempt["usage"],
        "new_paid_call": False,
    }


def _maximum_reservation(estimated_input_tokens: int) -> Decimal:
    return (
        Decimal(estimated_input_tokens + INPUT_RESERVATION_SAFETY_TOKENS)
        * INPUT_USD_PER_MTOK
        + Decimal(DG_OFFICIAL_MAX_OUTPUT_TOKENS) * OUTPUT_USD_PER_MTOK
    ) / Decimal("1000000")


def _actual_cost(usage: dict[str, int]) -> Decimal:
    return (
        Decimal(int(usage.get("prompt_tokens", 0))) * INPUT_USD_PER_MTOK
        + Decimal(int(usage.get("completion_tokens", 0))) * OUTPUT_USD_PER_MTOK
    ) / Decimal("1000000")


def main() -> int:
    args = _args()
    authorization, requests = _load_frozen_requests(args)
    endpoint = Endpoint(
        base_url=OPENAI_BASE_URL,
        model=DG_REPRODUCIBLE_SEEKER_SNAPSHOT,
        api_key_env="OPENAI_API_KEY",
        timeout_seconds=180.0,
        family="GPT-4o",
        transport="openai_chat_completions",
        temperature_mode="omit",
        max_output_tokens_parameter="max_completion_tokens",
    )
    planned: list[dict[str, Any]] = []
    for request in requests:
        if request["reused"]:
            continue
        payload = chat_request_payload(
            endpoint,
            list(request["messages"]),
            temperature=0,
            max_tokens=DG_OFFICIAL_MAX_OUTPUT_TOKENS,
            seed=None,
            response_schema=None,
        )
        maximum = _maximum_reservation(int(request["estimated_input_tokens"]))
        planned.append(
            {
                "target_id": request["target_id"],
                "request_messages_sha256": request["request_messages_sha256"],
                "provider_request_sha256": sha256_text(canonical_json(payload)),
                "estimated_input_tokens": request["estimated_input_tokens"],
                "maximum_reservation_usd": str(maximum),
            }
        )
    total_reservation = sum(
        (Decimal(row["maximum_reservation_usd"]) for row in planned), Decimal("0")
    )
    if total_reservation > STAGE_HARD_CAP_USD:
        raise RuntimeError("eight-call reservation exceeds researcher USD 0.11 authorization")
    dry = {
        "protocol": PROTOCOL,
        "mode": "DRY_RUN",
        "status": "AUTHORIZED_READY" if not args.live else "LIVE_PENDING",
        "authorization_sha256": sha256_file(args.authorization),
        "authorized_usd": str(STAGE_HARD_CAP_USD),
        "aggregate_maximum_reservation_usd": str(total_reservation),
        "new_physical_calls": len(planned),
        "planned_calls": planned,
        "formal_outcome_calls": 0,
        "evaluator_calls": 0,
        "pm_training_runs": 0,
    }
    if not args.live:
        print(canonical_json(dry))
        return 0
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set")

    ledger = CumulativePaper1ApiBudgetLedger(args.ledger)
    client = OpenAICompatibleClient(endpoint)
    private_rows = [_reused_response(args)]
    tracked_rows: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    try:
        for request, plan in zip(
            [row for row in requests if not row["reused"]], planned, strict=True
        ):
            logical_id = f"{PROTOCOL}:{request['target_id']}:{plan['provider_request_sha256']}"
            reservation = ledger.reserve(
                reservation_id=f"{logical_id}:attempt:1",
                logical_call_id=logical_id,
                call_hash=plan["provider_request_sha256"],
                stage=STAGE,
                provider="OpenAI",
                model=DG_REPRODUCIBLE_SEEKER_SNAPSHOT,
                maximum_cost_usd=Decimal(plan["maximum_reservation_usd"]),
                call_class="PRIMARY",
                stage_hard_cap_usd=STAGE_HARD_CAP_USD,
            )
            known_actual_cost: Decimal | None = None
            try:
                call, _ = client.chat(
                    list(request["messages"]),
                    temperature=0,
                    max_tokens=DG_OFFICIAL_MAX_OUTPUT_TOKENS,
                    retries=1,
                )
                usage = {str(key): int(value) for key, value in call.usage.items()}
                known_actual_cost = _actual_cost(usage)
                raw_text = call.text
                finish_reason = str(call.provider_finish_reason or "unknown")
                accepted_text = (
                    raw_text
                    if finish_reason.casefold() == "stop"
                    else trim_to_last_complete_sentence(raw_text)
                )
                returned_model = str(call.raw_response.get("model") or "")
                if not accepted_text:
                    raise RuntimeError("one-attempt DG complete-sentence prefix is empty")
                if returned_model != DG_REPRODUCIBLE_SEEKER_SNAPSHOT:
                    raise RuntimeError("OpenAI returned a model outside the frozen snapshot")
                settled = ledger.settle(
                    reservation,
                    actual_cost_usd=known_actual_cost,
                    outcome="SUCCEEDED",
                )
                private_rows.append(
                    {
                        "target_id": request["target_id"],
                        "raw_text": raw_text,
                        "accepted_text": accepted_text,
                        "new_paid_call": True,
                    }
                )
                tracked_rows.append(
                    {
                        "target_id": request["target_id"],
                        "request_messages_sha256": request["request_messages_sha256"],
                        "provider_request_sha256": call.request_hash,
                        "raw_response_sha256": sha256_text(raw_text),
                        "accepted_response_sha256": sha256_text(accepted_text),
                        "finish_reason": finish_reason,
                        "normalized_finish_reason": call.normalized_finish_reason,
                        "complete_sentence_prefix_applied": accepted_text != raw_text,
                        "usage": usage,
                        "latency_ms": call.latency_ms,
                        "returned_model": returned_model,
                        "settled_cost_usd": str(settled),
                        "response_text_retained_in_tracked_output": False,
                    }
                )
            except Exception as exc:
                failure_cost = (
                    known_actual_cost
                    if known_actual_cost is not None
                    and known_actual_cost <= reservation.maximum_cost_usd
                    else None
                )
                ledger.settle(
                    reservation, actual_cost_usd=failure_cost, outcome="FAILED"
                )
                failures.append(
                    {
                        "target_id": request["target_id"],
                        "error_type": type(exc).__name__,
                        "error_message_sha256": sha256_text(str(exc)),
                    }
                )
            write_json(
                args.private_out,
                {
                    "protocol": PROTOCOL,
                    "status": "IN_PROGRESS",
                    "contains_private_generated_text": True,
                    "response_quality_inspected_or_scored": False,
                    "responses": private_rows,
                    "failures": failures,
                },
            )
    finally:
        client.close()

    status = "PASS" if len(tracked_rows) == 8 and not failures else "PARTIAL"
    write_json(
        args.private_out,
        {
            "protocol": PROTOCOL,
            "status": status,
            "contains_private_generated_text": True,
            "response_quality_inspected_or_scored": False,
            "responses": private_rows,
            "failures": failures,
        },
    )
    finish_counts = Counter(row["finish_reason"] for row in tracked_rows)
    result = {
        "protocol": PROTOCOL,
        "date": "2026-09-04",
        "status": status,
        "completed_at": utc_now(),
        "authorization": {
            "artifact": args.authorization.name,
            "sha256": sha256_file(args.authorization),
            "authorized_usd": str(STAGE_HARD_CAP_USD),
            "aggregate_maximum_reservation_usd": str(total_reservation),
        },
        "frozen_input": {
            "preflight_sha256": sha256_file(args.preflight),
            "base_pair_manifest_sha256": sha256_file(args.base_pairs),
            "raw_data_sha256": sha256_file(args.raw_data),
        },
        "execution": {
            "provider": "OpenAI",
            "model": DG_REPRODUCIBLE_SEEKER_SNAPSHOT,
            "temperature": "provider default omitted",
            "max_completion_tokens": DG_OFFICIAL_MAX_OUTPUT_TOKENS,
            "physical_attempts_per_new_request": 1,
            "existing_identity_matched_response_reused": 1,
            "new_calls_planned": 8,
            "new_calls_succeeded": len(tracked_rows),
            "new_calls_failed": len(failures),
            "finish_reason_counts": dict(sorted(finish_counts.items())),
            "response_quality_inspected_or_scored": False,
            "tracked_response_text_retained": False,
            "private_generated_text_under_ignored_outputs": True,
            "responses": tracked_rows,
            "failures": failures,
        },
        "budget": {
            "estimated_input_tokens_before_calls": authorization["frozen_input"][
                "estimated_input_tokens"
            ],
            "actual_prompt_tokens": sum(
                int(row["usage"].get("prompt_tokens", 0)) for row in tracked_rows
            ),
            "actual_completion_tokens": sum(
                int(row["usage"].get("completion_tokens", 0)) for row in tracked_rows
            ),
            "settled_new_call_cost_usd": str(
                sum(
                    (Decimal(row["settled_cost_usd"]) for row in tracked_rows),
                    Decimal("0"),
                )
            ),
            "accounted_stage_cost_usd": str(ledger.accounted_stage_cost_usd(STAGE)),
            "accounted_paper1_total_usd": str(ledger.accounted_cost_usd),
            "paper1_remaining_usd": str(ledger.remaining_usd),
        },
        "next_local_step": "bind the nine accepted seeker turns, retrieve DG resources dynamically, and generate 142 distinct local ON/OFF responses",
        "formal_outcome_calls": 0,
        "evaluator_calls": 0,
        "pm_training_runs": 0,
        "locks": {
            name: load_public_only_config(PROJECT / "configs/paper1_public_only.yaml")[name][
                "status"
            ]
            for name in (
                "RQ1_RS_CALIBRATION_OUTCOME_LOCK",
                "RQ2_MEMORY_CALIBRATION_OUTCOME_LOCK",
                "RQ1_CONFIRMATORY_OUTCOME_LOCK",
                "RQ2_CONFIRMATORY_OUTCOME_LOCK",
            )
        },
    }
    write_json(args.authority_out, result)
    print(canonical_json(result))
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
