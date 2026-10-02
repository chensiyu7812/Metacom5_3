#!/usr/bin/env python3
"""Close the final 401-session runtime-identity question without model calls."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import iter_jsonl, read_json, sha256_file, write_json  # noqa: E402
from metacom_pm.paper1.multi_view_memory.runtime import SessionCompilationResult  # noqa: E402
from metacom_pm.paper1.outcome_lock import (  # noqa: E402
    assert_pre_outcome_locked,
    load_public_only_config,
)


PROTOCOL = "paper1-multi-view-401-runtime-identity-uniformity-audit-v1"
STABLE_IDENTITY_FIELDS = (
    "protocol",
    "phase",
    "compiler_version",
    "provider",
    "region",
    "base_url",
    "model",
    "prompt_sha256",
    "schema_sha256",
)
STABLE_PARAMETER_FIELDS = (
    "temperature",
    "max_tokens",
    "seed",
    "tokenizer_identity",
    "maximum_prompt_tokens",
    "prompt_token_safety_margin",
)


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=PROJECT / "outputs/paper1_multi_view_compiler_v7",
    )
    parser.add_argument(
        "--promoted-results",
        type=Path,
        default=PROJECT
        / "data/paper1_public_memory/es_memeval_public_multi_view_session_results_v1.jsonl",
    )
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def _cache_surface(run_dir: Path, phase: str) -> dict[str, Any]:
    values: dict[str, set[str]] = defaultdict(set)
    paths = sorted((run_dir / "success_cache" / phase).glob("*.json"))
    for path in paths:
        row = read_json(path)
        identity = row["identity"]
        for field in STABLE_IDENTITY_FIELDS:
            values[field].add(str(identity[field]))
        parameters = identity["request_parameters"]
        for field in STABLE_PARAMETER_FIELDS:
            values[f"request_parameters.{field}"].add(str(parameters[field]))
    return {
        "success_cache_files": len(paths),
        "stable_identity_unique_counts": {
            key: len(value) for key, value in sorted(values.items())
        },
        "stable_identity_values": {
            key: sorted(value) for key, value in sorted(values.items())
        },
        "contains_response_or_dialogue_text": False,
    }


def _attempt_surface(run_dir: Path, phase: str) -> dict[str, Any]:
    prompt_hashes: set[str] = set()
    terminal_counts: dict[str, int] = defaultdict(int)
    files = sorted((run_dir / "attempts" / phase).glob("*.jsonl"))
    for path in files:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            event = json.loads(line)
            if event["event"] == "STARTED":
                prompt_hashes.add(str(event["prompt_sha256"]))
            else:
                terminal_counts[str(event["event"])] += 1
    return {
        "logical_call_ledgers": len(files),
        "started_prompt_sha256_unique_count": len(prompt_hashes),
        "started_prompt_sha256": sorted(prompt_hashes),
        "terminal_counts": dict(sorted(terminal_counts.items())),
    }


def main() -> int:
    args = _args()
    config = load_public_only_config(PROJECT / "configs/paper1_public_only.yaml")
    assert_pre_outcome_locked(config)
    run_dir = args.run_dir.resolve()
    results_path = run_dir / "session_results.jsonl"
    report_path = run_dir / "batch_report.json"
    report = read_json(report_path)
    rows = tuple(
        SessionCompilationResult.model_validate(row) for row in iter_jsonl(results_path)
    )
    compiler_versions = {row.compiler_version for row in rows}
    grounding_versions = {row.grounding_version for row in rows}
    accepted_compiler_ids = {
        unit.compiler_identity_sha256 for row in rows for unit in row.accepted_units
    }
    extractor = _cache_surface(run_dir, "extractor")
    verifier = _cache_surface(run_dir, "verifier")
    extractor_attempts = _attempt_surface(run_dir, "extractor")
    verifier_attempts = _attempt_surface(run_dir, "verifier")
    stable_cache_fields_singleton = all(
        count == 1
        for surface in (extractor, verifier)
        for count in surface["stable_identity_unique_counts"].values()
    )
    checks = {
        "exact_401_session_results": len(rows) == 401,
        "single_compiler_version": len(compiler_versions) == 1,
        "single_grounding_version": len(grounding_versions) == 1,
        "single_accepted_unit_compiler_identity": accepted_compiler_ids
        == {str(report["compiler_identity_sha256"])},
        "exact_401_extractor_success_caches": extractor["success_cache_files"] == 401,
        "exact_401_verifier_success_caches": verifier["success_cache_files"] == 401,
        "all_cache_stable_identity_fields_singleton": stable_cache_fields_singleton,
        "single_extractor_attempt_prompt": extractor_attempts[
            "started_prompt_sha256_unique_count"
        ]
        == 1,
        "single_verifier_attempt_prompt": verifier_attempts[
            "started_prompt_sha256_unique_count"
        ]
        == 1,
        "batch_report_binds_session_results": report["session_results_sha256"]
        == sha256_file(results_path),
        "promoted_results_byte_identical": sha256_file(args.promoted_results.resolve())
        == sha256_file(results_path),
    }
    artifact = {
        "protocol": PROTOCOL,
        "date": "2026-09-04",
        "status": "UNIFORM_IDENTITY_PASS" if all(checks.values()) else "IDENTITY_FAIL",
        "not_an_empirical_pass_gate": True,
        "scope": "mechanical reproducibility identity only; no candidate correctness judgement",
        "checks": checks,
        "session_surface": {
            "rows": len(rows),
            "compiler_versions": sorted(compiler_versions),
            "grounding_versions": sorted(grounding_versions),
            "accepted_unit_compiler_identities": sorted(accepted_compiler_ids),
        },
        "extractor": extractor,
        "verifier": verifier,
        "extractor_attempts": extractor_attempts,
        "verifier_attempts": verifier_attempts,
        "artifacts": {
            "session_results_sha256": sha256_file(results_path),
            "batch_report_sha256": sha256_file(report_path),
            "promoted_results_sha256": sha256_file(args.promoted_results.resolve()),
        },
        "rerun_required": False if all(checks.values()) else None,
        "formal_outcome_calls": 0,
        "pm_training_runs": 0,
        "paid_api_calls": 0,
    }
    write_json(args.out.resolve(), artifact)
    print(json.dumps(artifact, ensure_ascii=False, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
