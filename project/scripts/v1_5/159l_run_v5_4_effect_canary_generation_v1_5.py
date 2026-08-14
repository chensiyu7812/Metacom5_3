#!/usr/bin/env python3
"""Run the frozen V5.4 canary generator while persisting raw replies before guard."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from pydantic import Field  # noqa: E402
from metacom_pm.api import RetryableProviderError, make_client  # noqa: E402
from metacom_pm.config import endpoint_from_config, load_config  # noqa: E402
from metacom_pm.contracts import StrictModel  # noqa: E402
from metacom_pm.io import canonical_json, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_typed_resource_adapter import TypedResourceCandidate  # noqa: E402
from metacom_pm.v1_5_v5_3_typed_response_program import (  # noqa: E402
    RewritePolicy,
    build_typed_response_program,
    evidence_aware_generation_messages,
    execute_typed_response,
)

PROTOCOL = "pm-v1.5-v5.4-effect-canary-generation-v1"
PREFLIGHT_DIR = ROOT / "outputs/pm_v1_5_v5_4_effect_canary_preflight_20260810"
PREFLIGHT = PREFLIGHT_DIR / "preflight.json"
CANARY = PREFLIGHT_DIR / "canary_effect_groups_private.jsonl"
OUT = ROOT / "outputs/pm_v1_5_v5_4_effect_canary_generation_20260810"
USD_CAP = 1.0


class GeneratorSchema(StrictModel):
    reply: str = Field(min_length=1)
    used_evidence_ids: list[str]
    realized_response_act: str = Field(min_length=1)


def rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def context(row: dict) -> str:
    return "\n".join(f"{turn['role'].upper()}: {turn['content']}" for turn in row["visible_dialogue"])


def aliases_by_owner() -> dict[str, tuple[str, ...]]:
    raw = json.loads((ROOT / "data/external/evo_emo.json").read_text())
    result = {}
    for user in raw:
        name = str((user.get("basic_info") or {}).get("name") or "").strip()
        result[str(user["id"])] = (name,) if name else ()
    return result


def call_id(row: dict, seed: int, arm: str) -> str:
    return f"{row['effect_group_id']}:{seed}:{arm}"


class RawPersistingClient:
    """Duck-typed execution client that writes parsed provider output first."""

    def __init__(self, client, *, call_key: str, seed: int, raw_rows: dict[str, dict], out_dir: Path = OUT):
        self.client = client
        self.call_key = call_key
        self.seed = seed
        self.raw_rows = raw_rows
        self.out_dir = out_dir

    def chat(self, messages, *, response_schema):
        result = None
        parsed = None
        error = None
        for physical_attempt in (1, 2):
            try:
                result, parsed = self.client.chat(
                    messages, temperature=0.7, max_tokens=512, seed=self.seed,
                    response_schema=response_schema, retries=1,
                )
                error = None
                break
            except Exception as exc:
                error = exc
                retry_class = getattr(exc, "last_retry_class", None)
                retryable = isinstance(exc, RetryableProviderError) and retry_class in {
                    "rate_limited_429", "request_timeout_408", "http_5xx", "network_timeout"
                }
                attempt_key = f"{self.call_key}:attempt{physical_attempt}"
                self.raw_rows[attempt_key] = {
                    "protocol": PROTOCOL, "call_id": self.call_key,
                    "physical_attempt": physical_attempt, "succeeded": False,
                    "retry_class": retry_class, "identical_transport_retry": retryable and physical_attempt == 1,
                    "error": f"{type(exc).__name__}: {exc}",
                    "raw_structured_provider_reply_before_guard": None,
                }
                write_jsonl(self.out_dir / "raw_provider_attempts_before_guard.jsonl", list(self.raw_rows.values()))
                if not retryable or physical_attempt == 2:
                    break
                time.sleep(max(float(getattr(exc, "retry_after_seconds", 0.0) or 0.0), 1.0))
        if result is not None:
            attempt_key = f"{self.call_key}:success"
            self.raw_rows[attempt_key] = {
                "protocol": PROTOCOL, "call_id": self.call_key,
                "physical_attempt": 1 + sum(1 for key in self.raw_rows if key.startswith(self.call_key + ":attempt")),
                "succeeded": True,
                "request_hash": result.request_hash,
                "usage": result.usage,
                "latency_ms": result.latency_ms,
                "finish_reason": result.normalized_finish_reason,
                "raw_structured_provider_reply_before_guard": parsed.model_dump(mode="json") if parsed is not None else None,
            }
            write_jsonl(self.out_dir / "raw_provider_attempts_before_guard.jsonl", list(self.raw_rows.values()))
            return result, parsed
        return error or RuntimeError("provider returned no result"), None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--accept-usd-cap", type=float)
    args = parser.parse_args()
    preflight = json.loads(PREFLIGHT.read_text())
    canary = rows(CANARY)
    if preflight["status"] != "CANARY_PREFLIGHT_FROZEN_RUNNER_AND_SCHEMA_TEST_PENDING":
        raise RuntimeError("canary preflight is not ready")
    if len(canary) != 8:
        raise RuntimeError("canary selection incomplete")
    dry = {
        "protocol": PROTOCOL,
        "status": "GENERATION_LIVE_READY" if preflight["checks"]["usd_upper_within_cap"] else "COST_BLOCKED",
        "effect_groups": 8,
        "generator_logical_calls": 48,
        "raw_provider_reply_persisted_before_guard": True,
        "rewrite_policy": "DETERMINISTIC_FALLBACK",
        "maximum_identical_transport_attempts": 2,
        "accepted_usd_cap_required_for_end_to_end_canary": USD_CAP,
        "canary_sha256": sha256_file(CANARY),
        "preflight_sha256": sha256_file(PREFLIGHT),
        "api_calls": 0,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    write_json(OUT / "generation_preflight.json", dry)
    print(json.dumps(dry, ensure_ascii=False, indent=2), flush=True)
    if not args.live:
        return
    if args.accept_usd_cap is None or args.accept_usd_cap < USD_CAP:
        raise SystemExit(f"live canary requires --accept-usd-cap {USD_CAP:g}")

    config = load_config(ROOT / "configs/experiment.yaml")
    client = make_client(endpoint_from_config(config, "generator"))
    aliases = aliases_by_owner()
    completed = {row["call_id"]: row for row in rows(OUT / "generator_arm_results.jsonl")}
    raw_attempts = {
        f"{row['call_id']}:{row.get('physical_attempt')}:{index}": row
        for index, row in enumerate(rows(OUT / "raw_provider_attempts_before_guard.jsonl"))
    }
    try:
        for group_index, row in enumerate(canary, start=1):
            candidate = TypedResourceCandidate(**row["actual_rank1_candidate"])
            for seed in row["paired_generator_seeds"]:
                arm_order = ("ON", "OFF") if seed % 2 == 0 else ("OFF", "ON")
                for arm in arm_order:
                    key = call_id(row, seed, arm)
                    if key in completed:
                        continue
                    on = arm == "ON"
                    program = build_typed_response_program(
                        requested_action_id=row["on_action_id"] if on else row["off_action_id"],
                        current_goal="Respond supportively to the latest user message using only visible authorized information.",
                        current_user_id=row["current_owner_id"],
                        candidates={row["component"]: candidate} if on else {},
                        expected_execution_candidate_ids={row["component"]: candidate.resource_id} if on else {},
                        current_user_known_aliases=aliases.get(row["current_owner_id"], ()),
                    )
                    messages = evidence_aware_generation_messages(current_context=context(row), program=program)
                    wrapper = RawPersistingClient(client, call_key=key, seed=int(seed), raw_rows=raw_attempts)
                    execution = execute_typed_response(
                        wrapper, GeneratorSchema, messages, program,
                        rewrite_policy=RewritePolicy.DETERMINISTIC_FALLBACK,
                    )
                    completed[key] = {
                        "protocol": PROTOCOL, "call_id": key,
                        "effect_group_id": row["effect_group_id"], "state_id": row["state_id"],
                        "component": row["component"], "seed": seed, "arm": arm,
                        "requested_action_id": execution.requested_action_id,
                        "realized_action_id": execution.realized_action_id,
                        "status": execution.status,
                        "first_pass_errors": list(execution.first_pass_errors),
                        "final_guard_errors": list(execution.final_guard_errors),
                        "final_reply": execution.response.reply if execution.response else None,
                        "final_used_evidence_ids": list(execution.used_evidence_ids),
                        "reported_used_evidence_ids": list(execution.reported_used_evidence_ids),
                        "raw_provider_reply_persisted_before_guard": any(value.get("call_id") == key for value in raw_attempts.values()),
                        "post_generation_resource_concatenation": False,
                    }
                    write_jsonl(OUT / "generator_arm_results.jsonl", list(completed.values()))
            print(f"generation group {group_index}/8 complete_calls={len(completed)}/48", flush=True)
    finally:
        client.close()
    result_rows = list(completed.values())
    report = {
        "protocol": PROTOCOL,
        "status": "CANARY_GENERATION_COMPLETE_MEASUREMENT_MAY_RUN" if len(result_rows) == 48 and all(row["raw_provider_reply_persisted_before_guard"] for row in result_rows) else "CANARY_GENERATION_INCOMPLETE_NO_MEASUREMENT",
        "logical_calls_completed": len(result_rows),
        "raw_provider_attempt_rows": len(rows(OUT / "raw_provider_attempts_before_guard.jsonl")),
        "raw_persisted_before_guard": sum(row["raw_provider_reply_persisted_before_guard"] for row in result_rows),
        "status_counts": dict(Counter(row["status"] for row in result_rows)),
        "requested_realized_exact": sum(row["requested_action_id"] == row["realized_action_id"] for row in result_rows),
        "response_effect_judged": False,
        "accepted_usd_cap": args.accept_usd_cap,
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
