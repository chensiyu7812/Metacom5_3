from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any
from sklearn.model_selection import GroupKFold

from .io import iter_jsonl, write_jsonl, write_json, stable_hex


def make_grouped_folds(
    runtime_path: str | Path,
    out_path: str | Path,
    out_summary_path: str | Path,
    *,
    n_splits: int = 5,
) -> dict[str, Any]:
    rows = list(iter_jsonl(runtime_path))
    state_ids = sorted({row["state_id"] for row in rows})
    state_meta = {}
    for row in rows:
        state_meta.setdefault(row["state_id"], {
            "user_id": row["user_id"],
            "semantic_family": row["semantic_family"],
        })
    output = []
    summaries = {}
    for mode in ("user", "semantic"):
        groups = [
            state_meta[state_id]["user_id" if mode == "user" else "semantic_family"]
            for state_id in state_ids
        ]
        unique_groups = len(set(groups))
        splits = min(n_splits, unique_groups)
        if splits < 2:
            raise ValueError(f"not enough {mode} groups")
        gkf = GroupKFold(n_splits=splits)
        fold_counts = []
        for fold, (train_idx, val_idx) in enumerate(
            gkf.split(state_ids, groups=groups)
        ):
            train_states = {state_ids[i] for i in train_idx}
            val_states = {state_ids[i] for i in val_idx}
            train_cards = [
                row["card_id"] for row in rows if row["state_id"] in train_states
            ]
            val_cards = [
                row["card_id"] for row in rows if row["state_id"] in val_states
            ]
            output.append({
                "mode": mode,
                "fold": fold,
                "train_state_ids": sorted(train_states),
                "validation_state_ids": sorted(val_states),
                "train_card_ids": sorted(train_cards),
                "validation_card_ids": sorted(val_cards),
            })
            fold_counts.append({
                "fold": fold,
                "train_states": len(train_states),
                "validation_states": len(val_states),
                "train_cards": len(train_cards),
                "validation_cards": len(val_cards),
            })
        summaries[mode] = {
            "n_groups": unique_groups,
            "n_splits": splits,
            "folds": fold_counts,
        }
    write_jsonl(out_path, output)
    summary = {
        "n_runtime_cards": len(rows),
        "n_states": len(state_ids),
        "modes": summaries,
    }
    write_json(out_summary_path, summary)
    return summary
