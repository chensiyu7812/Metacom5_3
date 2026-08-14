#!/usr/bin/env python3
"""Run blinded per-response absolute quality scoring for the frozen canary."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import random
import re
import sys
from typing import Any, Literal

from pydantic import Field, model_validator


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from metacom_pm.api import Endpoint, make_client  # noqa: E402
from metacom_pm.attempt_ledger import PersistentAttemptLedger  # noqa: E402
from metacom_pm.contracts import StrictModel  # noqa: E402
from metacom_pm.io import canonical_json, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402

PROTOCOL = "pm-v1.5-v5.4-effect-canary-absolute-quality-v1"
CANARY = ROOT / "outputs/pm_v1_5_v5_4_effect_canary_preflight_20260810/canary_effect_groups_private.jsonl"
GEN = ROOT / "outputs/pm_v1_5_v5_4_effect_canary_transport_continuation_20260810/merged_generator_arm_results_for_measurement.jsonl"
ENDPOINTS = ROOT / "configs/pm_v1_5_role_decomposed_judge_qualification_v1.json"
CONTRACT = ROOT / "data/pm_v1_5_contracts/v5_4_effect_canary_absolute_quality_repair_v1.json"
OUT = ROOT / "outputs/pm_v1_5_v5_4_effect_canary_absolute_quality_20260810"
REVIEWERS = (("REVIEWER_A", "anthropic_claude_haiku_4_5"), ("REVIEWER_B", "openai_gpt_5_mini"))
MAX_ATTEMPTS = 2
USD_CAP = 0.30


class AbsoluteQualityItem(StrictModel):
    case_id: str
    assessment_status: Literal["RESOLVED", "UNRESOLVED"]
    goal_advance: int | None = Field(ge=1, le=5)
    emotional_attunement: int | None = Field(ge=1, le=5)
    specific_positive_support: int | None = Field(ge=1, le=5)
    clarity_naturalness: int | None = Field(ge=1, le=5)
    evidence_ids: list[str] = Field(min_length=1)
    concise_reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def score_completeness(self):
        scores = (self.goal_advance, self.emotional_attunement, self.specific_positive_support, self.clarity_naturalness)
        if self.assessment_status == "RESOLVED" and any(score is None for score in scores):
            raise ValueError("RESOLVED requires all four scores")
        if self.assessment_status == "UNRESOLVED" and any(score is not None for score in scores):
            raise ValueError("UNRESOLVED requires four null scores")
        return self


class AbsoluteQualityBatch(StrictModel):
    effect_group_id: str
    cases: list[AbsoluteQualityItem] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def unique(self):
        if len({row.case_id for row in self.cases}) != 6:
            raise ValueError("case IDs must be unique")
        return self


def rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def endpoint(raw: dict[str, Any]) -> Endpoint:
    return Endpoint(
        base_url=str(raw["base_url"]), model=str(raw["model"]), api_key_env=str(raw["api_key_env"]),
        timeout_seconds=240.0, family=str(raw["family"]), transport=str(raw["transport"]),
        supports_strict_json_schema=bool(raw["supports_strict_json_schema"]),
        temperature_mode=str(raw.get("temperature_mode") or "explicit"),
        max_output_tokens_parameter=str(raw.get("max_output_tokens_parameter") or "max_tokens"),
        anthropic_strict_tool_use=bool(raw.get("anthropic_strict_tool_use", False)),
        openai_reasoning_effort=raw.get("openai_reasoning_effort"),
    )


def span_map(text: str, prefix: str) -> dict[str, str]:
    pieces = [piece for piece in re.split(r"(?<=[.!?])\s+|\n+", text.strip()) if piece] or [text]
    return {f"{prefix}{index}": piece for index, piece in enumerate(pieces)}


def grouped() -> tuple[dict[str, dict], dict[str, list[dict]]]:
    canary = {row["effect_group_id"]: row for row in rows(CANARY)}
    generation: dict[str, list[dict]] = defaultdict(list)
    for row in rows(GEN):
        generation[row["effect_group_id"]].append(row)
    if len(canary) != 8 or any(len(generation[group_id]) != 6 for group_id in canary):
        raise RuntimeError("frozen canary generation incomplete")
    return canary, generation


def case_id(reviewer: str, group_id: str, replicate: int, arm: str) -> str:
    return "qcase_" + hashlib.sha256(f"{PROTOCOL}:{reviewer}:{group_id}:{replicate}:{arm}".encode()).hexdigest()[:16]


def build_cases(reviewer: str, group_id: str, generated: list[dict]) -> tuple[list[dict], list[dict]]:
    source = {(row["seed"], row["arm"]): row for row in generated}
    seeds = sorted({row["seed"] for row in generated})
    prompt_cases = []
    private = []
    for replicate, seed in enumerate(seeds, start=1):
        for arm in ("ON", "OFF"):
            cid = case_id(reviewer, group_id, replicate, arm)
            reply = source[(seed, arm)]["final_reply"]
            prompt_cases.append({"case_id": cid, "response_spans": span_map(reply, f"{cid}_S")})
            private.append({
                "protocol": PROTOCOL, "reviewer_id": reviewer, "effect_group_id": group_id,
                "case_id": cid, "replicate_id": f"r{replicate}", "seed": seed, "arm": arm,
                "response_sha256": sha256_text(reply),
            })
    rng = random.Random(int(hashlib.sha256(f"{PROTOCOL}:{reviewer}:{group_id}:order".encode()).hexdigest()[:16], 16))
    rng.shuffle(prompt_cases)
    order = {row["case_id"]: index for index, row in enumerate(prompt_cases)}
    for row in private:
        row["reviewer_visible_position"] = order[row["case_id"]]
    return prompt_cases, private


def messages(item: dict, cases: list[dict], reviewer: str) -> list[dict[str, str]]:
    system = f"""You are {reviewer}, an independent absolute positive-support judge. Score every anonymous response independently, not relative to neighboring cases. Return only the strict schema. Use integers 1-5 for four axes. Goal advance: 1 obstructs/misses, 2 weak, 3 adequate, 4 strong concrete advance, 5 exceptional without overreach. Emotional attunement: 1 mismatched, 2 generic/weak, 3 adequate, 4 specifically attuned, 5 exceptionally precise/proportionate. Specific positive support: 1 none or harmful, 2 slight/generic, 3 adequate, 4 clearly useful/specific, 5 exceptional immediate contribution. Clarity/naturalness: 1 confusing, 2 awkward, 3 acceptable, 4 clear/natural, 5 exceptional. Do not subtract factual/grounding risk, memory or candidate function/non-use, applicability, length, tokens, latency, or cost. Select one or more evidence IDs belonging to that case only; never copy text. UNRESOLVED requires all scores null."""
    payload = {"effect_group_id": item["effect_group_id"], "visible_dialogue": item["visible_dialogue"], "anonymous_independently_scored_cases": cases}
    return [{"role": "system", "content": system}, {"role": "user", "content": canonical_json(payload)}]


def validate(parsed: AbsoluteQualityBatch, group_id: str, cases: list[dict]) -> None:
    allowed = {row["case_id"]: set(row["response_spans"]) for row in cases}
    if parsed.effect_group_id != group_id or {row.case_id for row in parsed.cases} != set(allowed):
        raise ValueError("absolute quality identities")
    for row in parsed.cases:
        if not set(row.evidence_ids) <= allowed[row.case_id]:
            raise ValueError("evidence ID is absent or belongs to another case")


def call_key(reviewer: str, group_id: str) -> str:
    return "v54absq_" + sha256_text(f"{PROTOCOL}:{reviewer}:{group_id}")[:24]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--accept-usd-cap", type=float)
    args = parser.parse_args()
    canary, generation = grouped()
    config = json.loads(ENDPOINTS.read_text())
    private_rows = []
    prepared: dict[tuple[str, str], list[dict]] = {}
    for reviewer, _endpoint_key in REVIEWERS:
        for group_id in sorted(canary):
            cases, private = build_cases(reviewer, group_id, generation[group_id])
            prepared[(reviewer, group_id)] = cases
            private_rows.extend(private)
    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "absolute_quality_case_manifest_private.jsonl", private_rows)
    preflight = {
        "protocol": PROTOCOL, "status": "ABSOLUTE_QUALITY_LIVE_READY", "logical_calls": 16,
        "response_items": 96, "paired_effect_items_per_reviewer": 24,
        "reviewers": [key for _reviewer, key in REVIEWERS], "accepted_usd_cap_required": USD_CAP,
        "contract_sha256": sha256_file(CONTRACT), "generation_sha256": sha256_file(GEN),
        "case_ids_hide_arm_and_replicate": True, "reviewer_orders_differ": True, "api_calls": 0,
    }
    write_json(OUT / "preflight.json", preflight)
    print(json.dumps(preflight, ensure_ascii=False, indent=2), flush=True)
    if not args.live:
        return
    if args.accept_usd_cap is None or args.accept_usd_cap < USD_CAP:
        raise SystemExit(f"live absolute quality requires --accept-usd-cap {USD_CAP:g}")
    expected = {call_key(reviewer, group_id): MAX_ATTEMPTS for reviewer, _key in REVIEWERS for group_id in canary}
    ledger = PersistentAttemptLedger(OUT / "attempt_ledger.jsonl", stage=PROTOCOL, expected_calls=expected, maximum_total_attempts=32)
    completed = {row["call_key"]: row for row in rows(OUT / "results.jsonl")}
    for reviewer, endpoint_key in REVIEWERS:
        ep = endpoint(config["candidates"][endpoint_key])
        client = make_client(ep)
        try:
            for index, group_id in enumerate(sorted(canary), start=1):
                key = call_key(reviewer, group_id)
                if key in completed:
                    continue
                prompt = messages(canary[group_id], prepared[(reviewer, group_id)], reviewer)
                while not ledger.exhausted(key) and not ledger.succeeded(key):
                    reservation = ledger.reserve(key, record_ids={"reviewer": reviewer, "effect_group_id": group_id}, prompt_sha256=sha256_text(canonical_json(prompt)))
                    response = None
                    try:
                        response, parsed = client.chat(prompt, temperature=0.0, max_tokens=2400, seed=20260810 + index, response_schema=AbsoluteQualityBatch, retries=1)
                        if parsed is None:
                            raise ValueError("no parsed absolute quality")
                        validate(parsed, group_id, prepared[(reviewer, group_id)])
                        output = {
                            "protocol": PROTOCOL, "call_key": key, "reviewer_id": reviewer,
                            "endpoint_key": endpoint_key, "effect_group_id": group_id,
                            "judgment": parsed.model_dump(mode="json"), "usage": response.usage,
                            "arm_replicate_candidate_function_risk_cost_visible": False,
                        }
                        ledger.finish(reservation, succeeded=True, request_hash=response.request_hash, usage=response.usage, error=None, result=output, metadata={"endpoint": endpoint_key, "model": ep.model})
                        completed[key] = output
                        write_jsonl(OUT / "results.jsonl", list(completed.values()))
                    except Exception as exc:
                        ledger.finish(reservation, succeeded=False, request_hash=response.request_hash if response else None, usage=response.usage if response else None, error=f"{type(exc).__name__}: {exc}", metadata={"endpoint": endpoint_key, "model": ep.model})
                        prompt += [{"role": "user", "content": "Return exactly six cases. Every RESOLVED case needs four integer scores 1-5 and only evidence IDs from its own response; UNRESOLVED needs four null scores."}]
                print(f"{reviewer} absolute quality {index}/8 complete={len(completed)}/16 attempts={ledger.started_attempts}", flush=True)
        finally:
            client.close()
    report = {
        "protocol": PROTOCOL,
        "status": "ABSOLUTE_QUALITY_COMPLETE_AWAITING_RELIABILITY" if len(completed) == 16 else "ABSOLUTE_QUALITY_INCOMPLETE_NO_TARGETS",
        "logical_calls_complete": len(completed), "physical_attempts": ledger.started_attempts,
        "reviewer_counts": dict(Counter(row["reviewer_id"] for row in completed.values())),
        "effect_targets_materialized": False, "accepted_usd_cap": args.accept_usd_cap,
    }
    write_json(OUT / "live_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
