#!/usr/bin/env python3
"""Assemble four web-model artifacts and run the authoritative V2 validator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import read_json, write_json  # noqa: E402
from metacom_pm.v1_5_v5_3_wave1_generation import assemble_user  # noqa: E402


ASSIGNMENTS = ROOT / "data/pm_v1_5_contracts/v5_3_wave1_sentinel_assignments_v1.json"
CONTRACT = ROOT / "data/pm_v1_5_contracts/v5_3_complete_training_data_generation_v2.json"
VALIDATOR = ROOT / "scripts/v1_5/82l_validate_formal_longitudinal_user_v1_5.py"
DEFAULT_OUT = ROOT / "outputs/pm_v1_5_v5_3_wave1_web_user_intake_v1"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--chunk", type=Path, action="append", required=True)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    if len(args.chunk) != 3:
        raise RuntimeError("exactly three --chunk files are required")
    rows = read_json(ASSIGNMENTS)["rows"]
    by_id = {row["user_id"]: row for row in rows}
    if args.user_id not in by_id:
        raise RuntimeError("user is not in frozen Wave-1 assignments")
    user = assemble_user(
        by_id[args.user_id], read_json(args.world), [read_json(path) for path in args.chunk]
    )
    user_dir = args.out_dir / args.user_id
    if user_dir.exists() and any(user_dir.iterdir()):
        raise RuntimeError("web intake output is not fresh")
    user_dir.mkdir(parents=True, exist_ok=True)
    raw_user = user_dir / f"{args.user_id}.json"
    write_json(raw_user, user)
    validation = user_dir / "validation"
    command = [
        sys.executable, str(VALIDATOR), "--input", str(raw_user),
        "--contract", str(CONTRACT), "--out-dir", str(validation),
    ]
    completed = subprocess.run(
        command, cwd=ROOT, text=True, capture_output=True, check=False,
        env={**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")},
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout)[-3000:])
    report = read_json(validation / "report.json")
    result = {
        "protocol": "pm-v1.5-v5.3-wave1-web-user-intake-result-v1",
        "user_id": args.user_id,
        "status": report["status"],
        "hard_issue_count": report["users"][0]["hard_issue_count"],
        "canonical_user": report["canonical_output_paths"][0],
        "report": str(validation / "report.json"),
        "api_calls": 0,
    }
    write_json(user_dir / "intake_result.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "MACHINE_PASS_BATCH_AND_SEMANTIC_REVIEW_PENDING":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
