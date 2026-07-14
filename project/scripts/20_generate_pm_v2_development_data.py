#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from metacom_pm.config import endpoint_from_config, load_config
from metacom_pm.io import append_jsonl, sha256_file
from metacom_pm.pm_v2_contracts import PMV2Split, ResourceNeedRegime
from metacom_pm.pm_v2_data import (
    GeneratedUserBundle,
    generate_user_bundle,
    load_bundles,
    validate_bundle,
    write_development_dataset,
)

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


def strict_bundle_check(bundle: GeneratedUserBundle, allowed_families: list[str]) -> None:
    validate_bundle(bundle)
    expected_regimes = set(ResourceNeedRegime)
    observed_regimes = {case.regime for case in bundle.cases}
    if observed_regimes != expected_regimes or len(bundle.cases) != len(expected_regimes):
        raise ValueError(
            "bundle must contain exactly one case per PM-v2 regime; "
            f"missing={sorted(x.value for x in expected_regimes-observed_regimes)}, "
            f"extra={len(bundle.cases)-len(observed_regimes)}"
        )
    invalid_families = sorted(
        {case.semantic_family for case in bundle.cases} - set(allowed_families)
    )
    if invalid_families:
        raise ValueError(
            f"bundle used semantic families outside its frozen split pool: {invalid_families}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "experiment.yaml")
    parser.add_argument("--pm-v2-config", type=Path, default=ROOT / "configs" / "pm_v2.yaml")
    parser.add_argument("--endpoint", default="generator")
    parser.add_argument("--seed-dialogues", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "data" / "pm_v2")
    parser.add_argument("--train-users", type=int)
    parser.add_argument("--calibration-users", type=int)
    parser.add_argument("--internal-test-users", type=int)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--max-users", type=int)
    parser.add_argument("--max-generation-attempts", type=int)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--seed", type=int, default=1701)
    args = parser.parse_args()

    pm_config = load_config(args.pm_v2_config)
    if pm_config.get("version") != "pm-v2.0":
        raise ValueError("unsupported PM-v2 config version")
    generation_cfg = pm_config["data_generation"]
    args.train_users = (
        int(args.train_users)
        if args.train_users is not None
        else int(generation_cfg["train_users"])
    )
    args.calibration_users = (
        int(args.calibration_users)
        if args.calibration_users is not None
        else int(generation_cfg["calibration_users"])
    )
    args.internal_test_users = (
        int(args.internal_test_users)
        if args.internal_test_users is not None
        else int(generation_cfg["internal_test_users"])
    )
    args.max_generation_attempts = (
        int(args.max_generation_attempts)
        if args.max_generation_attempts is not None
        else int(generation_cfg["max_generation_attempts"])
    )
    required_regimes = {str(value) for value in generation_cfg["required_regimes"]}
    if required_regimes != {regime.value for regime in ResourceNeedRegime}:
        raise ValueError("PM-v2 config required_regimes does not match code contract")
    if int(generation_cfg["cases_per_user"]) != len(ResourceNeedRegime):
        raise ValueError("PM-v2 config cases_per_user must equal the regime count")

    total = args.train_users + args.calibration_users + args.internal_test_users
    if args.max_users is not None:
        total = min(total, args.max_users)
    print(
        {
            "status": "DRY_RUN" if not args.run else "STARTING",
            "planned_users": total,
            "maximum_generation_calls": total * args.max_generation_attempts,
            "planned_states": total * len(ResourceNeedRegime),
            "strict_split": "user + semantic-family + normalized-text disjoint",
            "regimes": [regime.value for regime in ResourceNeedRegime],
            "pm_v2_config_sha256": sha256_file(args.pm_v2_config),
            "seed_dialogues_sha256": sha256_file(args.seed_dialogues),
        }
    )
    if not args.run:
        return

    args.out_dir.mkdir(parents=True, exist_ok=True)
    work_path = args.out_dir / "_generated_bundles_work.jsonl"
    error_path = args.out_dir / "_generation_errors.jsonl"
    if args.overwrite:
        for path in (work_path, error_path):
            if path.exists():
                path.unlink()
    existing = {
        bundle.user_id: bundle
        for bundle in (load_bundles(work_path) if work_path.exists() else [])
    }
    seeds = read_seed_dialogues(args.seed_dialogues)
    endpoint = endpoint_from_config(load_config(args.config), args.endpoint)
    split_specs = [
        (PMV2Split.TRAIN, args.train_users, FAMILIES[:14]),
        (PMV2Split.CALIBRATION, args.calibration_users, FAMILIES[14:19]),
        (PMV2Split.INTERNAL_TEST, args.internal_test_users, FAMILIES[19:24]),
    ]
    split_by_user: dict[str, PMV2Split] = {}
    family_by_user: dict[str, list[str]] = {}
    planned_users: list[str] = []
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
            split_by_user[user_id] = split
            family_by_user[user_id] = families
            planned_users.append(user_id)
            global_index += 1
    for index, user_id in enumerate(planned_users):
        if user_id in existing:
            strict_bundle_check(existing[user_id], family_by_user[user_id])
            continue
        last_error = None
        for attempt in range(args.max_generation_attempts):
            try:
                bundle = generate_user_bundle(
                    endpoint=endpoint,
                    seed_dialogue=seeds[index % len(seeds)],
                    user_id=user_id,
                    semantic_families=family_by_user[user_id],
                    regimes=list(ResourceNeedRegime),
                    seed=args.seed + index * 100 + attempt,
                )
                strict_bundle_check(bundle, family_by_user[user_id])
                append_jsonl(work_path, bundle.model_dump(mode="json"))
                existing[user_id] = bundle
                last_error = None
                break
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                append_jsonl(
                    error_path,
                    {
                        "user_id": user_id,
                        "attempt": attempt + 1,
                        "error": last_error,
                    },
                )
        if last_error is not None:
            raise RuntimeError(
                f"failed to generate valid bundle for {user_id} after "
                f"{args.max_generation_attempts} attempts: {last_error}"
            )
    bundles = [existing[user_id] for user_id in planned_users]
    report = write_development_dataset(
        bundles=bundles,
        split_by_user=split_by_user,
        out_dir=args.out_dir,
    )
    report["work_path"] = str(work_path)
    report["error_path"] = str(error_path)
    report["pm_v2_config"] = str(args.pm_v2_config)
    report["pm_v2_config_sha256"] = sha256_file(args.pm_v2_config)
    report["seed_dialogues"] = str(args.seed_dialogues)
    report["seed_dialogues_sha256"] = sha256_file(args.seed_dialogues)
    write_json(args.out_dir / "pm_v2_data_report.json", report)
    print(report)


if __name__ == "__main__":
    main()
