from __future__ import annotations

from collections import Counter
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
)
from metacom_pm.v1_5_v5_3_semantic_ms_retrieval import BgeM3Encoder  # noqa: E402


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
PHASE = (
    ROOT
    / "data/pm_v1_5_contracts"
    / "paper1_p1b_actual_rank1_materialization_phase_v1.json"
)
MATERIALIZED = ROOT / "outputs/pm_v1_5_paper1_p1b_actual_rank1"
OUT = (
    ROOT
    / "outputs/pm_v1_5_paper1_p1b_actual_rank1_final_audit_20260810"
    / "report.json"
)


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


def main() -> None:
    authority = _read(AUTHORITY)
    phase = _read(PHASE)
    materialized_report = _read(MATERIALIZED / "report.json")
    rank1_path = MATERIALIZED / "actual_rank1_unlabeled.jsonl"
    rows = _jsonl(rank1_path)
    inputs = {row["role"]: _resolve(row["path"]) for row in phase["input_bindings"]}
    es_states = _jsonl(inputs["esconv_states"])
    evo_states = _jsonl(inputs["evoemo_states"])
    candidates = _jsonl(inputs["evoemo_candidates"])
    cards = [StrategyCard(**row) for row in _jsonl(inputs["strategy_bank"])]

    base_validation = validate_rank1_rows(
        esconv_states=es_states,
        evo_states=evo_states,
        candidates=candidates,
        rows=rows,
    )
    observed = {
        (str(row["state_id"]), str(row["component"])): row for row in rows
    }
    grouped = group_candidates_by_owner(candidates)

    # Recompute the deterministic non-neural paths from the frozen sources.
    non_neural_match = True
    for state in es_states:
        expected = rank_rs(state, cards)
        non_neural_match = non_neural_match and expected == observed[
            (str(state["state_id"]), "RS")
        ]
    for state in evo_states:
        owner_candidates = grouped.get(str(state["runtime_owner_key"]), [])
        for component, expected in (
            ("MP", rank_mp(state, owner_candidates)),
            ("ME", rank_me(state, owner_candidates)),
            ("RS", rank_rs(state, cards)),
        ):
            non_neural_match = non_neural_match and expected == observed[
                (str(state["state_id"]), component)
            ]

    # Re-encode independently from the persisted artifact and require exact
    # Rank-1 identities plus numerically stable scores/margins.
    ms_candidates = [row for row in candidates if row["component"] == "MS"]
    unique_texts = list(
        dict.fromkeys(
            [str(row["literal_text"]) for row in ms_candidates]
            + [str(state["current_user_text"]) for state in evo_states]
        )
    )
    snapshot = Path(phase["local_semantic_encoder"]["snapshot_path"])
    snapshot_hash_matches = semantic_snapshot_tree_sha256(snapshot) == phase[
        "local_semantic_encoder"
    ]["snapshot_tree_sha256"]
    vectors = BgeM3Encoder(snapshot).encode(unique_texts)
    vector_by_text = dict(zip(unique_texts, vectors, strict=True))
    vector_by_id = {
        str(row["candidate_id"]): vector_by_text[str(row["literal_text"])]
        for row in ms_candidates
    }
    ms_identity_match = True
    ms_numeric_match = True
    for state in evo_states:
        expected = rank_ms_from_vectors(
            state,
            grouped.get(str(state["runtime_owner_key"]), []),
            query_vector=vector_by_text[str(state["current_user_text"])],
            candidate_vectors=vector_by_id,
        )
        actual = observed[(str(state["state_id"]), "MS")]
        ms_identity_match = ms_identity_match and (
            expected["candidate_present"] == actual["candidate_present"]
            and expected["actual_rank1_id"] == actual["actual_rank1_id"]
            and expected["hard_off_reason"] == actual["hard_off_reason"]
        )
        for field in ("selection_score", "top1_top2_margin"):
            if expected[field] is None or actual[field] is None:
                ms_numeric_match = ms_numeric_match and expected[field] is actual[field]
            else:
                ms_numeric_match = ms_numeric_match and abs(
                    float(expected[field]) - float(actual[field])
                ) <= 1e-7

    component_total = Counter(str(row["component"]) for row in rows)
    component_present = Counter(
        str(row["component"]) for row in rows if row["candidate_present"]
    )
    checks = {
        "authority_and_phase_are_active_and_hash_bound": authority["current_phase"][
            "id"
        ]
        == "P1B_ACTUAL_RANK1_MATERIALIZATION"
        and authority["current_phase"]["active_phase_manifest"]["sha256"]
        == _sha(PHASE),
        "materializer_terminal_status": materialized_report["status"]
        == "P1B_ACTUAL_RANK1_MATERIALIZATION_PASS_LABELS_AND_OUTCOMES_ABSENT",
        "artifact_hash_matches_report": _sha(rank1_path)
        == materialized_report["artifact"]["sha256"],
        "expected_row_denominators": len(rows) == 37097
        and component_total
        == Counter({"RS": 23030, "MP": 4689, "MS": 4689, "ME": 4689}),
        "base_causality_and_null_label_validation": not base_validation[
            "failed_checks"
        ],
        "non_neural_rank1_paths_recompute_exactly": non_neural_match,
        "semantic_snapshot_hash_matches": snapshot_hash_matches,
        "ms_rank1_identity_recomputes_exactly": ms_identity_match,
        "ms_rank1_scores_recompute_within_tolerance": ms_numeric_match,
        "no_api_labels_responses_training_or_outcomes": materialized_report[
            "api_calls"
        ]
        == 0
        and materialized_report["labels_created"] == 0
        and materialized_report["responses_generated"] == 0
        and materialized_report["pm_trained"] is False
        and materialized_report["external_outcomes_read"] is False,
    }
    failed = [name for name, passed in checks.items() if not passed]
    report = {
        "protocol": "pm-v1.5-paper1-p1b-actual-rank1-final-audit-v1",
        "status": (
            "P1B_ACTUAL_RANK1_FINAL_PASS_P2_LABEL_DESIGN_MAY_BEGIN"
            if not failed
            else "P1B_ACTUAL_RANK1_FINAL_FAIL_CLOSED"
        ),
        "checks": checks,
        "failed_checks": failed,
        "counts": {
            component: {
                "total": component_total[component],
                "candidate_present": component_present[component],
                "candidate_absent": component_total[component]
                - component_present[component],
            }
            for component in ("MP", "MS", "ME", "RS")
        },
        "artifact_sha256": _sha(rank1_path),
        "phase_manifest_sha256": _sha(PHASE),
        "authority_sha256": _sha(AUTHORITY),
        "api_calls": 0,
        "responses_generated": 0,
        "labels_created": 0,
        "pm_trained": False,
        "external_outcomes_read": False,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
