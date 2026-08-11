#!/usr/bin/env python3
"""Run/resume all 96 frozen generator + Q/F development-pilot groups.

The automatic risk instrument is intentionally omitted after failing the
8-group canary.  Risk is not a component label and its omission cannot alter
the positive-support contribution target.
"""

from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
CANARY_SCRIPT = ROOT / "scripts/v1_5/100l_run_v5_3_public_learnability_canary_v1_5.py"
SPEC = importlib.util.spec_from_file_location("v53_canary_runner", CANARY_SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load canary runner")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)

from metacom_pm.api import make_client  # noqa: E402
from metacom_pm.config import endpoint_from_config, load_config  # noqa: E402
from metacom_pm.io import write_json, write_jsonl  # noqa: E402


PROTOCOL = "pm-v1.5-v5.3-public-qf-development-pilot-v1"
OUT = ROOT / "outputs/pm_v1_5_v5_3_public_qf_development_pilot_20260809"


def _existing():
    path = OUT / "qf_results.jsonl"
    if not path.exists():
        canary_path = RUNNER.OUT_DIR / "canary_results.jsonl"
        if not canary_path.exists():
            return []
        bootstrapped = []
        for row in [json.loads(line) for line in canary_path.read_text().splitlines() if line.strip()]:
            copied = dict(row)
            copied["protocol"] = PROTOCOL
            copied["risk"] = None
            copied["risk_instrument_status"] = "CANARY_UNQUALIFIED_NOT_USED"
            copied["call_records"] = [
                call for call in copied["call_records"] if call["role"] != "judge_risk"
            ]
            copied["bootstrapped_from_complete_predeclared_canary"] = True
            bootstrapped.append(copied)
        return bootstrapped
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--accept-usd-cap", type=float)
    parser.add_argument("--limit-new-groups", type=int)
    args = parser.parse_args()
    rows = RUNNER._rows()
    prior = _existing()
    done = {row["effect_group_id"] for row in prior}
    pending = [row for row in rows if row["effect_group_id"] not in done]
    if args.limit_new_groups is not None:
        pending = pending[: args.limit_new_groups]
    print({"total": len(rows), "already_done": len(done), "pending_this_run": len(pending)})
    if not args.live:
        return
    if args.accept_usd_cap is None or args.accept_usd_cap < 0.20:
        raise SystemExit("requires --accept-usd-cap 0.20")
    config = load_config(ROOT / "configs/experiment.yaml")
    gen_client = make_client(endpoint_from_config(config, "generator"))
    judge_client = make_client(endpoint_from_config(config, "training_judge"))
    aliases = RUNNER._aliases(rows)
    results = list(prior)
    try:
        for index, row in enumerate(pending, start=1):
            print(f"[{index}/{len(pending)}] {row['component']} {row['state_id']}", flush=True)
            result = RUNNER.run_group(
                row, gen_client=gen_client, judge_client=judge_client,
                aliases=aliases.get(str(row.get("user_id")), ()), include_risk=False,
            )
            result["protocol"] = PROTOCOL
            results.append(result)
            write_jsonl(OUT / "qf_results.jsonl", results)
    finally:
        gen_client.close()
        judge_client.close()
    all_calls = [call for row in results for call in row["call_records"]]
    report = {
        "protocol": PROTOCOL,
        "status": "COMPLETE" if len(results) == 96 else "PARTIAL_RESUMABLE",
        "groups_completed": len(results),
        "component_counts": dict(Counter(row["component"] for row in results)),
        "api_calls_recorded": len(all_calls),
        "structured_output_failures": sum(not call["structured_output"] for call in all_calls),
        "generator_status_counts": dict(Counter(
            arm["status"] for row in results for rep in row["generated"]
            for arm in (rep["ON"], rep["OFF"])
        )),
        "effect_sign_counts": {
            component: dict(Counter(
                "positive" if row["quality_effect"]["aggregate"]["mean_positive_support_contribution"] > 0
                else "negative" if row["quality_effect"]["aggregate"]["mean_positive_support_contribution"] < 0
                else "tie"
                for row in results if row["component"] == component
            ))
            for component in ("MP", "MS", "ME", "RS")
        },
        "risk_instrument": "AUTOMATIC_RISK_JUDGE_CANARY_FAILED_NOT_RUN_AND_NOT_IN_LABEL",
        "accepted_usd_cap": args.accept_usd_cap,
    }
    write_json(OUT / "report.json", report)
    print(report)


if __name__ == "__main__":
    main()
