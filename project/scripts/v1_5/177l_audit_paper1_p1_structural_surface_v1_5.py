from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "outputs" / "pm_v1_5_paper1_p1_public_surface"
PRIVATE = ROOT / "outputs" / "pm_v1_5_paper1_p1_public_surface_private"
OUT = (
    ROOT
    / "outputs"
    / "pm_v1_5_paper1_p1_structural_surface_final_audit_20260810"
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


def main() -> None:
    audit = _read(PUBLIC / "audit_report.json")
    source_index = _read(PUBLIC / "source_index.json")
    es_states = _jsonl(PUBLIC / "esconv_states_unlabeled.jsonl")
    evo_states = _jsonl(PUBLIC / "evoemo_states_unlabeled.jsonl")
    candidates = _jsonl(PUBLIC / "evoemo_candidates_unlabeled.jsonl")
    groups = _jsonl(PUBLIC / "canonical_groups.jsonl")
    qa_visible = _jsonl(PUBLIC / "qa_generator_visible.jsonl")
    qa_gold = _jsonl(PRIVATE / "qa_evaluator_only.jsonl")

    artifact_hashes_match = all(
        _sha(Path(binding["path"])) == binding["sha256"]
        for binding in audit["artifacts"].values()
    )
    components = Counter(str(row["component"]) for row in candidates)
    candidates_by_owner_component_session: dict[
        tuple[str, str], list[int]
    ] = defaultdict(list)
    for row in candidates:
        candidates_by_owner_component_session[
            (str(row["runtime_owner_key"]), str(row["component"]))
        ].append(int(row["available_after_session_index"]))

    strict_past_count_match = True
    visible_prefix_match = True
    for state in evo_states:
        session_index = int(state["source_session_index"])
        owner = str(state["runtime_owner_key"])
        expected = {
            component: sum(
                available < session_index
                for available in candidates_by_owner_component_session.get(
                    (owner, component), []
                )
            )
            for component in ("MP", "MS", "ME")
        }
        strict_past_count_match = strict_past_count_match and (
            state["candidate_source_counts"] == expected
        )
        visible = state["visible_current_session_dialogue"]
        visible_prefix_match = visible_prefix_match and bool(visible)
        visible_prefix_match = visible_prefix_match and (
            visible[-1]["speaker"] == "seeker"
            and visible[-1]["content"] == state["current_user_text"]
            and visible[-1]["raw_turn_index"]
            == state["raw_current_turn_index"]
        )

    es_split_states = Counter(str(row["split"]) for row in es_states)
    qa_visible_keys_clean = all(
        set(row) == {"protocol", "question_id", "question", "history_surface_key"}
        for row in qa_visible
    )
    qa_ids_match = {row["question_id"] for row in qa_visible} == {
        row["question_id"] for row in qa_gold
    }
    evo_groups = [row for row in groups if row["dataset"] == "EvoEmo"]
    shared_group = next(
        (row for row in evo_groups if set(row["runtime_owners"]) == {"p13", "p18"}),
        None,
    )
    owner_separation = all(
        row["runtime_owner_key"] in {"evo::p13", "evo::p18"}
        for row in candidates
        if row["split_group_key"] == "evo_component::p13__p18"
    ) and not any(
        row["runtime_owner_key"] == "evo::p13"
        and str(row["candidate_id"]).startswith("evo::p18")
        for row in candidates
    )
    checks = {
        "materializer_terminal_status": audit["status"]
        == "P1_STRUCTURAL_SURFACE_PASS_ACTUAL_RANK1_NOT_YET_MATERIALIZED",
        "artifact_hashes_match": artifact_hashes_match,
        "expected_denominators": len(es_states) == 18341
        and len(evo_states) == 4689
        and len(candidates) == 4696
        and len(qa_visible) == len(qa_gold) == 1427
        and len(groups) == 1233,
        "candidate_component_counts": components
        == Counter({"MS": 4564, "MP": 108, "ME": 24}),
        "strict_past_candidate_counts_recomputed": strict_past_count_match,
        "current_visible_prefix_ends_at_current_seeker": visible_prefix_match,
        "esconv_split_state_counts": es_split_states
        == Counter({"train": 13235, "validation": 2638, "test": 2468}),
        "qa_visible_schema_has_no_owner_or_gold": qa_visible_keys_clean,
        "qa_visible_and_gold_ids_match": qa_ids_match,
        "shared_session_group_bound": shared_group is not None
        and int(shared_group["outer_fold"]) == 1,
        "shared_group_runtime_owners_remain_separate": owner_separation,
        "all_state_labels_are_null": all(
            row["label"] is None for row in [*es_states, *evo_states]
        ),
        "source_index_records_no_calls_or_outcomes": source_index["api_calls"] == 0
        and source_index["responses_generated"] == 0
        and source_index["labels_created"] == 0
        and source_index["pm_trained"] is False
        and source_index["external_outcomes_read"] is False,
        "actual_rank1_still_absent": audit["actual_rank1_materialized"] is False,
    }
    failed = [name for name, passed in checks.items() if not passed]
    report = {
        "protocol": "pm-v1.5-paper1-p1-structural-surface-final-audit-v1",
        "status": "P1_STRUCTURAL_SURFACE_FINAL_PASS_P1B_RANK1_MAY_BE_DESIGNED"
        if not failed
        else "P1_STRUCTURAL_SURFACE_FINAL_FAIL_CLOSED",
        "checks": checks,
        "failed_checks": failed,
        "counts": {
            "esconv_states": len(es_states),
            "evoemo_states": len(evo_states),
            "candidates": dict(components),
            "qa_visible": len(qa_visible),
            "qa_evaluator_only": len(qa_gold),
            "canonical_groups": len(groups),
        },
        "execution_authority_sha256": source_index["active_authority_sha256"],
        "actual_rank1_materialized": False,
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
