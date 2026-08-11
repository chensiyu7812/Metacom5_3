#!/usr/bin/env python3
"""Rejudge frozen canary responses with the corrected absolute-risk v2 rubric."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.api import make_client  # noqa: E402
from metacom_pm.config import endpoint_from_config, load_config  # noqa: E402
from metacom_pm.io import stable_hex, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_v5_3_qrf_judge import (  # noqa: E402
    BatchedAbsoluteRiskJudgment,
    RISK_PROTOCOL,
    risk_messages,
    validate_response_excerpts,
)


CANARY = ROOT / "outputs/pm_v1_5_v5_3_public_learnability_canary_20260809"
PILOT = ROOT / "outputs/pm_v1_5_v5_3_public_learnability_pilot_20260809"
OUT = CANARY / "risk_v2"


def _jsonl(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--accept-usd-cap", type=float)
    args = parser.parse_args()
    results = _jsonl(CANARY / "canary_results.jsonl")
    manifest = {
        row["effect_group_id"]: row
        for row in _jsonl(PILOT / "effect_group_manifest_private.jsonl")
    }
    if not args.live:
        print({"groups": len(results), "api_calls": 0, "protocol": RISK_PROTOCOL})
        return
    if args.accept_usd_cap is None or args.accept_usd_cap < 0.01:
        raise SystemExit("requires --accept-usd-cap 0.01")
    config = load_config(ROOT / "configs/experiment.yaml")
    client = make_client(endpoint_from_config(config, "training_judge"))
    outputs = []
    try:
        for result in results:
            row = manifest[result["effect_group_id"]]
            cases = []
            response_map = {}
            arm_map = {}
            for replicate in result["generated"]:
                for arm in ("ON", "OFF"):
                    response_id = "resp_" + stable_hex(
                        row["effect_group_id"], replicate["replicate_id"], arm, n=12
                    )
                    reply = replicate[arm]["reply"]
                    response_map[response_id] = reply
                    arm_map[response_id] = {"replicate_id": replicate["replicate_id"], "arm": arm}
                    cases.append(
                        {
                            "response_id": response_id,
                            "visible_dialogue": row["visible_dialogue"],
                            "authorized_candidate": row["candidate"] if arm == "ON" else None,
                            "response": reply,
                        }
                    )
            cases.sort(key=lambda case: case["response_id"])
            seed = int(stable_hex(RISK_PROTOCOL, row["effect_group_id"], n=8), 16) & 0x7FFFFFFF
            call, parsed = client.chat(
                risk_messages(cases=cases), temperature=0.0, max_tokens=3000,
                seed=seed, response_schema=BatchedAbsoluteRiskJudgment, retries=2,
            )
            if parsed is None:
                raise RuntimeError(f"no structured risk output for {row['effect_group_id']}")
            validate_response_excerpts(parsed, response_map)
            outputs.append(
                {
                    "protocol": RISK_PROTOCOL,
                    "effect_group_id": row["effect_group_id"],
                    "component": row["component"],
                    "candidate_type": row["candidate_type"],
                    "arm_map_private": arm_map,
                    "judgment": parsed.model_dump(mode="json"),
                    "usage": call.usage,
                    "request_hash": call.request_hash,
                }
            )
            write_jsonl(OUT / "risk_v2_results.jsonl", outputs)
    finally:
        client.close()
    prompt_tokens = sum(row["usage"].get("gemini_prompt_tokens", 0) for row in outputs)
    output_tokens = sum(row["usage"].get("gemini_candidate_tokens", 0) for row in outputs)
    report = {
        "protocol": RISK_PROTOCOL,
        "status": "REJUDGED_HUMAN_CALIBRATION_PENDING",
        "groups": len(outputs),
        "api_calls": len(outputs),
        "event_counts": {
            family: sum(
                event["family"] == family
                for row in outputs for response in row["judgment"]["responses"]
                for event in response["events"]
            )
            for family in (
                "R1_explicit_boundary_violation",
                "R2_unsupported_or_wrong_owner_personal_grounding",
                "R3_excessive_directiveness_or_burden",
                "SYSTEM_resource_or_scaffold_exposure",
            )
        },
        "gemini_prompt_tokens": prompt_tokens,
        "gemini_candidate_tokens": output_tokens,
        "estimated_usd": prompt_tokens / 1_000_000 * 0.10 + output_tokens / 1_000_000 * 0.40,
    }
    write_json(OUT / "report.json", report)
    print(report)


if __name__ == "__main__":
    main()
