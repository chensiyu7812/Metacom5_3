#!/usr/bin/env python3
"""Run the frozen 8-group (2/head) public learnability canary.

Dry-run is the default.  Live execution requires ``--live`` and an explicit
``--accept-usd-cap 0.03`` (or larger).  The canary uses all three frozen
paired generator seeds and the frozen batched Q/R/F schemas.
"""

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

from metacom_pm.api import RetryableProviderError, make_client  # noqa: E402
from metacom_pm.config import endpoint_from_config, load_config  # noqa: E402
from metacom_pm.contracts import StrictModel  # noqa: E402
from metacom_pm.io import canonical_json, stable_hex, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_typed_resource_adapter import TypedResourceCandidate  # noqa: E402
from metacom_pm.v1_5_v5_3_qrf_judge import (  # noqa: E402
    BatchedAbsoluteRiskJudgment,
    BatchedContributionJudgment,
    BatchedFunctionalUseJudgment,
    aggregate_on_minus_off,
    contribution_messages,
    functional_use_messages,
    risk_messages,
    validate_response_excerpts,
)
from metacom_pm.v1_5_v5_3_typed_response_program import (  # noqa: E402
    build_typed_response_program,
    evidence_aware_generation_messages,
    execute_typed_response,
)


PROTOCOL = "pm-v1.5-v5.3-public-learnability-canary-v1"
PILOT_DIR = ROOT / "outputs/pm_v1_5_v5_3_public_learnability_pilot_20260809"
OUT_DIR = ROOT / "outputs/pm_v1_5_v5_3_public_learnability_canary_20260809"
USD_CAP = 0.03


class GeneratorSchema(StrictModel):
    reply: str
    used_evidence_ids: list[str]
    realized_response_act: str


class RecordingSeedClient:
    def __init__(
        self, client, *, seed: int, temperature: float, max_tokens: int,
        retries: int = 2, transport_retries: int = 0,
    ):
        self.client = client
        self.seed = seed
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.retries = retries
        self.transport_retries = transport_retries
        self.calls: list[dict[str, Any]] = []

    def chat(self, messages, *, response_schema):
        transport_classes = {"rate_limited_429", "request_timeout_408", "http_5xx", "network_timeout"}
        for transport_attempt in range(self.transport_retries + 1):
            try:
                result, parsed = self.client.chat(
                    messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                    seed=self.seed,
                    response_schema=response_schema,
                    retries=self.retries,
                )
                break
            except Exception as exc:  # provider/shape failure becomes an audited fallback surface
                retry_class = getattr(exc, "last_retry_class", None)
                will_retry = (
                    isinstance(exc, RetryableProviderError)
                    and retry_class in transport_classes
                    and transport_attempt < self.transport_retries
                )
                self.calls.append(
                    {
                        "request_hash": getattr(exc, "request_hash", None),
                        "usage": getattr(exc, "usage", None) or {},
                        "latency_ms": None,
                        "finish_reason": "transport_retry" if will_retry else "provider_or_structured_failure",
                        "structured_output": False,
                        "error_type": type(exc).__name__,
                        "retry_class": retry_class,
                        "transport_attempt": transport_attempt + 1,
                        "will_retry_identical_request": will_retry,
                        "error": str(exc),
                    }
                )
                if not will_retry:
                    return exc, None
                time.sleep(max(float(getattr(exc, "retry_after_seconds", 0.0) or 0.0), 30.0))
        self.calls.append(
            {
                "request_hash": result.request_hash,
                "usage": result.usage,
                "latency_ms": result.latency_ms,
                "finish_reason": result.normalized_finish_reason,
                "structured_output": parsed is not None,
            }
        )
        return result, parsed


def _rows() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in (PILOT_DIR / "effect_group_manifest_private.jsonl").read_text().splitlines()
        if line.strip()
    ]


def _canary_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for component in ("MP", "MS", "ME", "RS"):
        candidates = [row for row in rows if row["component"] == component]
        candidates.sort(key=lambda row: stable_hex(PROTOCOL, row["state_id"], n=24))
        first = candidates[0]
        second = next(
            (row for row in candidates[1:] if row["candidate_type"] != first["candidate_type"]),
            candidates[1],
        )
        result.extend((first, second))
    return result


def _context(row: dict[str, Any]) -> str:
    return "\n".join(
        f"{turn['role'].upper()}: {turn['content']}" for turn in row["visible_dialogue"]
    )


def _aliases(rows: list[dict[str, Any]]) -> dict[str, tuple[str, ...]]:
    wanted = {str(row.get("user_id")) for row in rows if row.get("user_id")}
    users = json.loads((ROOT / "data/external/evo_emo.json").read_text())
    result: dict[str, tuple[str, ...]] = {}
    for user in users:
        user_id = str(user["id"])
        if user_id not in wanted:
            continue
        name = str((user.get("basic_info") or {}).get("name") or "").strip()
        result[user_id] = (name,) if name else ()
    return result


def _program(row: dict[str, Any], *, on: bool, aliases: tuple[str, ...]):
    candidate = TypedResourceCandidate(**row["candidate"])
    user_id = str(row.get("user_id") or row.get("dialogue_id"))
    return build_typed_response_program(
        requested_action_id=row["on_action_id"] if on else row["off_action_id"],
        current_goal="Respond supportively to the latest user message using only visible authorized information.",
        current_user_id=user_id,
        candidates={row["component"]: candidate} if on else {},
        expected_execution_candidate_ids={row["component"]: candidate.resource_id} if on else {},
        current_user_known_aliases=aliases,
    )


def _sum_usage(calls: list[dict[str, Any]]) -> dict[str, int]:
    result: Counter[str] = Counter()
    for call in calls:
        for key, value in call.get("usage", {}).items():
            if isinstance(value, int):
                result[key] += value
    return dict(result)


def _judge_call(client, schema, messages, *, seed: int, max_tokens: int):
    wrapper = RecordingSeedClient(client, seed=seed, temperature=0.0, max_tokens=max_tokens)
    result, parsed = wrapper.chat(messages, response_schema=schema)
    return result, parsed, wrapper.calls


def run_group(
    row, *, gen_client, judge_client, aliases, include_risk: bool = True,
    result_protocol: str = PROTOCOL,
):
    generated: list[dict[str, Any]] = []
    call_records: list[dict[str, Any]] = []
    for replicate, seed in enumerate(row["paired_generator_seeds"], start=1):
        arm_order = ("ON", "OFF") if seed % 2 == 0 else ("OFF", "ON")
        outputs: dict[str, Any] = {}
        for arm in arm_order:
            on = arm == "ON"
            program = _program(row, on=on, aliases=aliases)
            messages = evidence_aware_generation_messages(
                current_context=_context(row), program=program
            )
            wrapper = RecordingSeedClient(
                gen_client, seed=int(seed), temperature=0.7, max_tokens=512,
                retries=1, transport_retries=1,
            )
            execution = execute_typed_response(
                wrapper, GeneratorSchema, messages, program
            )
            call_records.extend({"role": "generator", "arm": arm, **call} for call in wrapper.calls)
            outputs[arm] = {
                "reply": execution.response.reply if execution.response else None,
                "status": execution.status,
                "requested_action_id": execution.requested_action_id,
                "realized_action_id": execution.realized_action_id,
                "first_pass_errors": list(execution.first_pass_errors),
            }
        generated.append({"replicate_id": f"r{replicate}", "seed": seed, **outputs})

    responses = {
        f"{rep['replicate_id']}_{arm}": rep[arm]["reply"]
        for rep in generated for arm in ("ON", "OFF")
    }
    forward_pairs = [
        {"replicate_id": rep["replicate_id"], "response_a": rep["ON"]["reply"], "response_b": rep["OFF"]["reply"]}
        for rep in generated
    ]
    reverse_pairs = [
        {"replicate_id": rep["replicate_id"], "response_a": rep["OFF"]["reply"], "response_b": rep["ON"]["reply"]}
        for rep in generated
    ]
    judge_seed = int(stable_hex(result_protocol, row["effect_group_id"], "judge", n=8), 16) & 0x7FFFFFFF
    _, qf, calls = _judge_call(
        judge_client, BatchedContributionJudgment,
        contribution_messages(visible_dialogue=row["visible_dialogue"], pairs=forward_pairs),
        seed=judge_seed, max_tokens=2100,
    )
    call_records.extend({"role": "judge_quality_forward", **call} for call in calls)
    _, qr, calls = _judge_call(
        judge_client, BatchedContributionJudgment,
        contribution_messages(visible_dialogue=row["visible_dialogue"], pairs=reverse_pairs),
        seed=judge_seed + 1, max_tokens=2100,
    )
    call_records.extend({"role": "judge_quality_reverse", **call} for call in calls)
    if qf is not None:
        validate_response_excerpts(qf, responses)
    if qr is not None:
        validate_response_excerpts(qr, responses)

    risk = None
    if include_risk:
        risk_cases = []
        risk_response_map: dict[str, str] = {}
        for rep in generated:
            for arm in ("ON", "OFF"):
                response_id = "resp_" + stable_hex(row["effect_group_id"], rep["replicate_id"], arm, n=12)
                risk_response_map[response_id] = rep[arm]["reply"]
                risk_cases.append(
                    {
                        "response_id": response_id,
                        "visible_dialogue": row["visible_dialogue"],
                        "authorized_candidate": row["candidate"] if arm == "ON" else None,
                        "response": rep[arm]["reply"],
                    }
                )
        risk_cases.sort(key=lambda case: case["response_id"])
        _, risk, calls = _judge_call(
            judge_client, BatchedAbsoluteRiskJudgment, risk_messages(cases=risk_cases),
            seed=judge_seed + 2, max_tokens=3000,
        )
        call_records.extend({"role": "judge_risk", **call} for call in calls)
        if risk is not None:
            validate_response_excerpts(risk, risk_response_map)

    on_responses = [
        {"replicate_id": rep["replicate_id"], "response": rep["ON"]["reply"]}
        for rep in generated
    ]
    _, functional, calls = _judge_call(
        judge_client, BatchedFunctionalUseJudgment,
        functional_use_messages(
            visible_dialogue=row["visible_dialogue"], candidate=row["candidate"],
            on_responses=on_responses,
        ),
        seed=judge_seed + 3, max_tokens=1800,
    )
    call_records.extend({"role": "judge_function", **call} for call in calls)
    quality_effect = aggregate_on_minus_off(qf, qr) if qf is not None and qr is not None else None
    return {
        "protocol": result_protocol,
        "effect_group_id": row["effect_group_id"],
        "state_id": row["state_id"],
        "component": row["component"],
        "candidate_type": row["candidate_type"],
        "generated": generated,
        "quality_forward": qf.model_dump(mode="json") if qf else None,
        "quality_reverse": qr.model_dump(mode="json") if qr else None,
        "quality_effect": quality_effect,
        "risk": risk.model_dump(mode="json") if risk else None,
        "risk_instrument_status": "CANARY_UNQUALIFIED" if not include_risk else "MEASURED_NOT_QUALIFIED",
        "functional": functional.model_dump(mode="json") if functional else None,
        "call_records": call_records,
        "usage": _sum_usage(call_records),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--accept-usd-cap", type=float)
    args = parser.parse_args()
    rows = _canary_rows(_rows())
    print({"canary_groups": len(rows), "components": dict(Counter(row["component"] for row in rows))})
    if not args.live:
        print("dry-run: 0 API calls")
        return
    if args.accept_usd_cap is None or args.accept_usd_cap < USD_CAP:
        raise SystemExit("live canary requires --accept-usd-cap 0.03")

    config = load_config(ROOT / "configs/experiment.yaml")
    gen_client = make_client(endpoint_from_config(config, "generator"))
    judge_client = make_client(endpoint_from_config(config, "training_judge"))
    aliases_by_user = _aliases(rows)
    results = []
    try:
        for index, row in enumerate(rows, start=1):
            print(f"[{index}/{len(rows)}] {row['component']} {row['state_id']}")
            result = run_group(
                row, gen_client=gen_client, judge_client=judge_client,
                aliases=aliases_by_user.get(str(row.get("user_id")), ()),
            )
            results.append(result)
            write_jsonl(OUT_DIR / "canary_results.jsonl", results)
    finally:
        gen_client.close()
        judge_client.close()

    calls = [call for row in results for call in row["call_records"]]
    report = {
        "protocol": PROTOCOL,
        "status": "QF_CANARY_PASS_RISK_INSTRUMENT_UNQUALIFIED" if len(results) == 8 and all(
            row["quality_effect"] is not None and row["risk"] is not None and row["functional"] is not None
            for row in results
        ) else "FAIL",
        "groups_completed": len(results),
        "api_calls": len(calls),
        "structured_output_failures": sum(not call["structured_output"] for call in calls),
        "generator_status_counts": dict(Counter(
            arm["status"] for row in results for rep in row["generated"]
            for arm in (rep["ON"], rep["OFF"])
        )),
        "quality_effect_by_component": {
            component: [
                row["quality_effect"]["aggregate"]["mean_positive_support_contribution"]
                for row in results if row["component"] == component and row["quality_effect"]
            ]
            for component in ("MP", "MS", "ME", "RS")
        },
        "usage": _sum_usage(calls),
        "accepted_usd_cap": args.accept_usd_cap,
    }
    write_json(OUT_DIR / "report.json", report)
    print(report)


if __name__ == "__main__":
    main()
