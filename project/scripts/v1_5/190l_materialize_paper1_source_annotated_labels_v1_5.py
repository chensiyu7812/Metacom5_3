#!/usr/bin/env python3
"""Materialize private source-annotated labels exactly once, with no fitting."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_paper1_annotated_labels import (  # noqa: E402
    event_ancestor_source_sessions,
    first_future_supporter,
    memory_source_annotated_label,
    rs_source_annotated_label,
)


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_source_annotated_label_materialization_phase_v1.json"
ESCONV = ROOT / "data/external/ESConv.json"
EVO = ROOT / "data/external/evo_emo.json"
RANK1 = ROOT / "outputs/pm_v1_5_paper1_p1b_actual_rank1/actual_rank1_unlabeled.jsonl"
SURFACE = ROOT / "outputs/pm_v1_5_paper1_p1_public_surface"
OUT = ROOT / "outputs/pm_v1_5_paper1_source_annotated_labels_20260810"
PRIVATE = ROOT / "outputs/pm_v1_5_paper1_source_annotated_labels_private_20260810"


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    if OUT.exists() or PRIVATE.exists():
        raise RuntimeError("source-annotated labels already exist; refusing overwrite")
    authority = read(AUTHORITY)
    current = authority["current_phase"]
    if current["id"] != "SOURCE_ANNOTATED_LABEL_MATERIALIZATION":
        raise RuntimeError("label materialization is not active")
    if current["active_phase_manifest"]["sha256"] != sha256_file(PHASE):
        raise RuntimeError("label phase is not hash-bound by active authority")
    phase = read(PHASE)
    for binding in [*phase["input_bindings"], *phase["implementation_bindings"]]:
        if sha256_file(ROOT / binding["path"]) != binding["sha256"]:
            raise RuntimeError(f"bound label input drifted: {binding['path']}")
    rank = rows(RANK1)
    states = {
        row["state_id"]: row
        for path in (SURFACE / "esconv_states_unlabeled.jsonl", SURFACE / "evoemo_states_unlabeled.jsonl")
        for row in rows(path)
    }
    candidates = {row["candidate_id"]: row for row in rows(SURFACE / "evoemo_candidates_unlabeled.jsonl")}
    esconv = read(ESCONV)
    evo = read(EVO)
    ancestors = {str(user["id"]): event_ancestor_source_sessions(user) for user in evo}
    labels: list[dict[str, Any]] = []
    for row in rank:
        component = str(row["component"])
        if component not in {"RS", "MS", "ME"} or not row["candidate_present"]:
            continue
        state = states[row["state_id"]]
        basis: str
        if component == "RS":
            if state["dataset"] != "ESConv":
                continue
            raw_dialogue_index = int(str(state["dialogue_id"]).split("_")[-1])
            future = first_future_supporter(esconv[raw_dialogue_index]["dialog"], int(state["raw_current_turn_index"]))
            if future is None:
                continue
            label = rs_source_annotated_label(
                move_id=str(row["retrieval_observations"]["move_id"]),
                current_user_text=str(state["current_user_text"]),
                next_supporter_turn=future,
            )
            basis = "ESCONV_NEXT_SUPPORT_STRATEGY_OR_EXPLICIT_CLOSURE"
        else:
            user_id = str(state["runtime_owner_key"]).split("::", 1)[1]
            candidate = candidates[str(row["actual_rank1_id"])]
            label = memory_source_annotated_label(
                source_session_id=str(candidate["source_session_id"]),
                current_session_id=str(state["source_session_id"]),
                ancestors=ancestors[user_id],
            )
            basis = "EVOEMO_RECURSIVE_EVENT_ANCESTRY"
        labels.append(
            {
                "protocol": "pm-v1.5-paper1-source-annotated-label-row-v1",
                "state_id": row["state_id"],
                "component": component,
                "actual_rank1_id": row["actual_rank1_id"],
                "split_group_key": state["split_group_key"],
                "outer_partition": state.get("split") if component == "RS" else state.get("outer_fold"),
                "label": "SOURCE_ANNOTATED_SUITABLE" if label else "SOURCE_ANNOTATED_NOT_SUITABLE",
                "label_value": int(label),
                "label_basis_code": basis,
            }
        )
    counts = Counter((row["component"], row["label_value"]) for row in labels)
    checks = {
        "exact_counts": counts == Counter({("RS", 0): 16854, ("RS", 1): 1378, ("MS", 0): 3610, ("MS", 1): 832, ("ME", 0): 346, ("ME", 1): 71}),
        "unique_state_component": len({(row["state_id"], row["component"]) for row in labels}) == len(labels),
        "no_mp_labels": all(row["component"] != "MP" for row in labels),
        "only_frozen_label_basis": {row["label_basis_code"] for row in labels}
        == {"ESCONV_NEXT_SUPPORT_STRATEGY_OR_EXPLICIT_CLOSURE", "EVOEMO_RECURSIVE_EVENT_ANCESTRY"},
        "no_future_text_event_ids_or_answers_in_rows": all(
            not ({"future_supporter_text", "strategy_annotation", "event_ids", "influenced_by", "answer", "evidence"} & set(row))
            for row in labels
        ),
    }
    if not all(checks.values()):
        raise RuntimeError(f"label materialization checks failed: {[k for k, v in checks.items() if not v]}")
    PRIVATE.mkdir(parents=True)
    label_path = PRIVATE / "source_annotated_labels.jsonl"
    write_jsonl(label_path, labels)
    OUT.mkdir(parents=True)
    report = {
        "protocol": "pm-v1.5-paper1-source-annotated-label-materialization-report-v1",
        "status": "SOURCE_ANNOTATED_LABELS_PASS_LEARNABILITY_PHASE_MAY_BE_DESIGNED",
        "authority_sha256": sha256_file(AUTHORITY),
        "phase_sha256": sha256_file(PHASE),
        "checks": checks,
        "counts": {component: {"positive": counts[(component, 1)], "negative": counts[(component, 0)]} for component in ("RS", "MS", "ME")},
        "private_labels": {"path": str(label_path.relative_to(ROOT)), "sha256": sha256_file(label_path), "rows": len(labels)},
        "runtime_feature_files_modified": 0,
        "api_calls": 0,
        "pm_fit": False,
        "response_or_external_outcomes": 0,
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
