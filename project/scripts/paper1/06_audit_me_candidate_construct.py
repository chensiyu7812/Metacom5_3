#!/usr/bin/env python3
"""B20: build the per-candidate ME construct audit deliverable.

Zero-outcome, Codex-B lane. Reads *only* the already-materialized sanitized
runtime artifact (same as ``02_build_public_memory_census.py``), never
``data/external/evo_emo.json`` directly. Run
``05_materialize_sanitized_runtime_artifact.py`` first. Writes
``es_memeval_public_me_candidate_audit_v1.json``: every surviving unique ME
candidate corpus-wide, fully disclosed -- action span, result span, linkage
rule, owner/session/turn. Diagnostic/audit only -- this script does not
modify ``metacom_pm.paper1.memory.me`` and does not change what the primary
compiler extracts; see ``metacom_pm.paper1.features.me_candidate_audit``
module docstring.

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

from metacom_pm.paper1.data.memory_source import load_sanitized_runtime_users  # noqa: E402
from metacom_pm.paper1.features import build_me_candidate_audit_report  # noqa: E402
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config  # noqa: E402

OUT_DIR = PROJECT / "data" / "paper1_public_memory"
ARTIFACT_PATH = OUT_DIR / "es_memeval_public_sanitized_runtime_artifact_v1.json"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
    audit = build_me_candidate_audit_report(users)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    audit_path = OUT_DIR / "es_memeval_public_me_candidate_audit_v1.json"
    rendered = _canonical(audit) + "\n"
    audit_path.write_text(rendered, encoding="utf-8")

    return {
        "protocol": "pm-paper1-me-candidate-audit-build-v1",
        "status": "ME_CONSTRUCT_PER_CANDIDATE_AUDIT_BUILT",
        "outcome_calls": 0,
        "surviving_unique_candidate_count": audit["surviving_unique_candidate_count"],
        "surviving_candidates_by_owner": audit["surviving_candidates_by_owner"],
        "outputs": {
            "me_candidate_audit": {
                "path": _relpath(audit_path),
                "sha256": _sha_text(rendered),
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
