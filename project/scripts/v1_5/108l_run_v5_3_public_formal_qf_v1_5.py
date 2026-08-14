#!/usr/bin/env python3
"""Run or resume one frozen outer-fold shard of the 576-group formal Q/F panel."""

from __future__ import annotations

import argparse
from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
BASE_RUNNER_PATH = ROOT / "scripts/v1_5/100l_run_v5_3_public_learnability_canary_v1_5.py"
SPEC = importlib.util.spec_from_file_location("v53_qf_base_runner", BASE_RUNNER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load Q/F base runner")
BASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASE)

from metacom_pm.api import make_client  # noqa: E402
from metacom_pm.config import endpoint_from_config, load_config  # noqa: E402
from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402


PROTOCOL = "pm-v1.5-v5.3-public-formal-qf-v1"
MANIFEST_DIR = ROOT / "outputs/pm_v1_5_v5_3_public_formal_effect_manifest_20260809"
OUT = ROOT / "outputs/pm_v1_5_v5_3_public_formal_qf_20260809"
USD_CAP = 0.84


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _manifest_rows(fold: int) -> list[dict]:
    rows = _jsonl(MANIFEST_DIR / "effect_group_manifest_private.jsonl")
    return [row for row in rows if int(row["outer_fold"]) == fold]


def _result_path(fold: int) -> Path:
    return OUT / "shards" / f"fold_{fold}_results.jsonl"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fold", type=int, required=True, choices=range(1, 7))
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--accept-usd-cap", type=float)
    parser.add_argument("--limit-new-groups", type=int)
    args = parser.parse_args()

    review = json.loads((MANIFEST_DIR / "independent_review.json").read_text())
    contract = json.loads((MANIFEST_DIR / "contract.json").read_text())
    rows = _manifest_rows(args.fold)
    prior = _jsonl(_result_path(args.fold))
    done = {row["effect_group_id"] for row in prior}
    pending = [row for row in rows if row["effect_group_id"] not in done]
    if args.limit_new_groups is not None:
        pending = pending[:args.limit_new_groups]
    print({"fold": args.fold, "total": len(rows), "already_done": len(done), "pending_this_run": len(pending)})
    if len(rows) != 96:
        raise SystemExit("each frozen fold must contain exactly 96 groups")
    if not args.live:
        return
    if not review["live_execution_authorized"] or review["manifest_identity"] != contract["manifest_identity"]:
        raise SystemExit("matching independent live authorization is required")
    current_runner_hashes = {
        "formal_runner": sha256_file(Path(__file__)),
        "base_qf_runner": sha256_file(BASE_RUNNER_PATH),
        "qrf_schema": sha256_file(ROOT / "src/metacom_pm/v1_5_v5_3_qrf_judge.py"),
        "typed_response_program": sha256_file(ROOT / "src/metacom_pm/v1_5_v5_3_typed_response_program.py"),
        "transport_repair": sha256_file(ROOT / "scripts/v1_5/109l_repair_v5_3_public_formal_transport_failures_v1_5.py"),
    }
    if current_runner_hashes != review.get("runner_hashes"):
        raise SystemExit("runner/schema hashes changed after live authorization")
    if args.accept_usd_cap is None or args.accept_usd_cap < USD_CAP:
        raise SystemExit("formal execution requires --accept-usd-cap 0.84")

    config = load_config(ROOT / "configs/experiment.yaml")
    gen_client = make_client(endpoint_from_config(config, "generator"))
    judge_client = make_client(endpoint_from_config(config, "training_judge"))
    aliases = BASE._aliases(rows)
    results = list(prior)
    try:
        for index, row in enumerate(pending, start=1):
            print(f"[{index}/{len(pending)}] fold={args.fold} {row['component']} {row['state_id']}", flush=True)
            result = BASE.run_group(
                row, gen_client=gen_client, judge_client=judge_client,
                aliases=aliases.get(str(row.get("user_id")), ()), include_risk=False,
                result_protocol=PROTOCOL,
            )
            result["outer_fold"] = args.fold
            result["manifest_identity"] = contract["manifest_identity"]
            results.append(result)
            write_jsonl(_result_path(args.fold), results)
    finally:
        gen_client.close()
        judge_client.close()

    calls = [call for row in results for call in row["call_records"]]
    report = {
        "protocol": PROTOCOL,
        "status": "COMPLETE" if len(results) == 96 else "PARTIAL_RESUMABLE",
        "fold": args.fold,
        "manifest_identity": contract["manifest_identity"],
        "manifest_sha256": sha256_file(MANIFEST_DIR / "effect_group_manifest_private.jsonl"),
        "groups_completed": len(results),
        "component_counts": dict(Counter(row["component"] for row in results)),
        "quality_complete": sum(row.get("quality_effect") is not None for row in results),
        "function_complete": sum(row.get("functional") is not None for row in results),
        "api_calls_recorded": len(calls),
        "structured_output_failures": sum(not call["structured_output"] for call in calls),
        "generator_status_counts": dict(Counter(
            arm["status"] for row in results for rep in row["generated"]
            for arm in (rep["ON"], rep["OFF"])
        )),
        "automatic_risk_judge_calls": sum(call["role"] == "judge_risk" for call in calls),
        "accepted_usd_cap_full_panel": args.accept_usd_cap,
    }
    write_json(OUT / "shards" / f"fold_{args.fold}_report.json", report)
    print(report)


if __name__ == "__main__":
    main()
