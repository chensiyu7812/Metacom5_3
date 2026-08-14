#!/usr/bin/env python3
"""Independently recompute and audit the one-shot source-annotated labels."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import canonical_json, sha256_file, write_json  # noqa: E402
from metacom_pm.v1_5_paper1_annotated_labels import (  # noqa: E402
    event_ancestor_source_sessions,
    first_future_supporter,
    memory_source_annotated_label,
    rs_source_annotated_label,
)


LABELS = ROOT / "outputs/pm_v1_5_paper1_source_annotated_labels_private_20260810/source_annotated_labels.jsonl"
REPORT = ROOT / "outputs/pm_v1_5_paper1_source_annotated_labels_20260810/report.json"
RANK1 = ROOT / "outputs/pm_v1_5_paper1_p1b_actual_rank1/actual_rank1_unlabeled.jsonl"
SURFACE = ROOT / "outputs/pm_v1_5_paper1_p1_public_surface"
OUT = ROOT / "outputs/pm_v1_5_paper1_source_annotated_labels_final_audit_20260810/report.json"


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    labels = rows(LABELS)
    materialization = read(REPORT)
    states = {row["state_id"]: row for path in (SURFACE / "esconv_states_unlabeled.jsonl", SURFACE / "evoemo_states_unlabeled.jsonl") for row in rows(path)}
    candidates = {row["candidate_id"]: row for row in rows(SURFACE / "evoemo_candidates_unlabeled.jsonl")}
    rank = rows(RANK1)
    esconv = read(ROOT / "data/external/ESConv.json")
    evo = read(ROOT / "data/external/evo_emo.json")
    ancestors = {str(user["id"]): event_ancestor_source_sessions(user) for user in evo}
    recomputed: dict[tuple[str, str], int] = {}
    for row in rank:
        component = str(row["component"])
        if component not in {"RS", "MS", "ME"} or not row["candidate_present"]:
            continue
        state = states[row["state_id"]]
        if component == "RS":
            if state["dataset"] != "ESConv":
                continue
            raw_index = int(str(state["dialogue_id"]).split("_")[-1])
            future = first_future_supporter(esconv[raw_index]["dialog"], int(state["raw_current_turn_index"]))
            if future is None:
                continue
            value = int(rs_source_annotated_label(move_id=str(row["retrieval_observations"]["move_id"]), current_user_text=str(state["current_user_text"]), next_supporter_turn=future))
        else:
            user_id = str(state["runtime_owner_key"]).split("::", 1)[1]
            candidate = candidates[str(row["actual_rank1_id"])]
            value = int(memory_source_annotated_label(source_session_id=str(candidate["source_session_id"]), current_session_id=str(state["source_session_id"]), ancestors=ancestors[user_id]))
        recomputed[(row["state_id"], component)] = value
    observed = {(row["state_id"], row["component"]): int(row["label_value"]) for row in labels}
    public_files = list((ROOT / "outputs/pm_v1_5_paper1_source_annotated_labels_20260810").glob("*"))
    checks = {
        "exact_full_recomputation": observed == recomputed,
        "label_file_hash_bound_by_report": materialization["private_labels"]["sha256"] == sha256_file(LABELS),
        "exact_rows": len(labels) == len(observed) == 23091,
        "only_private_label_file": all(path.name == "report.json" for path in public_files),
        "runtime_files_remain_unlabeled": all(all(row.get("label") is None for row in rows(SURFACE / name)) for name in ("esconv_states_unlabeled.jsonl", "evoemo_states_unlabeled.jsonl")),
        "no_mp_or_absent_as_negative": set(row["component"] for row in labels) == {"RS", "MS", "ME"},
        "no_fit_or_api": materialization["pm_fit"] is False and materialization["api_calls"] == 0,
    }
    counts = Counter((row["component"], int(row["label_value"])) for row in labels)
    report = {
        "protocol": "pm-v1.5-paper1-source-annotated-label-final-audit-v1",
        "status": "SOURCE_ANNOTATED_LABELS_FINAL_PASS_GROUPED_LEARNABILITY_MAY_BE_DESIGNED" if all(checks.values()) else "SOURCE_ANNOTATED_LABELS_FINAL_FAIL",
        "checks": checks,
        "failed_checks": [key for key, value in checks.items() if not value],
        "counts": {component: {"positive": counts[(component, 1)], "negative": counts[(component, 0)]} for component in ("RS", "MS", "ME")},
        "labels_sha256": sha256_file(LABELS),
        "runtime_surface_hashes": {name: sha256_file(SURFACE / name) for name in ("esconv_states_unlabeled.jsonl", "evoemo_states_unlabeled.jsonl", "evoemo_candidates_unlabeled.jsonl")},
        "api_calls": 0,
        "pm_fit": False,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    write_json(OUT, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["failed_checks"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
