#!/usr/bin/env python3
"""Validate and materialize the researcher-authorized v9 DEV evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


EXPECTED = {
    "session_results.jsonl": "11107e81c9acea4cc313d503915207952aa711776350448deebb5e94988013f7",
    "v9_matrix.jsonl": "149a5250f9f7f10ad75a654ae2f3b61d8231788fac83a41b9e21f9abd55f4d2d",
    "v9_summary.json": "7bcc0340bcc525fbede16e3321268b59581a07bb0f56172eec211b6723ef95a5",
    "budget_ledger.jsonl": "c540021606949e453857563599508eda8d9bb56f55eb096d02d9eb3120622bf1",
}
DESTINATIONS = {
    "session_results.jsonl": "paper1_semantic_memory_v9_dev_session_results_20260902_v1.jsonl",
    "v9_matrix.jsonl": "paper1_semantic_memory_v9_dev_matrix_20260902_v1.jsonl",
    "v9_summary.json": "paper1_semantic_memory_v9_dev_results_20260902_v1.json",
    "budget_ledger.jsonl": "paper1_semantic_memory_v9_dev_budget_ledger_20260902_v1.jsonl",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def validate(source: Path) -> None:
    for relative, expected in EXPECTED.items():
        if sha256(source / relative) != expected:
            raise RuntimeError(f"v9 DEV artifact hash drifted: {relative}")

    sessions = json_rows(source / "session_results.jsonl")
    matrix = json_rows(source / "v9_matrix.jsonl")
    budget = json_rows(source / "budget_ledger.jsonl")
    summary = json.loads((source / "v9_summary.json").read_text(encoding="utf-8"))

    if len(sessions) != 29 or not all(row.get("call_status") == "SUCCEEDED" for row in sessions):
        raise RuntimeError("v9 DEV is not exact 29/29 successful sessions")
    if len({(row["owner_id"], row["session_id"]) for row in sessions}) != 29:
        raise RuntimeError("v9 DEV session identities are not unique")
    if len(matrix) != 32 or len({row["memory_id"] for row in matrix}) != 32:
        raise RuntimeError("v9 DEV matrix is not exact 32 unique items")
    if any(row.get("outcome_calls") != 0 for row in sessions + matrix):
        raise RuntimeError("v9 DEV evidence violates zero-outcome boundary")
    reserved = [row for row in budget if row.get("event") == "RESERVED"]
    settled = [row for row in budget if row.get("event") == "SETTLED"]
    if len(budget) != 58 or len(reserved) != 29 or len(settled) != 29:
        raise RuntimeError("v9 DEV budget ledger is not exact 29 reserve/settle pairs")
    if not all(row.get("outcome") == "SUCCEEDED" for row in settled):
        raise RuntimeError("v9 DEV budget ledger contains a failed settlement")
    counts = summary.get("counts", {})
    expected_counts = {
        "items": 32,
        "source_sessions": 29,
        "provider_call_successes": 29,
        "provider_call_failures": 0,
        "known_fail_or_review_rejection": 10,
        "known_fail_or_review_total": 12,
        "old_pass_retention": 17,
        "old_pass_total": 20,
        "semantic_false_accept": 2,
        "semantic_false_reject": 3,
        "schema_reject": 0,
        "call_failure_items": 0,
    }
    if counts != expected_counts:
        raise RuntimeError("v9 DEV result counts drifted")
    if summary.get("cost", {}).get("accounted_usd") != "0.03079930":
        raise RuntimeError("v9 DEV accounted cost drifted")
    if summary.get("status") != "DEV_COMPLETE_STOP_FOR_RESEARCHER_REVIEW_401_NOT_AUTHORIZED":
        raise RuntimeError("v9 DEV stop status drifted")
    if summary.get("outcome_calls") != 0 or summary.get("full_401_started") is not False:
        raise RuntimeError("v9 DEV crossed its authorization boundary")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    validate(args.source)
    args.destination.mkdir(parents=True, exist_ok=True)
    for relative, destination_name in DESTINATIONS.items():
        destination = args.destination / destination_name
        if destination.exists():
            raise RuntimeError(f"refusing to overwrite evidence: {destination}")
        destination.write_bytes((args.source / relative).read_bytes())
    print(json.dumps({"status": "INGESTED", "files": list(DESTINATIONS.values())}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
