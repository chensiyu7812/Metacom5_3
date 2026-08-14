#!/usr/bin/env python3
"""Zero-API aggregate capacity audit for the replacement annotation labels."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, write_json  # noqa: E402
from metacom_pm.v1_5_paper1_annotated_labels import (  # noqa: E402
    event_ancestor_source_sessions,
    first_future_supporter,
    memory_source_annotated_label,
    rs_source_annotated_label,
)


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
CONTRACT = ROOT / "data/pm_v1_5_contracts/paper1_source_annotated_resource_suitability_method_candidate_v1.json"
ESCONV = ROOT / "data/external/ESConv.json"
EVO = ROOT / "data/external/evo_emo.json"
RANK1 = ROOT / "outputs/pm_v1_5_paper1_p1b_actual_rank1/actual_rank1_unlabeled.jsonl"
SURFACE = ROOT / "outputs/pm_v1_5_paper1_p1_public_surface"
OUT = ROOT / "outputs/pm_v1_5_paper1_source_annotated_label_capacity_20260810/report.json"


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    authority = read(AUTHORITY)
    if authority["current_phase"]["id"] != "P2B_CONTROL_FAILED_ANNOTATED_LABEL_REDESIGN_PENDING":
        raise RuntimeError("annotation label capacity audit is not authorized")
    contract = read(CONTRACT)
    if contract["authorization"]["label_materialization"] is not False:
        raise RuntimeError("candidate contract unexpectedly authorizes labels")
    rank = rows(RANK1)
    states = {
        row["state_id"]: row
        for path in (
            SURFACE / "esconv_states_unlabeled.jsonl",
            SURFACE / "evoemo_states_unlabeled.jsonl",
        )
        for row in rows(path)
    }
    candidates = {
        row["candidate_id"]: row
        for row in rows(SURFACE / "evoemo_candidates_unlabeled.jsonl")
    }
    esconv = read(ESCONV)
    evo = read(EVO)
    ancestors_by_user = {
        str(user["id"]): event_ancestor_source_sessions(user) for user in evo
    }
    counts = {component: Counter() for component in ("RS", "MS", "ME")}
    groups: dict[str, dict[bool, set[str]]] = {
        component: defaultdict(set) for component in ("RS", "MS", "ME")
    }
    for row in rank:
        component = str(row["component"])
        if component not in counts or not bool(row["candidate_present"]):
            continue
        state = states[row["state_id"]]
        if component == "RS":
            if state["dataset"] != "ESConv":
                continue
            raw_index = int(str(state["dialogue_id"]).split("_")[-1])
            future = first_future_supporter(esconv[raw_index]["dialog"], int(state["raw_current_turn_index"]))
            if future is None:
                continue
            label = rs_source_annotated_label(
                move_id=str(row["retrieval_observations"]["move_id"]),
                current_user_text=str(state["current_user_text"]),
                next_supporter_turn=future,
            )
        else:
            user_id = str(state["runtime_owner_key"]).split("::", 1)[1]
            candidate = candidates[str(row["actual_rank1_id"])]
            label = memory_source_annotated_label(
                source_session_id=str(candidate["source_session_id"]),
                current_session_id=str(state["source_session_id"]),
                ancestors=ancestors_by_user[user_id],
            )
        counts[component][label] += 1
        groups[component][label].add(str(state["split_group_key"]))
    absent = Counter(
        row["component"] for row in rank if row["component"] in counts and not row["candidate_present"]
    )
    checks = {
        "rs_bidirectional_capacity": counts["RS"][True] >= 1000 and counts["RS"][False] >= 1000,
        "ms_bidirectional_capacity": counts["MS"][True] >= 500 and counts["MS"][False] >= 500,
        "ms_all_connected_groups_both_classes": len(groups["MS"][True]) == len(groups["MS"][False]) == 17,
        "me_disclosed_sparse_but_nonzero": counts["ME"][True] >= 50 and len(groups["ME"][True]) >= 8,
        "mp_fixed_off_no_gold_invented": contract["label_factory"]["MP"]["status"].startswith("FIXED_OFF"),
        "contract_forbids_label_materialization_and_fit": not contract["authorization"]["label_materialization"]
        and not contract["authorization"]["pm_fit"],
        "no_row_labels_written": True,
    }
    report = {
        "protocol": "pm-v1.5-paper1-source-annotated-label-capacity-audit-v1",
        "status": "SOURCE_ANNOTATED_LABEL_CAPACITY_PASS_METHOD_VALIDATION_MAY_CONTINUE" if all(checks.values()) else "SOURCE_ANNOTATED_LABEL_CAPACITY_FAIL",
        "method_candidate_sha256": sha256_file(CONTRACT),
        "source_hashes": {"ESConv": sha256_file(ESCONV), "EvoEmo": sha256_file(EVO), "actual_rank1": sha256_file(RANK1)},
        "counts": {
            component: {
                "positive": counts[component][True],
                "negative": counts[component][False],
                "structural_absent": absent[component],
                "positive_groups": len(groups[component][True]),
                "negative_groups": len(groups[component][False]),
            }
            for component in ("RS", "MS", "ME")
        },
        "MP": "FIXED_OFF_NO_STABLE_AUTHOR_GOLD",
        "checks": checks,
        "failed_checks": [name for name, passed in checks.items() if not passed],
        "label_rows_written": 0,
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
