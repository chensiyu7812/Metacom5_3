#!/usr/bin/env python3
"""Validate the portable, tracked V3 authority and optional private evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PROJECT_ROOT.parent
AUTHORITY_DIR = PROJECT_ROOT / "data" / "v3_authority"


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _combined_private_hash(root: Path) -> str:
    lines: list[bytes] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        relative = path.relative_to(REPO_ROOT).as_posix()
        lines.append(f"{digest}  {relative}\n".encode("utf-8"))
    return hashlib.sha256(b"".join(lines)).hexdigest()


def validate(require_private_evidence: bool = False) -> dict[str, Any]:
    authority_path = AUTHORITY_DIR / "v3_research_authority_v1.json"
    assets_path = AUTHORITY_DIR / "v3_asset_compatibility_manifest_v1.json"
    profile_path = AUTHORITY_DIR / "v3_active_test_profile_v1.json"
    authority = _load_json(authority_path)
    assets = _load_json(assets_path)
    profile = _load_json(profile_path)

    failures: list[str] = []

    expected_commit = "ef318c3e35982e277883e06c5ec25cc7392eab67"
    if authority["source_revision"]["source_commit"] != expected_commit:
        failures.append("unexpected authority source commit")
    if assets["source_commit"] != expected_commit:
        failures.append("authority/asset source commit mismatch")
    if authority["execution_boundary"]["this_file_authorizes"] == []:
        failures.append("execution boundary is empty")
    if any(phase.get("api_authority") for phase in authority["execution_phases"]):
        failures.append("a planning phase unexpectedly authorizes API execution")

    phase_ids = [phase["phase"] for phase in authority["execution_phases"]]
    if phase_ids != [f"V3-P{index}" for index in range(7)]:
        failures.append("execution phases are not the frozen V3-P0..V3-P6 sequence")

    memeval = authority["external_tracks"]["ES_MemEval"]
    if memeval["status"] != "BLOCKED_ON_OFFICIAL_VERSION_RECONCILIATION":
        failures.append("ES-MemEval version discrepancy is not an explicit blocker")
    if not all(token in memeval["version_discrepancy"] for token in ("1209", "1427", "418")):
        failures.append("ES-MemEval discrepancy does not bind all known counts")

    required_documents = [
        PROJECT_ROOT / "docs" / "V3_MASTER_RESEARCH_PROGRAM_ZH.md",
        PROJECT_ROOT / "docs" / "V3_EVALUATION_BENCHMARK_PLAN_ZH.md",
        PROJECT_ROOT / "docs" / "V3_DATASET_AND_EVIDENCE_CARDS_ZH.md",
        REPO_ROOT / "V3_MIGRATION_REPORT_ZH.md",
    ]
    failures.extend(
        f"missing required document: {path.relative_to(REPO_ROOT)}"
        for path in required_documents
        if not path.is_file()
    )

    test_paths = [PROJECT_ROOT / relative for relative in profile["tests"]]
    failures.extend(
        f"missing active test: {path.relative_to(PROJECT_ROOT)}"
        for path in test_paths
        if not path.is_file()
    )
    if profile["expected_test_count"] != 39:
        failures.append("active profile expected test count changed without authority update")

    for path in (authority_path, assets_path, profile_path):
        if "/home/tokkio/snap/" in path.read_text(encoding="utf-8"):
            failures.append(f"legacy absolute path leaked into {path.name}")

    private_spec = assets["private_evidence"]
    private_root = REPO_ROOT / private_spec["path"]
    private_result: dict[str, Any] = {"present": private_root.is_dir()}
    if private_root.is_dir():
        files = [path for path in private_root.rglob("*") if path.is_file()]
        private_result.update(
            {
                "file_count": len(files),
                "bytes": sum(path.stat().st_size for path in files),
                "combined_sha256": _combined_private_hash(private_root),
            }
        )
        if private_result["file_count"] != private_spec["file_count"]:
            failures.append("private evidence file count mismatch")
        if private_result["bytes"] != private_spec["bytes"]:
            failures.append("private evidence byte count mismatch")
        if private_result["combined_sha256"] != private_spec["deterministic_combined_sha256"]:
            failures.append("private evidence combined hash mismatch")
    elif require_private_evidence:
        failures.append("private evidence is required locally but not present")
    else:
        private_result["public_clone_status"] = "not_present_public_ok"

    return {
        "protocol": "metacom-v3-workspace-validation-v1",
        "valid": not failures,
        "failures": failures,
        "source_commit": expected_commit,
        "phase_ids": phase_ids,
        "active_test_files": len(test_paths),
        "expected_active_test_count": profile["expected_test_count"],
        "private_evidence": private_result,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-private-evidence", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = validate(require_private_evidence=args.require_private_evidence)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
