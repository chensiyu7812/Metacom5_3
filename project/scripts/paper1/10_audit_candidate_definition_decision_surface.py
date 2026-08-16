#!/usr/bin/env python3
"""B29: build the MP/ME candidate-definition decision surface.

Zero-outcome, Codex-B lane, diagnostic only. Reads the already-materialized
sanitized runtime artifact (targets/candidates), plus -- for B29.1's MP
source ontology B row only -- ``data/external/evo_emo.json``'s ``basic_info``
block via ``mp_source_ontology_audit._load_raw_basic_info_only``, the sole
reader of that field anywhere in this lane. Writes:

- ``es_memeval_public_mp_source_ontology_audit_v1.json``
- ``es_memeval_public_mp_conversation_proposal_rows_v1.jsonl`` /
  ``..._audit_v1.json``
- ``es_memeval_public_me_cross_turn_proposal_rows_v1.jsonl`` /
  ``..._audit_v1.json``
- ``es_memeval_public_candidate_definition_decision_surface_v1.json``: the
  combined report, explicitly carrying no winner/PASS-FAIL/minimum-N/
  synthetic-rescue and a list of researcher decisions still required.

This script never modifies memory/mp.py or memory/me.py, never expands the
primary MP/ME candidate pool, never calls a scorer or generator, and never
reads any gold/answer/observation/reference-summary/evidence field.

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
from metacom_pm.paper1.features.candidate_definition_decision_surface import (  # noqa: E402
    build_candidate_definition_decision_surface,
    write_candidate_definition_decision_surface,
)
from metacom_pm.paper1.features.me_cross_turn_proposal_audit import (  # noqa: E402
    build_me_cross_turn_proposal_report,
    build_me_cross_turn_proposal_rows,
    write_me_cross_turn_proposal_manifest,
)
from metacom_pm.paper1.features.mp_conversation_proposal_audit import (  # noqa: E402
    build_mp_conversation_proposal_report,
    build_mp_conversation_proposal_rows,
    write_mp_conversation_proposal_manifest,
)
from metacom_pm.paper1.features.mp_source_ontology_audit import (  # noqa: E402
    build_mp_source_ontology_report,
    write_mp_source_ontology_manifest,
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

    mp_ontology_report = build_mp_source_ontology_report(users, targets, EVO_PATH)
    mp_ontology_path = write_mp_source_ontology_manifest(mp_ontology_report, OUT_DIR)

    mp_proposal_rows = build_mp_conversation_proposal_rows(users)
    mp_proposal_report = build_mp_conversation_proposal_report(users)
    mp_proposal_paths = write_mp_conversation_proposal_manifest(mp_proposal_rows, mp_proposal_report, OUT_DIR)

    me_proposal_rows = build_me_cross_turn_proposal_rows(users)
    me_proposal_report = build_me_cross_turn_proposal_report(users)
    me_proposal_paths = write_me_cross_turn_proposal_manifest(me_proposal_rows, me_proposal_report, OUT_DIR)

    surface_report = build_candidate_definition_decision_surface(users, targets, EVO_PATH)
    surface_path = write_candidate_definition_decision_surface(surface_report, OUT_DIR)

    outputs = {
        "mp_source_ontology_audit": mp_ontology_path,
        "mp_conversation_proposal_rows": mp_proposal_paths["rows"],
        "mp_conversation_proposal_audit": mp_proposal_paths["report"],
        "me_cross_turn_proposal_rows": me_proposal_paths["rows"],
        "me_cross_turn_proposal_audit": me_proposal_paths["report"],
        "candidate_definition_decision_surface": surface_path,
    }

    return {
        "protocol": "pm-paper1-candidate-definition-decision-surface-build-v1",
        "status": "B29_CANDIDATE_DEFINITION_AUDIT_BUILT_NO_WINNER",
        "outcome_calls": 0,
        "mp_ontology_a_unique": mp_ontology_report["ontologies"][0]["unique_candidate_count"],
        "mp_ontology_b_unique_facts": mp_ontology_report["ontologies"][1]["unique_candidate_count"],
        "mp_conversation_proposal_row_count": len(mp_proposal_rows),
        "me_cross_turn_proposal_row_count": len(me_proposal_rows),
        "primary_mp_unchanged": mp_proposal_report["primary_mp_unchanged"],
        "primary_me_unchanged": me_proposal_report["primary_me_unchanged"],
        "outputs": {
            name: {"path": _relpath(path), "sha256": _sha_text(path.read_text(encoding="utf-8"))}
            for name, path in outputs.items()
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
