#!/usr/bin/env python3
"""Repair only missing F diagnostics in the completed Q/F development pilot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.api import make_client  # noqa: E402
from metacom_pm.config import endpoint_from_config, load_config  # noqa: E402
from metacom_pm.io import stable_hex, write_jsonl  # noqa: E402
from metacom_pm.v1_5_v5_3_qrf_judge import (  # noqa: E402
    BatchedFunctionalUseJudgment,
    functional_use_messages,
    validate_response_excerpts,
)


RESULTS = ROOT / "outputs/pm_v1_5_v5_3_public_qf_development_pilot_20260809/qf_results.jsonl"
MANIFEST = ROOT / "outputs/pm_v1_5_v5_3_public_learnability_pilot_20260809/effect_group_manifest_private.jsonl"


def _rows(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--accept-usd-cap", type=float)
    args = parser.parse_args()
    rows = _rows(RESULTS)
    manifest = {row["effect_group_id"]: row for row in _rows(MANIFEST)}
    missing = [row for row in rows if row.get("functional") is None]
    print({"missing_functional": len(missing)})
    if not args.live:
        return
    if args.accept_usd_cap is None or args.accept_usd_cap < 0.01:
        raise SystemExit("requires --accept-usd-cap 0.01")
    config = load_config(ROOT / "configs/experiment.yaml")
    client = make_client(endpoint_from_config(config, "training_judge"))
    try:
        for result in missing:
            source = manifest[result["effect_group_id"]]
            responses = [
                {"replicate_id": rep["replicate_id"], "response": rep["ON"]["reply"]}
                for rep in result["generated"]
            ]
            response_map = {row["replicate_id"]: row["response"] for row in responses}
            seed = int(stable_hex("FUNCTION_REPAIR", result["effect_group_id"], n=8), 16) & 0x7FFFFFFF
            call, parsed = client.chat(
                functional_use_messages(
                    visible_dialogue=source["visible_dialogue"],
                    candidate=source["candidate"], on_responses=responses,
                ),
                temperature=0.0, max_tokens=2500, seed=seed + 1,
                response_schema=BatchedFunctionalUseJudgment, retries=2,
            )
            if parsed is None:
                raise RuntimeError("functional repair returned no structured output")
            validate_response_excerpts(parsed, response_map)
            result["functional"] = parsed.model_dump(mode="json")
            result["functional_repair"] = {
                "request_hash": call.request_hash,
                "usage": call.usage,
                "reason": "initial_structured_provider_failure_only",
            }
    finally:
        client.close()
    write_jsonl(RESULTS, rows)
    print({"remaining_missing": sum(row.get('functional') is None for row in rows)})


if __name__ == "__main__":
    main()
