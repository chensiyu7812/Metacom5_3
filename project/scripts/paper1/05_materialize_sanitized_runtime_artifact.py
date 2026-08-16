#!/usr/bin/env python3
"""B18: materialize the sanitized runtime artifact -- run this first.

Zero-outcome, Codex-B lane. This is the *only* script (besides
``03_build_public_memory_folds.py``'s evidence-only side and the official
evaluator, out of this lane's scope) allowed to read
``data/external/evo_emo.json`` directly. It writes
``es_memeval_public_sanitized_runtime_artifact_v1.json``: owner identity,
``dialog_history`` session/turn text/timestamp, the officially-visible QA/
Summary ``question`` text, and opaque DG target identity (idx only) --
nothing else. No ``answer``, no ``evidence``, no gold/reference summary, no
``observation``, no Summary ``group``, no DG ``related_sessions``/``topic``/
background, no ``basic_info``.

``02_build_public_memory_census.py`` and ``04_audit_mp_self_disclosure_
coverage.py`` read *only* this artifact (via ``metacom_pm.paper1.data.
memory_source.load_sanitized_runtime_users``) -- never
``data/external/evo_emo.json`` and never ``metacom_pm.paper1.data.
materializer`` or ``metacom_pm.paper1.data.es_memeval`` directly.

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

from metacom_pm.paper1.data.materializer import (  # noqa: E402
    SANITIZED_ARTIFACT_SCHEMA_VERSION,
    write_sanitized_runtime_artifact,
)
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config  # noqa: E402

OUT_DIR = PROJECT / "data" / "paper1_public_memory"
ARTIFACT_PATH = OUT_DIR / "es_memeval_public_sanitized_runtime_artifact_v1.json"

FORBIDDEN_ARTIFACT_TOKENS = (
    '"answer"',
    '"evidence"',
    '"theme"',
    '"group"',
    '"related_sessions"',
    '"more_details"',
    '"physical_condition"',
    '"psychological_condition"',
    '"basic_info"',
    '"observation"',
    '"summary"',
)


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _relpath(path: Path) -> str:
    return path.resolve().relative_to(REPO).as_posix()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build() -> dict[str, Any]:
    config = load_public_only_config(PROJECT / "configs" / "paper1_public_only.yaml")
    assert_pre_outcome_locked(config)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    evo_path = PROJECT / "data" / "external" / "evo_emo.json"
    materialize_report = write_sanitized_runtime_artifact(evo_path, ARTIFACT_PATH)

    # B18: a schema-level self-check, not just an AST/import scan -- the
    # written artifact file itself must not contain any forbidden key, byte
    # for byte.
    artifact_text = ARTIFACT_PATH.read_text(encoding="utf-8")
    found_forbidden = [tok for tok in FORBIDDEN_ARTIFACT_TOKENS if tok in artifact_text]
    if found_forbidden:
        raise RuntimeError(
            f"sanitized runtime artifact unexpectedly contains forbidden key(s): {found_forbidden}"
        )

    report = {
        "protocol": "pm-paper1-sanitized-runtime-artifact-materialize-v1",
        "status": "SANITIZED_RUNTIME_ARTIFACT_MATERIALIZED_SCHEMA_CHECKED",
        "outcome_calls": 0,
        "schema": SANITIZED_ARTIFACT_SCHEMA_VERSION,
        "forbidden_key_scan": {
            "tokens_checked": list(FORBIDDEN_ARTIFACT_TOKENS),
            "found": found_forbidden,
        },
        "materialize_report": materialize_report,
        "outputs": {
            "sanitized_runtime_artifact": {
                "path": _relpath(ARTIFACT_PATH),
                "sha256": _sha_text(artifact_text),
                "bytes": len(artifact_text.encode("utf-8")),
            }
        },
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
