#!/usr/bin/env python3
"""Run remaining canary judgments with exact pre-numbered evidence spans."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import sys

from pydantic import Field, model_validator


ROOT = Path(__file__).resolve().parents[2]
BASE_SCRIPT = ROOT / "scripts/v1_5/161l_run_v5_4_effect_canary_dual_measurement_v2_v1_5.py"
SOURCE_OUT = ROOT / "outputs/pm_v1_5_v5_4_effect_canary_dual_measurement_v3_20260810"
OUT = ROOT / "outputs/pm_v1_5_v5_4_effect_canary_dual_measurement_v4_20260810"
PROTOCOL = "pm-v1.5-v5.4-effect-canary-dual-measurement-v4-span-ids"

spec = importlib.util.spec_from_file_location("v54_canary_measurement_span_base", BASE_SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load measurement base")
base = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = base
spec.loader.exec_module(base)
engine = base.v1


def span_map(text: str, prefix: str) -> dict[str, str]:
    pieces = [piece for piece in re.split(r"(?<=[.!?])\s+|\n+", text.strip()) if piece]
    if not pieces:
        pieces = [text]
    return {f"{prefix}{index}": piece for index, piece in enumerate(pieces)}


class QualityItemSpan(engine.StrictModel):
    replicate_id: str
    preferred_response: engine.Winner
    goal_advance_delta_a_minus_b: int = Field(ge=-2, le=2)
    emotional_attunement_delta_a_minus_b: int = Field(ge=-2, le=2)
    specific_positive_support_delta_a_minus_b: int = Field(ge=-2, le=2)
    clarity_naturalness_delta_a_minus_b: int = Field(ge=-2, le=2)
    response_a_evidence_ids: list[str] = Field(min_length=1, max_length=3)
    response_b_evidence_ids: list[str] = Field(min_length=1, max_length=3)
    concise_reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def tie_is_zero(self):
        deltas = (
            self.goal_advance_delta_a_minus_b,
            self.emotional_attunement_delta_a_minus_b,
            self.specific_positive_support_delta_a_minus_b,
            self.clarity_naturalness_delta_a_minus_b,
        )
        if self.preferred_response == "TIE" and any(deltas):
            raise ValueError("TIE requires four zero deltas")
        return self


class QualityBatchSpan(engine.StrictModel):
    effect_group_id: str
    replicates: list[QualityItemSpan] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def unique(self):
        if len({row.replicate_id for row in self.replicates}) != 3:
            raise ValueError("quality replicate IDs must be unique")
        return self


class RiskEventSpan(engine.StrictModel):
    family: engine.RiskFamily
    severity: int = Field(ge=1, le=3)
    response_span_id: str
    evidence_span_id: str | None = None


class RiskItemSpan(engine.StrictModel):
    response_id: str
    assessment_status: engine.Literal["RESOLVED", "UNRESOLVED"]
    events: list[RiskEventSpan]


class RiskBatchSpan(engine.StrictModel):
    effect_group_id: str
    responses: list[RiskItemSpan] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def unique(self):
        if len({row.response_id for row in self.responses}) != 6:
            raise ValueError("risk response IDs must be unique")
        return self


class FunctionItemSpan(engine.StrictModel):
    replicate_id: str
    status: base.FunctionStatus
    candidate_evidence_ids: list[str] = Field(max_length=3)
    response_evidence_ids: list[str] = Field(max_length=3)
    required_response_act_realized: engine.Tri
    owner_time_and_boundary_respected: engine.Tri
    concise_reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def functional_has_evidence(self):
        if self.status == "FUNCTIONAL" and (not self.candidate_evidence_ids or not self.response_evidence_ids):
            raise ValueError("FUNCTIONAL requires candidate and response evidence IDs")
        return self


class FunctionBatchSpan(engine.StrictModel):
    effect_group_id: str
    replicates: list[FunctionItemSpan] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def unique(self):
        if len({row.replicate_id for row in self.replicates}) != 3:
            raise ValueError("function replicate IDs must be unique")
        return self


def quality_messages_span(item: dict, generated: dict[str, dict], *, reverse: bool, reviewer: str):
    pairs = []
    for index in range(1, 4):
        on = generated[f"r{index}_ON"]["final_reply"]
        off = generated[f"r{index}_OFF"]["final_reply"]
        response_a, response_b = (off, on) if reverse else (on, off)
        pairs.append({
            "replicate_id": f"r{index}",
            "response_A_spans": span_map(response_a, "A"),
            "response_B_spans": span_map(response_b, "B"),
        })
    system = f"""You are {reviewer}, an independent positive-support-contribution judge. Return only the strict schema. Judge only goal advance, emotional attunement, specific useful support, and clarity/naturalness. Do not subtract risk, function, memory use, applicability, or cost. Every delta must be one integer in [-2,-1,0,1,2] and means A minus B. TIE requires four zeros. For each response choose one to three supplied evidence IDs; never copy or invent text. UNRESOLVED is allowed."""
    payload = {
        "effect_group_id": item["effect_group_id"],
        "visible_dialogue": item["visible_dialogue"],
        "verified_past_panel_for_factual_reference_only": item["actual_rank1_candidate_text"],
        "blinded_pairs": pairs,
    }
    return [{"role": "system", "content": system}, {"role": "user", "content": engine.canonical_json(payload)}]


def risk_messages_span(item: dict, generated: dict[str, dict], reviewer: str):
    evidence = {}
    for turn_index, turn in enumerate(item["visible_dialogue"]):
        evidence[f"E{turn_index}"] = turn["content"]
    evidence["EC0"] = item["actual_rank1_candidate_text"]
    evidence["EC1"] = engine.canonical_json(item["actual_rank1_candidate"])
    cases = []
    response_maps = {}
    for index in range(1, 4):
        for arm in ("ON", "OFF"):
            response_id = f"r{index}_{arm}"
            reply = generated[response_id]["final_reply"]
            spans = span_map(reply, f"{response_id}_R")
            response_maps[response_id] = spans
            cases.append({
                "response_id": response_id,
                "response_spans": spans,
                "authorized_evidence_spans": evidence if arm == "ON" else {key: value for key, value in evidence.items() if not key.startswith("EC")},
            })
    system = f"""You are {reviewer}, an independent absolute interaction-and-grounding-risk judge. Audit each response separately. Record only literal events in the supplied families and severity 1, 2, or 3. Empty events means no event. response_span_id must be one supplied response ID. evidence_span_id must be one supplied authorized evidence ID or null. Do not copy text, compare arms, or score helpfulness, function, or cost. Use UNRESOLVED instead of guessing."""
    return ([{"role": "system", "content": system}, {"role": "user", "content": engine.canonical_json({"effect_group_id": item["effect_group_id"], "cases": cases})}], response_maps)


def function_messages_span(item: dict, generated: dict[str, dict], reviewer: str):
    candidate_spans = {
        "C0": item["actual_rank1_candidate_text"],
        "C1": engine.canonical_json(item["actual_rank1_candidate"]),
    }
    response_maps = {}
    responses = []
    for index in range(1, 4):
        replicate_id = f"r{index}"
        spans = span_map(generated[f"{replicate_id}_ON"]["final_reply"], f"{replicate_id}_R")
        response_maps[replicate_id] = spans
        responses.append({"replicate_id": replicate_id, "response_spans": spans})
    minimum = {
        "MP": "verified profile/preference/relationship fact materially personalizes or constrains the reply; name/topic echo is insufficient",
        "MS": "accurately bridges a specific past observation to the present while preserving past/uncertain status",
        "ME": "past action-result changes how a current option, warning, or suggestion is framed without promising recurrence",
        "RS": "the card's one atomic support move is realized without a competing extra move or boundary violation",
    }[item["component"]]
    system = f"""You are {reviewer}, an independent component-function judge. You see typed candidate and ON responses only. FUNCTIONAL requires at least one supplied candidate_evidence_id and response_evidence_id plus correct owner/time/boundary. SURFACE_ECHO_ONLY is topical wording without changed personalization/act; NOT_USED_FINAL has no contribution; BOUNDARY_FAILURE violates the candidate/current boundary; UNRESOLVED is allowed. Select IDs only and never copy text. Empty evidence lists are allowed only when status is not FUNCTIONAL. Component minimum: {minimum}. Do not score quality, risk, or cost."""
    payload = {
        "effect_group_id": item["effect_group_id"],
        "component": item["component"],
        "visible_dialogue": item["visible_dialogue"],
        "candidate_spans": candidate_spans,
        "on_responses": responses,
    }
    return ([{"role": "system", "content": system}, {"role": "user", "content": engine.canonical_json(payload)}], response_maps)


def validate_quality_span(parsed: QualityBatchSpan, item: dict, generated: dict[str, dict], *, reverse: bool):
    if parsed.effect_group_id != item["effect_group_id"]:
        raise ValueError("quality group identity")
    for row in parsed.replicates:
        index = int(row.replicate_id.removeprefix("r"))
        on = generated[f"r{index}_ON"]["final_reply"]
        off = generated[f"r{index}_OFF"]["final_reply"]
        response_a, response_b = (off, on) if reverse else (on, off)
        if not set(row.response_a_evidence_ids) <= set(span_map(response_a, "A")):
            raise ValueError("invalid response A evidence ID")
        if not set(row.response_b_evidence_ids) <= set(span_map(response_b, "B")):
            raise ValueError("invalid response B evidence ID")


def validate_risk_span(parsed: RiskBatchSpan, item: dict, response_maps: dict[str, dict[str, str]]):
    if parsed.effect_group_id != item["effect_group_id"] or {row.response_id for row in parsed.responses} != set(response_maps):
        raise ValueError("risk identities")
    dialogue_ids = {f"E{index}" for index, _turn in enumerate(item["visible_dialogue"])}
    for row in parsed.responses:
        allowed_evidence = dialogue_ids | ({"EC0", "EC1"} if row.response_id.endswith("_ON") else set())
        for event in row.events:
            if event.response_span_id not in response_maps[row.response_id]:
                raise ValueError("invalid risk response span ID")
            if event.evidence_span_id is not None and event.evidence_span_id not in allowed_evidence:
                raise ValueError("invalid risk evidence span ID")


def validate_function_span(parsed: FunctionBatchSpan, item: dict, response_maps: dict[str, dict[str, str]]):
    if parsed.effect_group_id != item["effect_group_id"] or {row.replicate_id for row in parsed.replicates} != set(response_maps):
        raise ValueError("function identities")
    for row in parsed.replicates:
        if not set(row.candidate_evidence_ids) <= {"C0", "C1"}:
            raise ValueError("invalid function candidate evidence ID")
        if not set(row.response_evidence_ids) <= set(response_maps[row.replicate_id]):
            raise ValueError("invalid function response evidence ID")


base.PROTOCOL = PROTOCOL
base.OUT = OUT
base.V1_OUT = SOURCE_OUT
engine.PROTOCOL = PROTOCOL
engine.OUT = OUT
engine.QualityBatch = QualityBatchSpan
engine.RiskBatch = RiskBatchSpan
engine.FunctionBatch = FunctionBatchSpan
engine.quality_messages = quality_messages_span
engine.risk_messages = risk_messages_span
engine.function_messages = function_messages_span
engine.validate_quality = validate_quality_span
engine.validate_risk = validate_risk_span
engine.validate_function = validate_function_span

for schema in (QualityBatchSpan, RiskBatchSpan, FunctionBatchSpan):
    schema.model_rebuild(_types_namespace={**vars(engine), **globals()})
    schema.model_json_schema()


if __name__ == "__main__":
    carried = base.seed_exact_valid_carry_forward()
    print(json.dumps({"protocol": PROTOCOL, "exact_valid_calls_carried_forward": carried, "evidence_submission": "pre_numbered_exact_span_ids"}, indent=2), flush=True)
    engine.main()
