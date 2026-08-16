#!/usr/bin/env python3
"""Build the public-only zero-outcome memory target enumeration and census.

Zero-outcome, Codex-B (public data / memory / RQ2) lane. Reads only
``data/external/evo_emo.json`` (ES-MemEval-Public-v1.0.0-1427) through
``metacom_pm.paper1.data.es_memeval``, compiles MP/MS/ME candidates via
``metacom_pm.paper1.candidates``, and writes:

- ``es_memeval_public_targets_v1.jsonl``: every QA/Summary/DG target, its
  strict-past cutoff rank, and its identity-anomaly flag (no gold text).
- ``es_memeval_public_candidate_census_v1.jsonl`` /
  ``..._summary_v1.json``: the zero-outcome coverage/count/length/age/
  already-visible/retrieval-rank/variance census (no PASS/FAIL judgment).

Fold construction (exact-evidence primary grouping and the shared-session
sensitivity slice) is a separate script,
``03_build_public_memory_folds.py``, since it is a distinct deliverable.

Asserts the pre-outcome lock is engaged before doing anything, and never
imports or calls anything that would open a formal ON/OFF effect outcome.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.paper1.data.es_memeval import (  # noqa: E402
    enumerate_targets,
    load_users,
    parse_users,
    validate_es_memeval_identity,
)
from metacom_pm.paper1.features import build_census, summarize_census, write_census_manifest  # noqa: E402
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config  # noqa: E402

OUT_DIR = PROJECT / "data" / "paper1_public_memory"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_jsonl(rows: list[dict[str, Any]], path: Path) -> str:
    rendered = "".join(_canonical(row) + "\n" for row in rows)
    path.write_text(rendered, encoding="utf-8")
    return _sha_text(rendered)


def build() -> dict[str, Any]:
    config = load_public_only_config(PROJECT / "configs" / "paper1_public_only.yaml")
    assert_pre_outcome_locked(config)

    identity = validate_es_memeval_identity(PROJECT)

    users = parse_users(load_users(PROJECT / "data" / "external" / "evo_emo.json"))
    targets = enumerate_targets(users)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    target_rows = [
        {
            "protocol": "pm-paper1-public-memory-target-v1",
            "target_id": t.target_id,
            "task_type": t.task_type.value,
            "owner_id": t.owner_id,
            "primary_group_key": t.primary_group_key,
            "cutoff_rank": t.cutoff_rank,
            "context_session_ids": list(t.context_session_ids),
            "identity_anomaly": t.identity_anomaly,
        }
        for t in targets
    ]
    targets_path = OUT_DIR / "es_memeval_public_targets_v1.jsonl"
    targets_sha256 = _write_jsonl(target_rows, targets_path)

    census_rows = build_census(users, targets)
    census_summary = summarize_census(census_rows)
    census_paths = write_census_manifest(census_rows, census_summary, OUT_DIR)

    report = {
        "protocol": "pm-paper1-public-memory-census-build-v1",
        "status": "ZERO_OUTCOME_TARGETS_AND_CENSUS_BUILT",
        "outcome_calls": 0,
        "es_memeval_identity": identity,
        "outputs": {
            "targets": {"path": str(targets_path), "rows": len(target_rows), "sha256": targets_sha256},
            "candidate_census_manifest": {
                "path": str(census_paths["manifest"]),
                "rows": len(census_rows),
            },
            "candidate_census_summary": {"path": str(census_paths["summary"])},
        },
        "census_summary": census_summary,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = build()
    rendered = _canonical(report) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
