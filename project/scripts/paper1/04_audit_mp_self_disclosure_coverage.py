#!/usr/bin/env python3
"""B16: build the transparent MP self-disclosure extraction audit.

Zero-outcome, Codex-B lane. Reads the same public
``data/external/evo_emo.json`` (via the sanitized loader, same as
``02_build_public_memory_census.py``) and writes
``es_memeval_public_mp_extraction_audit_v1.json``: the primary compiler's
exact current hits (span/source ids) plus per-category coverage counts and
examples for plausibly-missed seeker self-disclosure (occupation, family
relationship, residence, study, diagnosis, durable trait). Diagnostic only
-- this script does not modify ``metacom_pm.paper1.memory.mp`` and does not
widen the primary compiler's coverage; see
``metacom_pm.paper1.features.mp_extraction_audit`` module docstring.

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
from metacom_pm.paper1.data.memory_source import parse_memory_source_users  # noqa: E402
from metacom_pm.paper1.features import build_mp_extraction_audit_report  # noqa: E402
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config  # noqa: E402

OUT_DIR = PROJECT / "data" / "paper1_public_memory"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _relpath(path: Path) -> str:
    return path.resolve().relative_to(REPO).as_posix()


def build() -> dict[str, Any]:
    config = load_public_only_config(PROJECT / "configs" / "paper1_public_only.yaml")
    assert_pre_outcome_locked(config)

    users = parse_memory_source_users(load_users(PROJECT / "data" / "external" / "evo_emo.json"))
    audit = build_mp_extraction_audit_report(users)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    audit_path = OUT_DIR / "es_memeval_public_mp_extraction_audit_v1.json"
    rendered = _canonical(audit) + "\n"
    audit_path.write_text(rendered, encoding="utf-8")

    return {
        "protocol": "pm-paper1-mp-extraction-audit-build-v1",
        "status": "DIAGNOSTIC_AUDIT_BUILT_PRIMARY_COMPILER_UNCHANGED",
        "outcome_calls": 0,
        "primary_compiler_unique_hits": audit["primary_compiler"]["unique_hit_count"],
        "category_totals": {
            category: row["total_matches"] for category, row in audit["category_coverage_audit"].items()
        },
        "outputs": {
            "mp_extraction_audit": {
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
