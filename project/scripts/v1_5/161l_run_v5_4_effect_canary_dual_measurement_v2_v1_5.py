#!/usr/bin/env python3
"""Resume the frozen canary measurement with evidence-complete schemas only."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from typing import Literal

from pydantic import Field, model_validator


ROOT = Path(__file__).resolve().parents[2]
V1_SCRIPT = ROOT / "scripts/v1_5/160l_run_v5_4_effect_canary_dual_measurement_v1_5.py"
V1_OUT = ROOT / "outputs/pm_v1_5_v5_4_effect_canary_dual_measurement_20260810"
OUT = ROOT / "outputs/pm_v1_5_v5_4_effect_canary_dual_measurement_v2_20260810"
PROTOCOL = "pm-v1.5-v5.4-effect-canary-dual-measurement-v2"

spec = importlib.util.spec_from_file_location("v54_canary_measurement_v1", V1_SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load V1 measurement runner")
v1 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = v1
spec.loader.exec_module(v1)

FunctionStatus = Literal["FUNCTIONAL", "SURFACE_ECHO_ONLY", "NOT_USED_FINAL", "BOUNDARY_FAILURE", "UNRESOLVED"]


class FunctionItemV2(v1.StrictModel):
    replicate_id: str
    status: FunctionStatus
    candidate_contribution_excerpt: str = Field(min_length=1)
    response_excerpt: str = Field(min_length=1)
    required_response_act_realized: v1.Tri
    owner_time_and_boundary_respected: v1.Tri
    concise_reason: str = Field(min_length=1)


class FunctionBatchV2(v1.StrictModel):
    effect_group_id: str
    replicates: list[FunctionItemV2] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def unique(self):
        if len({row.replicate_id for row in self.replicates}) != 3:
            raise ValueError("function replicate IDs must be unique")
        return self


def function_messages_v2(item: dict, generated: dict[str, dict], reviewer: str):
    messages, response_map = v1_function_messages(item, generated, reviewer)
    messages[0]["content"] += " For every replicate, both excerpt fields are mandatory strings. If and only if the status is not FUNCTIONAL, use the exact sentinel NONE for an excerpt that does not exist. For FUNCTIONAL, NONE is forbidden and both excerpts must be short literal substrings. Check these fields before returning."
    return messages, response_map


def risk_messages_v2(item: dict, generated: dict[str, dict], reviewer: str):
    messages, response_map = v1_risk_messages(item, generated, reviewer)
    messages[0]["content"] += " evidence_excerpt must be an exact copied substring of the supplied visible dialogue or authorized candidate; otherwise return null. Never paraphrase evidence."
    return messages, response_map


def validate_function_v2(parsed: FunctionBatchV2, item: dict, response_map: dict[str, str]) -> None:
    if parsed.effect_group_id != item["effect_group_id"] or {row.replicate_id for row in parsed.replicates} != set(response_map):
        raise ValueError("function identities")
    candidate_evidence = item["actual_rank1_candidate_text"] + "\n" + v1.canonical_json(item["actual_rank1_candidate"])
    for row in parsed.replicates:
        if row.status == "FUNCTIONAL":
            if row.candidate_contribution_excerpt == "NONE" or row.response_excerpt == "NONE":
                raise ValueError("FUNCTIONAL cannot use NONE evidence")
            if row.candidate_contribution_excerpt not in candidate_evidence:
                raise ValueError("functional candidate excerpt is not literal")
            if row.response_excerpt not in response_map[row.replicate_id]:
                raise ValueError("functional response excerpt is not literal")
        else:
            if row.candidate_contribution_excerpt != "NONE" and row.candidate_contribution_excerpt not in candidate_evidence:
                raise ValueError("nonfunctional candidate excerpt is neither NONE nor literal")
            if row.response_excerpt != "NONE" and row.response_excerpt not in response_map[row.replicate_id]:
                raise ValueError("nonfunctional response excerpt is neither NONE nor literal")


def read_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def seed_exact_valid_carry_forward() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "measurement_results.jsonl"
    if target.exists():
        return len(read_rows(target))
    carried = []
    for row in read_rows(V1_OUT / "measurement_results.jsonl"):
        copied = dict(row)
        copied["source_protocol"] = copied["protocol"]
        copied["source_call_key"] = copied["call_key"]
        copied["protocol"] = PROTOCOL
        copied["call_key"] = v1.call_key(copied["reviewer_id"], copied["role"], copied["effect_group_id"])
        copied["carry_forward_reason"] = "The source result already passed its role's strict schema and literal validation; the new runner changes only missing or locally invalid calls."
        carried.append(copied)
    v1.write_jsonl(target, carried)
    v1.write_json(OUT / "carry_forward_report.json", {
        "protocol": PROTOCOL,
        "source": str((V1_OUT / "measurement_results.jsonl").relative_to(ROOT)),
        "carried_logical_calls": len(carried),
        "roles": sorted({row["role"] for row in carried}),
        "function_calls_carried": sum(row["role"] == "function" for row in carried),
        "judgment_content_changed": False,
    })
    return len(carried)


v1_function_messages = v1.function_messages
v1_risk_messages = v1.risk_messages
v1.PROTOCOL = PROTOCOL
v1.OUT = OUT
v1.FunctionItem = FunctionItemV2
v1.FunctionBatch = FunctionBatchV2
v1.function_messages = function_messages_v2
v1.risk_messages = risk_messages_v2
v1.validate_function = validate_function_v2
for schema in (v1.QualityBatch, v1.RiskBatch, FunctionBatchV2):
    schema.model_rebuild(_types_namespace=vars(v1))
    schema.model_json_schema()


if __name__ == "__main__":
    carried = seed_exact_valid_carry_forward()
    print(json.dumps({"protocol": PROTOCOL, "exact_valid_calls_carried_forward": carried}, indent=2), flush=True)
    v1.main()
