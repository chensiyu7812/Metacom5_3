#!/usr/bin/env python3
"""Materialize the zero-API session-aligned MS V2 surface, Rank-1, and labels."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402

from metacom_pm.evoemo import load_evoemo  # noqa: E402
from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402
from metacom_pm.pm_v1_5_semantic import semantic_snapshot_tree_sha256  # noqa: E402
from metacom_pm.v1_5_paper1_annotated_labels import (  # noqa: E402
    event_ancestor_source_sessions,
    memory_source_annotated_label,
)
from metacom_pm.v1_5_paper1_session_aligned_ms import (  # noqa: E402
    build_surfaces,
    rank1_rows,
    validate_public_surfaces,
)


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_ms_session_aligned_materialization_phase_v2.json"


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def encode_bge(snapshot: Path, texts: list[str]) -> np.ndarray:
    """Exact CLS pooling used by production BGE-M3, with local GPU if present."""

    import torch
    from transformers import AutoModel, AutoTokenizer

    device = torch.device("cuda:1" if torch.cuda.device_count() > 1 else "cuda:0" if torch.cuda.is_available() else "cpu")
    tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True)
    model = AutoModel.from_pretrained(snapshot, local_files_only=True).to(device)
    model.eval()
    pieces = []
    with torch.inference_mode():
        for start in range(0, len(texts), 16):
            batch = tokenizer(
                texts[start : start + 16],
                padding=True,
                truncation=True,
                max_length=8192,
                return_tensors="pt",
            )
            batch = {key: value.to(device) for key, value in batch.items()}
            vector = model(**batch).last_hidden_state[:, 0]
            vector = torch.nn.functional.normalize(vector.float(), p=2, dim=1)
            pieces.append(vector.cpu().numpy())
    return np.concatenate(pieces, axis=0) if pieces else np.zeros((0, 1024), dtype="float32")


def main() -> None:
    authority = read(AUTHORITY)
    current = authority["current_phase"]
    if current["id"] != "MS_SESSION_ALIGNED_MATERIALIZATION_V2":
        raise RuntimeError("MS session-aligned V2 materialization is not active")
    configured = current["active_phase_manifest"]
    if configured["path"] != str(PHASE.relative_to(ROOT)) or configured["sha256"] != sha256_file(PHASE):
        raise RuntimeError("active V2 phase binding drifted")
    phase = read(PHASE)
    for binding in [*phase["input_bindings"], *phase["implementation_bindings"]]:
        if sha256_file(ROOT / binding["path"]) != binding["sha256"]:
            raise RuntimeError(f"binding drifted: {binding['path']}")
    snapshot = Path(phase["local_semantic_encoder"]["snapshot_path"])
    if semantic_snapshot_tree_sha256(snapshot) != phase["local_semantic_encoder"]["snapshot_tree_sha256"]:
        raise RuntimeError("BGE-M3 snapshot drifted")

    public = ROOT / phase["outputs"]["public_dir"]
    private = ROOT / phase["outputs"]["private_dir"]
    report_dir = ROOT / phase["outputs"]["report_dir"]
    if public.exists() or private.exists() or report_dir.exists():
        raise RuntimeError("V2 output exists; refusing overwrite")

    users = load_evoemo(ROOT / phase["source"]["path"])
    legacy_states = rows(ROOT / phase["input_roles"]["legacy_evo_states"])
    owner_assignments: dict[str, dict[str, Any]] = {}
    for row in legacy_states:
        owner_assignments.setdefault(
            str(row["runtime_owner_key"]),
            {
                "split_group_key": row["split_group_key"],
                "outer_fold": row["outer_fold"],
            },
        )
    states, candidates = build_surfaces(users, owner_assignments)
    unique_texts = list(
        dict.fromkeys(
            [str(row["visible_text"]) for row in states]
            + [str(row["literal_text"]) for row in candidates]
        )
    )
    vectors = encode_bge(snapshot, unique_texts)
    vector_by_text = dict(zip(unique_texts, vectors, strict=True))
    state_vectors = {str(row["state_id"]): vector_by_text[str(row["visible_text"])] for row in states}
    candidate_vectors = {str(row["candidate_id"]): vector_by_text[str(row["literal_text"])] for row in candidates}
    rank1 = rank1_rows(states, candidates, state_vectors, candidate_vectors)
    validation = validate_public_surfaces(states, candidates, rank1)
    if validation["status"] != "PASS":
        raise RuntimeError("session-aligned public surface validation failed")

    user_by_owner = {f"evo::{user['id']}": user for user in users}
    ancestors = {
        owner: event_ancestor_source_sessions(user)
        for owner, user in user_by_owner.items()
    }
    state_by_id = {str(row["state_id"]): row for row in states}
    labels = []
    for selected in rank1:
        if not selected["candidate_present"]:
            continue
        state = state_by_id[str(selected["state_id"])]
        value = memory_source_annotated_label(
            source_session_id=str(selected["candidate_source_session_id"]),
            current_session_id=str(state["source_session_id"]),
            ancestors=ancestors[str(state["runtime_owner_key"])],
        )
        labels.append(
            {
                "protocol": "pm-v1.5-paper1-session-aligned-ms-label-v2",
                "state_id": state["state_id"],
                "component": "MS",
                "actual_rank1_id": selected["actual_rank1_id"],
                "split_group_key": state["split_group_key"],
                "outer_partition": state["outer_fold"],
                "label_basis_code": "EVOEMO_RECURSIVE_AUTHOR_ANCESTRY_SESSION_ALIGNED",
                "label_value": int(value),
                "label": "SOURCE_ANNOTATED_SUITABLE" if value else "SOURCE_ANNOTATED_NOT_SUITABLE",
            }
        )

    public.mkdir(parents=True)
    private.mkdir(parents=True)
    report_dir.mkdir(parents=True)
    state_path = public / "ms_checkpoint_states_unlabeled.jsonl"
    candidate_path = public / "ms_raw_session_candidates_unlabeled.jsonl"
    rank1_path = public / "ms_actual_rank1_unlabeled.jsonl"
    label_path = private / "ms_session_aligned_labels.jsonl"
    write_jsonl(state_path, states)
    write_jsonl(candidate_path, candidates)
    write_jsonl(rank1_path, rank1)
    write_jsonl(label_path, labels)

    label_counts = Counter(int(row["label_value"]) for row in labels)
    positive_groups = {row["split_group_key"] for row in labels if row["label_value"] == 1}
    negative_groups = {row["split_group_key"] for row in labels if row["label_value"] == 0}
    capacity = {
        "both_classes": label_counts[0] > 0 and label_counts[1] > 0,
        "positive_owner_groups_at_least_12": len(positive_groups) >= 12,
        "negative_owner_groups_at_least_12": len(negative_groups) >= 12,
        "runtime_evaluator_physical_separation": all(row.get("label") is None for row in [*states, *candidates, *rank1]),
        "one_state_per_owner_session": len(states)
        == len({(row["runtime_owner_key"], row["source_session_id"]) for row in states}),
    }
    report = {
        "protocol": "pm-v1.5-paper1-session-aligned-ms-materialization-report-v2",
        "status": "MS_SESSION_ALIGNED_CAPACITY_PASS_FINAL_OOF_MAY_BE_DESIGNED" if all(capacity.values()) else "MS_SESSION_ALIGNED_CAPACITY_FAIL_STOP",
        "method_id": phase["method_id"],
        "validation": validation,
        "capacity_checks": capacity,
        "counts": {
            "users": len(users),
            "connected_owner_groups": len(set(row["split_group_key"] for row in states)),
            "checkpoint_states": len(states),
            "raw_session_candidates": len(candidates),
            "rank1_present": sum(bool(row["candidate_present"]) for row in rank1),
            "rank1_absent": sum(not bool(row["candidate_present"]) for row in rank1),
            "positive_labels": label_counts[1],
            "negative_labels": label_counts[0],
            "positive_owner_groups": len(positive_groups),
            "negative_owner_groups": len(negative_groups),
        },
        "artifacts": {
            "states": {"path": str(state_path.relative_to(ROOT)), "sha256": sha256_file(state_path)},
            "candidates": {"path": str(candidate_path.relative_to(ROOT)), "sha256": sha256_file(candidate_path)},
            "rank1": {"path": str(rank1_path.relative_to(ROOT)), "sha256": sha256_file(rank1_path)},
            "private_labels": {"path": str(label_path.relative_to(ROOT)), "sha256": sha256_file(label_path)},
        },
        "summary_observation_event_or_qa_in_runtime": False,
        "api_calls": 0,
        "pm_fit": False,
        "response_or_external_outcomes": 0,
    }
    write_json(report_dir / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
