#!/usr/bin/env python3
"""B26: build the structural outer-fold packing decision surface.

Zero-outcome, Codex-B lane. Reads the already-materialized sanitized
runtime artifact for target identity (same as
``02_build_public_memory_census.py``) and, separately, raw
``data/external/evo_emo.json`` through the evaluator/split-only
``metacom_pm.paper1.data.es_memeval`` loader purely to build the same 477
``PREPACK_EXACT_EVIDENCE_COMPONENT`` components ``03_build_public_memory_
folds.py`` already builds (via ``metacom_pm.paper1.splits.
build_group_components`` -- no new grouping logic, the identical
deterministic construction). Enumerates
``metacom_pm.paper1.splits.enumerate_packing_surface`` over K=2..10 x
seed=0..31 (288 points by default) and writes every point's diagnostics:
per-fold target/QA/Summary/DG/component/owner counts, min/max/mean/
variance/imbalance-ratio, and three independently re-verified structural
invariants (exactly-once target assignment, component atomicity, no
missing/duplicate target).

This script never reads any outcome/gold/answer/observation field, never
selects a "best" K or seed, never declares a PASS/FAIL verdict, and never
writes a frozen outer-fold assignment manifest -- see
``metacom_pm.paper1.splits.outer_fold_decision_surface`` module docstring.
K/seed ranges are CLI-overridable so this surface can be re-run at a
different grid without editing the script.

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

from metacom_pm.paper1.data.es_memeval import load_users  # noqa: E402
from metacom_pm.paper1.data.es_memeval import parse_users as parse_evaluator_users  # noqa: E402
from metacom_pm.paper1.data.memory_source import (  # noqa: E402
    enumerate_targets,
    load_sanitized_runtime_users,
)
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config  # noqa: E402
from metacom_pm.paper1.splits import build_group_components, enumerate_packing_surface, summarize_packing_surface  # noqa: E402
from metacom_pm.paper1.splits.evidence import enumerate_split_evidence  # noqa: E402

OUT_DIR = PROJECT / "data" / "paper1_public_memory"
ARTIFACT_PATH = OUT_DIR / "es_memeval_public_sanitized_runtime_artifact_v1.json"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _relpath(path: Path) -> str:
    return path.resolve().relative_to(REPO).as_posix()


def build(k_values: tuple[int, ...], seed_values: tuple[int, ...]) -> dict[str, Any]:
    config = load_public_only_config(PROJECT / "configs" / "paper1_public_only.yaml")
    assert_pre_outcome_locked(config)

    if not ARTIFACT_PATH.exists():
        raise RuntimeError(
            f"{ARTIFACT_PATH} does not exist -- run "
            "05_materialize_sanitized_runtime_artifact.py first"
        )
    users = load_sanitized_runtime_users(ARTIFACT_PATH)
    targets = enumerate_targets(users)
    evaluator_users = parse_evaluator_users(load_users(PROJECT / "data" / "external" / "evo_emo.json"))
    evidence_records = enumerate_split_evidence(evaluator_users)
    components = build_group_components(targets, evidence_records)

    points = enumerate_packing_surface(components, k_values=k_values, seed_values=seed_values)
    summary = summarize_packing_surface(
        points, k_values=k_values, seed_values=seed_values, total_components=len(components)
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    points_path = OUT_DIR / "es_memeval_public_outer_fold_packing_surface_v1.jsonl"
    rendered_points = "".join(_canonical(p.to_manifest_row()) + "\n" for p in points)
    points_path.write_text(rendered_points, encoding="utf-8")

    summary_with_hash = dict(summary)
    summary_with_hash["surface_points_filename"] = points_path.name
    summary_with_hash["surface_points_sha256"] = _sha_text(rendered_points)
    summary_path = OUT_DIR / "es_memeval_public_outer_fold_packing_surface_summary_v1.json"
    summary_path.write_text(_canonical(summary_with_hash) + "\n", encoding="utf-8")

    return {
        "protocol": "pm-paper1-outer-fold-packing-surface-build-v1",
        "status": "OUTER_FOLD_PACKING_DECISION_SURFACE_BUILT_NOT_FROZEN",
        "outcome_calls": 0,
        "evidence_usage": (
            "READS_EVIDENCE_ONLY_TO_REBUILD_THE_SAME_477_GROUP_COMPONENTS_"
            "03_BUILD_PUBLIC_MEMORY_FOLDS_ALREADY_BUILDS_NO_NEW_GROUPING"
        ),
        "total_components": len(components),
        "k_values": list(k_values),
        "seed_values": list(seed_values),
        "surface_points_total": len(points),
        "all_points_pass_structural_integrity_checks": summary["all_points_pass_structural_integrity_checks"],
        "outputs": {
            "surface_points": {
                "path": _relpath(points_path),
                "rows": len(points),
                "sha256": summary_with_hash["surface_points_sha256"],
            },
            "surface_summary": {"path": _relpath(summary_path)},
        },
    }


def _parse_range(spec: str) -> tuple[int, ...]:
    """Parse 'start:stop' (inclusive) or a comma-separated list into a tuple of ints."""

    if ":" in spec:
        start_s, stop_s = spec.split(":", 1)
        return tuple(range(int(start_s), int(stop_s) + 1))
    return tuple(int(x) for x in spec.split(","))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--k-values",
        type=str,
        default="2:10",
        help="'start:stop' inclusive range or comma-separated list, e.g. '2:10' or '4,6,8'",
    )
    parser.add_argument(
        "--seed-values",
        type=str,
        default="0:31",
        help="'start:stop' inclusive range or comma-separated list, e.g. '0:31' or '0,1,2'",
    )
    args = parser.parse_args()
    k_values = _parse_range(args.k_values)
    seed_values = _parse_range(args.seed_values)
    report = build(k_values, seed_values)
    rendered = _canonical(report) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
