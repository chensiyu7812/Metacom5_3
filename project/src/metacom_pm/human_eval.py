from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
import csv
import random

import numpy as np

from .io import iter_jsonl, stable_hex, write_json, write_jsonl
from .stats import win_tie_loss


def _canonical_win_tie_loss(
    winner_systems: Iterable[str], target: str = "pm"
) -> dict[str, Any]:
    """Win/tie/loss from the perspective of target canonical system."""
    wins = ties = losses = 0
    for w in winner_systems:
        if w == "tie":
            ties += 1
        elif w == target:
            wins += 1
        else:
            losses += 1
    total = wins + ties + losses
    return {
        "wins": wins,
        "ties": ties,
        "losses": losses,
        "preference_score": (wins + 0.5 * ties) / total if total else None,
        "target_system": target,
    }


def export_blinded_pairs(
    comparison_path: str | Path,
    out_jsonl: str | Path,
    key_path: str | Path,
    *,
    n_pairs: int | None = None,
    seed: int = 20260621,
) -> dict[str, Any]:
    rows = list(iter_jsonl(comparison_path))
    if not rows:
        raise ValueError("no comparison rows")
    rng = random.Random(seed)
    rng.shuffle(rows)
    if n_pairs is not None:
        rows = rows[:n_pairs]
    blinded: list[dict[str, Any]] = []
    keys: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        required = {"response_a", "response_b"}
        if not required <= set(row):
            raise ValueError(f"comparison row missing {required - set(row)}")
        swap = bool(rng.getrandbits(1))
        a = row["response_b"] if swap else row["response_a"]
        b = row["response_a"] if swap else row["response_b"]
        pair_code = f"human_{stable_hex(seed, i, row.get('card_id'), n=16)}"
        blinded.append({
            "pair_code": pair_code,
            "context": row.get("context") or row.get("current_context") or "",
            "response_A": a,
            "response_B": b,
            "preference": "",
            "notes": "",
        })
        keys.append({
            "pair_code": pair_code,
            "source_id": row.get("pair_id") or row.get("card_id") or str(i),
            "swap": swap,
            "system_a": row.get("system_b") if swap else row.get("system_a"),
            "system_b": row.get("system_a") if swap else row.get("system_b"),
        })
    write_jsonl(out_jsonl, blinded)
    write_jsonl(key_path, keys)
    return {"n_pairs": len(blinded), "seed": seed}


def _fleiss_kappa(matrix: np.ndarray) -> float | None:
    if matrix.ndim != 2 or matrix.shape[0] < 2:
        return None
    n_raters = matrix.sum(axis=1)
    if np.any(n_raters != n_raters[0]) or n_raters[0] < 2:
        return None
    n = float(n_raters[0])
    p = matrix.sum(axis=0) / matrix.sum()
    p_e = float(np.sum(p ** 2))
    p_i = (np.sum(matrix ** 2, axis=1) - n) / (n * (n - 1))
    p_bar = float(np.mean(p_i))
    if p_e >= 1.0:
        return 1.0 if p_bar >= 1.0 else None
    return (p_bar - p_e) / (1.0 - p_e)


def analyze_annotations(
    annotation_csvs: Sequence[str | Path],
    key_path: str | Path,
    out_path: str | Path,
) -> dict[str, Any]:
    keys = {row["pair_code"]: row for row in iter_jsonl(key_path)}
    judgments: dict[str, list[str]] = defaultdict(list)
    annotators: dict[str, int] = Counter()
    for csv_path in annotation_csvs:
        annotator = Path(csv_path).stem
        with Path(csv_path).open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                code = str(row.get("pair_code") or "").strip()
                pref = str(row.get("preference") or "").strip()
                if code not in keys:
                    raise ValueError(f"unknown pair_code {code!r}")
                if pref not in {"A", "B", "tie"}:
                    raise ValueError(f"invalid preference {pref!r} for {code}")
                judgments[code].append(pref)
                annotators[annotator] += 1
    if not judgments:
        raise ValueError("no annotations")

    categories = ["A", "B", "tie"]
    agreement_rows: list[list[int]] = []
    majority_preferences: list[str] = []
    resolved: list[dict[str, Any]] = []
    for code in sorted(judgments):
        votes = Counter(judgments[code])
        agreement_rows.append([votes[c] for c in categories])
        ordered = votes.most_common()
        majority = ordered[0][0] if len(ordered) == 1 or ordered[0][1] > ordered[1][1] else "tie"
        key = keys[code]
        # Resolve the blinded display winner to canonical system identity.
        # "majority" is in display space (A/B/tie); winner_system is the
        # canonical name of the system that won (e.g. "pm", "baseline", "tie").
        if majority == "tie":
            winner_system = "tie"
        else:
            winner_system = key["system_a"] if majority == "A" else key["system_b"]
        majority_preferences.append(winner_system)
        resolved.append({
            "pair_code": code,
            "votes": dict(votes),
            "majority_blinded": majority,
            "canonical_system_a": key["system_a"],
            "canonical_system_b": key["system_b"],
            "winner_system": winner_system,
            # Legacy fields kept for backward compatibility
            "system_a": key["system_a"],
            "system_b": key["system_b"],
            "system_preference": majority,
        })
    matrix = np.asarray(agreement_rows, dtype=float)
    result = {
        "n_pairs": len(resolved),
        "annotator_rows": dict(annotators),
        "fleiss_kappa": _fleiss_kappa(matrix),
        # majority_wtl_pm: wins/ties/losses from PM's perspective (canonical)
        "majority_wtl_pm": _canonical_win_tie_loss(majority_preferences, target="pm"),
        # majority_wtl_display: legacy display-space A/B counts (not for preference reporting)
        "majority_wtl_display": win_tie_loss([
            "A" if w == r["canonical_system_a"] else "B" if w != "tie" else "tie"
            for w, r in zip(majority_preferences, resolved)
        ]),
        "rows": resolved,
    }
    write_json(out_path, result)
    return result
