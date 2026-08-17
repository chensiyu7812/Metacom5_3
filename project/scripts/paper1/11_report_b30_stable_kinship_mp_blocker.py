#!/usr/bin/env python3
"""B30-FINAL Part A: stable-kinship MP recovery -- blocker report.

Zero-outcome, Codex-B lane, diagnostic only. Locates the researcher-approved
exact stable-kinship extraction rule required before any new stable-kinship
MP candidate can be added (see AGENTS.md and this task's brief). No such
rule exists in tracked GitHub authority -- B21 (``mp_extraction_audit``) and
B29 (``candidate_definition_decision_surface``) both already established
that no mechanical, precision-first rule separates a stable relationship-
existence fact from situational relationship narration without semantic
judgment. This script re-derives both findings fresh from the live corpus
and compiler (never hand-copies stale numbers) and writes a formal
``IMPLEMENTATION BLOCKER -- RESEARCHER DECISION REQUIRED`` report.

This script never modifies ``memory/mp.py``, never adds a stable-kinship MP
candidate, never expands the primary MP candidate pool (3 unique / 3
owners, recomputed here for contrast, not hardcoded), and never reads any
gold/answer/observation/reference-summary field.

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
from metacom_pm.paper1.features.b30_stable_kinship_mp_blocker import (  # noqa: E402
    build_stable_kinship_mp_blocker_report,
    write_stable_kinship_mp_blocker_manifest,
)
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config  # noqa: E402

OUT_DIR = PROJECT / "data" / "paper1_public_memory"
ARTIFACT_PATH = OUT_DIR / "es_memeval_public_sanitized_runtime_artifact_v1.json"
EVO_PATH = PROJECT / "data" / "external" / "evo_emo.json"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _relpath(path: Path) -> str:
    return path.resolve().relative_to(REPO).as_posix()


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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

    blocker_report = build_stable_kinship_mp_blocker_report(users, targets, EVO_PATH)
    blocker_path = write_stable_kinship_mp_blocker_manifest(blocker_report, OUT_DIR)

    return {
        "protocol": "pm-paper1-b30-stable-kinship-mp-blocker-build-v1",
        "status": "IMPLEMENTATION_BLOCKER_RESEARCHER_DECISION_REQUIRED",
        "outcome_calls": 0,
        "primary_mp_unique_hit_count": blocker_report["primary_mp_unchanged"]["unique_hit_count"],
        "blocker_id": blocker_report["blocker_id"],
        "outputs": {
            "stable_kinship_mp_blocker": {
                "path": _relpath(blocker_path),
                "sha256": _sha_text(blocker_path.read_text(encoding="utf-8")),
            }
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
