#!/usr/bin/env python3
"""Independently reconstruct and audit the session-aligned MS V2 artifacts."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402

from metacom_pm.evoemo import load_evoemo  # noqa: E402
from metacom_pm.io import canonical_json, sha256_file, write_json  # noqa: E402
from metacom_pm.v1_5_paper1_annotated_labels import (  # noqa: E402
    event_ancestor_source_sessions,
    memory_source_annotated_label,
)
from metacom_pm.v1_5_paper1_session_aligned_ms import (  # noqa: E402
    build_surfaces,
    rank1_rows,
    validate_public_surfaces,
)


PUBLIC = ROOT / "outputs/pm_v1_5_paper1_ms_session_aligned_public_20260810"
PRIVATE = ROOT / "outputs/pm_v1_5_paper1_ms_session_aligned_labels_private_20260810"
MATERIAL = ROOT / "outputs/pm_v1_5_paper1_ms_session_aligned_materialization_20260810/report.json"
LEGACY = ROOT / "outputs/pm_v1_5_paper1_p1_public_surface/evoemo_states_unlabeled.jsonl"
SOURCE = ROOT / "data/external/evo_emo.json"
SNAPSHOT = Path("/home/tokkio/.cache/huggingface/hub/models--BAAI--bge-m3/snapshots/5617a9f61b028005a4858fdac845db406aefb181")
OUT = ROOT / "outputs/pm_v1_5_paper1_ms_session_aligned_final_audit_20260810"


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def encode_independent(texts: list[str]) -> np.ndarray:
    import torch
    from transformers import AutoModel, AutoTokenizer

    device = torch.device("cuda:1" if torch.cuda.device_count() > 1 else "cuda:0" if torch.cuda.is_available() else "cpu")
    tokenizer = AutoTokenizer.from_pretrained(SNAPSHOT, local_files_only=True)
    model = AutoModel.from_pretrained(SNAPSHOT, local_files_only=True).to(device).eval()
    result = []
    with torch.inference_mode():
        # Deliberately use a different batch size from the materializer.
        for start in range(0, len(texts), 13):
            batch = tokenizer(texts[start : start + 13], padding=True, truncation=True, max_length=8192, return_tensors="pt")
            batch = {key: value.to(device) for key, value in batch.items()}
            value = model(**batch).last_hidden_state[:, 0].float()
            result.append(torch.nn.functional.normalize(value, p=2, dim=1).cpu().numpy())
    return np.concatenate(result, axis=0)


def forbidden_keys(value: Any, path: str = "") -> list[str]:
    forbidden = {"summary", "observation", "event", "influenced_by", "answer", "evidence", "capability"}
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            current = f"{path}.{key}" if path else str(key)
            if str(key) in forbidden:
                found.append(current)
            found.extend(forbidden_keys(child, current))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(forbidden_keys(child, f"{path}[{index}]"))
    return found


def main() -> None:
    if OUT.exists():
        raise RuntimeError("audit output exists; refusing overwrite")
    stored_states = rows(PUBLIC / "ms_checkpoint_states_unlabeled.jsonl")
    stored_candidates = rows(PUBLIC / "ms_raw_session_candidates_unlabeled.jsonl")
    stored_rank1 = rows(PUBLIC / "ms_actual_rank1_unlabeled.jsonl")
    stored_labels = rows(PRIVATE / "ms_session_aligned_labels.jsonl")
    legacy = rows(LEGACY)
    assignments: dict[str, dict[str, Any]] = {}
    for row in legacy:
        assignments.setdefault(str(row["runtime_owner_key"]), {"split_group_key": row["split_group_key"], "outer_fold": row["outer_fold"]})
    users = load_evoemo(SOURCE)
    states, candidates = build_surfaces(users, assignments)

    unique = list(dict.fromkeys([str(row["visible_text"]) for row in states] + [str(row["literal_text"]) for row in candidates]))
    vectors = encode_independent(unique)
    by_text = dict(zip(unique, vectors, strict=True))
    recomputed_rank1 = rank1_rows(
        states,
        candidates,
        {str(row["state_id"]): by_text[str(row["visible_text"])] for row in states},
        {str(row["candidate_id"]): by_text[str(row["literal_text"])] for row in candidates},
    )
    user_by_owner = {f"evo::{user['id']}": user for user in users}
    ancestor = {owner: event_ancestor_source_sessions(user) for owner, user in user_by_owner.items()}
    state_by_id = {str(row["state_id"]): row for row in states}
    recomputed_labels = []
    for selected in recomputed_rank1:
        if not selected["candidate_present"]:
            continue
        state = state_by_id[str(selected["state_id"])]
        value = memory_source_annotated_label(
            source_session_id=str(selected["candidate_source_session_id"]),
            current_session_id=str(state["source_session_id"]),
            ancestors=ancestor[str(state["runtime_owner_key"])],
        )
        recomputed_labels.append((str(state["state_id"]), str(selected["actual_rank1_id"]), int(value)))
    stored_label_tuples = [(str(row["state_id"]), str(row["actual_rank1_id"]), int(row["label_value"])) for row in stored_labels]
    rank_identity = [(row["state_id"], row["actual_rank1_id"]) for row in recomputed_rank1]
    stored_identity = [(row["state_id"], row["actual_rank1_id"]) for row in stored_rank1]
    score_deltas = [
        abs(float(left["selection_score"]) - float(right["selection_score"]))
        for left, right in zip(recomputed_rank1, stored_rank1, strict=True)
        if left["candidate_present"]
    ]
    public_values = [*stored_states, *stored_candidates, *stored_rank1]
    checks = {
        "source_surface_exact_reconstruction": canonical_json(states) == canonical_json(stored_states) and canonical_json(candidates) == canonical_json(stored_candidates),
        "independent_rank1_identity_exact": rank_identity == stored_identity,
        "independent_rank1_score_max_abs_delta_le_1e_5": max(score_deltas, default=0.0) <= 1e-5,
        "independent_labels_exact": recomputed_labels == stored_label_tuples,
        "public_surface_validation": validate_public_surfaces(stored_states, stored_candidates, stored_rank1)["status"] == "PASS",
        "no_forbidden_evaluator_keys_in_runtime": not forbidden_keys(public_values),
        "runtime_labels_null": all(row.get("label") is None for row in public_values),
        "materialization_declared_no_fit": json.loads(MATERIAL.read_text())["pm_fit"] is False,
    }
    report = {
        "protocol": "pm-v1.5-paper1-session-aligned-ms-final-audit-v2",
        "status": "MS_SESSION_ALIGNED_FINAL_AUDIT_PASS_FINAL_OOF_MAY_BE_FROZEN" if all(checks.values()) else "MS_SESSION_ALIGNED_FINAL_AUDIT_FAIL_STOP",
        "checks": checks,
        "rank1_score_max_abs_delta": max(score_deltas, default=0.0),
        "forbidden_runtime_key_paths": forbidden_keys(public_values),
        "artifact_hashes": {
            "states": sha256_file(PUBLIC / "ms_checkpoint_states_unlabeled.jsonl"),
            "candidates": sha256_file(PUBLIC / "ms_raw_session_candidates_unlabeled.jsonl"),
            "rank1": sha256_file(PUBLIC / "ms_actual_rank1_unlabeled.jsonl"),
            "private_labels": sha256_file(PRIVATE / "ms_session_aligned_labels.jsonl"),
        },
        "api_calls": 0,
        "pm_fit": False,
    }
    OUT.mkdir(parents=True)
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
