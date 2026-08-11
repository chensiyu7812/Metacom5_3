from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.evoemo import load_evoemo  # noqa: E402
from metacom_pm.v1_5_paper1_public_surface import (  # noqa: E402
    build_esconv_states,
    build_evo_states_and_candidates,
    build_qa_surfaces,
    write_structural_surface,
)


AUTHORITY = ROOT / "data" / "pm_v1_5_contracts" / "active_method_authority_v1.json"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    path.relative_to(ROOT.resolve())
    return path


def _authorized_phase(phase_manifest_path: Path | None) -> tuple[dict[str, Any], dict[str, Any]]:
    authority = _read_json(AUTHORITY)
    current = authority["current_phase"]
    if current["id"] != "P1_PUBLIC_SOURCE_AND_CANONICAL_GROUP_MATERIALIZATION":
        raise RuntimeError(
            "P1 structural materialization is not active; current authority phase is "
            + str(current["id"])
        )
    configured = current.get("active_phase_manifest")
    if not configured or phase_manifest_path is None:
        raise RuntimeError("P1 authority does not bind an active phase manifest")
    expected_path = _resolve(str(configured["path"]))
    supplied_path = phase_manifest_path.resolve()
    if supplied_path != expected_path:
        raise RuntimeError("supplied phase manifest is not the authority-bound path")
    if _sha256(expected_path) != configured["sha256"]:
        raise RuntimeError("authority-bound phase manifest hash drifted")
    phase = _read_json(expected_path)
    if phase["status"] != "P1_ACTIVE_ZERO_API_STRUCTURAL_MATERIALIZATION":
        raise RuntimeError("phase manifest does not authorize structural materialization")
    if phase["parent_authority_sha256"] != current.get(
        "promoted_from_authority_sha256"
    ):
        raise RuntimeError("phase manifest is not bound to the promoted parent authority")
    if phase["authorization"] != {
        "structural_surface_materialization": True,
        "actual_rank1_materialization": False,
        "api_calls": False,
        "response_generation": False,
        "label_creation": False,
        "pm_training": False,
        "baseline_execution": False,
        "external_outcome_scoring": False,
        "paid_execution": False,
    }:
        raise RuntimeError("phase authorization is broader than structural materialization")
    for binding in phase["implementation_bindings"]:
        path = _resolve(binding["path"])
        if _sha256(path) != binding["sha256"]:
            raise RuntimeError(f"implementation hash drifted: {binding['path']}")
    return authority, phase


def run(phase_manifest_path: Path) -> dict[str, Any]:
    authority, phase = _authorized_phase(phase_manifest_path)
    candidate_path = _resolve(phase["p1_candidate_manifest"]["path"])
    if _sha256(candidate_path) != phase["p1_candidate_manifest"]["sha256"]:
        raise RuntimeError("P1 candidate manifest hash drifted")
    candidate = _read_json(candidate_path)
    source = candidate["source_bindings"]

    es_path = _resolve(source["ESConv"]["path"])
    split_path = _resolve(source["ESConv"]["split_manifest_path"])
    evo_path = _resolve(source["EvoEmo_and_ES_MemEval"]["path"])
    if _sha256(es_path) != source["ESConv"]["sha256"]:
        raise RuntimeError("ESConv source hash drifted")
    if _sha256(split_path) != source["ESConv"]["split_manifest_sha256"]:
        raise RuntimeError("ESConv split manifest hash drifted")
    if _sha256(evo_path) != source["EvoEmo_and_ES_MemEval"]["sha256"]:
        raise RuntimeError("EvoEmo source hash drifted")

    esconv = _read_json(es_path)
    split_rows = _read_jsonl(split_path)
    users = load_evoemo(evo_path)
    fold_by_user = {
        str(user_id): int(row["fold"])
        for row in candidate["frozen_outer_folds"]["folds"]
        for user_id in row["held_out_users"]
    }
    esconv_states = build_esconv_states(esconv, split_rows)
    evo_states, candidates, evo_groups = build_evo_states_and_candidates(
        users, fold_by_user
    )
    qa_visible, qa_evaluator = build_qa_surfaces(users, fold_by_user)
    es_groups = [
        {
            "dataset": "ESConv",
            "split_group_key": f"esconv::{row['dialogue_id']}",
            "runtime_owners": [f"esconv::{row['dialogue_id']}"],
            "split": row["split"],
        }
        for row in split_rows
        if not bool(row["excluded_for_evoemo_overlap"])
    ]
    source_index = {
        "protocol": "pm-v1.5-paper1-p1-source-index-v1",
        "method_id": authority["active_method"]["method_id"],
        "active_contract_sha256": authority["active_method"]["contract_sha256"],
        "active_method_amendment_sha256": authority["active_method"][
            "method_amendment_sha256"
        ],
        "active_authority_sha256": _sha256(AUTHORITY),
        "phase_manifest_sha256": _sha256(phase_manifest_path),
        "p1_candidate_manifest_sha256": _sha256(candidate_path),
        "source_hashes": {
            "ESConv": _sha256(es_path),
            "ESConv_split": _sha256(split_path),
            "EvoEmo_ES_MemEval": _sha256(evo_path),
        },
        "actual_rank1_materialized": False,
        "api_calls": 0,
        "responses_generated": 0,
        "labels_created": 0,
        "pm_trained": False,
        "external_outcomes_read": False,
    }
    return write_structural_surface(
        output_dir=_resolve(phase["outputs"]["public_dir"]),
        private_output_dir=_resolve(phase["outputs"]["private_dir"]),
        esconv_states=esconv_states,
        evo_states=evo_states,
        candidates=candidates,
        groups=[*es_groups, *evo_groups],
        qa_visible=qa_visible,
        qa_evaluator=qa_evaluator,
        source_index=source_index,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase-manifest", type=Path)
    args = parser.parse_args()
    if args.phase_manifest is None:
        # The authority check intentionally happens before any public source read.
        _authorized_phase(None)
        raise AssertionError("unreachable")
    report = run(args.phase_manifest)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
