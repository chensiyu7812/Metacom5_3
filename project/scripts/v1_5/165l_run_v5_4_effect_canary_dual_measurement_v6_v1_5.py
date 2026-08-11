#!/usr/bin/env python3
"""Complete one missing risk call with case-scoped exact evidence IDs."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
V5_SCRIPT = ROOT / "scripts/v1_5/164l_run_v5_4_effect_canary_dual_measurement_v5_v1_5.py"
SOURCE_OUT = ROOT / "outputs/pm_v1_5_v5_4_effect_canary_dual_measurement_v5_20260810"
OUT = ROOT / "outputs/pm_v1_5_v5_4_effect_canary_dual_measurement_v6_20260810"
PROTOCOL = "pm-v1.5-v5.4-effect-canary-dual-measurement-v6-case-scoped-span-ids"

spec = importlib.util.spec_from_file_location("v54_canary_measurement_v5", V5_SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load V5 measurement runner")
v5 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = v5
spec.loader.exec_module(v5)
engine = v5.engine


def risk_messages_case_scoped(item: dict, generated: dict[str, dict], reviewer: str):
    cases = []
    response_maps = {}
    for index in range(1, 4):
        for arm in ("ON", "OFF"):
            response_id = f"r{index}_{arm}"
            reply = generated[response_id]["final_reply"]
            response_spans = v5.v4.span_map(reply, f"{response_id}_R")
            evidence_spans = {
                f"{response_id}_E{turn_index}": turn["content"]
                for turn_index, turn in enumerate(item["visible_dialogue"])
            }
            if arm == "ON":
                evidence_spans[f"{response_id}_EC0"] = item["actual_rank1_candidate_text"]
                evidence_spans[f"{response_id}_EC1"] = engine.canonical_json(item["actual_rank1_candidate"])
            response_maps[response_id] = response_spans
            cases.append({
                "response_id": response_id,
                "response_spans": response_spans,
                "authorized_evidence_spans_for_this_case_only": evidence_spans,
            })
    system = f"""You are {reviewer}, an independent absolute interaction-and-grounding-risk judge. Audit each response separately. Record only literal events in the supplied families and severity 1, 2, or 3. Empty events means no event. response_span_id and evidence_span_id must begin with that same case's full response_id and must be selected only from that case. evidence_span_id may be null. Never reuse an ID from another case. Do not compare arms or score helpfulness, function, or cost. Use UNRESOLVED instead of guessing."""
    return ([{"role": "system", "content": system}, {"role": "user", "content": engine.canonical_json({"effect_group_id": item["effect_group_id"], "cases": cases})}], response_maps)


def validate_risk_case_scoped(parsed, item: dict, response_maps: dict[str, dict[str, str]]):
    if parsed.effect_group_id != item["effect_group_id"] or {row.response_id for row in parsed.responses} != set(response_maps):
        raise ValueError("risk identities")
    for row in parsed.responses:
        dialogue_ids = {f"{row.response_id}_E{index}" for index, _turn in enumerate(item["visible_dialogue"])}
        candidate_ids = {f"{row.response_id}_EC0", f"{row.response_id}_EC1"} if row.response_id.endswith("_ON") else set()
        for event in row.events:
            if event.response_span_id not in response_maps[row.response_id]:
                raise ValueError("invalid case-scoped risk response span ID")
            if event.evidence_span_id is not None and event.evidence_span_id not in dialogue_ids | candidate_ids:
                raise ValueError("invalid case-scoped risk evidence span ID")


v5.v4.base.PROTOCOL = PROTOCOL
v5.v4.base.OUT = OUT
v5.v4.base.V1_OUT = SOURCE_OUT
engine.PROTOCOL = PROTOCOL
engine.OUT = OUT
engine.risk_messages = risk_messages_case_scoped
engine.validate_risk = validate_risk_case_scoped


if __name__ == "__main__":
    carried = v5.v4.base.seed_exact_valid_carry_forward()
    print(json.dumps({"protocol": PROTOCOL, "exact_valid_calls_carried_forward": carried, "risk_evidence_submission": "case_scoped_exact_span_ids"}, indent=2), flush=True)
    engine.main()
