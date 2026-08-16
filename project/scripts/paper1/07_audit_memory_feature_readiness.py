#!/usr/bin/env python3
"""B24: build the Phase-1 memory feature-readiness / identifiability audit.

Zero-outcome, Codex-B lane. Reads *only* the already-materialized sanitized
runtime artifact (same as ``02_build_public_memory_census.py``), never
``data/external/evo_emo.json`` directly. Run
``05_materialize_sanitized_runtime_artifact.py`` first. Writes, per
(head, task): unique candidates, owners with candidates, target coverage,
target-candidate edges (explicitly not a distinct-memory count), and
missingness/variance/zero-variance readiness for every outcome-blind
feature axis already computable in the census (candidate count, token
length, relative age, lexical overlap, already-visible, retrieval rank).
Embedding similarity is reported NOT_IMPLEMENTED; DG's query-dependent axes
are reported N/A (no static current-dialogue state pre-generation).

Diagnostic only -- this script never widens the primary MP/ME compilers,
never selects n_outer_folds/seed/top-k/token-cap, never declares a per-head
PASS/FAIL verdict, and never sets a minimum-N gate; see
``metacom_pm.paper1.features.feature_readiness_audit`` module docstring.

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

from metacom_pm.paper1.data.memory_source import (  # noqa: E402
    enumerate_targets,
    load_sanitized_runtime_users,
)
from metacom_pm.paper1.features import (  # noqa: E402
    build_feature_readiness_rows,
    summarize_feature_readiness,
    write_feature_readiness_manifest,
)
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config  # noqa: E402

OUT_DIR = PROJECT / "data" / "paper1_public_memory"
ARTIFACT_PATH = OUT_DIR / "es_memeval_public_sanitized_runtime_artifact_v1.json"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _relpath(path: Path) -> str:
    return path.resolve().relative_to(REPO).as_posix()


def build() -> dict[str, Any]:
    config = load_public_only_config(PROJECT / "configs" / "paper1_public_only.yaml")
    assert_pre_outcome_locked(config)

    if not ARTIFACT_PATH.exists():
        raise RuntimeError(
            f"{ARTIFACT_PATH} does not exist -- run "
            "05_materialize_sanitized_runtime_artifact.py first"
        )
    users = load_sanitized_runtime_users(ARTIFACT_PATH)
    targets = enumerate_targets(users)

    rows = build_feature_readiness_rows(users, targets)
    summary = summarize_feature_readiness(rows)
    paths = write_feature_readiness_manifest(rows, summary, OUT_DIR)

    return {
        "protocol": "pm-paper1-memory-feature-readiness-audit-build-v1",
        "status": "PHASE1_FEATURE_READINESS_AUDIT_BUILT",
        "outcome_calls": 0,
        "zero_variance_axes": summary["zero_variance_axes"],
        "already_visible_zero_variance_head_tasks": summary["already_visible_zero_variance_head_tasks"],
        "outputs": {
            "rows_manifest": {
                "path": _relpath(paths["rows_manifest"]),
                "rows": len(rows),
            },
            "summary": {"path": _relpath(paths["summary"])},
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
