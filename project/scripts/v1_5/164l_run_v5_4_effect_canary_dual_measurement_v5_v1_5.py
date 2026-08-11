#!/usr/bin/env python3
"""Complete the canary after removing non-scientific span count limits."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

from pydantic import Field, model_validator


ROOT = Path(__file__).resolve().parents[2]
V4_SCRIPT = ROOT / "scripts/v1_5/163l_run_v5_4_effect_canary_dual_measurement_v4_v1_5.py"
SOURCE_OUT = ROOT / "outputs/pm_v1_5_v5_4_effect_canary_dual_measurement_v4_20260810"
OUT = ROOT / "outputs/pm_v1_5_v5_4_effect_canary_dual_measurement_v5_20260810"
PROTOCOL = "pm-v1.5-v5.4-effect-canary-dual-measurement-v5-span-ids"

spec = importlib.util.spec_from_file_location("v54_canary_measurement_v4", V4_SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load V4 measurement runner")
v4 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = v4
spec.loader.exec_module(v4)
engine = v4.engine


class QualityItemSpanV5(engine.StrictModel):
    replicate_id: str
    preferred_response: engine.Winner
    goal_advance_delta_a_minus_b: int = Field(ge=-2, le=2)
    emotional_attunement_delta_a_minus_b: int = Field(ge=-2, le=2)
    specific_positive_support_delta_a_minus_b: int = Field(ge=-2, le=2)
    clarity_naturalness_delta_a_minus_b: int = Field(ge=-2, le=2)
    response_a_evidence_ids: list[str] = Field(min_length=1)
    response_b_evidence_ids: list[str] = Field(min_length=1)
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


class QualityBatchSpanV5(engine.StrictModel):
    effect_group_id: str
    replicates: list[QualityItemSpanV5] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def unique(self):
        if len({row.replicate_id for row in self.replicates}) != 3:
            raise ValueError("quality replicate IDs must be unique")
        return self


class RiskEventSpanV5(engine.StrictModel):
    family: engine.RiskFamily
    severity: int = Field(ge=1, le=3)
    response_span_id: str
    evidence_span_id: str | None


class RiskItemSpanV5(engine.StrictModel):
    response_id: str
    assessment_status: engine.Literal["RESOLVED", "UNRESOLVED"]
    events: list[RiskEventSpanV5]


class RiskBatchSpanV5(engine.StrictModel):
    effect_group_id: str
    responses: list[RiskItemSpanV5] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def unique(self):
        if len({row.response_id for row in self.responses}) != 6:
            raise ValueError("risk response IDs must be unique")
        return self


class FunctionItemSpanV5(engine.StrictModel):
    replicate_id: str
    status: v4.base.FunctionStatus
    candidate_evidence_ids: list[str]
    response_evidence_ids: list[str]
    required_response_act_realized: engine.Tri
    owner_time_and_boundary_respected: engine.Tri
    concise_reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def functional_has_evidence(self):
        if self.status == "FUNCTIONAL" and (not self.candidate_evidence_ids or not self.response_evidence_ids):
            raise ValueError("FUNCTIONAL requires candidate and response evidence IDs")
        return self


class FunctionBatchSpanV5(engine.StrictModel):
    effect_group_id: str
    replicates: list[FunctionItemSpanV5] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def unique(self):
        if len({row.replicate_id for row in self.replicates}) != 3:
            raise ValueError("function replicate IDs must be unique")
        return self


v4.base.PROTOCOL = PROTOCOL
v4.base.OUT = OUT
v4.base.V1_OUT = SOURCE_OUT
engine.PROTOCOL = PROTOCOL
engine.OUT = OUT
engine.QualityBatch = QualityBatchSpanV5
engine.RiskBatch = RiskBatchSpanV5
engine.FunctionBatch = FunctionBatchSpanV5

for schema in (QualityBatchSpanV5, RiskBatchSpanV5, FunctionBatchSpanV5):
    schema.model_rebuild(_types_namespace={**vars(engine), **globals()})
    schema.model_json_schema()


if __name__ == "__main__":
    carried = v4.base.seed_exact_valid_carry_forward()
    print(json.dumps({"protocol": PROTOCOL, "exact_valid_calls_carried_forward": carried, "evidence_submission": "unbounded_pre_numbered_exact_span_ids"}, indent=2), flush=True)
    engine.main()
