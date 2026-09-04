#!/usr/bin/env python3
"""Run one zero-outcome ES-MemEval DG execution-compatibility trajectory.

The paid seeker is the official GPT-4o role with the pinned upstream prompt,
ten sequential rounds, a 60-token ceiling, and upstream's at-most-three
generation attempts when finish_reason is not ``stop``.  The supporter is the
frozen local Llama reference backend in the No-Memory arm.  No evaluator is
called and no response is inspected or scored for quality.

Tracked output contains only identities, hashes, finish reasons, usage,
latency, retry counts and cost.  Dialogue text is written only under ignored
``outputs/`` so that the sequential run is auditable without publishing the
simulator's hidden scenario or generated responses.
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
from typing import Any, Callable

import httpx

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.api import Endpoint, OpenAICompatibleClient  # noqa: E402
from metacom_pm.io import (  # noqa: E402
    canonical_json,
    read_json,
    sha256_file,
    sha256_text,
    utc_now,
    write_json,
)
from metacom_pm.paper1.api_budget import (  # noqa: E402
    CumulativePaper1ApiBudgetLedger,
)
from metacom_pm.paper1.execution.dg_official import (  # noqa: E402
    DG_OFFICIAL_MAX_GENERATION_ATTEMPTS,
    DG_OFFICIAL_MAX_OUTPUT_TOKENS,
    DG_OFFICIAL_ROUNDS,
    DG_REPRODUCIBLE_SEEKER_SNAPSHOT,
    build_official_dg_seeker_system_prompt,
    build_official_dg_supporter_system_prompt,
    official_dg_seeker_messages,
    official_dg_supporter_messages,
    trim_to_last_complete_sentence,
)
from metacom_pm.paper1.execution.rq2_prompts import (  # noqa: E402
    LOCAL_GENERATOR_ARTIFACT_IDENTITY_SHA256,
    LOCAL_GENERATOR_CHAT_TEMPLATE_SHA256,
    LOCAL_GENERATOR_MODEL_REVISION,
    LOCAL_GENERATOR_SERVER_PROTOCOL,
)
from metacom_pm.paper1.outcome_lock import (  # noqa: E402
    assert_pre_outcome_locked,
    load_public_only_config,
)


PROTOCOL = "paper1-official-dg-execution-compatibility-pilot-v1"
ES_MEMEVAL_COMMIT = "692624208acc077b8867698c1d6fcd998dee641a"
OWNER_ID = "p7"
TOPIC_INDEX = 1
ARM = "No_Memory"
LOCAL_MODEL = "meta/llama-3.1-8b-instruct"
STAGE = "token_call_latency_pilots"
STAGE_HARD_CAP_USD = Decimal("1.00")
BUNDLE_MAXIMUM_COST_USD = Decimal("0.305025")
INPUT_USD_PER_MTOK = Decimal("2.50")
OUTPUT_USD_PER_MTOK = Decimal("10.00")
OPENAI_BASE_URL = "https://api.openai.com/v1"


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--local-base-url", default="http://127.0.0.1:8011")
    parser.add_argument(
        "--raw-data",
        type=Path,
        default=PROJECT / "data/external/evo_emo.json",
    )
    parser.add_argument(
        "--cost-surface",
        type=Path,
        default=PROJECT
        / "data/paper1_authority/paper1_official_dg_simulator_call_cost_surface_20260904_v1.json",
    )
    parser.add_argument(
        "--upstream-source",
        type=Path,
        default=PROJECT / "outputs/vendor_es_memeval/src/lib/dg/dg_experiment.py",
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
        / "outputs/paper1_dg_compatibility_pilot_v1/private_trajectory.json",
    )
    parser.add_argument("--authority-out", type=Path)
    args = parser.parse_args()
    if args.authority_out is None:
        filename = (
            "paper1_official_dg_compatibility_pilot_live_result_20260904_v1.json"
            if args.live
            else "paper1_official_dg_compatibility_pilot_preflight_20260904_v1.json"
        )
        args.authority_out = PROJECT / "data/paper1_authority" / filename
    return args


def _scenario(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    users = read_json(path)
    user = next(row for row in users if str(row["id"]) == OWNER_ID)
    topic = next(
        row for row in user["subsequent_topics"] if int(row["idx"]) == TOPIC_INDEX
    )
    return user, topic


def _manifest(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    config = load_public_only_config(PROJECT / "configs/paper1_public_only.yaml")
    assert_pre_outcome_locked(config)
    user, topic = _scenario(args.raw_data)
    seeker_prompt = build_official_dg_seeker_system_prompt(user=user, topic=topic)
    supporter_prompt = build_official_dg_supporter_system_prompt(
        seeker_name=str(user["basic_info"]["name"])
    )
    opening = f'Hi {user["basic_info"]["name"]}! How are you these days?'

    cost_surface = read_json(args.cost_surface)
    scenario_row = next(
        row
        for row in cost_surface["public_population"]["scenario_rows"]
        if row["owner_id"] == OWNER_ID and int(row["topic_index"]) == TOPIC_INDEX
    )
    if scenario_row["system_prompt_sha256"] != sha256_text(seeker_prompt):
        raise RuntimeError("live DG seeker prompt differs from the frozen cost surface")
    calculated_maximum = (
        Decimal(str(scenario_row["ten_turn_seeker_input_reserve_tokens"]))
        * DG_OFFICIAL_MAX_GENERATION_ATTEMPTS
        * INPUT_USD_PER_MTOK
        + Decimal(DG_OFFICIAL_ROUNDS)
        * DG_OFFICIAL_MAX_GENERATION_ATTEMPTS
        * DG_OFFICIAL_MAX_OUTPUT_TOKENS
        * OUTPUT_USD_PER_MTOK
    ) / Decimal("1000000")
    if calculated_maximum != BUNDLE_MAXIMUM_COST_USD:
        raise RuntimeError("DG bundle reserve no longer matches the frozen token surface")

    identity = {
        "protocol": PROTOCOL,
        "upstream_repo": "slptongji/ES-MemEval",
        "upstream_commit": ES_MEMEVAL_COMMIT,
        "upstream_dg_source_sha256": sha256_file(args.upstream_source),
        "raw_data_sha256": sha256_file(args.raw_data),
        "owner_id": OWNER_ID,
        "topic_index": TOPIC_INDEX,
        "arm": ARM,
        "seeker_provider": "OpenAI",
        "seeker_model": DG_REPRODUCIBLE_SEEKER_SNAPSHOT,
        "seeker_temperature": "provider_default_omitted",
        "seeker_max_output_parameter": "max_completion_tokens",
        "seeker_max_output_tokens": DG_OFFICIAL_MAX_OUTPUT_TOKENS,
        "seeker_system_prompt_sha256": sha256_text(seeker_prompt),
        "supporter_model": LOCAL_MODEL,
        "supporter_model_revision": LOCAL_GENERATOR_MODEL_REVISION,
        "supporter_model_artifact_identity_sha256": (
            LOCAL_GENERATOR_ARTIFACT_IDENTITY_SHA256
        ),
        "supporter_chat_template_sha256": LOCAL_GENERATOR_CHAT_TEMPLATE_SHA256,
        "supporter_server_protocol": LOCAL_GENERATOR_SERVER_PROTOCOL,
        "supporter_temperature": 0,
        "supporter_system_prompt_sha256": sha256_text(supporter_prompt),
        "opening_message_sha256": sha256_text(opening),
        "rounds": DG_OFFICIAL_ROUNDS,
        "max_generation_attempts_after_non_stop": (
            DG_OFFICIAL_MAX_GENERATION_ATTEMPTS
        ),
        "third_non_stop_handling": "upstream_exact_last_complete_sentence_prefix",
        "formal_outcome_calls": 0,
        "evaluator_calls": 0,
        "pm_training_runs": 0,
    }
    manifest = {
        "identity": identity,
        "execution_identity_sha256": sha256_text(canonical_json(identity)),
        "purpose": (
            "zero-outcome execution compatibility and retry-frequency pilot; "
            "not a model-quality or benchmark evaluation"
        ),
        "response_quality_inspected_or_scored": False,
        "supporter_hidden_scenario_fields_visible": False,
        "supporter_memory_resources_visible": False,
        "tracked_response_text_retained": False,
        "private_sequential_text_retained_under_ignored_outputs": True,
        "pricing_snapshot": cost_surface["pricing_snapshot"],
        "budget": {
            "stage": STAGE,
            "stage_hard_cap_usd": str(STAGE_HARD_CAP_USD),
            "researcher_authorized_pilot_hard_cap_usd": "0.40",
            "bundle_maximum_reservation_usd": str(BUNDLE_MAXIMUM_COST_USD),
            "prompt_cache_discount_counted": False,
        },
        "locks": {
            name: config[name]["status"]
            for name in (
                "RQ1_RS_CALIBRATION_OUTCOME_LOCK",
                "RQ2_MEMORY_CALIBRATION_OUTCOME_LOCK",
                "RQ1_CONFIRMATORY_OUTCOME_LOCK",
                "RQ2_CONFIRMATORY_OUTCOME_LOCK",
            )
        },
    }
    runtime = {
        "user": user,
        "topic": topic,
        "seeker_prompt": seeker_prompt,
        "supporter_prompt": supporter_prompt,
        "opening": opening,
    }
    return manifest, runtime


def _local_health(base_url: str) -> dict[str, Any]:
    response = httpx.get(f"{base_url.rstrip('/')}/health", timeout=15.0)
    response.raise_for_status()
    health = response.json()
    expected = {
        "protocol": LOCAL_GENERATOR_SERVER_PROTOCOL,
        "model": LOCAL_MODEL,
        "revision": LOCAL_GENERATOR_MODEL_REVISION,
        "model_artifact_identity_sha256": LOCAL_GENERATOR_ARTIFACT_IDENTITY_SHA256,
        "chat_template_sha256": LOCAL_GENERATOR_CHAT_TEMPLATE_SHA256,
    }
    if any(health.get(key) != value for key, value in expected.items()):
        raise RuntimeError("local DG supporter health identity mismatch")
    return {key: health[key] for key in expected} | {
        "gpu": health.get("gpu"),
        "dtype": health.get("dtype"),
    }


def _local_call(
    client: httpx.Client,
    base_url: str,
    messages: tuple[dict[str, str], ...],
) -> dict[str, Any]:
    payload = {
        "model": LOCAL_MODEL,
        "messages": list(messages),
        "temperature": 0,
        "max_tokens": DG_OFFICIAL_MAX_OUTPUT_TOKENS,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    started = time.monotonic_ns()
    parts: list[str] = []
    usage: dict[str, int] = {}
    finish_reason = "unknown"
    returned_models: set[str] = set()
    with client.stream(
        "POST", f"{base_url.rstrip('/')}/v1/chat/completions", json=payload
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith("data:"):
                continue
            raw = line[5:].strip()
            if not raw or raw == "[DONE]":
                continue
            chunk = json.loads(raw)
            if chunk.get("error"):
                raise RuntimeError(f"local generation failed: {chunk['error']}")
            if chunk.get("model"):
                returned_models.add(str(chunk["model"]))
            if isinstance(chunk.get("usage"), dict):
                usage = {
                    str(key): int(value)
                    for key, value in chunk["usage"].items()
                    if isinstance(value, int)
                }
            choices = chunk.get("choices") or []
            if not choices:
                continue
            choice = choices[0]
            if choice.get("finish_reason") is not None:
                finish_reason = str(choice["finish_reason"])
            content = (choice.get("delta") or {}).get("content")
            if isinstance(content, str) and content:
                parts.append(content)
    text = "".join(parts)
    if not text:
        raise RuntimeError("local supporter returned no visible text")
    return {
        "text": text,
        "request_sha256": sha256_text(canonical_json(payload)),
        "response_sha256": sha256_text(text),
        "finish_reason": finish_reason,
        "usage": usage,
        "latency_ms": (time.monotonic_ns() - started) / 1_000_000,
        "returned_models": sorted(returned_models),
    }


def _paid_seeker_call(
    client: OpenAICompatibleClient,
    messages: tuple[dict[str, str], ...],
) -> dict[str, Any]:
    call, _ = client.chat(
        list(messages),
        temperature=0,
        max_tokens=DG_OFFICIAL_MAX_OUTPUT_TOKENS,
        retries=1,
    )
    raw_model = call.raw_response.get("model")
    return {
        "text": call.text,
        "request_sha256": call.request_hash,
        "response_sha256": sha256_text(call.text),
        "finish_reason": call.provider_finish_reason or "unknown",
        "normalized_finish_reason": call.normalized_finish_reason,
        "usage": call.usage,
        "latency_ms": call.latency_ms,
        "returned_models": [str(raw_model)] if raw_model else [],
    }


def _generate_with_official_non_stop_handling(
    *,
    role: str,
    turn: int,
    call: Callable[[], dict[str, Any]],
    audit_rows: list[dict[str, Any]],
) -> str:
    last: dict[str, Any] | None = None
    for attempt in range(1, DG_OFFICIAL_MAX_GENERATION_ATTEMPTS + 1):
        last = call()
        audit_rows.append(
            {
                "turn": turn,
                "role": role,
                "attempt": attempt,
                "request_sha256": last["request_sha256"],
                "response_sha256": last["response_sha256"],
                "finish_reason": last["finish_reason"],
                "normalized_finish_reason": last.get("normalized_finish_reason"),
                "usage": last["usage"],
                "latency_ms": last["latency_ms"],
                "returned_models": last["returned_models"],
                "response_text_retained_in_tracked_output": False,
            }
        )
        if str(last["finish_reason"]).casefold() == "stop":
            return str(last["text"])
    assert last is not None
    trimmed = trim_to_last_complete_sentence(str(last["text"]))
    audit_rows[-1]["third_non_stop_prefix_trim_applied"] = True
    audit_rows[-1]["trimmed_response_sha256"] = sha256_text(trimmed)
    if not trimmed:
        raise RuntimeError(f"{role} turn {turn} produced empty third-attempt prefix")
    return trimmed


def _actual_paid_cost(rows: list[dict[str, Any]]) -> Decimal:
    paid = [row for row in rows if row["role"] == "seeker"]
    input_tokens = sum(int(row["usage"].get("prompt_tokens", 0)) for row in paid)
    output_tokens = sum(
        int(row["usage"].get("completion_tokens", 0)) for row in paid
    )
    return (
        Decimal(input_tokens) * INPUT_USD_PER_MTOK
        + Decimal(output_tokens) * OUTPUT_USD_PER_MTOK
    ) / Decimal("1000000")


def main() -> int:
    args = _args()
    manifest, runtime = _manifest(args)
    base = manifest | {"created_at": utc_now()}
    if not args.live:
        output = base | {"mode": "DRY_RUN", "status": "DRY_RUN_READY"}
        write_json(args.authority_out, output)
        print(canonical_json(output))
        return 0

    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is not set")
    health = _local_health(args.local_base_url)
    call_hash = str(manifest["execution_identity_sha256"])
    ledger = CumulativePaper1ApiBudgetLedger(args.ledger)
    reservation = ledger.reserve(
        reservation_id=f"{call_hash}:bundle:1",
        logical_call_id=call_hash,
        call_hash=call_hash,
        stage=STAGE,
        provider="OpenAI",
        model=DG_REPRODUCIBLE_SEEKER_SNAPSHOT,
        maximum_cost_usd=BUNDLE_MAXIMUM_COST_USD,
        call_class="PRIMARY",
        stage_hard_cap_usd=STAGE_HARD_CAP_USD,
    )

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
    seeker_client = OpenAICompatibleClient(endpoint)
    local_client = httpx.Client(timeout=httpx.Timeout(180.0), http2=False)
    turns: list[tuple[str, str]] = []
    audit_rows: list[dict[str, Any]] = []
    private: dict[str, Any] = {
        "protocol": PROTOCOL,
        "execution_identity_sha256": call_hash,
        "opening_supporter_message": runtime["opening"],
        "turns": [],
        "contains_private_generated_text": True,
        "quality_inspected_or_scored": False,
    }
    status = "FAILED"
    error: dict[str, Any] | None = None
    unknown_cost = False
    try:
        for turn in range(1, DG_OFFICIAL_ROUNDS + 1):
            seeker_messages = official_dg_seeker_messages(
                system_prompt=runtime["seeker_prompt"],
                first_supporter_message=runtime["opening"],
                prior_turns=turns,
            )
            seeker_message = _generate_with_official_non_stop_handling(
                role="seeker",
                turn=turn,
                call=lambda messages=seeker_messages: _paid_seeker_call(
                    seeker_client, messages
                ),
                audit_rows=audit_rows,
            )
            supporter_messages = official_dg_supporter_messages(
                system_prompt=runtime["supporter_prompt"],
                first_supporter_message=runtime["opening"],
                prior_turns=turns,
                current_seeker_message=seeker_message,
            )
            supporter_message = _generate_with_official_non_stop_handling(
                role="supporter",
                turn=turn,
                call=lambda messages=supporter_messages: _local_call(
                    local_client, args.local_base_url, messages
                ),
                audit_rows=audit_rows,
            )
            turns.append((seeker_message, supporter_message))
            private["turns"].append(
                {
                    "turn": turn,
                    "seeker": seeker_message,
                    "supporter": supporter_message,
                }
            )
            write_json(args.private_out, private | {"status": "IN_PROGRESS"})
        status = "PASS"
    except Exception as exc:
        # A failed HTTP/transport call can be billable without complete usage.
        # Conservatively charge the full bundle reservation in that case.
        unknown_cost = True
        error = {
            "type": type(exc).__name__,
            "message_sha256": sha256_text(str(exc)),
        }
    finally:
        seeker_client.close()
        local_client.close()

    actual = None if unknown_cost else _actual_paid_cost(audit_rows)
    settled = ledger.settle(
        reservation,
        actual_cost_usd=actual,
        outcome="SUCCEEDED" if status == "PASS" else "FAILED",
    )
    write_json(args.private_out, private | {"status": status, "error": error})

    role_counts = Counter(row["role"] for row in audit_rows)
    finish_counts = Counter(
        f'{row["role"]}:{row["finish_reason"]}' for row in audit_rows
    )
    paid_rows = [row for row in audit_rows if row["role"] == "seeker"]
    output = base | {
        "mode": "LIVE",
        "status": status,
        "completed_at": utc_now(),
        "local_health": health,
        "trajectory": {
            "completed_rounds": len(turns),
            "physical_calls_by_role": dict(sorted(role_counts.items())),
            "finish_reason_counts": dict(sorted(finish_counts.items())),
            "seeker_non_stop_extra_attempts": max(0, len(paid_rows) - len(turns)),
            "seeker_input_tokens": sum(
                int(row["usage"].get("prompt_tokens", 0)) for row in paid_rows
            ),
            "seeker_output_tokens": sum(
                int(row["usage"].get("completion_tokens", 0)) for row in paid_rows
            ),
            "turn_response_pair_sha256": [
                sha256_text(canonical_json({"seeker": seeker, "supporter": supporter}))
                for seeker, supporter in turns
            ],
            "attempts": audit_rows,
            "contains_response_text": False,
        },
        "budget": manifest["budget"]
        | {
            "settled_pilot_cost_usd": str(settled),
            "settlement_is_reserved_maximum": unknown_cost,
            "accounted_stage_cost_usd": str(ledger.accounted_stage_cost_usd(STAGE)),
            "accounted_paper1_total_usd": str(ledger.accounted_cost_usd),
            "paper1_remaining_usd": str(ledger.remaining_usd),
        },
        "error": error,
    }
    write_json(args.authority_out, output)
    print(canonical_json(output))
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
