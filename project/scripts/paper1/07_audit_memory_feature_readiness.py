#!/usr/bin/env python3
"""Build the formal Phase-1 semantic-memory feature-readiness audit.

Zero-outcome, Codex-B lane. Reads *only* the already-materialized sanitized
runtime artifact and a completed v6 semantic-compiler result artifact, never
``data/external/evo_emo.json`` directly. Run
``05_materialize_sanitized_runtime_artifact.py`` first. Writes, per
(head, task): unique candidates, owners with candidates, target coverage,
target-candidate edges (explicitly not a distinct-memory count), and
missingness/variance/zero-variance readiness for every outcome-blind
diagnostic axis already computable in the census (candidate count, token
length, relative age, lexical overlap, the lexical-Jaccard already-visible
*proxy* -- B25: not the authoritative already-visible construct, see module
docstring -- retrieval rank). Embedding similarity is reported
NOT_IMPLEMENTED; DG's query-dependent axes are reported N/A (no static
current-dialogue state pre-generation). Also writes the full B25.5 feature
inventory (every blueprint-named MP/MS/ME/shared feature, honestly marked
IMPLEMENTED/IMPLEMENTED_AS_DIAGNOSTIC_PROXY/NOT_IMPLEMENTED/NOT_IMPLEMENTED_
PENDING_MECHANICAL_DEFINITION) inside the summary report.

Zero-outcome only -- this script never widens the MP/ME definitions,
never selects n_outer_folds/seed/top-k/token-cap, never declares a per-head
PASS/FAIL verdict, and never sets a minimum-N gate; see
``metacom_pm.paper1.features.feature_readiness_audit`` module docstring.

Asserts the pre-outcome lock is engaged before doing anything.
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
    build_semantic_feature_readiness_rows,
    summarize_semantic_feature_readiness,
    write_feature_readiness_manifest,
)
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config  # noqa: E402
from metacom_pm.paper1.semantic_memory.artifact import load_accepted_semantic_units  # noqa: E402

OUT_DIR = PROJECT / "data" / "paper1_public_memory"
ARTIFACT_PATH = OUT_DIR / "es_memeval_public_sanitized_runtime_artifact_v1.json"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _relpath(path: Path) -> str:
    return path.resolve().relative_to(REPO).as_posix()


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build(semantic_results_path: Path) -> dict[str, Any]:
    config = load_public_only_config(PROJECT / "configs" / "paper1_public_only.yaml")
    assert_pre_outcome_locked(config)

    if not ARTIFACT_PATH.exists():
        raise RuntimeError(
            f"{ARTIFACT_PATH} does not exist -- run "
            "05_materialize_sanitized_runtime_artifact.py first"
        )
    users = load_sanitized_runtime_users(ARTIFACT_PATH)
    targets = enumerate_targets(users)
    accepted_units = load_accepted_semantic_units(semantic_results_path, users=users)

    rows = build_semantic_feature_readiness_rows(users, targets, accepted_units)
    semantic_results_sha256 = _sha_text(
        semantic_results_path.read_text(encoding="utf-8")
    )
    summary = summarize_semantic_feature_readiness(
        rows,
        users=users,
        accepted_units=accepted_units,
        artifact_name=semantic_results_path.name,
        artifact_sha256=semantic_results_sha256,
    )
    paths = write_feature_readiness_manifest(rows, summary, OUT_DIR)

    return {
        "protocol": "pm-paper1-semantic-memory-feature-readiness-audit-build-v2",
        "status": "PHASE1_FEATURE_READINESS_AUDIT_BUILT",
        "outcome_calls": 0,
        "semantic_compiler_source": {
            "artifact_name": semantic_results_path.name,
            "sha256": semantic_results_sha256,
            "accepted_units": len(accepted_units),
        },
        "zero_variance_axes": summary["zero_variance_axes"],
        "lexical_candidate_query_jaccard_ge_0_6_proxy_zero_variance_head_tasks": summary[
            "lexical_candidate_query_jaccard_ge_0_6_proxy_zero_variance_head_tasks"
        ],
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
    parser.add_argument("--semantic-compiler-results", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = build(args.semantic_compiler_results)
    rendered = _canonical(report) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
