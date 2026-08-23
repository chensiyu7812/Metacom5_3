#!/usr/bin/env python3
"""Resolve the pinned ESC-RANK asset hashes before the >=24 GiB runtime run.

This script performs no download, model load, evaluator call, or outcome read.
It converts the committed pending patch template into a run-local resolved
manifest only after the exact official checkout, model snapshot, adapter
snapshot, and dependencies are present.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any


REQUIRED_ADAPTERS = (
    "fluency_en",
    "diversity_en",
    "empathic_en",
    "suggestion_en",
    "human_en",
    "tech_en",
    "overall_en",
)


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_sha(path: Path) -> str:
    rows = []
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        rows.append(f"{item.relative_to(path).as_posix()}\t{sha_file(item)}")
    if not rows:
        raise RuntimeError(f"asset tree is empty: {path}")
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()


def git_head(path: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def resolve_manifest(
    template: dict[str, Any],
    *,
    esc_eval: Path,
    rank_path: Path,
    base_path: Path,
    actual_dependencies: dict[str, str],
    observed_esc_eval_commit: str,
) -> dict[str, Any]:
    official = template["official_identity"]
    if observed_esc_eval_commit != official["esc_eval_commit"]:
        raise RuntimeError("ESC-Eval checkout is not at the pinned commit")
    score_py = esc_eval / "score.py"
    if sha_file(score_py) != official["score_py_sha256"]:
        raise RuntimeError("official score.py hash drifted")
    if rank_path.resolve().name != official["esc_rank_revision"]:
        raise RuntimeError("ESC-RANK snapshot directory name must be the pinned revision")
    if base_path.resolve().name != official["internlm2_revision"]:
        raise RuntimeError("InternLM2 snapshot directory name must be the pinned revision")
    if not (base_path / "config.json").is_file():
        raise RuntimeError("InternLM2 snapshot is missing config.json")
    for adapter in REQUIRED_ADAPTERS:
        if not (rank_path / adapter / "adapter_config.json").is_file():
            raise RuntimeError(f"ESC-RANK snapshot is missing {adapter}/adapter_config.json")
    for package, expected in template["dependency_pins"].items():
        if actual_dependencies.get(package) != expected:
            raise RuntimeError(
                f"dependency drift {package}: expected {expected}, got {actual_dependencies.get(package)}"
            )
    resolved = deepcopy(template)
    resolved["protocol"] = "pm-paper1-esc-rank-24gib-resolved-runtime-manifest-v1"
    resolved["status"] = "ASSETS_ATTESTED_READY_FOR_24GIB_RUNTIME"
    resolved["required_runtime_inventory"]["esc_rank_tree_sha256"] = tree_sha(rank_path)
    resolved["required_runtime_inventory"]["internlm2_tree_sha256"] = tree_sha(base_path)
    resolved["required_runtime_inventory"]["adapter_directories"] = list(REQUIRED_ADAPTERS)
    resolved["required_runtime_inventory"]["dependency_versions"] = actual_dependencies
    resolved["runtime_experiment_status"] = "READY_TO_EXECUTE_NOT_YET_RUN"
    resolved["calls"] = {
        "downloads_by_this_script": 0,
        "model_loads_by_this_script": 0,
        "evaluator_calls_by_this_script": 0,
        "outcome_calls": 0,
    }
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--esc-eval", type=Path, required=True)
    parser.add_argument("--rank-path", type=Path, required=True)
    parser.add_argument("--base-path", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    template = json.loads(args.template.read_text(encoding="utf-8"))
    dependencies = {
        package: importlib.metadata.version(package)
        for package in template["dependency_pins"]
    }
    resolved = resolve_manifest(
        template,
        esc_eval=args.esc_eval,
        rank_path=args.rank_path,
        base_path=args.base_path,
        actual_dependencies=dependencies,
        observed_esc_eval_commit=git_head(args.esc_eval),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(resolved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": resolved["status"],
                "resolved_manifest": str(args.out),
                "esc_rank_tree_sha256": resolved["required_runtime_inventory"]["esc_rank_tree_sha256"],
                "internlm2_tree_sha256": resolved["required_runtime_inventory"]["internlm2_tree_sha256"],
                "outcome_calls": 0,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
