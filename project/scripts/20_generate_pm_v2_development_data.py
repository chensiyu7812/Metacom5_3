#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from metacom_pm.config import endpoint_from_config, load_config
from metacom_pm.pm_v2_contracts import PMV2Split, ResourceNeedRegime
from metacom_pm.pm_v2_data import generate_user_bundle, write_development_dataset

ROOT = Path(__file__).resolve().parents[1]

FAMILIES = [
    "relocation_loneliness",
    "workload_burnout",
    "friendship_distance",
    "family_expectations",
    "relationship_uncertainty",
    "academic_pressure",
    "career_change",
    "caregiving_stress",
    "social_anxiety",
    "sleep_disruption",
    "identity_transition",
    "financial_uncertainty",
    "grief_adjustment",
    "health_routine_stress",
    "conflict_repair",
    "self_confidence",
    "belonging_and_isolation",
    "decision_paralysis",
    "parenting_pressure",
    "workplace_conflict",
    "life_stage_transition",
    "motivation_loss",
    "trust_rebuilding",
    "uncertain_future",
]


def read_seed_dialogues(path: Path) -> list[str]:
    seeds: list[str] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if isinstance(row, str):
                text = row
            else:
                text = row.get("dialogue_text") or row.get("text") or row.get("content")
                if not text and isinstance(row.get("dialogue"), list):
                    text = "\n".join(
                        f"{turn.get('role','unknown')}: {turn.get('content','')}"
                        for turn in row["dialogue"]
                    )
            if text and str(text).strip():
                seeds.append(str(text).strip())
    if not seeds:
        raise ValueError("seed dialogue file contains no usable text")
    return seeds


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "experiment.yaml")
    parser.add_argument("--endpoint", default="generator")
    parser.add_argument("--seed-dialogues", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "data" / "pm_v2")
    parser.add_argument("--train-users", type=int, default=24)
    parser.add_argument("--calibration-users", type=int, default=6)
    parser.add_argument("--internal-test-users", type=int, default=6)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--max-users", type=int)
    parser.add_argument("--seed", type=int, default=1701)
    args = parser.parse_args()

    total = args.train_users + args.calibration_users + args.internal_test_users
    if args.max_users is not None:
        total = min(total, args.max_users)
    print(
        {
            "status": "DRY_RUN" if not args.run else "STARTING",
            "planned_api_calls": total,
            "planned_states": total * len(ResourceNeedRegime),
            "strict_split": "user + semantic-family + normalized-text disjoint",
            "regimes": [regime.value for regime in ResourceNeedRegime],
        }
    )
    if not args.run:
        return

    seeds = read_seed_dialogues(args.seed_dialogues)
    endpoint = endpoint_from_config(load_config(args.config), args.endpoint)
    split_specs = [
        (PMV2Split.TRAIN, args.train_users, FAMILIES[:14]),
        (PMV2Split.CALIBRATION, args.calibration_users, FAMILIES[14:19]),
        (PMV2Split.INTERNAL_TEST, args.internal_test_users, FAMILIES[19:24]),
    ]
    bundles = []
    split_by_user = {}
    global_index = 0
    for split, count, family_pool in split_specs:
        for local_index in range(count):
            if args.max_users is not None and global_index >= args.max_users:
                break
            user_id = f"pmv2_{split.value}_u{local_index + 1:03d}"
            families = [
                family_pool[(local_index + offset) % len(family_pool)]
                for offset in range(min(3, len(family_pool)))
            ]
            bundle = generate_user_bundle(
                endpoint=endpoint,
                seed_dialogue=seeds[global_index % len(seeds)],
                user_id=user_id,
                semantic_families=families,
                regimes=list(ResourceNeedRegime),
                seed=args.seed + global_index,
            )
            bundles.append(bundle)
            split_by_user[user_id] = split
            global_index += 1
    report = write_development_dataset(
        bundles=bundles,
        split_by_user=split_by_user,
        out_dir=args.out_dir,
    )
    print(report)


if __name__ == "__main__":
    main()
