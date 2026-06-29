#!/usr/bin/env python3
"""No-API readiness check for EvoEmo PM external evaluation.

This script verifies whether the frozen PM can score the actual fixed EvoEmo
evaluation states before any supporter-generation API calls are made.  It is a
guardrail against spending API budget on an invalid external run.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from metacom_pm.evoemo import (
    _fixed_context_before_turn,
    _load_fixed_tracks,
    _policy_from_selection,
    _track_key,
    build_evo_memory,
    load_evoemo,
    make_evo_runtime_state,
)
from metacom_pm.freeze import require_study_freeze
from metacom_pm.io import read_json, write_json
from metacom_pm.training import PMModel


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", type=Path, default=ROOT / "outputs/study_freeze.json")
    parser.add_argument("--checkpoint", type=Path, default=ROOT / "outputs/final_model_m2b_attested/pm_final.joblib")
    parser.add_argument("--selection", type=Path, default=ROOT / "outputs/selection.json")
    parser.add_argument("--evoemo", type=Path, default=ROOT / "data/external/evo_emo.json")
    parser.add_argument("--fixed-tracks", type=Path, default=ROOT / "outputs/evoemo_fixed_tracks/fixed_seeker_tracks.jsonl")
    parser.add_argument("--simulator-id", default="seeker_main")
    parser.add_argument("--seeds", type=int, nargs="+", default=[101, 202, 303])
    parser.add_argument("--max-turns", type=int, default=10)
    parser.add_argument("--out", type=Path, default=ROOT / "outputs/evoemo_pm_readiness.json")
    parser.add_argument("--allow-unfrozen-debug", action="store_true")
    args = parser.parse_args()

    freeze = require_study_freeze(
        args.freeze,
        release_root=ROOT,
        required_files=[args.checkpoint, args.selection, args.evoemo, args.fixed_tracks],
        allow_unfrozen_debug=args.allow_unfrozen_debug,
    )

    users = load_evoemo(args.evoemo)
    tracks = _load_fixed_tracks(args.fixed_tracks)
    model = PMModel.load(args.checkpoint)
    selection = read_json(args.selection)
    pm_policy = _policy_from_selection(model, selection)

    errors: list[dict[str, object]] = []
    action_counts: Counter[str] = Counter()
    ood_counts: Counter[str] = Counter()
    safe_counts: Counter[int] = Counter()
    fallback_counts: Counter[bool] = Counter()
    checked = 0

    for user in users:
        items, _ = build_evo_memory(user)
        for topic in user.get("subsequent_topics") or []:
            for seed in args.seeds:
                track_key = _track_key(
                    str(user["id"]), int(topic["idx"]), int(seed), args.simulator_id
                )
                track = tracks.get(track_key)
                if track is None:
                    errors.append({"kind": "missing_track", "track_key": track_key})
                    continue
                for turn_index in range(1, args.max_turns + 1):
                    try:
                        context = _fixed_context_before_turn(track, turn_index)
                        state = make_evo_runtime_state(
                            user,
                            topic,
                            context,
                            track["seeker_turns"][turn_index - 1],
                            items,
                            turn_index,
                            "pm_readiness",
                            track_id=str(track["track_id"]),
                            fixed_open_loop=True,
                        )
                        action = pm_policy.choose(state)
                        checked += 1
                        action_counts[action] += 1
                        report = model.last_ood_report or {}
                        for key in (
                            "severe_scalar_ood",
                            "severe_catalog_ood",
                            "mild_scalar_ood",
                            "mild_catalog_ood",
                        ):
                            if report.get(key):
                                ood_counts[key] += 1
                        decision = pm_policy.last_decision_report or {}
                        safe_counts[len(decision.get("safe_actions") or [])] += 1
                        fallback_counts[bool(decision.get("constraint_fallback_used"))] += 1
                    except Exception as exc:
                        errors.append({
                            "kind": "exception",
                            "user_id": str(user.get("id")),
                            "topic_index": int(topic.get("idx")),
                            "seed": int(seed),
                            "turn_index": int(turn_index),
                            "error": f"{type(exc).__name__}: {str(exc)[:800]}",
                        })

    expected = sum(len(user.get("subsequent_topics") or []) for user in users) * len(args.seeds) * args.max_turns
    summary = {
        "status": "READY" if checked == expected and not errors else "BLOCKED",
        "interpretation": (
            "No supporter-generation API calls are made. BLOCKED means the frozen PM "
            "cannot be used for confirmatory EvoEmo generation without a preregistered "
            "OOD fallback, retraining, or feature-domain change."
        ),
        "freeze_sha256": freeze.get("freeze_sha256"),
        "n_users": len(users),
        "n_tracks": len(tracks),
        "expected_states": expected,
        "checked_states": checked,
        "n_errors": len(errors),
        "error_examples": errors[:10],
        "pm_action_distribution": dict(action_counts.most_common()),
        "ood_counts": dict(ood_counts),
        "safe_action_count_distribution": dict(sorted(safe_counts.items())),
        "constraint_fallback_used_distribution": {
            str(k): v for k, v in fallback_counts.items()
        },
        "selection_pm": selection.get("pm"),
    }
    write_json(args.out, summary)
    print(json.dumps(summary, ensure_ascii=False))
    if summary["status"] != "READY":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
