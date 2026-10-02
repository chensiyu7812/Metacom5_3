#!/usr/bin/env python3
"""Read-only validation of one V2 human submission; never adjudicate or score it."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import sha256_file
from metacom_pm.paper1.evaluation.human_reference import read_rating_json, validate_rated_sheet


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rated-file", type=Path, required=True)
    parser.add_argument("--allow-partial", action="store_true", help="validate a progress backup, without treating it as completed")
    args = parser.parse_args()
    try:
        manifest = read_rating_json(PROJECT / "data/paper1_authority/paper1_pairwise_teacher_human_sheet_manifest_20260908_v2.json")
        rated = read_rating_json(args.rated_file)
        rater = rated.get("rater_id")
        if not isinstance(rater, str) or rater not in manifest["sheets"]:
            raise ValueError("unknown rater identity")
        binding = manifest["sheets"][rater]
        blank_path = PROJECT / binding["path"]
        if sha256_file(blank_path) != binding["sha256"]:
            raise ValueError("canonical blank sheet does not match its frozen hash")
        counts = validate_rated_sheet(read_rating_json(blank_path), rated, require_complete=not args.allow_partial)
        if counts["presentations"] != binding["presentations"]:
            raise ValueError("manifest presentation count mismatch")
        print(json.dumps({"status": "VALID_COMPLETE" if counts["completed"] == counts["presentations"] else "VALID_PARTIAL",
                          "rater_id": rater, **counts, "submission_sha256": sha256_file(args.rated_file),
                          "files_modified": 0, "adjudication_performed": False}, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "INVALID", "reason": str(exc), "files_modified": 0}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
