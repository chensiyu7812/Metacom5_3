from __future__ import annotations

from collections import Counter, defaultdict
import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.contracts import StrategyCard  # noqa: E402
from metacom_pm.pm_v1_5_semantic import semantic_snapshot_tree_sha256  # noqa: E402
from metacom_pm.v1_5_paper1_rank1 import (  # noqa: E402
    group_candidates_by_owner,
    rank_me,
    rank_mp,
    rank_ms_from_vectors,
    rank_rs,
    validate_rank1_rows,
    write_jsonl,
)
from metacom_pm.v1_5_v5_3_semantic_ms_retrieval import BgeM3Encoder  # noqa: E402


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    path.relative_to(ROOT.resolve())
    return path


def _authorized(phase_path: Path | None) -> tuple[dict[str, Any], dict[str, Any]]:
    authority = _read(AUTHORITY)
    current = authority["current_phase"]
    if current["id"] != "P1B_ACTUAL_RANK1_MATERIALIZATION":
        raise RuntimeError(
            "P1B actual Rank-1 materialization is not active; current phase is "
            + str(current["id"])
        )
    configured = current.get("active_phase_manifest")
    if not configured or phase_path is None:
        raise RuntimeError("P1B authority does not bind a supplied phase manifest")
    expected = _resolve(str(configured["path"]))
    if phase_path.resolve() != expected:
        raise RuntimeError("supplied P1B phase manifest is not authority-bound")
    if _sha(expected) != configured["sha256"]:
        raise RuntimeError("authority-bound P1B phase hash drifted")
    phase = _read(expected)
    if phase["status"] != "P1B_ACTIVE_ZERO_API_ACTUAL_RANK1":
        raise RuntimeError("P1B phase is not active")
    if phase["parent_authority_sha256"] != current.get(
        "promoted_from_authority_sha256"
    ):
        raise RuntimeError("P1B phase parent authority mismatch")
    expected_auth = {
        "structural_surface_materialization": False,
        "actual_rank1_materialization": True,
        "api_calls": False,
        "response_generation": False,
        "label_creation": False,
        "pm_training": False,
        "baseline_execution": False,
        "external_outcome_scoring": False,
        "paid_execution": False,
    }
    if phase["authorization"] != expected_auth:
        raise RuntimeError("P1B phase authorization is broader than Rank-1 only")
    for binding in phase["implementation_bindings"]:
        if _sha(_resolve(binding["path"])) != binding["sha256"]:
            raise RuntimeError(f"implementation hash drifted: {binding['path']}")
    for binding in phase["input_bindings"]:
        if _sha(_resolve(binding["path"])) != binding["sha256"]:
            raise RuntimeError(f"input hash drifted: {binding['path']}")
    return authority, phase


def run(phase_path: Path) -> dict[str, Any]:
    authority, phase = _authorized(phase_path)
    inputs = {row["role"]: _resolve(row["path"]) for row in phase["input_bindings"]}
    es_states = _jsonl(inputs["esconv_states"])
    evo_states = _jsonl(inputs["evoemo_states"])
    candidates = _jsonl(inputs["evoemo_candidates"])
    cards = [StrategyCard(**row) for row in _jsonl(inputs["strategy_bank"])]
    snapshot = Path(phase["local_semantic_encoder"]["snapshot_path"])
    if semantic_snapshot_tree_sha256(snapshot) != phase["local_semantic_encoder"][
        "snapshot_tree_sha256"
    ]:
        raise RuntimeError("local BGE-M3 snapshot hash drifted")

    output_dir = _resolve(phase["outputs"]["output_dir"])
    rank1_path = output_dir / "actual_rank1_unlabeled.jsonl"
    report_path = output_dir / "report.json"
    if output_dir.exists() or rank1_path.exists() or report_path.exists():
        raise RuntimeError("P1B output already exists; refusing to overwrite or rerun")

    grouped = group_candidates_by_owner(candidates)
    ms_candidates = [row for row in candidates if row["component"] == "MS"]
    # Encode every unique text once.  This is local deterministic inference;
    # it creates no response, label, or outcome.
    unique_texts = list(
        dict.fromkeys(
            [str(row["literal_text"]) for row in ms_candidates]
            + [str(state["current_user_text"]) for state in evo_states]
        )
    )
    encoder = BgeM3Encoder(snapshot)
    vectors = encoder.encode(unique_texts)
    if len(vectors) != len(unique_texts):
        raise RuntimeError("BGE-M3 returned a different number of vectors")
    vector_by_text = dict(zip(unique_texts, vectors, strict=True))
    ms_vector_by_id = {
        str(row["candidate_id"]): vector_by_text[str(row["literal_text"])]
        for row in ms_candidates
    }

    rows: list[dict[str, Any]] = []
    for state in es_states:
        rows.append(rank_rs(state, cards))
    for state in evo_states:
        owner_candidates = grouped.get(str(state["runtime_owner_key"]), [])
        rows.append(rank_mp(state, owner_candidates))
        rows.append(
            rank_ms_from_vectors(
                state,
                owner_candidates,
                query_vector=vector_by_text[str(state["current_user_text"])],
                candidate_vectors=ms_vector_by_id,
            )
        )
        rows.append(rank_me(state, owner_candidates))
        rows.append(rank_rs(state, cards))

    validation = validate_rank1_rows(
        esconv_states=es_states,
        evo_states=evo_states,
        candidates=candidates,
        rows=rows,
    )
    if validation["failed_checks"]:
        raise RuntimeError(
            "P1B validation failed: " + ", ".join(validation["failed_checks"])
        )
    write_jsonl(rank1_path, rows)
    present = Counter(str(row["component"]) for row in rows if row["candidate_present"])
    total = Counter(str(row["component"]) for row in rows)
    off_reasons: dict[str, Counter[str]] = defaultdict(Counter)
    modes: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        component = str(row["component"])
        if row["hard_off_reason"]:
            off_reasons[component][str(row["hard_off_reason"])] += 1
        if row["selection_method"]:
            modes[component][str(row["selection_method"])] += 1
    report = {
        "protocol": "pm-v1.5-paper1-p1b-actual-rank1-report-v1",
        "status": "P1B_ACTUAL_RANK1_MATERIALIZATION_PASS_LABELS_AND_OUTCOMES_ABSENT",
        "method_id": authority["active_method"]["method_id"],
        "active_contract_sha256": authority["active_method"]["contract_sha256"],
        "active_method_amendment_sha256": authority["active_method"][
            "method_amendment_sha256"
        ],
        "active_authority_sha256": _sha(AUTHORITY),
        "phase_manifest_sha256": _sha(phase_path),
        "input_sha256": {
            row["role"]: row["sha256"] for row in phase["input_bindings"]
        },
        "semantic_snapshot_tree_sha256": phase["local_semantic_encoder"][
            "snapshot_tree_sha256"
        ],
        "artifact": {
            "path": str(rank1_path),
            "sha256": _sha(rank1_path),
            "rows": len(rows),
        },
        "counts": {
            component: {
                "total": total[component],
                "candidate_present": present[component],
                "candidate_absent": total[component] - present[component],
                "availability_rate": (
                    present[component] / total[component]
                    if total[component]
                    else 0.0
                ),
                "off_reasons": dict(off_reasons[component]),
                "selection_methods": dict(modes[component]),
            }
            for component in ("MP", "MS", "ME", "RS")
        },
        "validation": validation,
        "actual_rank1_materialized": True,
        "api_calls": 0,
        "responses_generated": 0,
        "labels_created": 0,
        "pm_trained": False,
        "baseline_executed": False,
        "external_outcomes_read": False,
    }
    # write_jsonl created the previously absent output directory.  Report
    # writing is intentionally the final operation after the immutable rows
    # hash has been computed.
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase-manifest", type=Path)
    args = parser.parse_args()
    if args.phase_manifest is None:
        _authorized(None)
        raise AssertionError("unreachable")
    report = run(args.phase_manifest)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
