#!/usr/bin/env python3
"""Build the public-only zero-outcome memory target enumeration and census.

Zero-outcome, Codex-B (public data / memory / RQ2) lane. B18: reads *only*
the already-materialized sanitized runtime artifact
(``es_memeval_public_sanitized_runtime_artifact_v1.json``, written by
``05_materialize_sanitized_runtime_artifact.py``) via ``metacom_pm.paper1.
data.memory_source.load_sanitized_runtime_users`` -- never
``data/external/evo_emo.json`` directly, and never ``metacom_pm.paper1.data.
es_memeval`` or ``metacom_pm.paper1.data.materializer``. Run
``05_materialize_sanitized_runtime_artifact.py`` first.

Writes:

- ``es_memeval_public_targets_v1.jsonl``: every QA/Summary/DG target, its
  (B17: always-full-history) cutoff rank, whether it has a runtime-visible
  query, and its identity-anomaly flag (no gold text).
- ``es_memeval_public_candidate_eligible_pool_v1.jsonl`` / ``..._summary_v1
  .json`` (B19.5 layer 1): the target-invariant MP/MS/ME pool per owner.
- ``es_memeval_public_candidate_census_v1.jsonl`` / ``..._summary_v1.json``
  (B19.5 layer 2): per-target scoring against ``visible_query_text`` (no
  PASS/FAIL judgment, no final-bundle/top-k selection).

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
REPO = PROJECT.parent
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.paper1.data.memory_source import (  # noqa: E402
    enumerate_targets,
    load_sanitized_runtime_users,
)
from metacom_pm.paper1.features import (  # noqa: E402
    build_census,
    build_eligible_pool,
    summarize_census,
    summarize_eligible_pool,
    write_census_manifest,
    write_eligible_pool_manifest,
)
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config  # noqa: E402

OUT_DIR = PROJECT / "data" / "paper1_public_memory"
ARTIFACT_PATH = OUT_DIR / "es_memeval_public_sanitized_runtime_artifact_v1.json"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _relpath(path: Path) -> str:
    """Repo-relative POSIX path -- B10: never an absolute or worktree-specific path."""

    return path.resolve().relative_to(REPO).as_posix()


def _write_jsonl(rows: list[dict[str, Any]], path: Path) -> str:
    rendered = "".join(_canonical(row) + "\n" for row in rows)
    path.write_text(rendered, encoding="utf-8")
    return _sha_text(rendered)


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

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    target_rows = [
        {
            "protocol": "pm-paper1-public-memory-target-v2",
            "target_id": t.target_id,
            "task_type": t.task_type.value,
            "owner_id": t.owner_id,
            "primary_group_key": t.primary_group_key,
            "cutoff_rank": t.cutoff_rank,
            "has_visible_query": t.visible_query_text is not None,
            "identity_anomaly": t.identity_anomaly,
        }
        for t in targets
    ]
    targets_path = OUT_DIR / "es_memeval_public_targets_v1.jsonl"
    targets_sha256 = _write_jsonl(target_rows, targets_path)

    pool_rows = build_eligible_pool(users)
    pool_summary = summarize_eligible_pool(pool_rows)
    pool_paths = write_eligible_pool_manifest(pool_rows, pool_summary, OUT_DIR)

    census_rows = build_census(users, targets)
    census_summary = summarize_census(census_rows)
    census_paths = write_census_manifest(census_rows, census_summary, OUT_DIR)

    report = {
        "protocol": "pm-paper1-public-memory-census-build-v2",
        "status": "ZERO_OUTCOME_TARGETS_ELIGIBLE_POOL_AND_CENSUS_BUILT",
        "outcome_calls": 0,
        "evidence_usage": "NONE_THIS_SCRIPT_NEVER_READS_QA_SUMMARY_EVIDENCE_SEE_03_BUILD_PUBLIC_MEMORY_FOLDS",
        "runtime_visibility_basis": (
            "B17: cutoff_rank is always the owner's full session count and "
            "visible_query_text is the actual officially-asked QA/Summary "
            "question, verified directly against the pinned official "
            "ES-MemEval evaluation harness source (commit "
            "692624208acc077b8867698c1d6fcd998dee641a) -- see "
            "metacom_pm.paper1.data.memory_source module docstring."
        ),
        "sanitized_artifact_source": {
            "path": _relpath(ARTIFACT_PATH),
            "sha256": _sha_text(ARTIFACT_PATH.read_text(encoding="utf-8")),
        },
        "outputs": {
            "targets": {
                "path": _relpath(targets_path),
                "rows": len(target_rows),
                "sha256": targets_sha256,
            },
            "eligible_pool_manifest": {
                "path": _relpath(pool_paths["manifest"]),
                "rows": len(pool_rows),
            },
            "eligible_pool_summary": {"path": _relpath(pool_paths["summary"])},
            "candidate_census_manifest": {
                "path": _relpath(census_paths["manifest"]),
                "rows": len(census_rows),
            },
            "candidate_census_summary": {"path": _relpath(census_paths["summary"])},
        },
        "eligible_pool_summary": pool_summary,
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
