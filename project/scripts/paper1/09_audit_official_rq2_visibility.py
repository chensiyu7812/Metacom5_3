#!/usr/bin/env python3
"""B28: build the official ES-MemEval RQ2 visibility / baseline-contract audit.

Zero-outcome, Codex-B lane. This script reads no local data at all (not
``evo_emo.json``, not the sanitized runtime artifact) -- it renders the
hardcoded, source-verified audit in
``metacom_pm.paper1.official_visibility_audit`` to disk. Writes:

- ``es_memeval_public_official_visibility_surface_rows_v1.jsonl``: one row
  per (task, arm, surface) -- 36 rows (3 tasks x 3 arms x 4 surfaces).
- ``es_memeval_public_official_visibility_audit_v1.json``: the full report,
  including the pinned commit/tag, every audited source file's blob sha,
  the Official RAG Top-4 contract, DG's round/utterance structure, and the
  evaluator-only field list.

This does not run generation, does not call a scorer, does not invoke
BGE-M3 or any embedding model, and does not select any M2-freeze
parameter. See ``metacom_pm.paper1.official_visibility_audit`` module
docstring.

Asserts the pre-outcome lock is engaged before doing anything.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]
REPO = PROJECT.parent
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.paper1.official_visibility_audit import (  # noqa: E402
    build_official_visibility_audit_report,
    build_task_arm_surface_rows,
    write_official_visibility_manifest,
)
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config  # noqa: E402

OUT_DIR = PROJECT / "data" / "paper1_public_memory"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _relpath(path: Path) -> str:
    return path.resolve().relative_to(REPO).as_posix()


def build() -> dict[str, Any]:
    config = load_public_only_config(PROJECT / "configs" / "paper1_public_only.yaml")
    assert_pre_outcome_locked(config)

    rows = build_task_arm_surface_rows()
    report = build_official_visibility_audit_report()
    paths = write_official_visibility_manifest(rows, report, OUT_DIR)

    return {
        "protocol": "pm-paper1-official-visibility-audit-build-v1",
        "status": "B28_OFFICIAL_VISIBILITY_AUDIT_BUILT",
        "outcome_calls": 0,
        "pinned_commit": report["pinned_source"]["commit"],
        "audited_source_file_count": report["audited_source_file_count"],
        "task_arm_surface_row_count": report["task_arm_surface_row_count"],
        "outputs": {
            "surface_rows_manifest": {
                "path": _relpath(paths["surface_rows_manifest"]),
                "rows": len(rows),
            },
            "report": {"path": _relpath(paths["report"])},
        },
    }


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
