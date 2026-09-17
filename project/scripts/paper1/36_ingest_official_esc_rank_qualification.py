#!/usr/bin/env python3
"""Validate and materialize the 2026-09-02 ESC-RANK qualification evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


EXPECTED = {
    "esc_rank_resolved_manifest.json": "68a397c35c89bb9dfa1bba125e0f0f95c3c423e7333c3d9aacceca15fcd390ab",
    "esc_rank_runtime_qualification.json": "b6df325b78a3c5182805950e3d99069820f63189f264ee738fd5267f17907c4a",
    "official_24item/esc_rank_judge_rows.jsonl": "c067d5d9a74d0e1eef39369d5f8bab76522046d29a136dea93d957e70f5bd363",
    "official_24item/esc_rank_trace.json": "574be030f9424b1c837d173df56ef4cdeb562daccc041234dbeedf20acb381f0",
    "official_24item/esc_rank_human_agreement.json": "4b9185088f865111d72ebfceba3bfd3f282e3069d0c66f9e379c7d700089bb8f",
}
DESTINATIONS = {
    "esc_rank_resolved_manifest.json": "paper1_esc_rank_resolved_manifest_20260902_v1.json",
    "esc_rank_runtime_qualification.json": "paper1_esc_rank_runtime_qualification_20260902_v1.json",
    "official_24item/esc_rank_judge_rows.jsonl": "paper1_official_esc_rank_judge_rows_20260902_v1.jsonl",
    "official_24item/esc_rank_trace.json": "paper1_official_esc_rank_trace_20260902_v1.json",
    "official_24item/esc_rank_human_agreement.json": "paper1_official_esc_rank_human_agreement_20260902_v1.json",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(source: Path) -> None:
    for relative, expected in EXPECTED.items():
        path = source / relative
        if sha(path) != expected:
            raise RuntimeError(f"qualification artifact hash drifted: {relative}")
    runtime = read_json(source / "esc_rank_runtime_qualification.json")
    trace = read_json(source / "official_24item/esc_rank_trace.json")
    agreement = read_json(source / "official_24item/esc_rank_human_agreement.json")
    rows = [
        json.loads(line)
        for line in (source / "official_24item/esc_rank_judge_rows.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    if runtime.get("status") != "READY" or runtime.get("outcome_calls") != 0:
        raise RuntimeError("runtime qualification is not READY and zero-outcome")
    if runtime.get("counts", {}).get("official_valid_parses") != 42:
        raise RuntimeError("runtime qualification is not 42/42")
    if trace.get("status") != "READY" or trace.get("counts", {}).get("dimension_calls") != 168:
        raise RuntimeError("24-item official trace is not READY with 168 calls")
    if trace.get("outcome_calls") != 0 or trace.get("PM_training_calls") != 0:
        raise RuntimeError("trace violates the zero-outcome/training boundary")
    if len(rows) != 24 or not all(row.get("parse_valid") is True for row in rows):
        raise RuntimeError("official judge rows are not complete 24/24")
    if agreement.get("status") != (
        "OFFICIAL_ESC_RANK_QUALIFICATION_COMPLETE_SUPPLEMENTAL_CANDIDATES_PENDING"
    ):
        raise RuntimeError("human-agreement status drifted")
    if agreement.get("formal_outcome_calls") != 0:
        raise RuntimeError("agreement artifact violates the zero-outcome boundary")


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
