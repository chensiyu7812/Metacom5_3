#!/usr/bin/env python3
"""WS-B B0: legal prefix census, owner/family folds, exposure registry.

CPU only.  Reads the sanitized public EvoEmo runtime artifact (never the raw
evaluator JSON), enumerates every legal seeker->supporter cut with strictly
past history, assigns owner/family-first folds and records repository
exposure.  Outputs are deterministic given the inputs and the tracked repo
contents (the exposure scan is pinned to the git HEAD recorded in the
manifest).

    PYTHONPATH=project/src python project/scripts/rl1v3/B0_prefix_census.py \
        --config project/configs/rl1v3/B0.yaml --out project/outputs/pm_rl1/v3/B0/
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
REPO = PROJECT.parent
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.rl1v3.prefixes import census as C  # noqa: E402
from metacom_pm.rl1v3.prefixes import exposure as X  # noqa: E402

CODE_FILES = (
    "src/metacom_pm/rl1v3/prefixes/__init__.py",
    "src/metacom_pm/rl1v3/prefixes/census.py",
    "src/metacom_pm/rl1v3/prefixes/exposure.py",
    "scripts/rl1v3/B0_prefix_census.py",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def write_jsonl(path: Path, rows) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(C.canonical_json(r) + "\n")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True,
                          check=True).stdout.strip()


def load_config(path: Path) -> dict:
    import yaml
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def esconv_overlap_check(manifest_path: Path, users) -> dict:
    rows = [json.loads(l) for l in manifest_path.read_text(encoding="utf-8").splitlines() if l]
    flagged = {r["dialogue_id"] for r in rows if r["excluded_for_evoemo_overlap"]}
    seeds = {C.session_family(u.owner_id, s).split(":", 1)[1] for u in users for s in u.sessions
             if C.source_kind(s) == "esconv_seed"}
    by_split: dict[str, int] = {}
    for r in rows:
        if r["excluded_for_evoemo_overlap"]:
            by_split[r["split"]] = by_split.get(r["split"], 0) + 1
    return dict(esconv_dialogues=len(rows), flagged_overlap=len(flagged),
                evoemo_esconv_seed_families=len(seeds), sets_equal=flagged == seeds,
                flagged_by_esconv_split=dict(sorted(by_split.items())),
                note=("these ESConv families appear as EvoEmo history/current sessions; the RS "
                      "bank (WS-A) must exclude them by family closure (RESOURCE_SPEC T24)"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--dry-run", action="store_true", help="compute and audit, write nothing")
    args = ap.parse_args()
    config_path = args.config.resolve()
    cfg = load_config(config_path)
    source = PROJECT / cfg["source_artifact"]
    split_manifest = PROJECT / cfg["esconv_split_manifest"]

    users = C.load_users(source)
    result = C.build_census(users)
    if not result.summary["audit"]["passed"]:
        print(json.dumps(result.summary["audit"], indent=2), file=sys.stderr)
        return 2
    overlap = esconv_overlap_check(split_manifest, users)
    if not overlap["sets_equal"]:
        print(json.dumps(overlap, indent=2), file=sys.stderr)
        return 3

    head = git("rev-parse", "HEAD")
    pairs = X.scan_git(REPO, tuple(cfg["exposure_scan_roots"]))
    sessions_by_owner = {u.owner_id: [s.session_id for s in
                                      sorted(u.sessions, key=lambda s: s.chronological_rank)]
                         for u in sorted(users, key=lambda u: C._owner_sort(u.owner_id))}
    registry = X.build_registry(pairs, sessions_by_owner, result.folds["historical_rl1_split"],
                                result.folds["fold_of_owner"])
    by_owner = {u.owner_id: u for u in users}
    legacy = {}
    for r in result.rows:
        user = by_owner[r["owner_id"]]
        legacy[r["prefix_id"]] = X.legacy_rl1_prefix_identity(
            r["owner_id"], r["session_id"], r["cutoff_rank"], r["cut_turn"], r["timestamp"],
            result.folds["historical_rl1_split"][r["owner_id"]],
            C.materialize_prefix(r, by_owner))
    prefix_hits = X.scan_hex_identities(REPO, set(legacy.values()),
                                        roots=tuple(cfg["exposure_scan_roots"]))
    prefix_records = X.prefix_exposure_records(result.rows, legacy, prefix_hits)
    for row in registry:
        if row["record"] == "owner":
            mine = [p for p in prefix_records if p["owner_id"] == row["owner_id"]]
            row["legacy_prefixes_by_category"] = {
                c: sum(c in p["categories"] for p in mine) for c in X.STRONG_CATEGORIES}
    registry.extend(prefix_records)
    summary = dict(result.summary)
    summary["esconv_family_overlap"] = overlap
    summary["exposure"] = dict(
        scan_rule="exact session-id match in git-tracked text files; run dir classified by name",
        scan_roots=list(cfg["exposure_scan_roots"]), scanned_git_head=head,
        distinct_run_dirs=len({d for d, _ in pairs}),
        category_rules=[dict(category=c, name_keys=list(k)) for c, k in X.CATEGORY_RULES],
        owners_with_human_review_artifacts=sorted(
            (r["owner_id"] for r in registry
             if r["record"] == "owner" and r["sessions_in_human_review_artifacts"]),
            key=C._owner_sort),
        sessions_in_any_artifact=sum(1 for r in registry
                                     if r["record"] == "session" and r["categories"]),
        prefix_level_rule=("legacy rl1 PrefixSpec.identity of each census prefix searched as "
                           "64-hex tokens in tracked files of human_review/training/"
                           "judge_or_feedback run dirs; other legacy identity schemas are not "
                           "recognised, so this is a lower bound"),
        legacy_prefixes_exposed_by_category={c: sum(c in p["categories"] for p in prefix_records)
                                             for c in X.STRONG_CATEGORIES},
        legacy_prefixes_exposed_any=len(prefix_records),
        lower_bound_only=True,
    )
    if args.dry_run:
        print(json.dumps(summary["totals"], indent=2))
        return 0

    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "prefix_census.jsonl", result.rows)
    write_json(out / "folds.json", result.folds)
    write_jsonl(out / "exposure_registry.jsonl", registry)
    write_json(out / "census_summary.json", summary)
    outputs = {name: dict(sha256=sha256_file(out / name), bytes=(out / name).stat().st_size)
               for name in ("prefix_census.jsonl", "folds.json", "exposure_registry.jsonl",
                            "census_summary.json")}
    outputs["prefix_census.jsonl"]["rows"] = len(result.rows)
    outputs["exposure_registry.jsonl"]["rows"] = len(registry)
    dirty = bool(git("status", "--porcelain", "--", *(f"project/{p}" for p in CODE_FILES)))
    write_json(out / "manifest.json", dict(
        task_id="B0",
        protocol=C.CENSUS_PROTOCOL,
        row_schema=C.ROW_SCHEMA,
        folds_schema=C.FOLDS_SCHEMA,
        evidence_tier=cfg["evidence_tier"],
        evidence_note=("deterministic CPU census of a public source; counts are exact facts of "
                       "the sanitized artifact, surface cues are not need labels"),
        inputs={
            cfg["source_artifact"]: sha256_file(source),
            cfg["esconv_split_manifest"]: sha256_file(split_manifest),
            str(config_path.relative_to(REPO)): sha256_file(config_path),
        },
        code_files_sha256={p: sha256_file(PROJECT / p) for p in CODE_FILES},
        git_head_at_run=head,
        code_dirty_at_run=dirty,
        python=platform.python_version(),
        model_calls=0, gpu_used=False, paid_calls=0,
        outputs=outputs,
        command=("PYTHONPATH=project/src python project/scripts/rl1v3/B0_prefix_census.py "
                 "--config project/configs/rl1v3/B0.yaml --out project/outputs/pm_rl1/v3/B0/"),
    ))
    print(json.dumps(dict(out=str(out), rows=len(result.rows), audit=summary["audit"]["passed"],
                          outputs={k: v["sha256"][:12] for k, v in outputs.items()}), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
