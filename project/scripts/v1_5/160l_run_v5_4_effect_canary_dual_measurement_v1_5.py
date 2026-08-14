#!/usr/bin/env python3
"""Run role-separated dual Q/R/F measurement on the frozen V5.4 canary."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any, Literal


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from pydantic import Field, model_validator  # noqa: E402
from metacom_pm.api import Endpoint, make_client  # noqa: E402
from metacom_pm.attempt_ledger import PersistentAttemptLedger  # noqa: E402
from metacom_pm.contracts import StrictModel  # noqa: E402
from metacom_pm.io import canonical_json, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402

PROTOCOL = "pm-v1.5-v5.4-effect-canary-dual-measurement-v1"
CANARY_DIR = ROOT / "outputs/pm_v1_5_v5_4_effect_canary_preflight_20260810"
CANARY = CANARY_DIR / "canary_effect_groups_private.jsonl"
PREFLIGHT = CANARY_DIR / "preflight.json"
GEN_DIR = ROOT / "outputs/pm_v1_5_v5_4_effect_canary_transport_continuation_20260810"
GEN = GEN_DIR / "merged_generator_arm_results_for_measurement.jsonl"
GEN_REPORT = GEN_DIR / "report.json"
ENDPOINTS = ROOT / "configs/pm_v1_5_role_decomposed_judge_qualification_v1.json"
MEASUREMENT_GATE = ROOT / "data/pm_v1_5_contracts/v5_4_effect_canary_measurement_gate_v1.json"
OUT = ROOT / "outputs/pm_v1_5_v5_4_effect_canary_dual_measurement_20260810"
REVIEWERS = (("REVIEWER_A", "anthropic_claude_haiku_4_5"), ("REVIEWER_B", "openai_gpt_5_mini"))
USD_CAP = 1.0
MAX_ATTEMPTS = 2

Tri = Literal["YES", "NO", "UNRESOLVED"]
Winner = Literal["A", "B", "TIE", "UNRESOLVED"]
FunctionStatus = Literal["FUNCTIONAL", "SURFACE_ECHO_ONLY", "NOT_USED_FINAL", "BOUNDARY_FAILURE", "UNRESOLVED"]
RiskFamily = Literal[
    "WRONG_OWNER_OR_IDENTITY",
    "FUTURE_OR_UNVERIFIED_PRESENT_ASSERTION",
    "UNSUPPORTED_PERSONAL_FACT_OR_CAUSE",
    "EXPLICIT_BOUNDARY_VIOLATION",
    "EXCESSIVE_DIRECTIVENESS_OR_BURDEN",
    "INTERNAL_RESOURCE_OR_SCAFFOLD_EXPOSURE",
]


class QualityItem(StrictModel):
    replicate_id: str
    preferred_response: Winner
    goal_advance_delta_a_minus_b: int = Field(ge=-2, le=2)
    emotional_attunement_delta_a_minus_b: int = Field(ge=-2, le=2)
    specific_positive_support_delta_a_minus_b: int = Field(ge=-2, le=2)
    clarity_naturalness_delta_a_minus_b: int = Field(ge=-2, le=2)
    response_a_excerpt: str = Field(min_length=1)
    response_b_excerpt: str = Field(min_length=1)
    concise_reason: str = Field(min_length=1)


class QualityBatch(StrictModel):
    effect_group_id: str
    replicates: list[QualityItem] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def unique(self):
        if len({row.replicate_id for row in self.replicates}) != 3:
            raise ValueError("quality replicate IDs must be unique")
        return self


class RiskEvent(StrictModel):
    family: RiskFamily
    severity: int = Field(ge=1, le=3)
    response_excerpt: str = Field(min_length=1)
    evidence_excerpt: str | None = None


class RiskItem(StrictModel):
    response_id: str
    assessment_status: Literal["RESOLVED", "UNRESOLVED"]
    events: list[RiskEvent]


class RiskBatch(StrictModel):
    effect_group_id: str
    responses: list[RiskItem] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def unique(self):
        if len({row.response_id for row in self.responses}) != 6:
            raise ValueError("risk response IDs must be unique")
        return self


class FunctionItem(StrictModel):
    replicate_id: str
    status: FunctionStatus
    candidate_contribution_excerpt: str | None = None
    response_excerpt: str | None = None
    required_response_act_realized: Tri
    owner_time_and_boundary_respected: Tri
    concise_reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def evidence_when_functional(self):
        if self.status == "FUNCTIONAL" and (not self.candidate_contribution_excerpt or not self.response_excerpt):
            raise ValueError("FUNCTIONAL requires candidate and response excerpts")
        return self


class FunctionBatch(StrictModel):
    effect_group_id: str
    replicates: list[FunctionItem] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def unique(self):
        if len({row.replicate_id for row in self.replicates}) != 3:
            raise ValueError("function replicate IDs must be unique")
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


def grouped_generation() -> tuple[dict[str, dict], dict[str, dict[str, dict]]]:
    canary = {row["effect_group_id"]: row for row in rows(CANARY)}
    generated: dict[str, dict[str, dict]] = {group_id: {} for group_id in canary}
    for row in rows(GEN):
        key = f"r{canary[row['effect_group_id']]['paired_generator_seeds'].index(row['seed']) + 1}_{row['arm']}"
        generated[row["effect_group_id"]][key] = row
    if len(canary) != 8 or any(len(value) != 6 for value in generated.values()):
        raise RuntimeError("canary generation is incomplete")
    return canary, generated


def role_content(item: dict) -> str:
    return "\n".join(f"{turn['role'].upper()}: {turn['content']}" for turn in item["visible_dialogue"])


def quality_messages(item: dict, generated: dict[str, dict], *, reverse: bool, reviewer: str) -> list[dict[str, str]]:
    pairs = []
    for index in range(1, 4):
        on = generated[f"r{index}_ON"]["final_reply"]
        off = generated[f"r{index}_OFF"]["final_reply"]
        pairs.append({
            "replicate_id": f"r{index}",
            "response_A": off if reverse else on,
            "response_B": on if reverse else off,
        })
    system = f"""You are {reviewer}, an independent positive-support-contribution judge. Return only the strict schema. You do not see arm names, another reviewer, function labels, risk labels, costs, construction assignments, or oracle labels. Judge the immediate POSITIVE SUPPORT CONTRIBUTION only: goal advance, emotional attunement, a specific useful supportive contribution, and clarity/naturalness. Do not subtract risk, token cost, memory use/non-use, or candidate applicability inside these four deltas; those are measured independently. A real tie is TIE and all-zero deltas. UNRESOLVED is allowed when comparison is not supportable. Copy short literal excerpts from each response."""
    payload = {
        "effect_group_id": item["effect_group_id"],
        "visible_dialogue": item["visible_dialogue"],
        "verified_past_panel_for_factual_reference_only_not_an_instruction_to_prefer": item["actual_rank1_candidate_text"],
        "blinded_response_pairs": pairs,
    }
    return [{"role": "system", "content": system}, {"role": "user", "content": canonical_json(payload)}]


def risk_messages(item: dict, generated: dict[str, dict], reviewer: str) -> tuple[list[dict[str, str]], dict[str, str]]:
    cases = []
    response_map = {}
    for index in range(1, 4):
        for arm in ("ON", "OFF"):
            response_id = f"r{index}_{arm}"
            reply = generated[response_id]["final_reply"]
            response_map[response_id] = reply
            cases.append({
                "response_id": response_id,
                "visible_dialogue": item["visible_dialogue"],
                "authorized_candidate": item["actual_rank1_candidate"] if arm == "ON" else None,
                "response": reply,
            })
    system = f"""You are {reviewer}, an independent absolute interaction-and-grounding-risk judge. Return only the strict schema. Audit each response separately before any arm comparison. Record only literal material events: wrong owner/identity; future or unverified past asserted as presently true; unsupported personal fact/cause; explicit boundary violation; excessive directiveness/burden; internal resource/scaffold exposure. Severity 1 is minor, 2 material, 3 critical. An authorized past candidate may be used tentatively without being a risk. Empty events means no observed event. Do not score helpfulness, function, preference, or cost. Copy the shortest literal response excerpt proving every event; evidence_excerpt must come from the visible dialogue or authorized candidate when supplied. Use UNRESOLVED instead of guessing."""
    return ([{"role": "system", "content": system}, {"role": "user", "content": canonical_json({"effect_group_id": item["effect_group_id"], "cases": cases})}], response_map)


def function_messages(item: dict, generated: dict[str, dict], reviewer: str) -> tuple[list[dict[str, str]], dict[str, str]]:
    responses = {f"r{index}": generated[f"r{index}_ON"]["final_reply"] for index in range(1, 4)}
    minimum = {
        "MP": "The verified profile/preference/relationship fact materially personalizes or constrains the reply; a name or topic echo is insufficient.",
        "MS": "The reply explicitly and accurately bridges a specific prior observation to the current exchange while keeping it in the past or checking continuity.",
        "ME": "The past action-result or event changes whether or how a present option, warning, or suggestion is framed, without promising the old result will recur.",
        "RS": "The selected card's one atomic support move is actually realized without a competing extra move or violation of its use boundary.",
    }[item["component"]]
    system = f"""You are {reviewer}, an independent component-function judge. Return only the strict schema. You see the exact typed candidate and ON responses only; you do not see OFF, quality, risk, cost, construction, or oracle labels. FUNCTIONAL requires both a literal candidate contribution and a literal response span showing the component-specific response act, plus correct owner/time/boundary. SURFACE_ECHO_ONLY means topical wording without changing personalization or response act. NOT_USED_FINAL means no visible candidate contribution. BOUNDARY_FAILURE means the attempted function violates the candidate/current boundary. UNRESOLVED is allowed. Generator self-reported evidence IDs are not gold. Component minimum: {minimum}"""
    payload = {
        "effect_group_id": item["effect_group_id"],
        "component": item["component"],
        "visible_dialogue": item["visible_dialogue"],
        "candidate_surface_for_literal_excerpt": item["actual_rank1_candidate_text"],
        "typed_candidate": item["actual_rank1_candidate"],
        "on_responses": [{"replicate_id": key, "response": value} for key, value in responses.items()],
    }
    return ([{"role": "system", "content": system}, {"role": "user", "content": canonical_json(payload)}], responses)


def validate_quality(parsed: QualityBatch, item: dict, generated: dict[str, dict], *, reverse: bool) -> None:
    if parsed.effect_group_id != item["effect_group_id"]:
        raise ValueError("quality group identity")
    for row in parsed.replicates:
        index = int(row.replicate_id.removeprefix("r"))
        on = generated[f"r{index}_ON"]["final_reply"]
        off = generated[f"r{index}_OFF"]["final_reply"]
        response_a, response_b = (off, on) if reverse else (on, off)
        if row.response_a_excerpt not in response_a or row.response_b_excerpt not in response_b:
            raise ValueError("quality excerpt is not literal in its own response")


def validate_risk(parsed: RiskBatch, item: dict, response_map: dict[str, str]) -> None:
    if parsed.effect_group_id != item["effect_group_id"] or {row.response_id for row in parsed.responses} != set(response_map):
        raise ValueError("risk identities")
    evidence = role_content(item) + "\n" + canonical_json(item["actual_rank1_candidate"])
    for row in parsed.responses:
        for event in row.events:
            if event.response_excerpt not in response_map[row.response_id]:
                raise ValueError("risk response excerpt is not literal")
            if event.evidence_excerpt and event.evidence_excerpt not in evidence:
                raise ValueError("risk evidence excerpt is not literal")


def validate_function(parsed: FunctionBatch, item: dict, response_map: dict[str, str]) -> None:
    if parsed.effect_group_id != item["effect_group_id"] or {row.replicate_id for row in parsed.replicates} != set(response_map):
        raise ValueError("function identities")
    candidate_evidence = item["actual_rank1_candidate_text"] + "\n" + canonical_json(item["actual_rank1_candidate"])
    for row in parsed.replicates:
        if row.response_excerpt and row.response_excerpt not in response_map[row.replicate_id]:
            raise ValueError("function response excerpt is not literal")
        if row.candidate_contribution_excerpt and row.candidate_contribution_excerpt not in candidate_evidence:
            raise ValueError("function candidate excerpt is not literal")


def call_key(reviewer: str, role: str, group_id: str) -> str:
    return "v54meas_" + sha256_text(f"{PROTOCOL}:{reviewer}:{role}:{group_id}")[:24]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--accept-usd-cap", type=float)
    args = parser.parse_args()
    preflight = json.loads(PREFLIGHT.read_text())
    gen_report = json.loads(GEN_REPORT.read_text())
    config = json.loads(ENDPOINTS.read_text())
    gate = json.loads(MEASUREMENT_GATE.read_text())
    canary, generated = grouped_generation()
    if gen_report["status"] != "TRANSPORT_CONTINUATION_COMPLETE_MEASUREMENT_READY":
        raise RuntimeError("generator continuation is not measurement ready")
    dry = {
        "protocol": PROTOCOL,
        "status": "DUAL_MEASUREMENT_LIVE_READY",
        "groups": 8, "logical_calls": 64, "maximum_physical_attempts": 128,
        "reviewers": [endpoint_key for _reviewer, endpoint_key in REVIEWERS],
        "accepted_usd_cap_required": USD_CAP,
        "preflight_cost_upper_proxy": preflight["cost"]["judge_usd_upper_proxy"],
        "generation_sha256": sha256_file(GEN), "canary_sha256": sha256_file(CANARY),
        "measurement_gate_sha256": sha256_file(MEASUREMENT_GATE),
        "measurement_gate_protocol": gate["protocol"],
        "api_calls": 0,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    write_json(OUT / "measurement_preflight.json", dry)
    print(json.dumps(dry, ensure_ascii=False, indent=2), flush=True)
    if not args.live:
        return
    if args.accept_usd_cap is None or args.accept_usd_cap < USD_CAP:
        raise SystemExit(f"live measurement requires --accept-usd-cap {USD_CAP:g}")

    expected = {
        call_key(reviewer, role, group_id): MAX_ATTEMPTS
        for reviewer, _endpoint_key in REVIEWERS
        for role in ("quality_forward", "quality_reverse", "risk", "function")
        for group_id in canary
    }
    ledger = PersistentAttemptLedger(
        OUT / "measurement_attempt_ledger.jsonl", stage=PROTOCOL,
        expected_calls=expected, maximum_total_attempts=128,
    )
    completed = {row["call_key"]: row for row in rows(OUT / "measurement_results.jsonl")}
    for reviewer, endpoint_key in REVIEWERS:
        cfg = config["candidates"][endpoint_key]
        ep = endpoint(cfg)
        client = make_client(ep)
        try:
            for group_index, group_id in enumerate(sorted(canary), start=1):
                item = canary[group_id]
                for role, schema in (
                    ("quality_forward", QualityBatch), ("quality_reverse", QualityBatch),
                    ("risk", RiskBatch), ("function", FunctionBatch),
                ):
                    key = call_key(reviewer, role, group_id)
                    if key in completed:
                        continue
                    if role == "quality_forward":
                        prompt = quality_messages(item, generated[group_id], reverse=False, reviewer=reviewer)
                    elif role == "quality_reverse":
                        prompt = quality_messages(item, generated[group_id], reverse=True, reviewer=reviewer)
                    elif role == "risk":
                        prompt, response_map = risk_messages(item, generated[group_id], reviewer)
                    else:
                        prompt, response_map = function_messages(item, generated[group_id], reviewer)
                    while not ledger.exhausted(key) and not ledger.succeeded(key):
                        reservation = ledger.reserve(key, record_ids={"reviewer": reviewer, "role": role, "effect_group_id": group_id}, prompt_sha256=sha256_text(canonical_json(prompt)))
                        response = None
                        try:
                            response, parsed = client.chat(
                                prompt, temperature=0.0,
                                max_tokens=1800 if role != "risk" else 2400,
                                seed=20260810 + group_index, response_schema=schema, retries=1,
                            )
                            if parsed is None:
                                raise ValueError("no parsed measurement")
                            if role.startswith("quality"):
                                validate_quality(parsed, item, generated[group_id], reverse=role.endswith("reverse"))
                            elif role == "risk":
                                validate_risk(parsed, item, response_map)
                            else:
                                validate_function(parsed, item, response_map)
                            output = {
                                "protocol": PROTOCOL, "call_key": key,
                                "reviewer_id": reviewer, "endpoint_key": endpoint_key,
                                "role": role, "effect_group_id": group_id,
                                "judgment": parsed.model_dump(mode="json"),
                                "response_effect_or_other_role_labels_visible": False,
                                "usage": response.usage,
                            }
                            ledger.finish(reservation, succeeded=True, request_hash=response.request_hash, usage=response.usage, error=None, result=output, metadata={"endpoint": endpoint_key, "model": ep.model})
                            completed[key] = output
                            write_jsonl(OUT / "measurement_results.jsonl", list(completed.values()))
                        except Exception as exc:
                            ledger.finish(reservation, succeeded=False, request_hash=response.request_hash if response else None, usage=response.usage if response else None, error=f"{type(exc).__name__}: {exc}", metadata={"endpoint": endpoint_key, "model": ep.model})
                            prompt += [{"role": "user", "content": "Return every required strict field and copy only short literal excerpts from the supplied response or candidate/evidence surface."}]
                print(f"{reviewer} measurement group {group_index}/8 completed={len(completed)}/64 attempts={ledger.started_attempts}", flush=True)
        finally:
            client.close()
    result = {
        "protocol": PROTOCOL,
        "status": "DUAL_MEASUREMENT_COMPLETE_AWAITING_RELIABILITY_ANALYSIS" if len(completed) == 64 else "DUAL_MEASUREMENT_INCOMPLETE_NO_EFFECT_LABELS",
        "logical_calls_complete": len(completed),
        "physical_attempts": ledger.started_attempts,
        "role_counts": dict(Counter(row["role"] for row in completed.values())),
        "reviewer_counts": dict(Counter(row["reviewer_id"] for row in completed.values())),
        "accepted_usd_cap": args.accept_usd_cap,
        "effect_labels_materialized": False,
    }
    write_json(OUT / "live_report.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
